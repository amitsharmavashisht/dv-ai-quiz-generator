# Porting notes — from `app.py` (Streamlit) to the web version

For Manish. Short version: the pipeline idea was right, the delivery layer had
to change, and four bugs would have surfaced the moment it went public.

## First: revoke the token

`app.py` line 15 has a live Hugging Face token in the source, and the file has
been shared over WhatsApp. Treat it as compromised.

huggingface.co → Settings → Access Tokens → delete → issue a new one → put it
in `.env`, which is never committed.

## Why not Streamlit on the site

Streamlit is a full-page app held together by a websocket. Embedding it in a
WordPress page means an iframe with Streamlit's own chrome inside dvdigital.in's
layout, a session that knows nothing about the logged-in student, and a server
holding an open connection per visitor. It is a great tool for a demo and the
wrong shape for a public page on a site that already gets traffic.

## Why plain JavaScript is not enough either

The suggestion was that JS alone might do the job. It cannot, for one reason:
the model call needs an API key, and anything JavaScript can read, a visitor can
read. The key would be in view-source within a day of launch.

So the backend is not there because we like Python. It is there to hold the
secret. Same reason the WordPress plugin proxies the request in PHP instead of
letting the browser call the API directly.

Flask instead of FastAPI is fine if the team prefers it — only `main.py` would
change. FastAPI is kept because multipart uploads and request validation are
already handled.

## Bugs carried out of `app.py`

**MCQ mode never produced options.** The parser reads only lines starting with
`Question:` and `Answer:`. The four `Option A–D` lines are read and discarded,
so an MCQ row ends up as a question plus the bare letter `A` with nothing to map
it to. Fixed by asking the model for JSON and validating it against a schema
instead of parsing prose.

**The generation loop had no exit.** `while len(qa_pairs_generated) < target_count`
only ends when the target is met. If the model returns unparseable text every
time — which happens on a free tier that 503s — it spins forever. In Streamlit
that is one stuck tab. On a shared web server it is a worker pinned until
restart. Now bounded by `attempts=2`, and a short set is returned rather than
an infinite retry.

**`max_tokens=512` truncated the batches.** Two MCQs with four options each do
not fit, so the reply got cut mid-question, failed to parse, and triggered the
retry path. Now 6000.

**Chunks repeated.** `docs[chunk_index % len(docs)]` wraps around, so asking for
20 questions from a 5-chunk PDF re-asks the same chunk and produces the same
questions. Now deduplicated by normalised question text.

**Nothing shuffled the answers.** Language models put the correct option first
far more often than chance. Left alone, a student who always picks A scores well
above 25%. `shuffle_answer()` re-randomises position and recomputes the index.

## What carried over

- The chunk-then-generate pipeline. Reworked as three-region sampling in
  `extractors.condense()` so a long PDF is covered end to end rather than
  truncated at chapter one.
- The focus topic field — now `focus_topic` on the API and a text input in the
  widget.
- Short-answer output alongside MCQ, since the CSV dataset use case is real.
  Set `output_format=short`.
- CSV download. Now built in the browser from the JSON, so no pandas dependency
  and no server round trip.
- Hugging Face and Qwen still work. Set `LLM_PROVIDER=huggingface` in `.env`.
  Groq is the default because it is faster and does not 503 the way the free HF
  inference tier does.

## What to look at

Open `demo/index.html` in a browser. Real CSS and JS, canned quiz data, no
hosting needed. Good enough to show the client before anything is deployed.


## 2026-08-15 parser fix
- Pasted quiz parsing now supports multiple numbered sections that restart at 1, such as 20 Hindi questions followed by English questions 1-20.
