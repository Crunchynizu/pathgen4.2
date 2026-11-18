"""Teacher exercise authoring (docs/user_features.md "Teacher", docs/database.md, docs/special_algo.md §1).

An exercise has numbered revisions. Teachers edit a draft revision; publishing freezes it and makes
it the version new sessions use, while sessions already started keep theirs. Editing a published
exercise starts a new draft copied from it, keeping each question's item key. Every function here
checks that the teacher owns the exercise; the views add the role check.
"""
import re
import secrets
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.classrooms.models import Classroom
from apps.curriculum.models import LessonSkill, Skill

from .models import (
    AnswerChoice,
    Exercise,
    ExerciseAssignment,
    ExerciseRevision,
    ExerciseSession,
    Question,
    RevisionSkill,
)
from .services import PublishError, assert_editable, publish_revision

# docs/agent.md: provisional numbers for a teacher's Easy/Medium/Hard tag, reported as uncalibrated.
# Bank questions keep their Junyi template's real struggle rate while their skill and tag stay the same.
PROVISIONAL_DIFFICULTY = {"easy": 0.15, "medium": 0.30, "hard": 0.50}
DIFFICULTY_TAGS_VERSION = "tags-v1-uncalibrated"
MAX_FIGURE_BYTES = 2 * 1024 * 1024
MAX_FIGURE_SIDE = 4000
MAX_VIDEO_START = 6 * 3600
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class AuthoringError(Exception):
    """A rule stops this change. The message is safe to show the teacher."""


# ---- Lesson scope --------------------------------------------------------------------------

def allowed_skills(lesson):
    """Skills a question in this lesson may use: taught, plus approved cumulative review."""
    return Skill.objects.filter(lesson_links__lesson=lesson).order_by("sort_order").distinct()


def scope_for(lesson):
    single = LessonSkill.objects.filter(lesson=lesson).count() == 1
    return ExerciseRevision.Scope.SINGLE if single else ExerciseRevision.Scope.MIXED


# ---- Media checks --------------------------------------------------------------------------

def check_figure(upload):
    """A PNG or JPEG under 2 MB that Pillow can read. Raises ValidationError with a plain message."""
    if upload.size > MAX_FIGURE_BYTES:
        raise ValidationError("The picture is bigger than 2 MB. Save it smaller and choose it again.")
    try:
        upload.seek(0)
        with Image.open(upload) as image:
            kind = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("That file isn't a picture PathGen can read. Use a PNG or JPEG.") from None
    finally:
        upload.seek(0)
    if kind not in ("PNG", "JPEG"):
        raise ValidationError("Use a PNG or JPEG picture.")
    if max(width, height) > MAX_FIGURE_SIDE:
        raise ValidationError(f"The picture is {width}×{height}. Keep both sides under {MAX_FIGURE_SIDE} pixels.")
    return kind


def parse_timestamp(value):
    """'90', '90s', '1m30s', '1h2m3s', '1:30' or '1:02:03' -> seconds, or None."""
    value = (value or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}", value):
        seconds = 0
        for part in value.split(":"):
            seconds = seconds * 60 + int(part)
        return seconds
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", value)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    return None


def parse_youtube(url):
    """A YouTube link -> (video ID, start seconds or None). Raises ValidationError if it isn't one."""
    url = (url or "").strip()
    if not url:
        raise ValidationError("Paste the YouTube link.")
    if "://" not in url:
        url = "https://" + url
    parts = urlparse(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    query = parse_qs(parts.query)
    video_id = None
    if host == "youtu.be":
        video_id = parts.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "youtube-nocookie.com", "music.youtube.com"):
        path = parts.path.strip("/").split("/")
        if path[0] == "watch":
            video_id = (query.get("v") or [""])[0]
        elif path[0] in ("embed", "shorts", "live", "v") and len(path) > 1:
            video_id = path[1]
    if not video_id or not YOUTUBE_ID.match(video_id):
        raise ValidationError("That isn't a YouTube video link. Copy it from the video's Share button.")
    start = None
    for key in ("t", "start"):
        if key in query:
            start = parse_timestamp(query[key][0])
            break
    if start is None and parts.fragment.startswith("t="):
        start = parse_timestamp(parts.fragment[2:])
    return video_id, start


# ---- Drafts --------------------------------------------------------------------------------

def owned(teacher, exercise_id, *, lock=False):
    queryset = Exercise.objects.select_related("lesson", "active_revision")
    if lock:
        queryset = queryset.select_for_update(of=("self",))  # the live version is an optional join
    exercise = queryset.filter(pk=exercise_id, owner_teacher=teacher).first()
    if exercise is None:
        raise Exercise.DoesNotExist("Not this teacher's exercise.")
    return exercise


def draft_of(exercise):
    """The editable draft: the newest unpublished revision after the live one, if any."""
    after = exercise.active_revision.number if exercise.active_revision_id else 0
    return (
        exercise.revisions.filter(state=ExerciseRevision.State.DRAFT, number__gt=after).order_by("-number").first()
    )


def ever_published(exercise):
    return exercise.revisions.filter(state=ExerciseRevision.State.PUBLISHED).exists()


def can_delete(exercise):
    """docs/modals.md #5: only a draft exercise that was never published and never used."""
    return not (
        ever_published(exercise)
        or exercise.assignments.exists()
        or ExerciseSession.objects.filter(exercise=exercise).exists()
    )


@transaction.atomic
def create_exercise(teacher, lesson, title, target_count):
    exercise = Exercise.objects.create(owner_teacher=teacher, lesson=lesson, status=Exercise.Status.DRAFT)
    revision = ExerciseRevision.objects.create(
        exercise=exercise, number=1, title=title.strip(), target_count=target_count, scope=scope_for(lesson),
    )
    RevisionSkill.objects.bulk_create(RevisionSkill(revision=revision, skill=skill) for skill in lesson.taught_skills())
    return exercise


@transaction.atomic
def start_draft(teacher, exercise_id):
    """A new draft copied from the live version. Repeating returns the same draft."""
    exercise = owned(teacher, exercise_id, lock=True)
    existing = draft_of(exercise)
    if existing:
        return existing
    source = exercise.active_revision or exercise.revisions.order_by("-number").first()
    if source is None:
        raise AuthoringError("This exercise has nothing to copy yet.")
    number = (exercise.revisions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    draft = ExerciseRevision.objects.create(
        exercise=exercise, number=number, title=source.title, target_count=source.target_count, scope=source.scope,
    )
    RevisionSkill.objects.bulk_create(RevisionSkill(revision=draft, skill_id=link.skill_id)
                                      for link in source.skill_links.all())
    for question in source.questions.prefetch_related("choices"):
        copy = Question.objects.create(
            revision=draft, item_key=question.item_key, author_order=question.author_order, format=question.format,
            prompt=question.prompt, skill_id=question.skill_id, difficulty=question.difficulty, hint=question.hint,
            explanation=question.explanation, figure_file=question.figure_file.name, figure_path=question.figure_path,
            figure_description=question.figure_description, video_id=question.video_id,
            video_start_seconds=question.video_start_seconds, junyi_template=question.junyi_template,
            difficulty_value=question.difficulty_value, source_code=question.source_code,
            review_status=question.review_status,
        )
        AnswerChoice.objects.bulk_create(
            AnswerChoice(question=copy, position=c.position, text=c.text, is_correct=c.is_correct)
            for c in question.choices.all()
        )
    return draft


def _new_item_key(exercise, taken):
    while True:
        key = f"q-{secrets.token_hex(4)}"
        if key not in taken and not Question.objects.filter(revision__exercise=exercise, item_key=key).exists():
            taken.add(key)
            return key


def _forget_unused_figures(names):
    """Delete uploaded figures no question uses any more (old revisions keep theirs)."""
    for name in names:
        if name and not Question.objects.filter(figure_file=name).exists():
            try:
                default_storage.delete(name)
            except OSError:
                pass  # a leftover file is harmless; a missing one is already gone


@transaction.atomic
def save_draft(teacher, exercise_id, revision_id, *, title, target_count, required_skills, questions):
    """Replace the draft's settings and pool with what the editor sent, in pool order.

    Each entry of `questions` is a dict from forms.QuestionForm.to_entry(). Pool and coverage
    checks wait for publishing (services.validate_revision), so a half-finished draft can be saved.
    """
    exercise = owned(teacher, exercise_id, lock=True)
    revision = ExerciseRevision.objects.select_for_update().filter(pk=revision_id, exercise=exercise).first()
    if revision is None or revision != draft_of(exercise):
        raise AuthoringError("This draft changed in another tab. Open the exercise again.")
    try:
        assert_editable(revision)
    except PublishError as error:
        raise AuthoringError(error.problems[0]) from None

    allowed = {skill.id: skill for skill in allowed_skills(exercise.lesson)}
    if revision.scope == ExerciseRevision.Scope.SINGLE:
        required_skills = list(allowed.values())
    required_skills = [skill for skill in required_skills if skill.id in allowed]

    revision.title = title.strip()
    revision.target_count = target_count
    revision.save(update_fields=["title", "target_count"])
    RevisionSkill.objects.filter(revision=revision).delete()
    RevisionSkill.objects.bulk_create(RevisionSkill(revision=revision, skill=skill) for skill in required_skills)

    old = {question.id: question for question in revision.questions.all()}
    old_figures = {question.figure_file.name for question in old.values() if question.figure_file}
    revision.questions.all().delete()  # drafts are never served, so nothing points at these rows

    taken = set()
    for order, entry in enumerate(questions, start=1):
        before = old.get(entry.get("source_id"))
        skill = entry["skill"]
        if skill.id not in allowed:
            raise AuthoringError(f"Question {order}: {skill.short_name} isn't part of {exercise.lesson.title}.")
        key = before.item_key if before and before.item_key not in taken else _new_item_key(exercise, taken)
        taken.add(key)
        same_kind = before and before.skill_id == skill.id and before.difficulty == entry["difficulty"]
        template = before.junyi_template if same_kind else ""
        value = before.difficulty_value if same_kind and template else PROVISIONAL_DIFFICULTY[entry["difficulty"]]

        figure_file, figure_path, description, video_id, video_start = "", "", "", "", None
        if entry["format"] == Question.Format.FIGURE:
            description = entry["figure_description"].strip()
            if entry.get("figure_upload"):
                figure_file = entry["figure_upload"]
            elif before and entry.get("keep_figure"):
                figure_file, figure_path = before.figure_file.name, before.figure_path
        elif entry["format"] == Question.Format.VIDEO:
            video_id, video_start = entry["video_id"], entry["video_start"]

        question = Question(
            revision=revision, item_key=key, author_order=order, format=entry["format"],
            prompt=entry["prompt"].strip(), skill=skill, difficulty=entry["difficulty"],
            hint=entry["hint"].strip(), explanation=(before.explanation if before else ""),
            figure_path=figure_path, figure_description=description, video_id=video_id,
            video_start_seconds=video_start, junyi_template=template, difficulty_value=value,
            source_code=before.source_code if before else "",
        )
        if hasattr(figure_file, "read"):
            question.figure_file.save(figure_file.name, figure_file, save=False)
        else:
            question.figure_file = figure_file
        question.save()
        AnswerChoice.objects.bulk_create(
            AnswerChoice(question=question, position=position, text=text.strip(), is_correct=entry["correct"] == position)
            for position, text in enumerate(entry["choices"], start=1)
            if text.strip()
        )
    transaction.on_commit(lambda: _forget_unused_figures(old_figures))
    return revision


# ---- Publish, unpublish, delete ------------------------------------------------------------

def publishable_revision(exercise):
    return draft_of(exercise) or exercise.active_revision


def publish(teacher, exercise_id, classroom_ids):
    """docs/modals.md #4. Publishes the draft (or the live version, to more classes)."""
    exercise = owned(teacher, exercise_id)
    revision = publishable_revision(exercise)
    if revision is None:
        raise PublishError("There is nothing to publish yet.")
    classrooms = Classroom.objects.filter(pk__in=[int(i) for i in classroom_ids if str(i).isdigit()])
    return publish_revision(revision, classrooms, teacher)


@transaction.atomic
def unpublish(teacher, exercise_id):
    """docs/modals.md #6: new starts and retakes stop; started sessions finish; results stay."""
    exercise = owned(teacher, exercise_id, lock=True)
    active = list(exercise.assignments.filter(status=ExerciseAssignment.Status.ACTIVE).select_related("classroom"))
    now = timezone.now()
    for assignment in active:
        assignment.status = ExerciseAssignment.Status.INACTIVE
        assignment.unpublished_at = now
        assignment.save(update_fields=["status", "unpublished_at"])
    if exercise.status == Exercise.Status.PUBLISHED:
        exercise.status = Exercise.Status.UNPUBLISHED
        exercise.save(update_fields=["status", "updated_at"])
    return [assignment.classroom for assignment in active]


@transaction.atomic
def delete_draft_exercise(teacher, exercise_id):
    """docs/modals.md #5: remove a never-published draft with its questions and hints."""
    exercise = owned(teacher, exercise_id, lock=True)
    if not can_delete(exercise):
        raise AuthoringError("This exercise has been published, so it can't be deleted. Unpublish it instead.")
    figures = set(
        Question.objects.filter(revision__exercise=exercise).exclude(figure_file="").values_list("figure_file", flat=True)
    )
    latest = exercise.revisions.order_by("-number").first()
    title = latest.title if latest else f"Exercise {exercise.pk}"
    exercise.delete()
    transaction.on_commit(lambda: _forget_unused_figures(figures))
    return title
