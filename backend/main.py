"""DV Digital AI Quiz Generator — API service.

Run locally:
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Union

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

import cache
import extractors
import providers
import quiz_engine
import ratelimit
from config import get_settings

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("dvq")

STATIC_DIR = Path(__file__).parent / "static"
STATIC = STATIC_DIR / "index.html"
EMBED = STATIC_DIR / "embed.js"

VALID_DIFFICULTY = {"easy", "medium", "hard"}
VALID_SOURCES = {"text", "file", "url", "youtube"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    problem = settings.credential_problem()
    if problem:
        log.error("PROVIDER NOT USABLE: %s", problem)
    state = providers.health()
    log.info("provider=%s model=%s ready=%s (%s)",
             state["provider"], state.get("model"), state["ready"], state["detail"])
    log.info("source budget=%s chars | batch=%s q/call | cache=%s",
             settings.max_source_chars, settings.QUESTIONS_PER_CALL,
             settings.CACHE_ENABLED)
    yield


app = FastAPI(title="DV Digital AI Quiz Generator", version="2.0.0",
              lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def tag_and_time(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    request.state.rid = rid
    started = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = rid
    if request.url.path.startswith("/api/"):
        log.info("%s %s %s -> %s in %.0fms",
                 rid, request.method, request.url.path,
                 response.status_code, elapsed)
    return response


def guard(request: Request) -> None:
    """Shared-key check, origin check, rate limit. Raises HTTPException."""
    if settings.APP_SHARED_KEY:
        if request.headers.get("x-dvq-key") != settings.APP_SHARED_KEY:
            raise HTTPException(status_code=401, detail="Invalid key.")

    if settings.ENFORCE_ORIGIN:
        origin = request.headers.get("origin")
        if origin and origin not in settings.ALLOWED_ORIGINS:
            log.warning("rejected origin %s", origin)
            raise HTTPException(status_code=403, detail="This origin is not allowed.")

    ip = ratelimit.client_ip(request)
    allowed, retry_after = ratelimit.check(ip)
    if not allowed:
        minutes = max(1, retry_after // 60)
        raise HTTPException(
            status_code=429,
            detail=f"Quiz limit reached. Try again in about {minutes} minute(s).",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def home():
    if STATIC.exists():
        return FileResponse(STATIC)
    return JSONResponse({"status": "ok", "hint": "static/index.html is missing"})

@app.get("/embed.js", include_in_schema=False)
def embed_script():
    if EMBED.exists():
        return FileResponse(
            EMBED,
            media_type="application/javascript"
        )
    return JSONResponse(
        {"error": "embed.js is missing"},
        status_code=404
    )

@app.get("/health")
def health() -> JSONResponse:
    state = providers.health()
    body = {
        "status": "ok" if state["ready"] else "degraded",
        "version": app.version,
        "llm": state,
        "cache": cache.stats(),
        "limits": {
            "max_questions": settings.MAX_QUESTIONS,
            "max_upload_mb": settings.MAX_UPLOAD_MB,
            "source_chars": settings.max_source_chars,
            "questions_per_call": settings.QUESTIONS_PER_CALL,
            "rate_limit": f"{settings.RATE_LIMIT_COUNT}/"
                          f"{settings.RATE_LIMIT_WINDOW_SEC}s",
        },
    }
    return JSONResponse(body, status_code=200 if state["ready"] else 503)


@app.post("/api/v1/quiz")
async def create_quiz(
    request: Request,
    source_type: str = Form(...),           # text | file | url | youtube
    text: str = Form(""),
    url: str = Form(""),
    num_questions: int = Form(10),
    difficulty: str = Form("medium"),
    language: str = Form("auto"),
    output_format: str = Form("mcq"),       # mcq | short
    focus_topic: str = Form(""),
    # Swagger posts an empty string when no file is chosen, and browsers can
    # post a zero-byte file. Accept both and normalise them away.
    file: Union[UploadFile, str, None] = File(None),
) -> JSONResponse:
    guard(request)

    if isinstance(file, str) or (file is not None and not getattr(file, "filename", "")):
        file = None

    source_type = (source_type or "").strip().lower()
    if source_type not in VALID_SOURCES:
        raise HTTPException(status_code=400,
                            detail=f"Unknown source type '{source_type}'.")

    num_questions = max(3, min(num_questions, settings.MAX_QUESTIONS))
    difficulty = (difficulty or "medium").lower()
    if difficulty not in VALID_DIFFICULTY:
        difficulty = "medium"
    output_format = "short" if output_format == "short" else "mcq"
    focus_topic = (focus_topic or "").strip()[:120]

    # --- 1. get raw text -------------------------------------------------
    try:
        if source_type == "text":
            raw = text or ""
        elif source_type == "file":
            if file is None:
                raise extractors.ExtractionError("No file was received.")
            data = await file.read()
            if len(data) > settings.max_upload_bytes:
                raise extractors.ExtractionError(
                    f"That file is {len(data) / 1048576:.1f} MB, over the "
                    f"{settings.MAX_UPLOAD_MB} MB limit."
                )
            raw = extractors.from_file(file.filename or "", data)
        elif source_type == "url":
            raw = extractors.from_url(url)
        else:
            raw = extractors.from_youtube(url)
    except extractors.ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("extraction crashed")
        raise HTTPException(
            status_code=500,
            detail="That source could not be read. Try a different file or link.",
        ) from exc

    source = extractors.condense(raw)
    if len(source) < settings.MIN_SOURCE_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Add more content — at least {settings.MIN_SOURCE_CHARS} "
                   f"characters are needed to write a fair quiz "
                   f"(found {len(source)}).",
        )

    # --- 2. generate -----------------------------------------------------
    try:
        quiz = quiz_engine.generate(source, num_questions, difficulty,
                                    language, output_format, focus_topic)
    except providers.ProviderUnavailable as exc:
        log.error("provider unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except quiz_engine.GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except providers.ProviderError as exc:
        log.error("provider failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="The model is busy or unreachable. Try again in a moment.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("generation crashed")
        raise HTTPException(
            status_code=500, detail="Something went wrong building the paper."
        ) from exc

    log.info("%s ok | %s | %s | %s q | %s | %s chars",
             getattr(request.state, "rid", "-"), source_type, output_format,
             len(quiz.questions), difficulty, len(source))
    return JSONResponse(quiz.model_dump())


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        {"error": "Something went wrong. Please try again.",
         "request_id": getattr(request.state, "rid", None)},
        status_code=500,
    )
