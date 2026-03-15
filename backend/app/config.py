"""
Application configuration loaded from the project root `.env`.
"""

import os
import shutil

from dotenv import load_dotenv

project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    load_dotenv(override=True)


class Config:
    """Flask configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "mirofish-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() == "true"
    JSON_AS_ASCII = False

    LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai_compatible").strip().lower()
    LLM_API_KEY = os.environ.get("LLM_API_KEY")
    LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL_NAME = os.environ.get("LLM_MODEL_NAME", "gpt-4o-mini")
    LLM_CODEX_EXECUTABLE = os.environ.get("LLM_CODEX_EXECUTABLE", "codex")
    LLM_CODEX_SANDBOX = os.environ.get("LLM_CODEX_SANDBOX", "read-only")
    LLM_CODEX_WORKDIR = os.environ.get(
        "LLM_CODEX_WORKDIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
    )
    LLM_CODEX_TIMEOUT_SECONDS = int(
        os.environ.get("LLM_CODEX_TIMEOUT_SECONDS", "180")
    )

    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    DEFAULT_CHUNK_SIZE = 500
    DEFAULT_CHUNK_OVERLAP = 50

    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get("OASIS_DEFAULT_MAX_ROUNDS", "10"))
    OASIS_SIMULATION_DATA_DIR = os.path.join(
        os.path.dirname(__file__),
        "../uploads/simulations",
    )

    OASIS_TWITTER_ACTIONS = [
        "CREATE_POST",
        "LIKE_POST",
        "REPOST",
        "FOLLOW",
        "DO_NOTHING",
        "QUOTE_POST",
    ]
    OASIS_REDDIT_ACTIONS = [
        "LIKE_POST",
        "DISLIKE_POST",
        "CREATE_POST",
        "CREATE_COMMENT",
        "LIKE_COMMENT",
        "DISLIKE_COMMENT",
        "SEARCH_POSTS",
        "SEARCH_USER",
        "TREND",
        "REFRESH",
        "DO_NOTHING",
        "FOLLOW",
        "MUTE",
    ]

    REPORT_AGENT_MAX_TOOL_CALLS = int(
        os.environ.get("REPORT_AGENT_MAX_TOOL_CALLS", "5")
    )
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(
        os.environ.get("REPORT_AGENT_MAX_REFLECTION_ROUNDS", "2")
    )
    REPORT_AGENT_TEMPERATURE = float(
        os.environ.get("REPORT_AGENT_TEMPERATURE", "0.5")
    )

    @classmethod
    def validate(cls):
        """Validate required settings."""
        errors = []

        if cls.LLM_PROVIDER not in {"openai_compatible", "codex_cli"}:
            errors.append(f"Unsupported LLM_PROVIDER: {cls.LLM_PROVIDER}")
        elif cls.LLM_PROVIDER == "openai_compatible" and not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is required when LLM_PROVIDER=openai_compatible.")
        elif cls.LLM_PROVIDER == "codex_cli" and not shutil.which(cls.LLM_CODEX_EXECUTABLE):
            errors.append(
                "LLM_PROVIDER=codex_cli requires a working Codex CLI executable "
                f"(`{cls.LLM_CODEX_EXECUTABLE}`)."
            )

        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY is required.")

        return errors
