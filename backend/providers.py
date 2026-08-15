"""AI provider layer.

Provider priority:
    1. Groq       - primary
    2. Gemini     - backup
    3. Ollama     - local fallback

The caller receives a raw string and parses it as JSON.

Existing pasted MCQs that already contain answers should continue to
bypass this provider layer completely.
"""

from __future__ import annotations

import logging
import random
import time

import httpx

from config import get_settings

log = logging.getLogger("dvq.provider")
settings = get_settings()


class ProviderError(Exception):
    """Upstream model call failed."""


class ProviderUnavailable(ProviderError):
    """Provider is not reachable or not configured."""


class RateLimited(ProviderError):
    """Provider asked us to slow down."""


# ============================================================
# OLLAMA
# ============================================================

def _ollama_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int
) -> str:

    url = f"{settings.OLLAMA_HOST}/api/chat"

    body = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_ctx": settings.OLLAMA_NUM_CTX,
            "num_predict": max_tokens,
        },
    }

    try:
        with httpx.Client(timeout=settings.OLLAMA_TIMEOUT) as client:
            resp = client.post(url, json=body)

    except httpx.ConnectError as exc:
        raise ProviderUnavailable(
            f"Cannot reach Ollama at {settings.OLLAMA_HOST}"
        ) from exc

    except httpx.TimeoutException as exc:
        raise ProviderError(
            f"Ollama timeout after {settings.OLLAMA_TIMEOUT}s"
        ) from exc

    if resp.status_code == 404:
        raise ProviderUnavailable(
            f"Ollama model '{settings.OLLAMA_MODEL}' is not installed. "
            f"Run: ollama pull {settings.OLLAMA_MODEL}"
        )

    if resp.status_code >= 400:
        raise ProviderError(
            f"Ollama HTTP {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()

    content = (data.get("message") or {}).get("content", "")

    if not content:
        raise ProviderError("Ollama returned an empty reply.")

    return content


def _ollama_health() -> tuple[bool, str]:

    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(
                f"{settings.OLLAMA_HOST}/api/tags"
            )

        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code} from Ollama"

        names = [
            m.get("name", "")
            for m in resp.json().get("models", [])
        ]

        if not names:
            return False, "Ollama has no models."

        want = settings.OLLAMA_MODEL

        if (
            want in names
            or any(
                n.split(":")[0] == want.split(":")[0]
                for n in names
            )
        ):
            return True, f"{len(names)} model(s) available"

        return False, (
            f"'{want}' not pulled. "
            f"Available: {', '.join(names[:5])}"
        )

    except Exception as exc:
        return False, f"Cannot reach Ollama: {exc}"


# ============================================================
# GROQ — PRIMARY
# ============================================================

_groq_client = None


def _groq():

    global _groq_client

    if _groq_client is None:

        from groq import Groq

        if not settings.GROQ_API_KEY:
            raise ProviderUnavailable(
                "GROQ_API_KEY is not set."
            )

        _groq_client = Groq(
            api_key=settings.GROQ_API_KEY,
            timeout=90.0,
        )

    return _groq_client


def _groq_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int
) -> str:

    try:

        resp = _groq().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,

            # Important for quiz JSON generation
            response_format={
                "type": "json_object"
            },
        )

    except Exception as exc:

        text = str(exc)
        low = text.lower()

        if "rate" in low and "limit" in low:
            raise RateLimited(
                f"Groq rate limit: {text[:200]}"
            ) from exc

        if (
            "context" in low
            or "too large" in low
            or "maximum" in low
        ):
            raise ProviderError(
                f"Groq context exceeded: {text[:200]}"
            ) from exc

        if (
            "authentication" in low
            or "api key" in low
            or "401" in low
        ):
            raise ProviderUnavailable(
                "Groq rejected the API key."
            ) from exc

        raise ProviderError(
            f"Groq error: {text[:300]}"
        ) from exc

    content = resp.choices[0].message.content or ""

    if not content:
        raise ProviderError(
            "Groq returned an empty reply."
        )

    return content


def _groq_health() -> tuple[bool, str]:

    if not settings.GROQ_API_KEY:
        return False, "GROQ_API_KEY is not set."

    return True, "key present"


# ============================================================
# GEMINI — BACKUP
# ============================================================

_gemini_client = None


def _gemini():

    global _gemini_client

    if _gemini_client is None:

        from google import genai

        if not settings.GEMINI_API_KEY:
            raise ProviderUnavailable(
                "GEMINI_API_KEY is not set."
            )

        _gemini_client = genai.Client(
            api_key=settings.GEMINI_API_KEY
        )

    return _gemini_client


def _gemini_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int
) -> str:

    try:

        client = _gemini()

        # Convert OpenAI/Groq-style messages into one prompt.
        parts = []

        for message in messages:

            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                parts.append(
                    f"SYSTEM INSTRUCTIONS:\n{content}"
                )
            else:
                parts.append(
                    f"USER:\n{content}"
                )

        prompt = "\n\n".join(parts)

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
            },
        )

    except Exception as exc:

        text = str(exc)
        low = text.lower()

        if (
            "429" in low
            or "rate" in low
            or "quota" in low
        ):
            raise RateLimited(
                f"Gemini rate limit: {text[:200]}"
            ) from exc

        if (
            "401" in low
            or "403" in low
            or "api key" in low
            or "authentication" in low
        ):
            raise ProviderUnavailable(
                "Gemini rejected the API key."
            ) from exc

        raise ProviderError(
            f"Gemini error: {text[:300]}"
        ) from exc

    content = getattr(response, "text", None) or ""

    if not content:
        raise ProviderError(
            "Gemini returned an empty reply."
        )

    return content


def _gemini_health() -> tuple[bool, str]:

    if not settings.GEMINI_API_KEY:
        return False, "GEMINI_API_KEY is not set."

    return True, "key present"


# ============================================================
# HUGGING FACE
# ============================================================

_hf_client = None


def _hf():

    global _hf_client

    if _hf_client is None:

        from huggingface_hub import InferenceClient

        if not settings.HF_TOKEN:
            raise ProviderUnavailable(
                "HF_TOKEN is not set."
            )

        _hf_client = InferenceClient(
            model=settings.HF_MODEL,
            token=settings.HF_TOKEN
        )

    return _hf_client


def _hf_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int
) -> str:

    try:

        resp = _hf().chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    except Exception as exc:

        text = str(exc)

        if "503" in text or "loading" in text.lower():
            raise RateLimited(
                f"Hugging Face model is loading: {text[:160]}"
            ) from exc

        raise ProviderError(
            text[:300]
        ) from exc

    return resp.choices[0].message.content or ""


def _hf_health() -> tuple[bool, str]:

    if not settings.HF_TOKEN:
        return False, "HF_TOKEN is not set."

    return True, "token present"


# ============================================================
# PROVIDERS
# ============================================================

_BACKENDS = {

    "groq": (
        _groq_chat,
        _groq_health,
    ),

    "gemini": (
        _gemini_chat,
        _gemini_health,
    ),

    "ollama": (
        _ollama_chat,
        _ollama_health,
    ),

    "huggingface": (
        _hf_chat,
        _hf_health,
    ),
}


# ============================================================
# HEALTH
# ============================================================

def health() -> dict:
    """Return status of the configured primary provider."""

    provider = settings.LLM_PROVIDER

    entry = _BACKENDS.get(provider)

    if entry is None:

        return {
            "provider": provider,
            "ready": False,
            "detail": "Unknown provider.",
        }

    ready, detail = entry[1]()

    return {
        "provider": provider,
        "model": settings.model_name,
        "ready": ready,
        "detail": detail,
    }


# ============================================================
# FALLBACK SYSTEM
# ============================================================

def _provider_order() -> list[str]:
    """Return providers in priority order."""

    primary = settings.LLM_PROVIDER.lower().strip()

    # Your desired production order
    if primary == "groq":

        return [
            "groq",
            "gemini",
            "ollama",
        ]

    # If someone deliberately selects Gemini
    if primary == "gemini":

        return [
            "gemini",
            "groq",
            "ollama",
        ]

    # If someone deliberately selects Ollama
    if primary == "ollama":

        return [
            "ollama",
            "groq",
            "gemini",
        ]

    return [
        primary,
        "groq",
        "gemini",
        "ollama",
    ]


def chat(
    messages: list[dict],
    temperature: float = 0.4,
    max_tokens: int = 4096
) -> str:
    """
    Generate a response using provider fallback.

    Default production order:

        Groq → Gemini → Ollama

    A provider failure automatically moves to the next provider.
    """

    providers = _provider_order()

    errors = []

    for provider_name in providers:

        entry = _BACKENDS.get(provider_name)

        if entry is None:
            continue

        call = entry[0]

        log.info(
            "trying provider=%s model=%s",
            provider_name,
            getattr(
                settings,
                "model_name",
                "unknown"
            ),
        )

        for attempt in range(
            settings.LLM_MAX_RETRIES
        ):

            try:

                result = call(
                    messages,
                    temperature,
                    max_tokens,
                )

                if result:

                    log.info(
                        "provider=%s succeeded",
                        provider_name,
                    )

                    return result

                raise ProviderError(
                    f"{provider_name} returned empty output."
                )

            except ProviderUnavailable as exc:

                errors.append(
                    f"{provider_name}: {exc}"
                )

                log.warning(
                    "provider=%s unavailable: %s",
                    provider_name,
                    exc,
                )

                # Don't retry a provider that isn't configured.
                break

            except RateLimited as exc:

                errors.append(
                    f"{provider_name}: {exc}"
                )

                delay = (
                    (2 ** attempt)
                    + random.uniform(0, 0.6)
                )

                log.warning(
                    "provider=%s rate limited; "
                    "waiting %.1fs",
                    provider_name,
                    delay,
                )

                time.sleep(delay)

            except ProviderError as exc:

                errors.append(
                    f"{provider_name}: {exc}"
                )

                log.warning(
                    "provider=%s failed "
                    "(attempt %s/%s): %s",
                    provider_name,
                    attempt + 1,
                    settings.LLM_MAX_RETRIES,
                    exc,
                )

                time.sleep(
                    0.5 * (attempt + 1)
                )

    raise ProviderError(
        "All AI providers failed. "
        + " | ".join(errors)
    )