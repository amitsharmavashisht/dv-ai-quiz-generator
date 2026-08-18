"""Runtime configuration, loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _list(name: str, default: str) -> list[str]:
    return [
        v.strip()
        for v in (os.getenv(name, "") or default).split(",")
        if v.strip()
    ]


class Settings:

    # ============================================================
    # Provider
    # ============================================================
    #
    # Supported:
    #   groq
    #   gemini
    #   ollama
    #   huggingface
    #
    # Production default:
    #   Groq → Gemini → Ollama
    #
    LLM_PROVIDER: str = (
        os.getenv("LLM_PROVIDER", "groq") or "groq"
    ).lower().strip()

    # ============================================================
    # Ollama — local fallback
    # ============================================================

    OLLAMA_HOST: str = (
        os.getenv(
            "OLLAMA_HOST",
            "http://localhost:11434"
        )
    ).rstrip("/")

    OLLAMA_MODEL: str = os.getenv(
        "OLLAMA_MODEL",
        "qwen2.5:7b"
    )

    OLLAMA_TIMEOUT: int = _int(
        "OLLAMA_TIMEOUT",
        300
    )

    OLLAMA_NUM_CTX: int = _int(
        "OLLAMA_NUM_CTX",
        8192
    )

    # ============================================================
    # Groq — PRIMARY
    # ============================================================

    GROQ_API_KEY: str = os.getenv(
        "GROQ_API_KEY",
        ""
    )

    GROQ_MODEL: str = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b"
    )

    # ============================================================
    # Gemini — BACKUP
    # ============================================================

    GEMINI_API_KEY: str = os.getenv(
        "GEMINI_API_KEY",
        ""
    )

    GEMINI_MODEL: str = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    # ============================================================
    # Hugging Face — optional
    # ============================================================

    HF_TOKEN: str = os.getenv(
        "HF_TOKEN",
        ""
    )

    HF_MODEL: str = os.getenv(
        "HF_MODEL",
        "Qwen/Qwen2.5-7B-Instruct"
    )

    # ============================================================
    # LLM behavior
    # ============================================================

    LLM_MAX_RETRIES: int = _int(
        "LLM_MAX_RETRIES",
        3
    )

    # ============================================================
    # Limits
    # ============================================================

    MAX_UPLOAD_MB: int = _int(
        "MAX_UPLOAD_MB",
        20
    )

    MIN_SOURCE_CHARS: int = _int(
        "MIN_SOURCE_CHARS",
        200
    )

    MAX_QUESTIONS: int = _int(
        "MAX_QUESTIONS",
        100
    )

    _MAX_SOURCE_CHARS: int = _int(
        "MAX_SOURCE_CHARS",
        0
    )

    QUESTIONS_PER_CALL: int = _int(
        "QUESTIONS_PER_CALL",
        8
    )

    # ============================================================
    # Cache
    # ============================================================

    CACHE_ENABLED: bool = _bool(
        "CACHE_ENABLED",
        True
    )

    CACHE_MAX_ENTRIES: int = _int(
        "CACHE_MAX_ENTRIES",
        500
    )

    CACHE_TTL_SEC: int = _int(
        "CACHE_TTL_SEC",
        60 * 60 * 24 * 7
    )

    # ============================================================
    # Rate limiting
    # ============================================================

    RATE_LIMIT_COUNT: int = _int(
        "RATE_LIMIT_COUNT",
        15
    )

    RATE_LIMIT_WINDOW_SEC: int = _int(
        "RATE_LIMIT_WINDOW_SEC",
        3600
    )

    # ============================================================
    # Access
    # ============================================================

    ALLOWED_ORIGINS: list[str] = _list(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    )

    ENFORCE_ORIGIN: bool = _bool(
        "ENFORCE_ORIGIN",
        True
    )

    APP_SHARED_KEY: str = os.getenv(
        "APP_SHARED_KEY",
        ""
    )

    # ============================================================
    # Network
    # ============================================================

    FETCH_TIMEOUT: int = _int(
        "FETCH_TIMEOUT",
        25
    )

    # ============================================================
    # Properties
    # ============================================================

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def max_source_chars(self) -> int:

        if self._MAX_SOURCE_CHARS:
            return self._MAX_SOURCE_CHARS

        # Hosted models can accept larger input than local models.
        if self.LLM_PROVIDER == "ollama":
            return max(
                4000,
                (self.OLLAMA_NUM_CTX - 2500) * 3
            )

        if self.LLM_PROVIDER == "huggingface":
            return 10000

        if self.LLM_PROVIDER == "gemini":
            return 28000

        # Groq
        return 28000

    @property
    def model_name(self) -> str:

        return {
            "groq": self.GROQ_MODEL,
            "gemini": self.GEMINI_MODEL,
            "ollama": self.OLLAMA_MODEL,
            "huggingface": self.HF_MODEL,
        }.get(
            self.LLM_PROVIDER,
            self.LLM_PROVIDER
        )

    def credential_problem(self) -> str | None:
        """Return a configuration problem for the primary provider."""

        if self.LLM_PROVIDER == "groq":

            if not self.GROQ_API_KEY:
                return "GROQ_API_KEY is not set."

        elif self.LLM_PROVIDER == "gemini":

            if not self.GEMINI_API_KEY:
                return "GEMINI_API_KEY is not set."

        elif self.LLM_PROVIDER == "huggingface":

            if not self.HF_TOKEN:
                return "HF_TOKEN is not set."

        elif self.LLM_PROVIDER == "ollama":
            # Ollama is checked separately by its health function.
            pass

        else:

            return (
                f"Unknown LLM_PROVIDER "
                f"'{self.LLM_PROVIDER}'."
            )

        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()