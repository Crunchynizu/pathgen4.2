"""Pretest/posttest rules (docs/database.md, "Assessments"; docs/user_features.md, "Student").

- The pretest unlock is a submitted pretest attempt.
- Posttest start needs a submitted pretest and the class's release.
- Start, save and final submit are safe to repeat. Answer keys never leave the server.
"""
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.classrooms.services import classroom_of

from .models import AssessmentAnswer, AssessmentAttempt, AssessmentForm, ClassAssessmentRelease, Kind


class AssessmentError(Exception):
    """A rule stops this action. The message is safe to show the student."""


class IncompleteSubmission(AssessmentError):
    def __init__(self, first_missing_position, missing_count):
        self.first_missing_position = first_missing_position
        self.missing_count = missing_count
        word = "question" if missing_count == 1 else "questions"
        super().__init__(
            f"{missing_count} {word} still need an answer. Start with question {first_missing_position}."
        )


def published_form(kind):
    return AssessmentForm.objects.filter(kind=kind, state=AssessmentForm.State.PUBLISHED).first()


def attempt_for(student, kind):
    return AssessmentAttempt.objects.filter(student=student, kind=kind).select_related("form").first()


def pretest_submitted(student):
    return AssessmentAttempt.objects.filter(
        student=student, kind=Kind.PRETEST, state=AssessmentAttempt.State.SUBMITTED
    ).exists()


def release_for(classroom):
    if classroom is None:
        return None
    return ClassAssessmentRelease.objects.filter(classroom=classroom).select_related("posttest_form").first()


@dataclass
class Journey:
    """Where a student is in the unit (docs/pages.md, "Student journey")."""

    classroom: object
    pretest: object
    posttest: object
    release: object

    @property
    def pretest_done(self):
        return bool(self.pretest and self.pretest.is_submitted)

    @property
    def posttest_done(self):
        return bool(self.posttest and self.posttest.is_submitted)

    @property
    def posttest_open(self):
        return self.pretest_done and self.release is not None

    @property
    def state(self):
        if not self.pretest_done:
            return "pretest_required"
        if self.posttest_done:
            return "unit_complete"
        if self.posttest_open:
            return "posttest_open"
        return "lessons_available"

    @property
    def score_change(self):
        """Percentage points, so forms of different lengths still compare (docs/user_features.md)."""
        if self.pretest_done and self.posttest_done:
            return score_change(self.pretest, self.posttest)
        return None


def score_change(pretest, posttest):
    """Percentage points from the raw counts (not from rounded percents)."""
    if not (pretest and posttest and pretest.is_submitted and posttest.is_submitted):
        return None
    return round(100 * (posttest.correct_count / posttest.item_count - pretest.correct_count / pretest.item_count), 1)


def journey_for(student):
    classroom = classroom_of(student)
    return Journey(
        classroom=classroom,
        pretest=attempt_for(student, Kind.PRETEST),
        posttest=attempt_for(student, Kind.POSTTEST),
        release=release_for(classroom),
    )


def can_start(student, kind):
    """None if the student may start or resume `kind`, otherwise the reason."""
    journey = journey_for(student)
    if journey.classroom is None:
        return "Your account isn't in a class yet. Ask your teacher."
    if kind == Kind.POSTTEST:
        if not journey.pretest_done:
            return "Take the pretest first."
        if journey.release is None:
            return "Waiting for your teacher to open the posttest."
    elif published_form(kind) is None and journey.pretest is None:
        return "The pretest isn't ready yet. Ask your teacher."
    return None


@transaction.atomic
def start_attempt(student, kind):
    """Start once; repeating returns the same attempt."""
    existing = AssessmentAttempt.objects.select_for_update().filter(student=student, kind=kind).first()
    if existing:
        return existing
    reason = can_start(student, kind)
    if reason:
        raise AssessmentError(reason)
    journey = journey_for(student)
    form = journey.release.posttest_form if kind == Kind.POSTTEST else published_form(kind)
    attempt, _ = AssessmentAttempt.objects.get_or_create(
        student=student,
        kind=kind,
        defaults={"form": form, "classroom": journey.classroom},
    )
    return attempt


def _parse(attempt, selections):
    """Keep only valid (item id -> 0..3) pairs for this attempt's form."""
    item_ids = set(attempt.form.items.values_list("id", flat=True))
    clean = {}
    for item_id, index in selections.items():
        try:
            item_id, index = int(item_id), int(index)
        except (TypeError, ValueError):
            continue
        if item_id in item_ids and 0 <= index <= 3:
            clean[item_id] = index
    return clean


def _store(attempt, clean):
    now = timezone.now()
    existing = {answer.item_id: answer for answer in attempt.answers.all()}
    to_create, to_update = [], []
    for item_id, index in clean.items():
        answer = existing.get(item_id)
        if answer is None:
            to_create.append(AssessmentAnswer(attempt=attempt, item_id=item_id, selected_index=index))
        elif answer.selected_index != index:
            answer.selected_index = index
            answer.last_saved_at = now
            to_update.append(answer)
    AssessmentAnswer.objects.bulk_create(to_create)
    AssessmentAnswer.objects.bulk_update(to_update, ["selected_index", "last_saved_at"])


@transaction.atomic
def save_answers(attempt, selections):
    """Save draft answers. After submission nothing changes; returns False then."""
    attempt = AssessmentAttempt.objects.select_for_update().select_related("form").get(pk=attempt.pk)
    if attempt.is_submitted:
        return False
    _store(attempt, _parse(attempt, selections))
    return True


@transaction.atomic
def submit_attempt(attempt):
    """Final submission: check every item has a saved answer, then grade once.

    Save the posted answers with save_answers() first: if an item is missing, this raises and
    its transaction rolls back, but the saved answers stay. A repeat call on a submitted
    attempt returns it unchanged, so the score stays stable.
    """
    attempt = AssessmentAttempt.objects.select_for_update().select_related("form").get(pk=attempt.pk)
    if attempt.is_submitted:
        return attempt

    items = list(attempt.form.items.order_by("position"))
    answers = {answer.item_id: answer for answer in attempt.answers.all()}
    missing = [item for item in items if answers.get(item.id) is None or answers[item.id].selected_index is None]
    if missing:
        raise IncompleteSubmission(missing[0].position, len(missing))

    correct = 0
    for item in items:
        answer = answers[item.id]
        answer.is_correct = answer.selected_index == item.correct_index
        correct += answer.is_correct
    AssessmentAnswer.objects.bulk_update(list(answers.values()), ["is_correct"])

    attempt.state = AssessmentAttempt.State.SUBMITTED
    attempt.submitted_at = timezone.now()
    attempt.correct_count = correct
    attempt.item_count = len(items)
    attempt.save(update_fields=["state", "submitted_at", "correct_count", "item_count"])
    return attempt


@transaction.atomic
def open_posttest(classroom, teacher):
    """The teacher opens the posttest for their own class. Repeating keeps the first release."""
    if classroom.teacher_id != teacher.id:
        raise AssessmentError("You can only open the posttest for your own class.")
    form = published_form(Kind.POSTTEST)
    if form is None:
        raise AssessmentError("There is no published posttest yet.")
    release, created = ClassAssessmentRelease.objects.get_or_create(
        classroom=classroom, defaults={"posttest_form": form, "opened_by": teacher}
    )
    return release, created


def coverage(form):
    """Items per skill, and the skills the form doesn't measure (shown, not enforced: PLAN.md)."""
    from apps.curriculum.models import Skill

    counts = {skill: 0 for skill in Skill.objects.order_by("sort_order")}
    by_id = {skill.id: skill for skill in counts}
    for skill_id in form.items.values_list("skill_id", flat=True):
        counts[by_id[skill_id]] += 1
    return counts, [skill for skill, count in counts.items() if count == 0]
