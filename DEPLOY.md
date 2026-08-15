# Running and deploying

## The decision you have to make first

Ollama runs a model on whatever machine it is installed on. That is excellent
for development and fine for production **if you rent a server big enough to
hold the model**. It cannot work from shared WordPress hosting, and it cannot
work from your laptop once the site is live, because your laptop is not
reachable from the internet and is not always on.

So there are three honest options:

| Setup | Cost | Speed | Good for |
|---|---|---|---|
| Ollama on your PC | free | 10–40s on CPU, 2–6s on GPU | development, building quizzes to export as HTML |
| Ollama on a VPS | ₹1,500–4,000/mo for 8–16 GB RAM | 20–60s on CPU | self-hosted, no per-quiz cost, full privacy |
| Groq | free tier, then paise per quiz | 2–5s | public traffic on dvdigital.in |

The code supports all three. Change one line in `.env`.

**The recommendation:** Ollama locally while you build, Groq in production, and
lean on the Copy HTML export so most student traffic never touches the API at
all. That combination costs almost nothing and stays fast.

---

## 1. Local development with Ollama

Install Ollama from https://ollama.com, then:

```bash
ollama pull llama3.1:8b        # 4.7 GB
ollama serve                   # usually already running as a service
```

Then the API:

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1     # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt
copy .env.example .env         # cp on macOS/Linux
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000

`.env` needs nothing changed for Ollama — it is the default.

### Choosing a model

| Model | Size | Notes |
|---|---|---|
| `llama3.2:3b` | 2 GB | fastest, weakest questions. Fine on 8 GB RAM. |
| `llama3.1:8b` | 4.7 GB | the default. Good balance. |
| `qwen2.5:7b` | 4.7 GB | noticeably better at Hindi. |
| `qwen2.5:14b` | 9 GB | best quality that still fits 16 GB RAM. |

If generation is slow or times out, lower `QUESTIONS_PER_CALL` to 4 or 5. Each
call then asks for less and finishes sooner, at the cost of more calls.

---

## 2. Production on Render with Groq

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
ALLOWED_ORIGINS=https://dvdigital.in,https://www.dvdigital.in
APP_SHARED_KEY=<a long random string>
```

1. Push `backend/` to GitHub. Confirm `.env` is **not** in the commit —
   `.gitignore` covers it, but check with `git status` before the first push.
2. Render → New → Web Service → point at the repo. It reads the Dockerfile.
3. Add the four environment variables above.
4. Note the URL, e.g. `https://dv-quiz.onrender.com`.
5. `GET /health` should return `"status": "ok"`.

Free instances sleep after inactivity, so the first request of the day takes
about 30 seconds.

## 3. Production self-hosted with Ollama

On a VPS with at least 8 GB RAM:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b

cd backend
docker build -t dvq .
docker run -d --name dvq -p 8000:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e LLM_PROVIDER=ollama \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -e ALLOWED_ORIGINS=https://dvdigital.in,https://www.dvdigital.in \
  -e APP_SHARED_KEY=<random> \
  dvq
```

Put nginx and a TLS certificate in front. Expect 20–60 seconds per paper on
CPU. Set `OLLAMA_TIMEOUT=300` and warn students that it takes a moment.

## 4. WordPress

1. Upload `dv-ai-quiz-plugin.zip` → Plugins → Add New → Upload → Activate.
2. Settings → AI Quiz Generator → paste the API address and the same
   `APP_SHARED_KEY`.
3. Put `[dv_ai_quiz]` on a page. In Elementor, use a Shortcode widget.

---

## Health and monitoring

`GET /health` returns the provider state, cache statistics and the active
limits. It answers 200 when the model is reachable and 503 when it is not,
so uptime monitors can watch it directly.

```json
{
  "status": "ok",
  "llm": {"provider": "ollama", "model": "llama3.1:8b", "ready": true,
          "detail": "2 model(s) available"},
  "cache": {"entries": 34, "hits": 112, "misses": 34, "hit_rate": 0.767}
}
```

Every API response carries an `X-Request-ID` header that also appears in the
logs, so a student reporting a failure can be traced to one line.

## Tuning

| Symptom | Setting to change |
|---|---|
| Local model times out | `QUESTIONS_PER_CALL=4`, `OLLAMA_TIMEOUT=600` |
| Groq rate limit errors | `MAX_SOURCE_CHARS=8000`, `QUESTIONS_PER_CALL=6` |
| Questions all from page one | raise `MAX_SOURCE_CHARS` |
| Model repeats itself | raise `QUESTIONS_PER_CALL` so fewer batches are needed |
| Memory growth | lower `CACHE_MAX_ENTRIES` |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

62 tests, no network and no model required. They cover URL normalisation and
scheme rejection, YouTube ID parsing, file type sniffing by magic bytes, the
HTML fallback extractor, three-region condensing, section splitting, JSON
repair, answer coercion from letters and numbers and option text, batching,
deduplication, partial-failure recovery, caching, and every HTTP status the
API can return.

## Known limits

- The rate limiter and cache live in memory. One container is fine; beyond
  that, move both to Redis.
- YouTube blocks transcript requests from most datacentre IPs. It works from a
  home connection and usually fails on Render. The error says so plainly.
- Some sites refuse automated readers, including dvdigital.in itself. The
  error reports the HTTP status rather than guessing.
- Scanned PDFs have no text layer and are rejected with an explanation. OCR
  would need Tesseract, which is not installed.
