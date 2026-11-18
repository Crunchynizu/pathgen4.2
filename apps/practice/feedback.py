"""The end-of-practice summary (docs/special_algo.md §4, docs/rag.md "Runtime sequence").

Django owns the score, the focus skill and the review link. At completion the words come from the
approved knowledge file when it has the focus skill, otherwise from the built-in text; that is saved
once and shown at once. Afterwards the results page may ask local Qwen to reword the approved note
(generate()): the job is claimed once, inference runs outside any database write, and any failure
leaves the saved text in place.
"""
import logging
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.curriculum.models import Skill
from learning.feedback import llm, service
from learning.feedback.retrieval import KnowledgeError, load

from .models import ExerciseFeedback, SessionQuestion

logger = logging.getLogger(__name__)
KNOWLEDGE_FILE = Path(settings.BASE_DIR) / "content" / "lesson_knowledge.json"


@lru_cache(maxsize=1)
def knowledge():
    """({skill code: Entry}, version), or ({}, "") when the file is missing or invalid (fallback)."""
    lesson_of_skill = dict(Skill.objects.values_list("code", "lesson__code"))
    try:
        return load(KNOWLEDGE_FILE, lesson_of_skill)
    except FileNotFoundError:
        return {}, ""
    except KnowledgeError:
        logger.exception("lesson_knowledge.json is invalid; using the built-in feedback text.")
        return {}, ""


def summarize(session, mastery):
    """Pick the one focus skill and, if earned, one strength."""
    items = list(session.items.select_related("question__skill").prefetch_related("attempts"))
    struggles, independent, order = {}, set(), {}
    for item in items:
        skill = item.question.skill
        order[skill.code] = skill
        struggled = item.outcome != SessionQuestion.Outcome.CORRECT_FIRST or item.hint_used
        struggles[skill.code] = struggles.get(skill.code, 0) + int(struggled)
        if item.outcome == SessionQuestion.Outcome.CORRECT_FIRST and not item.hint_used:
            independent.add(skill.code)
    if not order:
        return None, None
    practiced = sorted(order.values(), key=lambda s: s.sort_order)
    if any(struggles.values()):
        focus = min(practiced, key=lambda s: (-struggles[s.code], mastery.get(s.code, 1.0), s.sort_order))
    else:
        focus = min(practiced, key=lambda s: (mastery.get(s.code, 1.0), s.sort_order))
    strengths = [s for s in practiced if s.code in independent and s.code != focus.code]
    strength = max(strengths, key=lambda s: (mastery.get(s.code, 0.0), -s.sort_order)) if strengths else None
    return focus, strength


def compose(session, focus, strength, entry):
    """The saved words. The page shows the strength and next focus as their own labelled lines."""
    parts = []
    if strength:
        parts.append(f"Well done on {strength.short_name}: you got it right on your own.")
    elif session.first_try_correct:
        parts.append(f"You got {session.first_try_correct} right on the first try.")
    if focus:
        if entry:
            parts.append(f"{entry.explanation} Example: {entry.worked_example}")
        else:
            parts.append("Read that part of the lesson again, then practice it once more.")
    return " ".join(parts)


def save_for(session, mastery):
    existing = ExerciseFeedback.objects.filter(session=session).first()
    if existing:
        return existing
    focus, strength = summarize(session, mastery)
    entries, version = knowledge()
    entry = entries.get(focus.code) if focus else None
    text = compose(session, focus, strength, entry)
    return ExerciseFeedback.objects.create(
        session=session,
        focus_skill=focus,
        strength_skill=strength,
        review_url=focus.review_url() if focus else "",
        text=text,
        fallback_text=text,
        source=ExerciseFeedback.Source.KNOWLEDGE if entry else ExerciseFeedback.Source.BASIC,
        knowledge_version=version if entry else "",
        # Without approved knowledge there is nothing to ground Qwen on, so it is never asked.
        generation=ExerciseFeedback.Generation.PENDING if entry else ExerciseFeedback.Generation.NONE,
    )


def generation_enabled():
    return bool(settings.LLM_BASE_URL)


def _fail(feedback_id, note):
    logger.warning("Qwen feedback for %s not used: %s", feedback_id, note)
    ExerciseFeedback.objects.filter(pk=feedback_id, generation=ExerciseFeedback.Generation.CLAIMED).update(
        generation=ExerciseFeedback.Generation.FAILED, generation_note=note[:160],
    )


def generate(feedback):
    """Reword the saved feedback with Qwen, once. Returns the feedback as saved afterwards."""
    if feedback.generation != ExerciseFeedback.Generation.PENDING or not generation_enabled():
        return feedback
    claimed = ExerciseFeedback.objects.filter(
        pk=feedback.pk, generation=ExerciseFeedback.Generation.PENDING,
    ).update(generation=ExerciseFeedback.Generation.CLAIMED, claimed_at=timezone.now())
    if not claimed:  # another request has it; reuse whatever it saves
        feedback.refresh_from_db()
        return feedback

    entries, version = knowledge()
    entry = entries.get(feedback.focus_skill.code) if feedback.focus_skill_id else None
    if entry is None or version != feedback.knowledge_version:
        _fail(feedback.pk, "approved knowledge missing or changed since the session ended")
        feedback.refresh_from_db()
        return feedback
    session = feedback.session
    facts = service.Facts(
        focus=feedback.focus_skill.short_name,
        strength=feedback.strength_skill.short_name if feedback.strength_skill_id else None,
        needed_retries=(session.first_try_correct or 0) < session.target_count,
    )
    try:
        raw = llm.complete(settings.LLM_BASE_URL, service.messages(facts, entry), model=settings.LLM_MODEL,
                           timeout=settings.LLM_TIMEOUT_SECONDS, max_tokens=settings.LLM_MAX_TOKENS)
        text = service.clean(raw, entry)
    except (llm.LlmError, service.InvalidOutput) as error:
        _fail(feedback.pk, str(error))
        feedback.refresh_from_db()
        return feedback
    ExerciseFeedback.objects.filter(pk=feedback.pk, generation=ExerciseFeedback.Generation.CLAIMED).update(
        text=text, source=ExerciseFeedback.Source.GENERATED, generation=ExerciseFeedback.Generation.DONE,
        generated_at=timezone.now(), model_version=f"{settings.LLM_MODEL_VERSION}; {service.PROMPT_VERSION}",
    )
    feedback.refresh_from_db()
    return feedback
