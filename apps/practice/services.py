"""Exercise pool checks, publication and what each student can open (docs/special_algo.md §1,
docs/database.md, docs/user_features.md "Teacher")."""
from django.db import transaction
from django.utils import timezone

from apps.classrooms.services import classroom_of
from apps.curriculum.models import LessonSkill

from .models import Exercise, ExerciseAssignment, ExerciseRevision, Question


class PublishError(Exception):
    def __init__(self, problems):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__("; ".join(self.problems))


def validate_revision(revision):
    """Every reason this pool can't be published. An empty list means it can."""
    problems = []
    lesson = revision.exercise.lesson
    links = LessonSkill.objects.filter(lesson=lesson)
    allowed = set(links.values_list("skill_id", flat=True))
    required = list(revision.required_skills.order_by("sort_order"))
    required_ids = {skill.id for skill in required}
    questions = list(revision.questions.select_related("skill").prefetch_related("choices"))

    if revision.target_count < 1:
        problems.append("Set at least 1 question per session.")
    if len(questions) < revision.target_count:
        problems.append(
            f"The pool has {len(questions)} questions, but a session needs {revision.target_count}."
        )
    if not required:
        problems.append("Choose at least one required skill.")
    if revision.scope == ExerciseRevision.Scope.SINGLE and len(required) != 1:
        problems.append("A one-skill exercise needs exactly one required skill.")
    if len(required) > revision.target_count:
        problems.append(
            f"{len(required)} required skills can't all fit in {revision.target_count} questions."
        )
    for skill in required:
        if skill.id not in allowed:
            problems.append(f"{skill.short_name} isn't part of {lesson.title}.")
        if not any(question.skill_id == skill.id for question in questions):
            problems.append(f"No question in the pool covers {skill.short_name}.")

    for question in questions:
        where = f"Question {question.author_order} ({question.item_key})"
        if not question.prompt.strip():
            problems.append(f"{where} has no prompt.")
        if question.skill_id not in allowed:
            problems.append(f"{where}: {question.skill.short_name} isn't part of {lesson.title}.")
        elif revision.scope == ExerciseRevision.Scope.SINGLE and question.skill_id not in required_ids:
            problems.append(f"{where} must use the exercise's one skill.")
        if question.difficulty not in Question.Difficulty.values:
            problems.append(f"{where} needs Easy, Medium or Hard.")
        if not question.hint.strip():
            problems.append(f"{where} needs a hint.")
        choices = list(question.choices.all())
        texts = [choice.text.strip() for choice in choices]
        if len(choices) != 4 or sorted(choice.position for choice in choices) != [1, 2, 3, 4]:
            problems.append(f"{where} needs exactly four answer choices.")
        if sum(choice.is_correct for choice in choices) != 1:
            problems.append(f"{where} needs exactly one correct choice.")
        if any(not text for text in texts):
            problems.append(f"{where} has an empty answer choice.")
        elif len(set(texts)) != len(texts):
            problems.append(f"{where} repeats an answer choice.")
        if question.format == Question.Format.FIGURE:
            if not question.has_figure:
                problems.append(f"{where} is a figure question without a figure.")
            if not question.figure_description.strip():
                problems.append(f"{where} needs a short description of its figure.")
        elif question.format == Question.Format.VIDEO:
            if not question.video_id:
                problems.append(f"{where} is a video question without a video.")
        elif question.has_figure or question.video_id:
            problems.append(f"{where} is text only, so it can't have media.")
    return problems


@transaction.atomic
def publish_revision(revision, classrooms, teacher):
    """Freeze the revision and make it the exercise's active version in the chosen classes."""
    exercise = Exercise.objects.select_for_update().get(pk=revision.exercise_id)
    if exercise.owner_teacher_id != teacher.id:
        raise PublishError("You can only publish your own exercises.")
    classrooms = list(classrooms)
    if not classrooms:
        raise PublishError("Choose at least one class.")
    others = [classroom.name for classroom in classrooms if classroom.teacher_id != teacher.id]
    if others:
        raise PublishError(f"These classes aren't yours: {', '.join(others)}.")

    revision = ExerciseRevision.objects.select_for_update().get(pk=revision.pk)
    if not revision.is_published:
        problems = validate_revision(revision)
        if problems:
            raise PublishError(problems)
        revision.state = ExerciseRevision.State.PUBLISHED
        revision.published_at = timezone.now()
        revision.save(update_fields=["state", "published_at"])

    exercise.active_revision = revision
    exercise.status = Exercise.Status.PUBLISHED
    exercise.save(update_fields=["active_revision", "status", "updated_at"])

    now = timezone.now()
    for classroom in classrooms:
        ExerciseAssignment.objects.update_or_create(
            exercise=exercise,
            classroom=classroom,
            defaults={
                "status": ExerciseAssignment.Status.ACTIVE,
                "published_by": teacher,
                "published_at": now,
                "unpublished_at": None,
            },
        )
    return revision


def assert_editable(revision):
    """Published pools are frozen: edits go into a new draft revision (docs/database.md)."""
    if revision.is_published:
        raise PublishError("This version is published and can't change. Make a new draft to edit it.")


def active_assignments(classroom, lesson=None):
    if classroom is None:
        return ExerciseAssignment.objects.none()
    assignments = ExerciseAssignment.objects.filter(
        classroom=classroom,
        status=ExerciseAssignment.Status.ACTIVE,
        exercise__status=Exercise.Status.PUBLISHED,
        exercise__active_revision__isnull=False,
    ).select_related("exercise__active_revision", "exercise__lesson")
    if lesson is not None:
        assignments = assignments.filter(exercise__lesson=lesson)
    return assignments.order_by("exercise__lesson__sort_order", "exercise_id")


def status_text(sessions):
    """One line for an exercise card: not started, in progress, or the latest result."""
    from .models import ExerciseSession

    if not sessions:
        return "Not started", False
    latest = sessions[-1]
    if latest.status == ExerciseSession.Status.IN_PROGRESS:
        done = latest.items.filter(completed_at__isnull=False).count()
        return f"In progress: {done} of {latest.target_count} done", False
    label = "Retake done" if latest.attempt_number == 2 else "Done"
    return f"{label}: {latest.first_try_correct} of {latest.target_count} right on the first try", True


def exercise_cards(student, lesson=None):
    """What a student sees on a lesson page or the journey: assigned, published exercises."""
    from .models import ExerciseSession

    assignments = list(active_assignments(classroom_of(student), lesson))
    by_exercise = {}
    for session in ExerciseSession.objects.filter(
        student=student, exercise__in=[a.exercise for a in assignments]
    ).order_by("attempt_number"):
        by_exercise.setdefault(session.exercise_id, []).append(session)
    cards = []
    for assignment in assignments:
        revision = assignment.exercise.active_revision
        status, finished = status_text(by_exercise.get(assignment.exercise_id, []))
        cards.append(
            {
                "exercise": assignment.exercise,
                "revision": revision,
                "skills": list(revision.required_skills.order_by("sort_order")),
                "status": status,
                "finished": finished,
            }
        )
    return cards


def student_can_open(student, exercise):
    classroom = classroom_of(student)
    return active_assignments(classroom).filter(exercise=exercise).exists()
