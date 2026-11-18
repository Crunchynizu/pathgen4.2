"""Adaptive practice: sessions, first answers, BKT, selection and decision logs (docs/database.md,
"Write boundaries"; docs/special_algo.md).

Every write locks the session row first, then the student's mastery row, so repeated or
concurrent requests converge on one saved answer and one next question.
"""
import logging
from functools import lru_cache

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.classrooms.services import classroom_of
from learning import agent as agent_lib
from learning import bkt as bkt_lib
from learning.features import FEATURE_SCHEMA_VERSION, Encounter
from learning.selection import POLICY_VERSION, Candidate, SelectionError, Situation, choose

from . import feedback
from .models import (
    AnswerAttempt,
    ExerciseSession,
    MasteryUpdate,
    SelectionDecision,
    SessionQuestion,
    StudentSkillMastery,
)
from .services import active_assignments

logger = logging.getLogger(__name__)
MAX_ACTIVE_SECONDS = 3600


class PracticeError(Exception):
    """A rule stops this action. The message is safe to show the student."""


@lru_cache(maxsize=1)
def get_bkt():
    return bkt_lib.load(settings.MODEL_ARTIFACTS_DIR)


@lru_cache(maxsize=1)
def get_agent():
    """The struggle model, or None (selection then falls back to teacher order and logs why)."""
    try:
        return agent_lib.load(settings.MODEL_ARTIFACTS_DIR)
    except Exception:  # noqa: BLE001 - any failure means "use the fallback"
        logger.exception("The struggle model could not be loaded; using the teacher-order fallback.")
        return None


# ---- Reading state ------------------------------------------------------------------------------

def history_of(student):
    """Completed tracked encounters across all exercises, in completion order."""
    items = (
        SessionQuestion.objects.filter(session__student=student, completed_at__isnull=False)
        .select_related("question__skill")
        .prefetch_related("attempts")
        .order_by("completed_at", "id")
    )
    history = []
    for item in items:
        attempts = sorted(item.attempts.all(), key=lambda a: a.attempt_number)
        if not attempts:
            continue
        history.append(Encounter(
            skill=item.question.skill.code,
            difficulty=item.question.difficulty,
            first_correct=attempts[0].is_correct,
            hint_used=item.hint_used,
            attempts=len(attempts),
            seconds=item.answer_seconds,
        ))
    return history


def mastery_of(student):
    """Current mastery per skill code: the saved value, or the fitted prior without evidence."""
    bkt = get_bkt()
    values = {code: params.prior for code, params in bkt.params.items()}
    for row in StudentSkillMastery.objects.filter(student=student).select_related("skill"):
        values[row.skill.code] = row.mastery_probability
    return values


def current_item(session):
    return session.items.filter(completed_at__isnull=True).select_related("question").first()


def sessions_for(student, exercise):
    return list(ExerciseSession.objects.filter(student=student, exercise=exercise).order_by("attempt_number"))


# ---- Starting -----------------------------------------------------------------------------------

def start(student, exercise, *, retake=False):
    """Start (or resume) session 1, or the one retake. Safe to repeat."""
    for _ in range(2):
        try:
            with transaction.atomic():
                return _start(student, exercise, retake)
        except IntegrityError:
            continue  # a parallel request made the same session first: read it back
    raise PracticeError("Please try again.")


def _start(student, exercise, retake):
    existing = list(
        ExerciseSession.objects.select_for_update().filter(student=student, exercise=exercise).order_by("attempt_number")
    )
    open_session = next((s for s in existing if not s.is_completed), None)
    if open_session:
        return open_session
    classroom = classroom_of(student)
    if not active_assignments(classroom).filter(exercise=exercise).exists():
        raise PracticeError("This practice isn't open for your class right now.")
    if not existing:
        number = 1
    elif retake and len(existing) == 1:
        number = 2
    elif len(existing) >= 2:
        raise PracticeError("You've used your one retake for this practice.")
    else:
        return existing[-1]
    revision = exercise.active_revision
    session = ExerciseSession.objects.create(
        student=student, exercise=exercise, revision=revision, classroom=classroom,
        attempt_number=number, target_count=revision.target_count,
    )
    _serve_next(session)
    return session


# ---- Selecting ----------------------------------------------------------------------------------

def _situation(session):
    revision = session.revision
    questions = list(revision.questions.select_related("skill"))
    served = list(session.items.select_related("question__skill"))
    required = [s.code for s in revision.required_skills.order_by("sort_order")]
    seen_keys = set()
    if session.attempt_number == 2:
        seen_keys = set(
            SessionQuestion.objects.filter(
                session__student=session.student, session__exercise=session.exercise, session__attempt_number=1,
            ).values_list("question__item_key", flat=True)
        )
    return Situation(
        pool=[
            Candidate(id=q.id, item_key=q.item_key, skill=q.skill.code, difficulty=q.difficulty,
                      difficulty_value=q.difficulty_value, order=q.author_order)
            for q in questions
        ],
        required=required,
        target_count=session.target_count,
        served_ids={item.question_id for item in served},
        covered={item.question.skill.code for item in served if item.is_completed},
        single_skill=revision.scope == revision.Scope.SINGLE,
        history=history_of(session.student),
        mastery=mastery_of(session.student),
        seen_keys=seen_keys,
    )


def _serve_next(session):
    situation = _situation(session)
    agent = get_agent()
    choice = choose(situation, agent)
    item = SessionQuestion.objects.create(
        session=session, question_id=choice.candidate.id, position=len(situation.served_ids) + 1,
    )
    SelectionDecision.objects.create(
        session_question=item,
        policy_version=POLICY_VERSION,
        bkt_version=get_bkt().version,
        agent_version=agent.version if agent else "",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        difficulty_mapping_version=agent.difficulty_version if agent else "",
        rule=choice.rule,
        fallback_reason=choice.fallback_reason,
        model_ready=choice.model_ready,
        chosen_skill_code=choice.candidate.skill,
        preferred_direction=choice.direction,
        selected_inputs=choice.inputs,
        predicted_struggle=choice.predicted,
        selection_probability=1.0,
        candidates=choice.candidates,
        context=choice.context,
    )
    return item


# ---- Answering ----------------------------------------------------------------------------------

def _seconds(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return round(seconds, 3) if 0 < seconds <= MAX_ACTIVE_SECONDS else None


def _video_seconds(value):
    """Video play time: 0 is a real value (not played); missing or nonsense is None."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return round(seconds, 3) if 0 <= seconds <= MAX_ACTIVE_SECONDS else None


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise PracticeError("Something was missing from that answer. Please try again.") from None


def _locked(session, item_id):
    session = ExerciseSession.objects.select_for_update().get(pk=session.pk)
    item = session.items.select_related("question__skill").filter(pk=_number(item_id)).first()
    if item is None:
        raise PracticeError("That question isn't part of this practice.")
    return session, item


def answer(session, item_id, choice_id, active_seconds=None, video_seconds=None):
    """Save the first answer (and its one BKT update) or the one retry. Repeats change nothing."""
    with transaction.atomic():
        session, item = _locked(session, item_id)
        if item.is_completed or session.is_completed:
            return item
        attempts = list(item.attempts.order_by("attempt_number"))
        if len(attempts) >= 2 or (attempts and attempts[0].is_correct):
            return item
        if not choice_id:
            raise PracticeError("Choose one of the four answers.")
        choice = item.question.choices.filter(pk=_number(choice_id)).first()
        if choice is None:
            raise PracticeError("Choose one of the four answers.")
        if attempts and attempts[0].choice_id == choice.id:
            raise PracticeError("Pick a different answer for your second try.")
        attempt = AnswerAttempt.objects.create(
            session_question=item, attempt_number=len(attempts) + 1, choice=choice,
            is_correct=choice.is_correct, active_seconds=_seconds(active_seconds),
            video_seconds=_video_seconds(video_seconds) if item.question.format == "video" else None,
        )
        if attempt.attempt_number == 1:
            _update_mastery(session.student, item, attempt)
            if attempt.is_correct:
                _complete(session, item, SessionQuestion.Outcome.CORRECT_FIRST)
        else:
            outcome = SessionQuestion.Outcome.CORRECT_RETRY if attempt.is_correct else SessionQuestion.Outcome.WRONG_RETRY
            _complete(session, item, outcome)
        return item


def _update_mastery(student, item, attempt):
    bkt = get_bkt()
    skill = item.question.skill
    params = bkt.params[skill.code]
    StudentSkillMastery.objects.get_or_create(
        student=student, skill=skill,
        defaults={"mastery_probability": params.prior, "evidence_count": 0, "bkt_version": bkt.version},
    )
    row = StudentSkillMastery.objects.select_for_update().get(student=student, skill=skill)
    prior = row.mastery_probability
    posterior, next_mastery = bkt_lib.update(prior, attempt.is_correct, params)
    MasteryUpdate.objects.create(
        session_question=item, first_answer=attempt, skill=skill, prior=prior, posterior=posterior,
        next_mastery=next_mastery, observation=attempt.is_correct, bkt_version=bkt.version,
    )
    row.mastery_probability = next_mastery
    row.evidence_count += 1
    row.bkt_version = bkt.version
    row.save(update_fields=["mastery_probability", "evidence_count", "bkt_version", "updated_at"])


def reveal_hint(session, item_id):
    """The hint opens only after a wrong first answer, before the question is finished."""
    with transaction.atomic():
        session, item = _locked(session, item_id)
        first = item.attempts.filter(attempt_number=1).first()
        if item.is_completed or first is None or first.is_correct:
            return item
        if item.hint_revealed_at is None:
            item.hint_revealed_at = timezone.now()
            item.save(update_fields=["hint_revealed_at"])
        return item


def move_on(session, item_id):
    """Skip the retry after a wrong first answer."""
    with transaction.atomic():
        session, item = _locked(session, item_id)
        first = item.attempts.filter(attempt_number=1).first()
        if item.is_completed or first is None or first.is_correct:
            return item
        _complete(session, item, SessionQuestion.Outcome.WRONG_MOVED_ON)
        return item


def _complete(session, item, outcome):
    attempts = list(item.attempts.all())
    seconds = [a.active_seconds for a in attempts]
    item.completed_at = timezone.now()
    item.outcome = outcome
    item.answer_seconds = round(sum(seconds), 3) if seconds and all(s is not None for s in seconds) else None
    played = [a.video_seconds for a in attempts]
    item.video_seconds = (
        round(sum(played), 3) if item.question.format == "video" and played and all(v is not None for v in played)
        else None
    )
    item.save(update_fields=["completed_at", "outcome", "answer_seconds", "video_seconds"])
    done = session.items.filter(completed_at__isnull=False).count()
    if done >= session.target_count:
        _finish(session)
    else:
        try:
            _serve_next(session)
        except SelectionError:
            # Keep the saved answer; the page shows a recoverable error for this session.
            logger.exception("No legal next question for session %s", session.pk)


def _finish(session):
    items = list(session.items.prefetch_related("attempts"))
    session.first_try_correct = sum(1 for i in items if i.outcome == SessionQuestion.Outcome.CORRECT_FIRST)
    session.corrected_on_retry = sum(1 for i in items if i.outcome == SessionQuestion.Outcome.CORRECT_RETRY)
    session.status = ExerciseSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=["first_try_correct", "corrected_on_retry", "status", "completed_at"])
    feedback.save_for(session, mastery_of(session.student))


def repair(session):
    """For a session stuck without a current question (a broken pool): try selecting again."""
    with transaction.atomic():
        session = ExerciseSession.objects.select_for_update().get(pk=session.pk)
        if session.is_completed or current_item(session):
            return True
        try:
            _serve_next(session)
        except SelectionError:
            return False
        return True


