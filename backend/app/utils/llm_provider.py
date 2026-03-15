"""
Shared LLM provider utilities.

Supports both the existing OpenAI-compatible HTTP path and a subprocess-backed
`codex exec` path for locally authenticated Codex sessions.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import threading
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Type

from camel.models import BaseModelBackend, ModelFactory
from camel.types import ModelPlatformType, ModelType
from camel.utils import OpenAITokenCounter
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from ..config import Config

OPENAI_COMPATIBLE_PROVIDER = "openai_compatible"
CODEX_CLI_PROVIDER = "codex_cli"
SUPPORTED_LLM_PROVIDERS = {
    OPENAI_COMPATIBLE_PROVIDER,
    CODEX_CLI_PROVIDER,
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CODEX_EXEC_LOCK = threading.Lock()

_TEXT_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "content": {"type": "string"},
    },
    "required": ["content"],
}

_TOOL_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "content": {"type": ["string", "null"]},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "arguments_json": {"type": "string"},
                },
                "required": ["name", "arguments_json"],
            },
        },
    },
    "required": ["content", "tool_calls"],
}

_JSON_STRING_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "json": {"type": "string"},
    },
    "required": ["json"],
}


class CodexCLIError(RuntimeError):
    """Raised when the Codex CLI provider fails."""


def get_llm_provider(provider: Optional[str] = None) -> str:
    resolved = (provider or Config.LLM_PROVIDER or OPENAI_COMPATIBLE_PROVIDER).strip().lower()
    if resolved not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(
            f"Unsupported LLM_PROVIDER `{resolved}`. "
            f"Supported values: {', '.join(sorted(SUPPORTED_LLM_PROVIDERS))}."
        )
    return resolved


def is_codex_cli_provider(provider: Optional[str] = None) -> bool:
    return get_llm_provider(provider) == CODEX_CLI_PROVIDER


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _normalize_schema_for_codex(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_normalize_schema_for_codex(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    normalized = {
        key: _normalize_schema_for_codex(value)
        for key, value in schema.items()
    }
    if normalized.get("type") == "object" and "additionalProperties" not in normalized:
        normalized["additionalProperties"] = False
    return normalized


def _extract_error_text(completed: subprocess.CompletedProcess[str]) -> str:
    parts = []
    if completed.stderr:
        parts.append(completed.stderr.strip())
    if completed.stdout:
        parts.append(completed.stdout.strip())
    message = "\n".join(part for part in parts if part)
    return message[-2000:] if message else "No error output captured."


class CodexCLIClient:
    """Small wrapper around `codex exec` with schema-constrained output."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        executable: Optional[str] = None,
        sandbox: Optional[str] = None,
        working_dir: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        executable_name = executable or Config.LLM_CODEX_EXECUTABLE
        resolved_executable = shutil.which(executable_name)
        if not resolved_executable:
            raise CodexCLIError(
                f"Codex executable `{executable_name}` was not found on PATH."
            )

        self.executable = resolved_executable
        self.model_name = model_name or Config.LLM_MODEL_NAME
        self.sandbox = sandbox or Config.LLM_CODEX_SANDBOX
        self.working_dir = Path(working_dir or Config.LLM_CODEX_WORKDIR or PROJECT_ROOT)
        self.timeout_seconds = timeout_seconds or Config.LLM_CODEX_TIMEOUT_SECONDS

    def complete_text(self, messages: List[Dict[str, Any]]) -> str:
        payload = self._run_with_schema(
            prompt=self._build_text_prompt(messages),
            schema=_TEXT_RESPONSE_SCHEMA,
        )
        return str(payload.get("content", "")).strip()

    def complete_json_object(
        self,
        messages: List[Dict[str, Any]],
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if schema is None:
            payload = self._run_with_schema(
                prompt=self._build_json_string_prompt(messages),
                schema=_JSON_STRING_RESPONSE_SCHEMA,
            )
            raw_json = payload.get("json", "")
            try:
                parsed = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise CodexCLIError(
                    f"Codex CLI returned invalid JSON text: {raw_json[:500]}"
                ) from exc
            if not isinstance(parsed, dict):
                raise CodexCLIError(
                    f"Expected a JSON object from Codex CLI, got {type(parsed).__name__}."
                )
            return parsed

        payload = self._run_with_schema(
            prompt=self._build_json_prompt(messages),
            schema=_normalize_schema_for_codex(schema),
        )
        if not isinstance(payload, dict):
            raise CodexCLIError(
                f"Expected a JSON object from Codex CLI, got {type(payload).__name__}."
            )
        return payload

    def complete_tool_response(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = self._run_with_schema(
            prompt=self._build_tool_prompt(messages, tools),
            schema=_TOOL_RESPONSE_SCHEMA,
        )
        tool_calls = payload.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            raise CodexCLIError("Codex CLI returned invalid tool_calls payload.")

        normalized_calls = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                raise CodexCLIError("Each tool call must be an object.")
            arguments_json = tool_call.get("arguments_json", "")
            try:
                arguments = json.loads(arguments_json)
            except json.JSONDecodeError as exc:
                raise CodexCLIError(
                    f"Tool call arguments were not valid JSON: {arguments_json[:300]}"
                ) from exc
            if not isinstance(arguments, dict):
                raise CodexCLIError("Tool call arguments must decode to a JSON object.")
            normalized_calls.append(
                {
                    "name": str(tool_call.get("name", "")).strip(),
                    "arguments": arguments,
                }
            )

        return {
            "content": (payload.get("content") or "").strip(),
            "tool_calls": normalized_calls,
        }

    def _run_with_schema(self, prompt: str, schema: Dict[str, Any]) -> Any:
        with tempfile.TemporaryDirectory(prefix="mirofish-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "result.json"
            schema_path.write_text(
                json.dumps(schema, ensure_ascii=False),
                encoding="utf-8",
            )

            command = [
                self.executable,
                "exec",
                "-s",
                self.sandbox,
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-",
            ]
            if self.model_name:
                command[2:2] = ["-m", self.model_name]

            env = os.environ.copy()
            env.setdefault("NO_COLOR", "1")

            # ChatGPT-managed auth persists in a shared auth.json file.
            # Serializing Codex executions avoids concurrent refresh/write races.
            with _CODEX_EXEC_LOCK:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    cwd=str(self.working_dir),
                    env=env,
                    encoding="utf-8",
                    timeout=self.timeout_seconds,
                    check=False,
                )
            if completed.returncode != 0:
                raise CodexCLIError(
                    "codex exec failed: "
                    f"{_extract_error_text(completed)}"
                )

            if not output_path.exists():
                raise CodexCLIError(
                    "codex exec completed without writing the output file."
                )

            raw_output = output_path.read_text(encoding="utf-8").strip()
            try:
                return json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise CodexCLIError(
                    f"Failed to parse codex output as JSON: {raw_output[:500]}"
                ) from exc

    def _build_text_prompt(self, messages: List[Dict[str, Any]]) -> str:
        return (
            "You are acting as a stateless chat completion backend for another application.\n"
            "All required context is already included below.\n"
            "Do not use tools, inspect files, or mention Codex/OpenAI.\n"
            "Return only the next assistant message.\n\n"
            f"Conversation messages (JSON):\n{_dump_json(messages)}\n"
        )

    def _build_json_prompt(self, messages: List[Dict[str, Any]]) -> str:
        return (
            "You are acting as a stateless chat completion backend for another application.\n"
            "All required context is already included below.\n"
            "Return the next assistant response as a JSON object matching the provided schema.\n"
            "Do not use tools, inspect files, or wrap the JSON in markdown fences.\n\n"
            f"Conversation messages (JSON):\n{_dump_json(messages)}\n"
        )

    def _build_json_string_prompt(self, messages: List[Dict[str, Any]]) -> str:
        return (
            "You are acting as a stateless chat completion backend for another application.\n"
            "All required context is already included below.\n"
            "Return the next assistant response as a JSON object.\n"
            "Set the `json` field to a string whose contents are exactly that JSON object.\n"
            "Do not use tools, inspect files, or wrap the JSON in markdown fences.\n\n"
            f"Conversation messages (JSON):\n{_dump_json(messages)}\n"
        )

    def _build_tool_prompt(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> str:
        return (
            "You are acting as a tool-calling chat completion backend for another application.\n"
            "Choose the next assistant turn for the conversation below.\n"
            "If a tool should be called, return one or more tool calls and leave `content` empty.\n"
            "If a direct assistant reply is better, return text in `content` and an empty `tool_calls` array.\n"
            "Use only the provided tool names.\n"
            "When returning tool calls, set `arguments_json` to a string whose contents are a valid JSON object for that tool.\n"
            "Do not use external tools, inspect files, or mention Codex/OpenAI.\n\n"
            f"Conversation messages (JSON):\n{_dump_json(messages)}\n\n"
            f"Available tools (JSON):\n{_dump_json(tools)}\n"
        )


class CodexOpenAICompatibilityClient:
    """Minimal OpenAI-client-shaped adapter backed by `codex exec`."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self._runner = CodexCLIClient(model_name=model_name)
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_chat_completion)
        )

    def _create_chat_completion(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> SimpleNamespace:
        del temperature, max_tokens

        if response_format and response_format.get("type") == "json_object":
            content = json.dumps(
                self._runner.complete_json_object(messages),
                ensure_ascii=False,
            )
        else:
            content = self._runner.complete_text(messages)

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ]
        )


class CodexCLIModelBackend(BaseModelBackend):
    """CAMEL-compatible backend that proxies calls through `codex exec`."""

    def __init__(
        self,
        model_type: str,
        model_config_dict: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        token_counter: Optional[OpenAITokenCounter] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            model_type=model_type,
            model_config_dict=model_config_dict,
            api_key=api_key,
            url=url,
            token_counter=token_counter or OpenAITokenCounter(ModelType.GPT_4O_MINI),
            timeout=timeout,
            max_retries=max_retries,
        )
        self._token_counter = token_counter or OpenAITokenCounter(ModelType.GPT_4O_MINI)
        self._codex_client = CodexCLIClient(
            model_name=str(model_type),
            timeout_seconds=Config.LLM_CODEX_TIMEOUT_SECONDS,
        )

    @property
    def token_counter(self) -> OpenAITokenCounter:
        return self._token_counter

    def _run(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        processed_messages = self.preprocess_messages(messages)

        if tools:
            decision = self._codex_client.complete_tool_response(processed_messages, tools)
            return self._build_chat_completion(
                prompt_messages=processed_messages,
                content=decision.get("content", ""),
                tool_calls=decision.get("tool_calls", []),
            )

        if response_format is not None:
            structured_response = self._codex_client.complete_json_object(
                processed_messages,
                schema=response_format.model_json_schema(),
            )
            return self._build_chat_completion(
                prompt_messages=processed_messages,
                content=json.dumps(structured_response, ensure_ascii=False),
            )

        content = self._codex_client.complete_text(processed_messages)
        return self._build_chat_completion(
            prompt_messages=processed_messages,
            content=content,
        )

    async def _arun(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Type[BaseModel]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        return await asyncio.to_thread(self._run, messages, response_format, tools)

    def _build_chat_completion(
        self,
        prompt_messages: List[Dict[str, Any]],
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletion:
        openai_tool_calls = []
        for index, tool_call in enumerate(tool_calls or []):
            name = tool_call.get("name", "").strip()
            if not name:
                raise CodexCLIError("Tool call name cannot be empty.")
            openai_tool_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex}_{index}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(
                            tool_call.get("arguments", {}),
                            ensure_ascii=False,
                        ),
                    },
                }
            )

        prompt_tokens = self._count_prompt_tokens(prompt_messages)
        completion_source = content or json.dumps(tool_calls or [], ensure_ascii=False)
        completion_tokens = max(1, len(completion_source) // 4) if completion_source else 0

        payload = {
            "id": f"codex-cli-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": str(self.model_type),
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if openai_tool_calls else "stop",
                    "message": {
                        "role": "assistant",
                        "content": content or "",
                        **(
                            {"tool_calls": openai_tool_calls}
                            if openai_tool_calls
                            else {}
                        ),
                    },
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        return ChatCompletion.model_validate(payload)

    def _count_prompt_tokens(self, prompt_messages: List[Dict[str, Any]]) -> int:
        try:
            return self.token_counter.count_tokens_from_messages(prompt_messages)
        except Exception:
            serialized = json.dumps(prompt_messages, ensure_ascii=False)
            return max(1, len(serialized) // 4)


def create_camel_model_backend(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
    model_config_dict: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    max_retries: int = 3,
) -> BaseModelBackend:
    resolved_provider = get_llm_provider(provider)
    resolved_model_name = model_name or Config.LLM_MODEL_NAME

    if resolved_provider == CODEX_CLI_PROVIDER:
        return CodexCLIModelBackend(
            model_type=resolved_model_name,
            model_config_dict=model_config_dict,
            timeout=timeout,
            max_retries=max_retries,
        )

    resolved_api_key = api_key or Config.LLM_API_KEY
    if not resolved_api_key:
        raise ValueError("LLM_API_KEY is required for the openai_compatible provider.")

    return ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=resolved_model_name,
        model_config_dict=model_config_dict,
        api_key=resolved_api_key,
        url=base_url or Config.LLM_BASE_URL or None,
        timeout=timeout,
        max_retries=max_retries,
    )


def create_openai_compatible_client(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
):
    resolved_provider = get_llm_provider(provider)
    if resolved_provider == CODEX_CLI_PROVIDER:
        return CodexOpenAICompatibilityClient(model_name=model_name)

    from openai import OpenAI

    resolved_api_key = api_key or Config.LLM_API_KEY
    if not resolved_api_key:
        raise ValueError("LLM_API_KEY is required for the openai_compatible provider.")

    return OpenAI(
        api_key=resolved_api_key,
        base_url=base_url or Config.LLM_BASE_URL,
    )
