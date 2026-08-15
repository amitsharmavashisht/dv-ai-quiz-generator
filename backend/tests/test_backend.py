"""End-to-end checks that run without a live model or the internet.

    pytest -q
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("ENFORCE_ORIGIN", "false")

import cache            # noqa: E402
import extractors       # noqa: E402
import providers        # noqa: E402
import quiz_engine      # noqa: E402
from config import get_settings  # noqa: E402

settings = get_settings()

LOREM = ("The transformer architecture relies on self-attention. " * 12 +
         "It was introduced in 2017 and replaced recurrence entirely. " * 12)


# ---------------------------------------------------------------------------
# URL handling
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected_host", [
    ("example.com/page", "example.com"),
    ("https://example.com/page", "example.com"),
    ("  http://example.com  ", "example.com"),
    ("https://dvdigital.in/", "dvdigital.in"),
])
def test_normalise_url_adds_scheme(raw, expected_host):
    assert expected_host in extractors.normalise_url(raw)


@pytest.mark.parametrize("bad", ["", "   ", "ftp://example.com", "javascript:alert(1)"])
def test_normalise_url_rejects_junk(bad):
    with pytest.raises(extractors.ExtractionError):
        extractors.normalise_url(bad)


# ---------------------------------------------------------------------------
# YouTube id parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,vid", [
    ("https://youtu.be/IKh5vGZx8L0", "IKh5vGZx8L0"),
    ("https://www.youtube.com/watch?v=4YJmfgL8y_k", "4YJmfgL8y_k"),
    ("https://www.youtube.com/shorts/xx9XICCJsls", "xx9XICCJsls"),
    ("https://youtu.be/XSOmzWLwY-k?si=yFath_WCzECgE5MV", "XSOmzWLwY-k"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
])
def test_youtube_ids(url, vid):
    assert extractors.youtube_id(url) == vid


@pytest.mark.parametrize("bad", ["https://vimeo.com/12345", "not a link", ""])
def test_youtube_rejects_non_youtube(bad):
    with pytest.raises(extractors.ExtractionError):
        extractors.youtube_id(bad)


# ---------------------------------------------------------------------------
# File sniffing
# ---------------------------------------------------------------------------
def _fake_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def test_sniff_prefers_magic_bytes_over_extension():
    assert extractors.sniff_kind("notes.txt", b"%PDF-1.7 junk") == "pdf"
    assert extractors.sniff_kind("mystery.bin", _fake_docx()) == "docx"
    assert extractors.sniff_kind("notes.md", b"# heading") == "text"
    assert extractors.sniff_kind("photo.jpg", b"\xff\xd8\xff\xe0") == ""


def test_plaintext_survives_odd_encodings():
    assert "café" in extractors.from_plaintext("café".encode("utf-8"))
    assert extractors.from_plaintext("café".encode("cp1252"))


def test_empty_file_is_rejected():
    with pytest.raises(extractors.ExtractionError):
        extractors.from_file("a.txt", b"")


def test_unknown_binary_is_rejected():
    with pytest.raises(extractors.ExtractionError):
        extractors.from_file("photo.jpg", bytes(range(256)) * 8)


# ---------------------------------------------------------------------------
# HTML fallback
# ---------------------------------------------------------------------------
def test_html_fallback_strips_chrome_and_keeps_prose():
    html = """<html><head><style>.x{color:red}</style></head><body>
      <nav>Home About Contact</nav>
      <script>var tracking = 1;</script>
      <article><h1>Fundamental Rights</h1>
      <p>There are six fundamental rights in the Constitution of India.</p>
      <p>Article 32 is called the heart and soul of the Constitution.</p></article>
      <footer>Copyright 2026</footer></body></html>"""
    text = extractors._html_to_text(html)
    assert "six fundamental rights" in text
    assert "heart and soul" in text
    assert "var tracking" not in text
    assert "color:red" not in text


# ---------------------------------------------------------------------------
# Condense and section splitting
# ---------------------------------------------------------------------------
def test_condense_samples_three_regions():
    text = "A" * 900 + "B" * 900 + "C" * 900
    out = extractors.condense(text, limit=300)
    assert "A" in out and "B" in out and "C" in out
    assert len(out) < len(text)


def test_condense_leaves_short_text_alone():
    assert extractors.condense("hello world", limit=1000) == "hello world"


def test_split_sections_covers_whole_document():
    text = "\n\n".join(f"Paragraph number {i} with content." for i in range(30))
    parts = extractors.split_sections(text, 4)
    assert len(parts) == 4
    assert "number 0" in parts[0]
    assert "number 29" in parts[-1]


def test_split_sections_handles_tiny_input():
    assert extractors.split_sections("short", 5) == ["short"]


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------
def test_parse_handles_fences_and_prose_wrappers():
    assert quiz_engine.parse_payload('```json\n{"questions": []}\n```') == {"questions": []}
    assert quiz_engine.parse_payload('Sure!\n{"questions": []}\nHope that helps')["questions"] == []


def test_parse_accepts_bare_list_and_alternate_keys():
    assert quiz_engine.parse_payload('[{"question": "x"}]')["questions"][0]["question"] == "x"
    assert quiz_engine.parse_payload('{"mcqs": [{"question": "y"}]}')["questions"][0]["question"] == "y"


def test_parse_rejects_garbage():
    for junk in ["", "not json at all", "<html>nope</html>"]:
        with pytest.raises(quiz_engine.GenerationError):
            quiz_engine.parse_payload(junk)


# ---------------------------------------------------------------------------
# Validation and answer coercion
# ---------------------------------------------------------------------------
GOOD = {
    "question": "Which article is the heart and soul of the Constitution?",
    "options": ["Article 32", "Article 21", "Article 19", "Article 14"],
    "answer_index": 0,
    "explanation": "Ambedkar described Article 32 this way.",
}


def test_valid_mcq_passes_and_answer_survives_shuffle():
    q = quiz_engine.validate_item(dict(GOOD), "mcq")
    assert q is not None
    assert q.options[q.answer_index] == "Article 32"


@pytest.mark.parametrize("field,value", [
    ("options", ["only", "three", "options"]),
    ("options", ["same", "same", "b", "c"]),
    ("options", ["a", "", "b", "c"]),
    ("answer_index", 9),
    ("answer_index", None),
])
def test_broken_mcqs_are_dropped(field, value):
    item = dict(GOOD)
    item[field] = value
    assert quiz_engine.validate_item(item, "mcq") is None


@pytest.mark.parametrize("given,expected", [
    ("B", 1), ("c", 2), ("2", 1), ("Article 19", 2),
])
def test_answer_given_as_letter_number_or_text(given, expected):
    item = {"question": GOOD["question"], "options": list(GOOD["options"]),
            "answer": given}
    q = quiz_engine.validate_item(item, "mcq")
    assert q is not None
    assert q.options[q.answer_index] == GOOD["options"][expected]


def test_short_answer_format():
    q = quiz_engine.validate_item(
        {"question": "What does Article 32 provide?", "answer": "A remedy."}, "short")
    assert q is not None and q.answer == "A remedy."
    assert quiz_engine.validate_item({"question": "No answer here?"}, "short") is None


def test_non_dict_items_are_ignored():
    assert quiz_engine.validate_item("just a string", "mcq") is None
    assert quiz_engine.validate_item(None, "mcq") is None


# ---------------------------------------------------------------------------
# Generation, with a stubbed provider
# ---------------------------------------------------------------------------
def _reply(n, offset=0):
    return json.dumps({
        "title": "Fundamental Rights",
        "questions": [{
            "question": f"Question number {offset + i} about the Constitution?",
            "options": [f"Right {offset+i}", "Wrong one", "Wrong two", "Wrong three"],
            "answer_index": 0,
            "explanation": "Stated in the source.",
        } for i in range(n)],
    })


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_generate_batches_and_deduplicates(monkeypatch):
    calls = {"n": 0}

    def fake(messages, temperature=0.4, max_tokens=4096):
        calls["n"] += 1
        return _reply(8, offset=calls["n"] * 100)

    monkeypatch.setattr(providers, "chat", fake)
    quiz = quiz_engine.generate(LOREM, num_questions=16, use_cache=False)
    assert len(quiz.questions) == 16
    assert calls["n"] >= 2, "16 questions should take more than one batch"
    assert len({q.question for q in quiz.questions}) == 16


def test_identical_questions_across_batches_are_deduped(monkeypatch):
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: _reply(8))       # same 8 every time
    quiz = quiz_engine.generate(LOREM, num_questions=16, use_cache=False)
    assert len(quiz.questions) == 8


def test_partial_batch_failure_still_returns_questions(monkeypatch):
    calls = {"n": 0}

    def flaky(messages, temperature=0.4, max_tokens=4096):
        calls["n"] += 1
        if calls["n"] == 1:
            raise providers.ProviderError("upstream hiccup")
        return _reply(8, offset=calls["n"] * 100)

    monkeypatch.setattr(providers, "chat", flaky)
    quiz = quiz_engine.generate(LOREM, num_questions=8, use_cache=False)
    assert len(quiz.questions) >= 1


def test_total_failure_raises_with_detail(monkeypatch):
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(
                            providers.ProviderError("model exploded")))
    with pytest.raises(quiz_engine.GenerationError) as err:
        quiz_engine.generate(LOREM, num_questions=5, use_cache=False)
    assert "model exploded" in str(err.value)


def test_unavailable_provider_propagates(monkeypatch):
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(
                            providers.ProviderUnavailable("ollama is down")))
    with pytest.raises(providers.ProviderUnavailable):
        quiz_engine.generate(LOREM, num_questions=5, use_cache=False)


def test_garbage_questions_are_filtered_not_fatal(monkeypatch):
    payload = json.dumps({"title": "Mixed", "questions": [
        dict(GOOD),
        {"question": "bad", "options": ["a", "a", "b", "c"], "answer_index": 0},
        {"nonsense": True},
        "a string",
        {"question": "Second good question about rights?",
         "options": ["w", "x", "y", "z"], "answer_index": 2},
    ]})
    monkeypatch.setattr(providers, "chat", lambda *a, **k: payload)
    quiz = quiz_engine.generate(LOREM, num_questions=5, use_cache=False)
    assert len(quiz.questions) == 2


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def test_second_identical_request_is_served_from_cache(monkeypatch):
    calls = {"n": 0}

    def counted(messages, temperature=0.4, max_tokens=4096):
        calls["n"] += 1
        return _reply(5)

    monkeypatch.setattr(providers, "chat", counted)
    first = quiz_engine.generate(LOREM, num_questions=5)
    before = calls["n"]
    second = quiz_engine.generate(LOREM, num_questions=5)
    assert calls["n"] == before, "cached call should not hit the provider"
    assert [q.question for q in first.questions] == [q.question for q in second.questions]
    assert cache.stats()["hits"] >= 1


def test_cache_key_respects_settings(monkeypatch):
    monkeypatch.setattr(providers, "chat", lambda *a, **k: _reply(5))
    quiz_engine.generate(LOREM, num_questions=5, difficulty="easy")
    quiz_engine.generate(LOREM, num_questions=5, difficulty="hard")
    assert cache.stats()["entries"] == 2


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(providers, "chat", lambda *a, **k: _reply(8))
    with TestClient(main.app) as c:
        yield c


def test_home_serves_the_widget(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "dvq-root" in r.text


def test_health_reports_provider_and_cache(client):
    r = client.get("/health")
    body = r.json()
    assert body["llm"]["provider"] == "ollama"
    assert "cache" in body and "limits" in body
    assert r.status_code in (200, 503)


def test_text_source_returns_a_paper(client):
    r = client.post("/api/v1/quiz", data={
        "source_type": "text", "text": LOREM, "num_questions": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["questions"]) == 5
    assert all(len(q["options"]) == 4 for q in body["questions"])
    assert "X-Request-ID" in r.headers


def test_short_source_is_rejected_kindly(client):
    r = client.post("/api/v1/quiz", data={"source_type": "text", "text": "hi"})
    assert r.status_code == 422
    assert "at least" in r.json()["error"]


def test_unknown_source_type(client):
    r = client.post("/api/v1/quiz", data={"source_type": "telepathy", "text": LOREM})
    assert r.status_code == 400


def test_empty_file_field_does_not_crash(client):
    r = client.post("/api/v1/quiz",
                    data={"source_type": "text", "text": LOREM, "file": ""})
    assert r.status_code == 200


def test_file_upload_roundtrip(client):
    r = client.post("/api/v1/quiz",
                    data={"source_type": "file", "num_questions": 5},
                    files={"file": ("notes.txt", LOREM.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    assert len(r.json()["questions"]) == 5


def test_oversized_upload_rejected(client):
    big = b"x" * (settings.max_upload_bytes + 1024)
    r = client.post("/api/v1/quiz",
                    data={"source_type": "file"},
                    files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 422
    assert "limit" in r.json()["error"].lower()


def test_unsupported_file_type_rejected(client):
    r = client.post("/api/v1/quiz",
                    data={"source_type": "file"},
                    files={"file": ("cat.jpg", bytes(range(256)) * 40, "image/jpeg")})
    assert r.status_code == 422


def test_bad_url_is_a_422_not_a_500(client):
    r = client.post("/api/v1/quiz",
                    data={"source_type": "url", "url": "notaurl"})
    assert r.status_code == 422


def test_non_youtube_link_rejected(client):
    r = client.post("/api/v1/quiz",
                    data={"source_type": "youtube", "url": "https://vimeo.com/1"})
    assert r.status_code == 422


def test_question_count_is_clamped(client):
    r = client.post("/api/v1/quiz", data={
        "source_type": "text", "text": LOREM, "num_questions": 9999})
    assert r.status_code == 200
    assert len(r.json()["questions"]) <= settings.MAX_QUESTIONS


def test_provider_down_returns_503(client, monkeypatch):
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(
                            providers.ProviderUnavailable("Cannot reach Ollama")))
    r = client.post("/api/v1/quiz", data={
        "source_type": "text", "text": LOREM, "num_questions": 5})
    assert r.status_code == 503
    assert "Ollama" in r.json()["error"]

# ---------------------------------------------------------------------------
# Deterministic pasted-paper converter: Hindi/English, A-D/1-4, explanations
# ---------------------------------------------------------------------------
def test_pasted_mcq_supports_hindi_english_numeric_answers_and_explanations():
    source = """
Q1. 'दशानन' में कौन-सा समास है?
A. द्विगु
B. कर्मधारय
C. बहुव्रीहि
D. द्वंद्व
उत्तर: C. बहुव्रीहि
विग्रह: दस आनन हैं जिसके।

Q2. Which protocol is connection-oriented?
1. UDP
2. IP
3. TCP
4. ICMP
Answer: 3

Q3. 'गृहप्रवेश' में कौन-सा समास है?
A. द्वितीया तत्पुरुष
B. तृतीया तत्पुरुष
C. षष्ठी तत्पुरुष
D. सप्तमी तत्पुरुष
सही उत्तर: D. सप्तमी तत्पुरुष
समास: सप्तमी तत्पुरुष
विग्रह: गृह में प्रवेश।

Q4. Which memory is volatile?
A) ROM
B) SSD
C) RAM
D) Hard Disk
Answer: C
Explanation: RAM is volatile memory.
"""
    quiz = quiz_engine.parse_pasted_mcq(source)
    assert quiz is not None
    assert len(quiz.questions) == 4
    assert [q.answer_index for q in quiz.questions] == [2, 2, 3, 2]
    assert quiz.questions[0].answer == "बहुव्रीहि"
    assert "विग्रह: दस आनन हैं जिसके।" in quiz.questions[0].explanation
    assert "समास: सप्तमी तत्पुरुष" in quiz.questions[2].explanation
    assert "Explanation: RAM is volatile memory." in quiz.questions[3].explanation


def test_pasted_mcq_does_not_guess_missing_answers():
    source = """
Q1. Which data structure is used for BFS?
A. Stack
B. Queue
C. Tree
D. Graph

Q2. Which protocol uses port 80?
A. FTP
B. SMTP
C. HTTP
D. SSH

Q3. Which memory is volatile?
A. ROM
B. SSD
C. RAM
D. HDD
"""
    assert quiz_engine.parse_pasted_mcq(source) is None
