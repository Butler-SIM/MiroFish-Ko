"""
Small LLM wrapper used by backend services.
"""

import json
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config
from .llm_provider import CodexCLIClient, is_codex_cli_provider


class LLMClient:
    """Provider-aware chat client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.provider = (provider or Config.LLM_PROVIDER).strip().lower()
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        self.client: Optional[OpenAI] = None
        self.codex_client: Optional[CodexCLIClient] = None

        if is_codex_cli_provider(self.provider):
            self.codex_client = CodexCLIClient(model_name=self.model)
        else:
            if not self.api_key:
                raise ValueError("LLM_API_KEY is required for the openai_compatible provider.")
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
    ) -> str:
        if self.codex_client is not None:
            if response_format and response_format.get("type") == "json_object":
                content = json.dumps(
                    self.codex_client.complete_json_object(messages),
                    ensure_ascii=False,
                )
            else:
                content = self.codex_client.complete_text(messages)
            return self._clean_content(content)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return self._clean_content(content)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        if self.codex_client is not None:
            return self.codex_client.complete_json_object(messages)

        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        cleaned_response = response.strip()
        cleaned_response = re.sub(
            r"^```(?:json)?\s*\n?",
            "",
            cleaned_response,
            flags=re.IGNORECASE,
        )
        cleaned_response = re.sub(r"\n?```\s*$", "", cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response was not valid JSON: {cleaned_response}"
            ) from exc

    def _clean_content(self, content: Optional[str]) -> str:
        text = content or ""
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
