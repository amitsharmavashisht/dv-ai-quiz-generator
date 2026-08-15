"""Generate a validated question set from source text.

Questions are requested in batches, each drawn from a different part of the
source. That keeps every reply inside the token budget — which is what makes
a local 8B model workable — and spreads questions across the whole document
instead of clustering them in chapter one.
"""
from __future__ import annotations

import json
import logging
import random
import re

from pydantic import BaseModel, Field, field_validator

import cache
import extractors
import providers
from config import get_settings

log = logging.getLogger("dvq.engine")
settings = get_settings()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class Question(BaseModel):
    question: str = Field(min_length=8)
    options: list[str] = Field(default_factory=list)
    answer_index: int | None = None
    answer: str = ""
    explanation: str = ""

    @field_validator("options")
    @classmethod
    def options_distinct(cls, v: list[str]) -> list[str]:
        if not v:
            return v
        cleaned = [str(o).strip() for o in v]
        if len(cleaned) != 4 or any(not o for o in cleaned):
            raise ValueError("need exactly four non-empty options")
        if len({o.lower() for o in cleaned}) < 4:
            raise ValueError("duplicate options")
        return cleaned


class Quiz(BaseModel):
    title: str
    difficulty: str
    output_format: str
    questions: list[Question]


class GenerationError(Exception):
    """The model did not return a usable question set."""


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
BASE_RULES = """You set questions for Indian university and competitive exams \
(HPU, HPTU, IGNOU, ITI, state and central government papers).

Rules you never break:
1. Every question is answerable from the SOURCE alone. No outside facts.
2. Do not number questions. Do not prefix options with A/B/C/D.
3. Vary what you test: definitions, cause and effect, application, comparison,
   and any figures or dates the source contains.
4. If the source is too thin for the number asked, return fewer good questions
   rather than padding with weak ones."""

MCQ_SHAPE = """5. Exactly four options. Exactly one correct.
6. Distractors are plausible and similar in length to the answer. Never use
   "All of the above", "None of the above", or joke options.
7. The explanation is one or two sentences pointing at what settles it.

Reply with one JSON object and nothing else:
{"title": string, "questions": [{"question": string, "options": [string, string, string, string],
"answer_index": 0, "explanation": string}]}"""

SHORT_SHAPE = """5. The answer is one to three sentences, complete on its own.

Reply with one JSON object and nothing else:
{"title": string, "questions": [{"question": string, "answer": string}]}"""

DIFFICULTY_HINT = {
    "easy": "Recall level. Test facts stated plainly in the source.",
    "medium": "Understanding level. Test relationships, reasons, short application.",
    "hard": "Application and analysis level. Multi-step reasoning, close "
            "distractors, numerical or comparative items where the source allows.",
}


def system_prompt(output_format: str) -> str:
    return BASE_RULES + "\n" + (SHORT_SHAPE if output_format == "short" else MCQ_SHAPE)


def user_prompt(source: str, n: int, difficulty: str, language: str,
                focus_topic: str, avoid: list[str]) -> str:
    lang = ("Write in the same language as the source."
            if language.lower() in ("auto", "")
            else f"Write everything in {language}.")
    focus = (f"Only write questions about: {focus_topic}. Ignore parts of the "
             f"source that do not relate to it.\n" if focus_topic.strip() else "")
    dodge = ""
    if avoid:
        listed = "\n".join(f"- {q}" for q in avoid[-12:])
        dodge = f"Do not repeat or rephrase any of these already-asked questions:\n{listed}\n"

    return (
        f"Write {n} questions as JSON.\n"
        f"Difficulty: {difficulty}. {DIFFICULTY_HINT.get(difficulty, '')}\n"
        f"Language: {lang}\n"
        f"{focus}{dodge}"
        f"Give the set a short title naming the topic.\n\n"
        f'SOURCE:\n"""\n{source}\n"""'
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
FENCE = re.compile(r"```(?:json)?|```", re.MULTILINE)


def parse_payload(raw: str) -> dict:
    cleaned = FENCE.sub("", raw or "").strip()
    if not cleaned:
        raise GenerationError("The model returned an empty reply.")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise GenerationError("The model did not return JSON.")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise GenerationError("The model returned malformed JSON.") from exc

    if isinstance(data, list):                     # some models skip the wrapper
        data = {"questions": data}
    if not isinstance(data, dict):
        raise GenerationError("The model returned JSON of an unexpected shape.")

    # small models sometimes use a different key for the list
    if "questions" not in data:
        for alt in ("quiz", "items", "mcqs", "data", "result"):
            if isinstance(data.get(alt), list):
                data["questions"] = data[alt]
                break
    return data


def shuffle_answer(q: Question) -> Question:
    """Models put the correct option first far more often than chance."""
    if not q.options or q.answer_index is None:
        return q
    correct = q.options[q.answer_index]
    opts = q.options[:]
    random.shuffle(opts)
    return q.model_copy(update={"options": opts, "answer_index": opts.index(correct)})


def norm_key(text: str) -> str:
    return re.sub(r"\W+", "", (text or "").lower())[:90]


def coerce_answer_index(item: dict) -> dict:
    """Accept answer given as a letter, a number, or the option text."""
    if item.get("answer_index") is not None:
        return item

    options = item.get("options") or []
    raw = item.get("answer") or item.get("correct") or item.get("correct_answer")
    if raw is None or not options:
        return item

    text = str(raw).strip()
    if len(text) == 1 and text.upper() in "ABCD":
        item["answer_index"] = ord(text.upper()) - 65
        item["answer"] = ""
        return item
    if text.isdigit():
        n = int(text)
        item["answer_index"] = n - 1 if 1 <= n <= len(options) else n
        item["answer"] = ""
        return item
    for i, opt in enumerate(options):
        if str(opt).strip().lower() == text.lower():
            item["answer_index"] = i
            item["answer"] = ""
            return item
    return item


def validate_item(item, output_format: str) -> Question | None:
    if not isinstance(item, dict):
        return None
    item = dict(item)

    if output_format == "short":
        try:
            q = Question(question=str(item.get("question", "")),
                         answer=str(item.get("answer", "")))
        except Exception:  # noqa: BLE001
            return None
        return q if q.answer.strip() else None

    item = coerce_answer_index(item)
    try:
        q = Question(**item)
    except Exception:  # noqa: BLE001
        return None
    if len(q.options) != 4 or q.answer_index is None or not 0 <= q.answer_index <= 3:
        return None
    return shuffle_answer(q)



# ---------------------------------------------------------------------------
# Deterministic pasted-quiz converter
# ---------------------------------------------------------------------------
# When the user pastes an existing MCQ paper containing explicit Answer/उत्तर
# lines, NEVER ask the LLM to guess the answer. Parse and preserve the supplied
# answer. This is the safest path for exam papers in English, Hindi, or mixed
# Unicode text. The HTML renderer receives the verified answer_index directly.
QUESTION_START = re.compile(r"^\s*(?:(?:Q|Que|Ques|Question|प्रश्न)\s*)?(\d{1,3})\s*[.)\-:]\s*(.+?)\s*$", re.IGNORECASE)
OPTION_LINE = re.compile(r"^\s*(?:([A-Da-d])[.)]\s*(.+?)|([1-4])[.)]\s*(.+?))\s*$")
ANSWER_LINE = re.compile(
    r"^\s*(?:[✅✔☑]\s*)?(?:answer|correct\s*answer|ans|उत्तर|सही\s*उत्तर)\s*[:：\-–]?\s*"
    r"(?:([A-Da-d])\s*[.)\-:]?\s*|([1-4])\s*[.)\-:]?\s*)?(.*)\s*$",
    re.IGNORECASE,
)
EXTRA_LINE = re.compile(r"^\s*(?:विग्रह|समास|संधि|व्याख्या|explanation|विवरण)\s*[:：\-–]", re.IGNORECASE)


def _answer_index_from_text(raw: str, options: list[str], letter: str | None, number: str | None = None) -> int | None:
    if letter and letter.upper() in "ABCD":
        return ord(letter.upper()) - 65
    if number and number.isdigit():
        idx = int(number) - 1
        return idx if 0 <= idx < len(options) else None
    text = (raw or "").strip()
    if text.isdigit():
        idx = int(text) - 1
        return idx if 0 <= idx < len(options) else None
    # Remove common answer decorations while preserving Devanagari.
    text = re.sub(r"^[A-Da-d]\s*[.)\-:]\s*", "", text).strip()
    for i, opt in enumerate(options):
        if text.casefold() == opt.strip().casefold():
            return i
    # A supplied answer may include the option plus a short explanation.
    for i, opt in enumerate(options):
        if text.casefold().startswith(opt.strip().casefold()):
            return i
    return None


def parse_pasted_mcq(source: str) -> Quiz | None:
    """Parse an already-written MCQ paper without changing its answers.

    Supports examples such as:
      Q1. Question\nA. ...\nB. ...\n...\nAnswer: B
      Q2. ...\nA. ...\n...\n✅ उत्तर: C. बहुव्रीहि\n\nविग्रह: ...

    Returns None unless at least three complete questions are found, so normal
    study notes are still sent through the model-generation path.
    """
    text = (source or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None

    # Numeric question labels ("1. ...") overlap with numeric option labels
    # ("1. UDP"). A numeric line is treated as a question only when it is
    # sequential and looks like a real question (question mark, Hindi dash,
    # or enough text); Q/Question/प्रश्न prefixes are always accepted.
    lines_all = text.split("\n")
    start_line_indices = []
    expected_number = None
    for idx, line in enumerate(lines_all):
        m = QUESTION_START.match(line)
        if not m:
            continue
        n = int(m.group(1))
        content = m.group(2).strip()
        has_explicit_prefix = bool(re.match(r"^(?:q|que|ques|question|प्रश्न)\s*\d", line.strip(), re.IGNORECASE))
        looks_like_question = ("?" in content or "؟" in content or "—" in content or len(content) >= 24)
        # Accept a normal sequential run (1,2,3...) and also a new paper
        # section that restarts numbering at 1 after a previous run (for
        # example: 20 Hindi questions followed by English questions 1-20).
        # The content heuristic prevents ordinary numeric options such as
        # "1. UDP" from being mistaken for a new question.
        starts_new_sequence = (n == 1 and expected_number is not None and looks_like_question)
        if has_explicit_prefix or (looks_like_question and (expected_number is None or n == expected_number or starts_new_sequence)):
            start_line_indices.append(idx)
            expected_number = n + 1
    if len(start_line_indices) < 3:
        return None
    starts = [(idx, QUESTION_START.match(lines_all[idx])) for idx in start_line_indices]

    questions: list[Question] = []
    for pos, (start_idx, match) in enumerate(starts):
        block_end_idx = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines_all)
        block_lines = lines_all[start_idx:block_end_idx]
        block = "\n".join(block_lines).strip()
        lines = [ln.rstrip() for ln in block.split("\n")]
        first = re.sub(r"^\s*(?:Q\s*)?\d{1,3}\s*[.)\-:]\s*", "", lines[0], flags=re.I).strip()
        if not first:
            continue

        options: list[str] = []
        answer_letter: str | None = None
        answer_raw = ""
        answer_line_idx = None
        explanation_lines: list[str] = []

        answer_number: str | None = None
        for idx, line in enumerate(lines[1:], start=1):
            stripped = line.strip()
            if not stripped:
                continue
            om = OPTION_LINE.match(stripped)
            if om and len(options) < 4:
                option_text = (om.group(2) if om.group(1) else om.group(4)).strip()
                options.append(option_text)
                continue
            am = ANSWER_LINE.match(stripped)
            if am:
                answer_letter = am.group(1)
                answer_number = am.group(2)
                answer_raw = am.group(3).strip()
                answer_line_idx = idx
                continue
            if answer_line_idx is not None:
                explanation_lines.append(stripped)

        if len(options) != 4 or answer_line_idx is None:
            continue

        answer_index = _answer_index_from_text(answer_raw, options, answer_letter, answer_number)
        if answer_index is None or not 0 <= answer_index < 4:
            # Do not guess. A malformed answer is safer to reject than to publish.
            log.warning("Rejected pasted question %s: supplied answer did not match options", match.group(1))
            continue

        explanation = " ".join(explanation_lines).strip()
        # Keep the original supplied answer in the explanation only when there
        # is additional explanatory content; the answer itself is represented
        # by answer_index and therefore cannot drift in the HTML.
        questions.append(Question(
            question=first,
            options=options,
            answer_index=answer_index,
            answer=options[answer_index],
            explanation=explanation,
        ))

    if len(questions) < 3:
        return None

    # Preserve question order. No shuffling here: users expect the converted
    # paper to remain identical to their source.
    return Quiz(
        title="Converted Quiz",
        difficulty="practice",
        output_format="mcq",
        questions=questions,
    )

# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _one_batch(section: str, want: int, difficulty: str, language: str,
               output_format: str, focus_topic: str, avoid: list[str],
               temperature: float) -> tuple[str, list[Question]]:
    messages = [
        {"role": "system", "content": system_prompt(output_format)},
        {"role": "user", "content": user_prompt(section, want, difficulty,
                                                language, focus_topic, avoid)},
    ]
    budget = 320 * want + 600
    raw = providers.chat(messages, temperature=temperature,
                         max_tokens=min(8000, budget))

    payload = parse_payload(raw)
    title = str(payload.get("title") or "").strip()[:120]

    good: list[Question] = []
    for item in payload.get("questions") or []:
        q = validate_item(item, output_format)
        if q:
            good.append(q)
    return title, good


def generate(
    source: str,
    num_questions: int = 10,
    difficulty: str = "medium",
    language: str = "auto",
    output_format: str = "mcq",
    focus_topic: str = "",
    use_cache: bool = True,
) -> Quiz:
    output_format = "short" if output_format == "short" else "mcq"
    num_questions = max(1, min(num_questions, settings.MAX_QUESTIONS))

    # Existing MCQ paper: preserve the supplied answers exactly. This path is
    # deliberately deterministic and works for Hindi + English Unicode.
    if output_format == "mcq":
        pasted = parse_pasted_mcq(source)
        if pasted is not None:
            log.info("detected pasted MCQ paper: %s questions converted without answer guessing", len(pasted.questions))
            return pasted

    ck = cache.key_for(source, n=num_questions, d=difficulty, l=language,
                       f=output_format, t=focus_topic, m=settings.model_name)
    if use_cache:
        hit = cache.get(ck)
        if hit is not None:
            log.info("cache hit")
            return Quiz(**hit)

    per_call = max(1, settings.QUESTIONS_PER_CALL)
    batches = max(1, -(-num_questions // per_call))          # ceil
    sections = extractors.split_sections(source, batches)

    collected: list[Question] = []
    seen: set[str] = set()
    title = ""
    errors: list[str] = []

    for i in range(batches):
        if len(collected) >= num_questions:
            break
        section = sections[i % len(sections)]
        want = min(per_call, num_questions - len(collected))
        asked = [q.question for q in collected]

        for attempt in range(2):
            try:
                got_title, questions = _one_batch(
                    section, want, difficulty, language, output_format,
                    focus_topic, asked, 0.35 + 0.25 * attempt,
                )
            except providers.ProviderUnavailable:
                raise
            except (providers.ProviderError, GenerationError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                log.warning("batch %s attempt %s failed: %s", i + 1, attempt + 1, exc)
                continue

            title = title or got_title
            added = 0
            for q in questions:
                key = norm_key(q.question)
                if key and key not in seen:
                    seen.add(key)
                    collected.append(q)
                    added += 1
            if added:
                break

    if not collected:
        detail = errors[0] if errors else "no questions passed validation"
        log.warning("generation produced nothing: %s", detail)
        raise GenerationError(
            f"Could not build a question set from this content. ({detail[:160]})"
        )

    # A short set beats an error, but say so honestly in the log.
    if len(collected) < num_questions:
        log.info("returning %s of %s requested questions", len(collected), num_questions)

    quiz = Quiz(
        title=title or "Practice Paper",
        difficulty=difficulty,
        output_format=output_format,
        questions=collected[:num_questions],
    )
    if use_cache:
        cache.put(ck, quiz.model_dump())
    return quiz
