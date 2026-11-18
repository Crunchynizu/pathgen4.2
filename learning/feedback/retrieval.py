"""Approved lesson knowledge, retrieved by skill code (docs/rag.md, "Knowledge handoff").

Structured retrieval by the focus skill's ID, the spec's v1 default. The entry is the fallback
text, and the only content local Qwen may rephrase (service.py, llm.py). Pure, no Django.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
MAX_TEXT = 400


class KnowledgeError(ValueError):
    pass


@dataclass(frozen=True)
class Entry:
    skill_id: str
    lesson_code: str
    section_id: str
    title: str
    explanation: str
    worked_example: str


def anchor_for(skill_id: str) -> str:
    return "skill-" + skill_id.lower().replace("_", "-")


def load(path, lesson_of_skill: dict) -> tuple[dict, str]:
    """Return ({skill code: Entry}, content version). Partial files are allowed; bad ones raise."""
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise KnowledgeError("The knowledge file is not valid JSON.") from error
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError("The knowledge file must have schema_version 1.")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise KnowledgeError("The knowledge file has no entries list.")
    found = {}
    for number, row in enumerate(entries, start=1):
        if not isinstance(row, dict):
            raise KnowledgeError(f"Entry {number} is not an object.")
        values = {}
        for key in ("skill_id", "lesson_code", "section_id", "title", "explanation", "worked_example"):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
                raise KnowledgeError(f"Entry {number}: {key} must be short, non-empty text.")
            values[key] = value.strip()
        skill = values["skill_id"]
        if skill not in lesson_of_skill:
            raise KnowledgeError(f"Entry {number}: unknown skill {skill}.")
        if lesson_of_skill[skill] != values["lesson_code"]:
            raise KnowledgeError(f"Entry {number}: {skill} is taught in {lesson_of_skill[skill]}.")
        if values["section_id"] != anchor_for(skill):
            raise KnowledgeError(f"Entry {number}: section_id must be {anchor_for(skill)}.")
        if skill in found:
            raise KnowledgeError(f"{skill} appears twice.")
        found[skill] = Entry(**values)
    version = str(data.get("content_version") or "") or "sha-" + hashlib.sha256(raw).hexdigest()[:12]
    return found, version
