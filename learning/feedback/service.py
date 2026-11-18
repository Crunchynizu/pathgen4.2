"""What Qwen is asked, and the checks its answer must pass (docs/rag.md, "Runtime sequence").

Django has already chosen the focus skill, the strength and the review link, and the score is
shown on its own. Qwen only rewords the approved explanation and example into 2 or 3 short
sentences. The prompt carries no names or other records. Pure, no Django.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PROMPT_VERSION = "pg42-feedback-v1"
MIN_CHARS = 40
MAX_CHARS = 420
MAX_SENTENCES = 3
NUMBER = re.compile(r"\d+")
BANNED = ("http", "www.", "<", ">", "```", "**", "##", "\(", "$$")

SYSTEM = (
    "You write feedback for a Grade 7 student who just finished a short practice on integers. "
    "Write 2 or 3 short, friendly sentences in simple English. Use only the facts and the teacher's "
    "note below. Do not invent new examples, numbers or rules, do not give a score, do not use the "
    "student's name, lists, headings or emojis."
)


class InvalidOutput(ValueError):
    pass


@dataclass(frozen=True)
class Facts:
    focus: str                 # the focus skill's display name
    strength: str | None       # a skill answered right without help, if any
    needed_retries: bool       # some answers were fixed on the retry or missed


def messages(facts: Facts, entry) -> list:
    lines = [f"Next focus: {facts.focus}."]
    if facts.strength:
        lines.append(f"Strength: {facts.strength} (answered right on the first try without a hint).")
    if facts.needed_retries:
        lines.append("Some questions needed a second try.")
    lines += [
        "Teacher's note for the next focus:",
        f"- Idea: {entry.explanation}",
        f"- Example: {entry.worked_example}",
        "Write the feedback now: praise the strength if there is one, then explain the next focus "
        "using the idea and the example.",
    ]
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "\n".join(lines)}]


def clean(text: str, entry) -> str:
    """The model's text, tidied, if it passes every check; otherwise InvalidOutput."""
    text = " ".join((text or "").split()).strip().strip('"').strip()
    if any(token in text.lower() for token in BANNED):
        raise InvalidOutput("has links or markup")
    sentences = re.split(r"(?<=[.!?])\s+", text)
    text = " ".join(sentences[:MAX_SENTENCES]).strip()
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        raise InvalidOutput(f"length {len(text)} outside {MIN_CHARS}-{MAX_CHARS}")
    if text[-1] not in ".!?":
        raise InvalidOutput("stops mid-sentence")
    # Grounding: every number in the reply must come from the approved example or explanation.
    allowed = set(NUMBER.findall(entry.explanation + " " + entry.worked_example))
    invented = sorted(set(NUMBER.findall(text)) - allowed)
    if invented:
        raise InvalidOutput("numbers not in the approved note: " + ", ".join(invented))
    return text
