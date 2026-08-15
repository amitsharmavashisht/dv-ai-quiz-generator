from __future__ import annotations

import html
import json
import sys
from pathlib import Path

import streamlit as st

# ------------------------------------------------------------
# Make backend modules importable
# ------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import extractors
import quiz_engine
import providers
from config import get_settings


# ------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------
st.set_page_config(
    page_title="DV Digital AI Quiz Generator",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------
# Styling
# ------------------------------------------------------------
st.markdown(
    """
<style>
    .stApp {
        background:
            radial-gradient(circle at 10% 0%, #eef0ff 0, transparent 30%),
            radial-gradient(circle at 90% 5%, #e6fbff 0, transparent 28%),
            #f6f8fc;
    }

    .hero {
        padding: 42px 36px;
        border-radius: 28px;
        margin-bottom: 24px;
        color: white;
        background:
            radial-gradient(circle at 90% 0%, rgba(89,220,255,.22), transparent 25%),
            linear-gradient(135deg, #11182f, #293d7c 55%, #635bff);
        box-shadow: 0 25px 70px rgba(40,50,110,.18);
    }

    .hero-small {
        color: #cbd4ff;
        font-size: 12px;
        font-weight: 800;
        letter-spacing: .16em;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    .hero h1 {
        margin: 0;
        font-size: clamp(34px, 5vw, 58px);
        line-height: 1;
        letter-spacing: -0.05em;
    }

    .hero p {
        margin: 14px 0 0;
        color: #dce3ff;
        font-size: 16px;
    }

    .feature {
        background: white;
        border: 1px solid #e5e9f1;
        border-radius: 18px;
        padding: 20px;
        height: 100%;
        box-shadow: 0 10px 30px rgba(30,43,70,.05);
    }

    .feature-icon {
        font-size: 25px;
        margin-bottom: 8px;
    }

    .feature-title {
        font-weight: 800;
        color: #172033;
        margin-bottom: 5px;
    }

    .feature-text {
        color: #69758a;
        font-size: 13px;
        line-height: 1.5;
    }

    .status-box {
        padding: 12px 15px;
        border-radius: 12px;
        background: #f5f7fb;
        border: 1px solid #e4e8ef;
        font-size: 13px;
    }

    .success-box {
        padding: 15px 18px;
        border-radius: 14px;
        background: #ecfaf3;
        border: 1px solid #b7e7ce;
        color: #116b49;
    }

    .warning-box {
        padding: 15px 18px;
        border-radius: 14px;
        background: #fff8e8;
        border: 1px solid #f1d99a;
        color: #795b00;
    }

    div[data-testid="stFileUploader"] {
        background: white;
        border-radius: 16px;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 12px;
        font-weight: 700;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def quiz_to_dict(quiz):
    """Convert Pydantic quiz model to a normal dictionary."""
    if hasattr(quiz, "model_dump"):
        return quiz.model_dump()

    if isinstance(quiz, dict):
        return quiz

    raise TypeError("Unsupported quiz result type.")


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def option_letters(count: int):
    return list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")[:count]


def copy_html_button(html_output: str):
    """Render a one-click button that copies the complete generated HTML.

    Uses Streamlit's current st.html API instead of an iframe. This keeps the
    button in the main page so the browser Clipboard API can work on both
    localhost and Streamlit Cloud HTTPS pages.
    """

    html_json = json.dumps(html_output, ensure_ascii=False)

    component_html = f"""
<div class="copy-html-wrap">
    <button id="copy-html-button" type="button" class="copy-html-button">
        📋 Copy HTML Code
    </button>
    <div id="copy-html-status" class="copy-html-status" aria-live="polite"></div>
</div>

<style>
.copy-html-wrap {{
    width: 100%;
    margin: 0;
}}

.copy-html-button {{
    width: 100%;
    min-height: 46px;
    padding: 11px 18px;
    border: 0;
    border-radius: 12px;
    background: linear-gradient(135deg, #635bff, #7a65ef);
    color: #ffffff;
    font: 700 14px/1.2 Inter, ui-sans-serif, system-ui, -apple-system,
          BlinkMacSystemFont, "Segoe UI", sans-serif;
    cursor: pointer;
    box-shadow: 0 8px 20px rgba(99, 91, 255, .18);
    transition: transform .15s ease, box-shadow .15s ease, background .15s ease;
}}

.copy-html-button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 11px 25px rgba(99, 91, 255, .25);
}}

.copy-html-button:active {{
    transform: translateY(0);
}}

.copy-html-button.success {{
    background: linear-gradient(135deg, #15966a, #20b77d);
}}

.copy-html-button.error {{
    background: linear-gradient(135deg, #e05252, #c83d3d);
}}

.copy-html-status {{
    min-height: 18px;
    margin-top: 5px;
    text-align: center;
    font: 600 11px/1.3 Inter, ui-sans-serif, system-ui, sans-serif;
    color: #15966a;
}}
</style>

<script>
(function() {{
    "use strict";

    const htmlOutput = {html_json};
    const button = document.getElementById("copy-html-button");
    const status = document.getElementById("copy-html-status");

    if (!button || !status) return;

    async function copyText(text) {{
        // Modern Clipboard API. Streamlit Cloud is HTTPS, and localhost is
        // also treated as a secure context by modern browsers.
        if (navigator.clipboard && window.isSecureContext) {{
            await navigator.clipboard.writeText(text);
            return;
        }}

        // Fallback for browsers where navigator.clipboard is unavailable.
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        textarea.style.top = "0";
        textarea.style.width = "1px";
        textarea.style.height = "1px";
        textarea.style.opacity = "0";

        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);

        const copied = document.execCommand("copy");
        document.body.removeChild(textarea);

        if (!copied) {{
            throw new Error("The browser rejected the copy operation.");
        }}
    }}

    button.addEventListener("click", async function() {{
        const originalText = "📋 Copy HTML Code";

        button.disabled = true;
        button.textContent = "⏳ Copying...";
        button.classList.remove("success", "error");
        status.textContent = "";

        try {{
            await copyText(htmlOutput);

            button.textContent = "✅ HTML Copied!";
            button.classList.add("success");
            status.textContent = "Complete HTML code copied to your clipboard.";

            window.setTimeout(function() {{
                button.textContent = originalText;
                button.classList.remove("success");
                button.disabled = false;
                status.textContent = "";
            }}, 2200);
        }} catch (error) {{
            console.error("Copy HTML failed:", error);

            button.textContent = "❌ Copy Failed";
            button.classList.add("error");
            status.textContent = "Copy was blocked by the browser. Use the HTML Source box below.";

            window.setTimeout(function() {{
                button.textContent = originalText;
                button.classList.remove("error");
                button.disabled = false;
            }}, 3500);
        }}
    }});
}})();
</script>
"""

    # Streamlit's current st.html API can execute trusted JavaScript when
    # explicitly enabled. Unlike an iframe, this runs in the main page.
    st.html(
        component_html,
        unsafe_allow_javascript=True,
    )


def build_quiz_html(quiz_data: dict) -> str:
    """
    Build a standalone HTML quiz.

    The generated HTML contains the answer_index supplied by the
    deterministic parser / quiz engine. It does not ask an LLM
    to calculate the score.
    """

    title = quiz_data.get("title") or "Converted Quiz"
    difficulty = quiz_data.get("difficulty") or "practice"
    questions = quiz_data.get("questions") or []

    safe_questions = []

    for q in questions:
        options = q.get("options") or []

        safe_questions.append(
            {
                "question": q.get("question", ""),
                "options": options,
                "answer_index": q.get("answer_index", 0),
                "answer": q.get("answer", ""),
                "explanation": q.get("explanation", ""),
            }
        )

    payload = json.dumps(
        {
            "title": title,
            "difficulty": difficulty,
            "questions": safe_questions,
        },
        ensure_ascii=False,
    )

    payload_js = (
        payload
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    return f"""<!DOCTYPE html>
<html lang="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#635bff">
<title>{esc(title)}</title>

<style>
:root {{
    font-family: Inter, ui-sans-serif, system-ui, -apple-system,
                 BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: #172033;
    background: #f5f7fb;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    min-height: 100vh;
    background:
        radial-gradient(circle at 20% 0, #eef0ff 0, transparent 35%),
        radial-gradient(circle at 90% 10%, #e5fbff 0, transparent 28%),
        #f5f7fb;
}}

.qx {{
    max-width: 900px;
    margin: auto;
    padding: 28px 16px 60px;
}}

.hero {{
    position: relative;
    overflow: hidden;
    padding: 38px 32px;
    margin-bottom: 16px;
    border-radius: 26px;
    color: #fff;
    background:
        radial-gradient(circle at 90% 0,
                        rgba(91,220,255,.22),
                        transparent 25%),
        linear-gradient(135deg,#121a36,#293d7c 55%,#635bff);
    box-shadow: 0 24px 65px rgba(44,55,115,.2);
}}

.hero::after {{
    content: "";
    position: absolute;
    width: 250px;
    height: 250px;
    right: -110px;
    top: -140px;
    border-radius: 50%;
    background: rgba(112,228,255,.14);
}}

.eyebrow {{
    position: relative;
    z-index: 1;
    margin: 0 0 9px;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .15em;
    text-transform: uppercase;
    color: #c8d0ff;
}}

.title {{
    position: relative;
    z-index: 1;
    margin: 0;
    font-size: clamp(28px,5vw,46px);
    line-height: 1.08;
    letter-spacing: -.04em;
}}

.meta {{
    position: relative;
    z-index: 1;
    margin: 12px 0 0;
    color: #dbe2ff;
    font-size: 13px;
}}

.progress {{
    height: 8px;
    margin: 0 0 16px;
    border-radius: 99px;
    background: #e7eaf2;
    overflow: hidden;
}}

.progress i {{
    display: block;
    height: 100%;
    background: linear-gradient(90deg,#635bff,#00b8d9);
    border-radius: inherit;
    transition: width .35s;
}}

.card {{
    background: #fff;
    border: 1px solid #e5e9f1;
    border-radius: 22px;
    padding: 25px;
    box-shadow: 0 18px 50px rgba(30,43,70,.07);
}}

.counter {{
    display: inline-flex;
    padding: 6px 10px;
    border-radius: 9px;
    background: #f0efff;
    color: #635bff;
    font: 800 11px ui-monospace, monospace;
}}

.question {{
    margin: 16px 0 22px;
    font-size: clamp(20px,3vw,28px);
    line-height: 1.45;
    letter-spacing: -.02em;
    white-space: pre-wrap;
}}

.options {{
    display: grid;
    gap: 11px;
}}

.opt {{
    display: flex;
    align-items: flex-start;
    gap: 13px;
    padding: 15px;
    border: 1px solid #e1e6ef;
    border-radius: 15px;
    background: #fff;
    cursor: pointer;
    transition: .16s;
}}

.opt:hover {{
    border-color: #aaa5ff;
    background: #faf9ff;
    transform: translateY(-1px);
}}

.opt input {{
    position: absolute;
    opacity: 0;
}}

.badge {{
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 32px;
    height: 32px;
    border-radius: 10px;
    border: 1px solid #d7dce7;
    color: #7b869a;
    font: 800 11px ui-monospace, monospace;
}}

.opt input:checked ~ .badge {{
    background: #635bff;
    border-color: #635bff;
    color: #fff;
}}

.opt.right {{
    border-color: #72c8a6;
    background: #ebfaf3;
}}

.opt.right .badge {{
    background: #15966a;
    border-color: #15966a;
    color: #fff;
}}

.opt.wrong {{
    border-color: #ef9b9b;
    background: #fff0f0;
}}

.opt.wrong .badge {{
    background: #e05252;
    border-color: #e05252;
    color: #fff;
}}

.explain {{
    margin-top: 16px;
    padding: 15px;
    border-left: 4px solid #8b83ff;
    border-radius: 0 12px 12px 0;
    background: #f7f7ff;
    color: #566177;
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
}}

.answer-note {{
    margin-top: 12px;
    padding: 11px 14px;
    border-radius: 10px;
    background: #f5f7fb;
    color: #667187;
    font-size: 12px;
}}

.nav {{
    display: flex;
    gap: 10px;
    margin-top: 23px;
}}

.btn {{
    flex: 1;
    padding: 13px 16px;
    border: 1px solid #d7ddea;
    border-radius: 12px;
    background: #fff;
    color: #172033;
    font: 800 14px inherit;
    cursor: pointer;
}}

.btn:hover:not(:disabled) {{
    border-color: #aaa5ff;
    background: #f8f7ff;
    color: #635bff;
}}

.btn.primary {{
    border: 0;
    background: linear-gradient(135deg,#635bff,#7a65ef);
    color: #fff;
    box-shadow: 0 10px 22px rgba(99,91,255,.2);
}}

.btn:disabled {{
    opacity: .4;
    cursor: not-allowed;
}}

.result {{
    text-align: center;
}}

.score {{
    font: 850 clamp(70px,12vw,105px)/1 ui-monospace, monospace;
    letter-spacing: -.08em;
    margin: 8px 0;
}}

.score span {{
    font-size: .38em;
    color: #7d899f;
}}

.verdict {{
    color: #526078;
    font-size: 15px;
}}

.sheet {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin: 22px 0;
    padding: 18px;
    border: 1px solid #e4e8ef;
    border-radius: 16px;
    background: #f8fafc;
}}

.dot {{
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: 10px;
    background: #fff;
    border: 1px solid #d8deea;
    font: 800 10px ui-monospace, monospace;
    color: #7d899f;
}}

.dot.ok {{
    background: #15966a;
    border-color: #15966a;
    color: #fff;
}}

.dot.no {{
    background: #e05252;
    border-color: #e05252;
    color: #fff;
}}

.footer {{
    margin-top: 14px;
    text-align: center;
    color: #8b95a8;
    font-size: 11px;
}}

@media(max-width:560px) {{
    .qx {{
        padding: 12px 10px 40px;
    }}

    .hero {{
        padding: 27px 21px;
        border-radius: 21px;
    }}

    .card {{
        padding: 18px;
    }}

    .nav {{
        flex-direction: column;
    }}

    .btn {{
        width: 100%;
    }}
}}
</style>
</head>

<body>

<main class="qx" id="qx"></main>

<script>
(function() {{

"use strict";

var Q = {payload_js};

var root = document.getElementById("qx");
var current = 0;
var picked = {{}};
var done = false;

var LETTERS = [
    "A","B","C","D","E","F","G","H"
];

function esc(value) {{
    var d = document.createElement("div");
    d.textContent = value == null ? "" : String(value);
    return d.innerHTML;
}}

function draw() {{

    if (done) {{
        result();
        return;
    }}

    var q = Q.questions[current];
    var total = Q.questions.length;

    if (!q) {{
        result();
        return;
    }}

    var pct = Math.round(((current + 1) / total) * 100);

    var h = "";

    h += '<section class="hero">';
    h += '<p class="eyebrow">Interactive practice</p>';
    h += '<h1 class="title">' + esc(Q.title || "Quiz") + '</h1>';
    h += '<p class="meta">';
    h += 'Question ' + (current + 1) + ' of ' + total;
    h += ' · ' + esc(Q.difficulty || "practice");
    h += '</p>';
    h += '</section>';

    h += '<div class="progress">';
    h += '<i style="width:' + pct + '%"></i>';
    h += '</div>';

    h += '<section class="card">';

    h += '<span class="counter">';
    h += 'QUESTION ';
    h += String(current + 1).padStart(2, "0");
    h += ' / ';
    h += String(total).padStart(2, "0");
    h += '</span>';

    h += '<h2 class="question">';
    h += esc(q.question);
    h += '</h2>';

    h += '<div class="options">';

    var options = q.options || [];

    options.forEach(function(option, index) {{

        var selected = picked[current] === index;
        var cls = "opt";

        if (
            picked[current] !== undefined &&
            index === q.answer_index
        ) {{
            cls += " right";
        }}

        if (
            picked[current] !== undefined &&
            selected &&
            index !== q.answer_index
        ) {{
            cls += " wrong";
        }}

        h += '<label class="' + cls + '">';

        h += '<input type="radio" name="q" ';
        h += selected ? 'checked ' : '';
        h += 'data-index="' + index + '">';

        h += '<span class="badge">';
        h += esc(LETTERS[index] || String(index + 1));
        h += '</span>';

        h += '<span>';
        h += esc(option);
        h += '</span>';

        h += '</label>';
    }});

    h += '</div>';

    if (
        picked[current] !== undefined &&
        q.answer &&
        q.answer_index !== undefined
    ) {{
        h += '<div class="answer-note">';
        h += 'Correct answer: <strong>';
        h += esc(LETTERS[q.answer_index] || "");
        h += '. ';
        h += esc(q.answer);
        h += '</strong>';
        h += '</div>';
    }}

    if (
        picked[current] !== undefined &&
        q.explanation
    ) {{
        h += '<div class="explain">';
        h += esc(q.explanation);
        h += '</div>';
    }}

    h += '<div class="nav">';

    h += '<button class="btn" id="prev"';
    if (current === 0) {{
        h += ' disabled';
    }}
    h += '>← Previous</button>';

    h += '<button class="btn primary" id="next">';
    h += current === total - 1
        ? "Finish quiz"
        : "Next question →";
    h += '</button>';

    h += '</div>';

    h += '</section>';

    h += '<p class="footer">';
    h += 'Generated with DV Digital AI Quiz Generator';
    h += '</p>';

    root.innerHTML = h;

    root.querySelectorAll(".opt input").forEach(function(input) {{

        input.addEventListener("change", function() {{
            picked[current] = Number(this.dataset.index);
            draw();
        }});

    }});

    document.getElementById("prev").onclick = function() {{

        if (current > 0) {{
            current--;
            draw();
        }}

    }};

    document.getElementById("next").onclick = function() {{

        if (current < total - 1) {{
            current++;
            draw();
        }} else {{
            done = true;
            result();
        }}

    }};
}}

function result() {{

    var total = Q.questions.length;
    var score = 0;

    Q.questions.forEach(function(q, index) {{

        if (picked[index] === q.answer_index) {{
            score++;
        }}

    }});

    var pct = total
        ? Math.round((score / total) * 100)
        : 0;

    var verdict;

    if (pct >= 85) {{
        verdict = "Excellent work — you have a strong grasp of this material.";
    }} else if (pct >= 60) {{
        verdict = "Good progress — review the questions you missed.";
    }} else {{
        verdict = "Keep practicing and try the quiz again.";
    }}

    var h = "";

    h += '<section class="hero">';
    h += '<p class="eyebrow">Quiz complete</p>';
    h += '<h1 class="title">Your results</h1>';
    h += '<p class="meta">';
    h += esc(Q.title || "Quiz") + ' · ' + pct + '% score';
    h += '</p>';
    h += '</section>';

    h += '<section class="card result">';

    h += '<p class="score">';
    h += score;
    h += '<span>/' + total + '</span>';
    h += '</p>';

    h += '<p class="verdict">';
    h += esc(verdict);
    h += '</p>';

    h += '<div class="sheet">';

    Q.questions.forEach(function(q, index) {{

        h += '<span class="dot ';
        h += picked[index] === q.answer_index ? "ok" : "no";
        h += '">';
        h += index + 1;
        h += '</span>';

    }});

    h += '</div>';

    h += '<div class="nav">';

    h += '<button class="btn" id="review">';
    h += 'Review answers';
    h += '</button>';

    h += '<button class="btn primary" id="again">';
    h += 'Try again';
    h += '</button>';

    h += '</div>';

    h += '</section>';

    h += '<p class="footer">';
    h += 'Powered by DV Digital';
    h += '</p>';

    root.innerHTML = h;

    document.getElementById("review").onclick = function() {{
        current = 0;
        done = false;
        draw();
    }};

    document.getElementById("again").onclick = function() {{
        current = 0;
        picked = {{}};
        done = false;
        draw();
    }};
}}

draw();

}})();
</script>

</body>
</html>
"""


# ------------------------------------------------------------
# Generate quiz
# ------------------------------------------------------------
def generate_quiz(
    source_type: str,
    text: str,
    uploaded_file,
    url: str,
    num_questions: int,
    difficulty: str,
    language: str,
    output_format: str,
    focus_topic: str,
):
    """Use the existing backend engine."""

    if source_type == "text":
        raw = text or ""

    elif source_type == "file":
        if uploaded_file is None:
            raise ValueError("Please upload a file.")

        data = uploaded_file.getvalue()

        if len(data) > get_settings().max_upload_bytes:
            raise ValueError(
                f"File is larger than "
                f"{get_settings().MAX_UPLOAD_MB} MB."
            )

        raw = extractors.from_file(
            uploaded_file.name,
            data,
        )

    elif source_type == "url":
        if not url.strip():
            raise ValueError("Please enter a URL.")

        raw = extractors.from_url(url.strip())

    elif source_type == "youtube":
        if not url.strip():
            raise ValueError("Please enter a YouTube URL.")

        raw = extractors.from_youtube(url.strip())

    else:
        raise ValueError("Unknown source type.")

    source = extractors.condense(raw)

    settings = get_settings()

    if len(source) < settings.MIN_SOURCE_CHARS:
        raise ValueError(
            f"Please provide at least "
            f"{settings.MIN_SOURCE_CHARS} characters of useful content."
        )

    return quiz_engine.generate(
        source,
        num_questions,
        difficulty,
        language,
        output_format,
        focus_topic,
    )


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------
st.markdown(
    """
<div class="hero">
    <div class="hero-small">DV Digital AI</div>
    <h1>Quiz Generator</h1>
    <p>
        Convert Hindi or English study material into a beautiful,
        interactive HTML quiz — with existing answers preserved.
    </p>
</div>
""",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Feature cards
# ------------------------------------------------------------
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown(
        """
        <div class="feature">
            <div class="feature-icon">🎯</div>
            <div class="feature-title">Correct Answers</div>
            <div class="feature-text">
                Existing Answer: A/B/C/D, Hindi उत्तर,
                and numeric 1/2/3/4 answers are preserved.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        """
        <div class="feature">
            <div class="feature-icon">🌐</div>
            <div class="feature-title">Hindi + English</div>
            <div class="feature-text">
                Supports Hindi, English, and mixed-language
                quiz content using UTF-8.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        """
        <div class="feature">
            <div class="feature-icon">✨</div>
            <div class="feature-title">Beautiful HTML</div>
            <div class="feature-text">
                Generates a standalone quiz with progress,
                scoring, answer review, and retry.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.write("")


# ------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------
with st.sidebar:

    st.header("⚙️ Quiz Settings")

    num_questions = st.number_input(
        "Number of questions",
        min_value=3,
        max_value=get_settings().MAX_QUESTIONS,
        value=20,
        step=1,
    )

    difficulty = st.selectbox(
        "Difficulty",
        ["easy", "medium", "hard"],
        index=1,
    )

    language = st.selectbox(
        "Language",
        [
            "auto",
            "English",
            "Hindi",
            "Hindi + English",
        ],
    )

    output_format = st.selectbox(
        "Output format",
        ["mcq", "short"],
        index=0,
    )

    focus_topic = st.text_input(
        "Focus topic (optional)",
        placeholder="e.g. Operating Systems",
    )

    st.divider()

    settings = get_settings()

    st.caption(
        f"Primary provider: **{settings.LLM_PROVIDER.upper()}**"
    )

    st.caption(
        f"Model: `{settings.model_name}`"
    )

    st.caption(
        "Existing-answer MCQs are parsed without requiring an LLM."
    )


# ------------------------------------------------------------
# Source selection
# ------------------------------------------------------------
st.subheader("📥 Quiz Source")

source_type = st.radio(
    "Choose your input",
    [
        "Paste text",
        "Upload file",
        "Website URL",
        "YouTube",
    ],
    horizontal=True,
)


text = ""
uploaded_file = None
url = ""


if source_type == "Paste text":

    text = st.text_area(
        "Paste your questions or study material",
        height=360,
        placeholder="""Example:

Q1. Which data structure is used for BFS?

A. Stack
B. Queue
C. Linked List
D. Tree

Answer: B

Q2. 'दशानन' में कौन-सा समास है?

A. द्विगु
B. कर्मधारय
C. बहुव्रीहि
D. द्वंद्व

✅ उत्तर: C. बहुव्रीहि
""",
    )

elif source_type == "Upload file":

    uploaded_file = st.file_uploader(
        "Upload your study material",
        type=[
            "pdf",
            "docx",
            "pptx",
            "txt",
            "md",
            "csv",
            "tsv",
            "rtf",
            "log",
        ],
    )

elif source_type == "Website URL":

    url = st.text_input(
        "Website URL",
        placeholder="https://example.com/article",
    )

else:

    url = st.text_input(
        "YouTube URL",
        placeholder="https://www.youtube.com/watch?v=...",
    )


# ------------------------------------------------------------
# Generate
# ------------------------------------------------------------
st.write("")

generate_clicked = st.button(
    "🚀 Generate Quiz",
    type="primary",
    use_container_width=True,
)


if generate_clicked:

    if source_type == "Paste text" and not text.strip():
        st.error("Please paste your quiz or study material.")

    elif source_type == "Upload file" and uploaded_file is None:
        st.error("Please upload a file.")

    elif source_type in ("Website URL", "YouTube") and not url.strip():
        st.error("Please enter a URL.")

    else:

        source_map = {
            "Paste text": "text",
            "Upload file": "file",
            "Website URL": "url",
            "YouTube": "youtube",
        }

        actual_source_type = source_map[source_type]

        try:

            with st.spinner(
                "Converting your content into a quiz..."
            ):

                quiz = generate_quiz(
                    source_type=actual_source_type,
                    text=text,
                    uploaded_file=uploaded_file,
                    url=url,
                    num_questions=int(num_questions),
                    difficulty=difficulty,
                    language=language,
                    output_format=output_format,
                    focus_topic=focus_topic,
                )

            quiz_data = quiz_to_dict(quiz)

            st.session_state["quiz_data"] = quiz_data

            questions = quiz_data.get("questions", [])

            st.success(
                f"✅ Quiz generated successfully — "
                f"{len(questions)} questions."
            )

        except Exception as exc:
            st.error(str(exc))


# ------------------------------------------------------------
# Display generated quiz
# ------------------------------------------------------------
quiz_data = st.session_state.get("quiz_data")


if quiz_data:

    questions = quiz_data.get("questions", [])

    st.divider()

    st.subheader("✅ Quiz Ready")

    m1, m2, m3 = st.columns(3)

    with m1:
        st.metric(
            "Questions",
            len(questions),
        )

    with m2:
        st.metric(
            "Language",
            quiz_data.get("language", language),
        )

    with m3:
        st.metric(
            "Difficulty",
            quiz_data.get("difficulty", difficulty),
        )

    html_output = build_quiz_html(quiz_data)

    action_col1, action_col2 = st.columns(2)

    with action_col1:
        st.download_button(
            "⬇️ Download Interactive HTML",
            data=html_output.encode("utf-8"),
            file_name="converted-quiz.html",
            mime="text/html",
            use_container_width=True,
        )

    with action_col2:
        copy_html_button(html_output)

    with st.expander("📋 View HTML Source", expanded=False):
        st.markdown(
            f"**Generated HTML:** `{len(html_output):,}` characters · "
            f"Scroll inside the code viewer to inspect the complete file."
        )
        st.code(
            html_output,
            language="html",
            line_numbers=True,
            wrap_lines=False,
            height=650,
        )

    with st.expander("🔍 Preview generated quiz data"):

        st.json(quiz_data)

    st.info(
        "Open the downloaded `converted-quiz.html` directly in Chrome, "
        "Edge, or Firefox. It does not require a server."
    )