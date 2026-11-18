"""Load content/question_bank.json as one published exercise per lesson (PLAN.md, Phase 4).

All or nothing: if any pool fails the checks in services.validate_revision, nothing is saved.
Re-running with the same bank and difficulty file only adds the class assignments.
"""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.curriculum.models import Lesson, Skill

from .models import AnswerChoice, Exercise, ExerciseRevision, Question, RevisionSkill
from .services import PublishError, publish_revision

BANK_FILE = Path(settings.BASE_DIR) / "content" / "question_bank.json"
DIFFICULTY_FILE = Path(settings.MODEL_ARTIFACTS_DIR) / "template_difficulty.json"


class ImportProblem(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def _read(path):
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError as error:
        raise ImportProblem([f"No file at {path}."]) from error
    return raw, json.loads(raw.decode("utf-8"))


def load_bank(bank_path=BANK_FILE, difficulty_path=DIFFICULTY_FILE):
    _raw, bank = _read(bank_path)
    difficulty_raw, difficulty = _read(difficulty_path)
    if difficulty.get("skill_level") != "fine_skill":
        raise ImportProblem(["template_difficulty.json must come from the 10-skill fit (skill_level fine_skill)."])
    version = f"{bank['bank_version']}+td-{hashlib.sha256(difficulty_raw).hexdigest()[:10]}"
    return bank, difficulty["templates"], version


def _check_shape(entry, lessons, skills, templates):
    problems = []
    lesson_code = entry.get("lesson")
    if lesson_code not in lessons:
        return [f"Unknown lesson {lesson_code!r}: run seed_curriculum first."]
    for code in entry.get("required_skills", []):
        if code not in skills:
            problems.append(f"{lesson_code}: unknown skill {code!r}.")
    keys = set()
    for question in entry["questions"]:
        key = question.get("item_key", "?")
        if key in keys:
            problems.append(f"{lesson_code}: item key {key} is used twice.")
        keys.add(key)
        if question.get("skill") not in skills:
            problems.append(f"{key}: unknown skill {question.get('skill')!r}.")
        template = question.get("junyi_template")
        if not template:
            problems.append(f"{key}: needs its closest Junyi template.")
        elif template not in templates:
            problems.append(f"{key}: template {template} isn't in template_difficulty.json.")
    return problems


def _build_revision(exercise, entry, skills, templates, version, teacher):
    number = (exercise.revisions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    revision = ExerciseRevision.objects.create(
        exercise=exercise,
        number=number,
        title=entry["title"],
        target_count=entry["target_count"],
        scope=ExerciseRevision.Scope.MIXED if len(entry["required_skills"]) > 1 else ExerciseRevision.Scope.SINGLE,
        source_version=version,
    )
    RevisionSkill.objects.bulk_create(
        RevisionSkill(revision=revision, skill=skills[code]) for code in entry["required_skills"]
    )
    for order, item in enumerate(entry["questions"], start=1):
        question = Question.objects.create(
            revision=revision,
            item_key=item["item_key"],
            author_order=order,
            format=item.get("format", Question.Format.TEXT),
            prompt=item["prompt"],
            skill=skills[item["skill"]],
            difficulty=item["difficulty"],
            hint=item.get("hint") or "",
            explanation=item.get("explanation") or "",
            figure_path=item.get("figure") or "",
            figure_description=item.get("figure_description") or "",
            junyi_template=item["junyi_template"],
            difficulty_value=templates[item["junyi_template"]],
            source_code=item.get("source_code") or "",
            review_status=item.get("review_status", Question.ReviewStatus.DRAFT),
        )
        AnswerChoice.objects.bulk_create(
            AnswerChoice(question=question, position=position, text=choice["text"], is_correct=bool(choice.get("correct")))
            for position, choice in enumerate(item["choices"], start=1)
        )
    return revision


@transaction.atomic
def import_bank(*, teacher, classrooms, bank_path=BANK_FILE, difficulty_path=DIFFICULTY_FILE, only=None):
    """Returns a list of (lesson code, revision, outcome) for the report."""
    bank, templates, version = load_bank(bank_path, difficulty_path)
    lessons = {lesson.code: lesson for lesson in Lesson.objects.all()}
    skills = {skill.code: skill for skill in Skill.objects.all()}
    entries = [entry for entry in bank["exercises"] if not only or entry["lesson"] in only]
    if not entries:
        raise ImportProblem(["Nothing to import."])

    problems = []
    for entry in entries:
        problems += _check_shape(entry, lessons, skills, templates)
    if problems:
        raise ImportProblem(problems)

    report = []
    for entry in entries:
        lesson = lessons[entry["lesson"]]
        source_key = f"bank:{lesson.code}"
        exercise = Exercise.objects.filter(owner_teacher=teacher, source_key=source_key).first()
        if exercise is None:
            exercise = Exercise.objects.create(owner_teacher=teacher, lesson=lesson, source_key=source_key)
        current = exercise.active_revision
        if current is not None and current.source_version == version:
            revision, outcome = current, "unchanged"
        elif current is not None and not current.source_version:
            # The teacher changed it in the editor and published that: never overwrite their work.
            revision, outcome = current, "kept the teacher's edited version"
        else:
            revision, outcome = _build_revision(exercise, entry, skills, templates, version, teacher), "new"
        try:
            publish_revision(revision, classrooms, teacher)
        except PublishError as error:
            problems += [f"{lesson.title}: {problem}" for problem in error.problems]
            continue
        report.append((lesson.code, revision, outcome))
    if problems:
        raise ImportProblem(problems)
    return report
