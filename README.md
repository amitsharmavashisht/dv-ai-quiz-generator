# AI Quiz Generator — quick start

Turns notes, PDFs, web pages and YouTube videos into practice papers, and
exports any paper as a single self-contained HTML file you can paste into
WordPress.

Two ways to use it. The first needs no setup at all.

---

## A. Just the export tool — no install

Open **`demo/index.html`** in any browser.

The **Paste questions** tab works completely offline. Paste questions you
already have, press **Build quiz**, and you land on the HTML export screen with
a Copy button. Nothing is sent anywhere — the parsing happens in the browser.

This alone covers the common case: a previous year paper already typed out,
wanted as an interactive quiz on the site.

## B. The full tool with AI — 10 minutes

### 1. Install Ollama

Download from **https://ollama.com**, install, then:

```bash
ollama pull qwen2.5:7b
```

A roughly 4–5 GB one-time download (depending on the Ollama build/quantization). It runs on your own machine, costs nothing, and has
no usage limit.

### 2. Start the service

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env        # macOS/Linux: cp .env.example .env
uvicorn main:app --reload --port 8000
```

Open **http://localhost:8000**

`.env` needs no editing for Ollama — it is the default. If something looks
wrong, **http://localhost:8000/health** reports whether the model is reachable
and why not.

### On a 6 GB graphics card

Add these two lines to `.env` so the model stays on the GPU:

```
OLLAMA_NUM_CTX=4096
QUESTIONS_PER_CALL=5
```

---

## The four steps

1. **Add questions** — Notes, File, Web page, YouTube, or Paste questions
2. **Build quiz** — take it on screen with exam-style answer bubbles
3. **Copy HTML** — with a Preview tab, so you see it before pasting
4. **Paste in WordPress** — a Custom HTML block, or Elementor's HTML widget

Once pasted, the quiz runs entirely in the reader's browser. That page never
calls this service again, so it stays fast and costs nothing to serve.

## Paste format

```
Q1. When was Himachal Pradesh established as a state?  हिमाचल प्रदेश राज्य कब बना?
A) 1950   B) 1966   C) 1971*   D) 1975
Exp: Himachal became a full state on 25 January 1971.
```

- `*` marks the correct option, or add `Ans: C`, `Answer: 3`, or `उत्तर: B. अक्षम`
- Options can use A-D or 1-4, one per line or on one line
- Hindi and English can be mixed in the same quiz
- `Exp:`, `Explanation:`, `विग्रह:`, `समास:` and `संधि:` explanations are preserved
- If an answer is missing, the deterministic converter refuses to guess it

## Putting it on the site

Two options, suiting different things.

**Export the HTML** — recommended for most quizzes. Build the paper once, copy
the HTML, paste it into a page. No server needed afterwards, the page is
indexable by Google, and it cannot break when the service is down.

**Install the plugin** so visitors generate their own papers. Upload
`dv-ai-quiz-plugin.zip` under Plugins → Add New, set the API address in
Settings → AI Quiz Generator, and place `[dv_ai_quiz]` on a page. This needs
the Python service running somewhere reachable from the internet — see
`DEPLOY.md`.

## Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest -q     # 64 tests
npm install jsdom && node tests-frontend/ui.test.js                # browser checks
```

## Files

```
demo/index.html          open this first — works with no server
backend/                 the Python service
backend/static/          the interface it serves at /
wordpress/               plugin source
dv-ai-quiz-plugin.zip    upload this to WordPress
DEPLOY.md                hosting, tuning, known limits
PORTING-NOTES.md         notes on the original Streamlit version
```

## Recommended free/local model

The default local model is **Qwen2.5 7B (`qwen2.5:7b`) via Ollama**. On a 6 GB RTX 3050, use the Ollama model that fits your VRAM/RAM configuration.

Install Ollama, then run:

```bash
ollama pull qwen2.5:7b
ollama serve
```

Then start the backend with `uvicorn main:app --reload --port 8000` from `backend/`.

### Correct-answer protection

If the user pastes an existing MCQ paper containing `Answer: B` or `✅ उत्तर: B. ...`, the backend uses a deterministic parser instead of asking the LLM to guess the answer. It verifies that the supplied answer matches one of A/B/C/D and passes the exact `answer_index` to the HTML renderer. Hindi, English, and mixed Unicode are supported.

If the input is study material without explicit answers, Qwen generates MCQs using the source-grounded prompt and the backend validates the JSON structure before rendering.


## Updated deterministic converter

The paste converter is intentionally separate from the LLM path. Existing MCQ papers are parsed locally so supplied answers are never re-predicted by an LLM. The converter supports 100 questions per paper, numeric answers 1–4, letter answers A–D, Hindi/English/mixed Unicode, and preserves explanation lines.

The standalone HTML export is self-contained and uses the same premium interface for every question. The export generator emits a real `</script>` closing tag, so downloaded HTML runs directly in Chrome/Edge/Firefox without editing.
