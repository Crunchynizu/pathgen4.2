"""Exercises, frozen revisions, questions and class assignments (docs/database.md,
"Teacher content and student practice"), then sessions, answers, mastery, decision logs and feedback.

Exercises come from the teacher editor (authoring.py) or from the question bank (`import_bank`).
"""
import uuid
from pathlib import Path
from django.conf import settings
from django.db import models


def figure_upload_to(_question, filename):
    suffix = Path(filename).suffix.lower()
    return f"figures/{uuid.uuid4().hex}{'.jpg' if suffix == '.jpeg' else suffix}"


class Exercise(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        UNPUBLISHED = "unpublished", "Unpublished"

    owner_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="exercises",
        limit_choices_to={"role": "teacher"},
    )
    lesson = models.ForeignKey("curriculum.Lesson", on_delete=models.PROTECT, related_name="exercises")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    active_revision = models.ForeignKey(
        "ExerciseRevision", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    source_key = models.CharField(
        max_length=64, blank=True, help_text="Set by import_bank so a re-import finds the same exercise."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["lesson__sort_order", "id"]
        indexes = [models.Index(fields=["owner_teacher", "lesson"], name="exercise_owner_lesson_idx")]

    def __str__(self):
        revision = self.active_revision
        return revision.title if revision else f"Exercise {self.pk}"


class ExerciseRevision(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    class Scope(models.TextChoices):
        SINGLE = "single", "One skill"
        MIXED = "mixed", "Mixed skills"

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="revisions")
    number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    target_count = models.PositiveSmallIntegerField(help_text="Questions per session.")
    scope = models.CharField(max_length=16, choices=Scope.choices)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    source_version = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    required_skills = models.ManyToManyField(
        "curriculum.Skill", through="RevisionSkill", related_name="required_in_revisions"
    )

    class Meta:
        ordering = ["exercise", "number"]
        constraints = [
            models.UniqueConstraint(fields=["exercise", "number"], name="revision_unique_number"),
        ]

    def __str__(self):
        return f"{self.title} (rev {self.number})"

    @property
    def is_published(self):
        return self.state == self.State.PUBLISHED


class RevisionSkill(models.Model):
    revision = models.ForeignKey(ExerciseRevision, on_delete=models.CASCADE, related_name="skill_links")
    skill = models.ForeignKey("curriculum.Skill", on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["revision", "skill"], name="revisionskill_unique_pair"),
        ]


class Question(models.Model):
    class Format(models.TextChoices):
        TEXT = "text", "Text"
        FIGURE = "figure", "Figure and text"
        VIDEO = "video", "Video and text"

    class Difficulty(models.TextChoices):
        EASY = "easy", "Easy"
        MEDIUM = "medium", "Medium"
        HARD = "hard", "Hard"

    class ReviewStatus(models.TextChoices):
        DRAFT = "draft", "Draft, not yet checked"
        APPROVED = "approved", "Checked by a teacher"

    revision = models.ForeignKey(ExerciseRevision, on_delete=models.CASCADE, related_name="questions")
    item_key = models.CharField(max_length=40, help_text="Stable across revisions for the same item.")
    author_order = models.PositiveSmallIntegerField(help_text="The teacher's pool order.")
    format = models.CharField(max_length=16, choices=Format.choices, default=Format.TEXT)
    prompt = models.TextField()
    skill = models.ForeignKey("curriculum.Skill", on_delete=models.PROTECT, related_name="questions")
    difficulty = models.CharField(max_length=8, choices=Difficulty.choices)
    hint = models.TextField()
    explanation = models.TextField(blank=True)
    # A teacher's uploaded PNG/JPEG (served only to people allowed to see the question), or a static
    # file from the bank. Published questions keep their file even after later edits.
    figure_file = models.FileField(upload_to=figure_upload_to, max_length=255, blank=True)
    figure_path = models.CharField(max_length=255, blank=True, help_text="A static file, for bank questions.")
    figure_description = models.CharField(max_length=300, blank=True)
    video_id = models.CharField(max_length=32, blank=True)
    video_start_seconds = models.PositiveIntegerField(null=True, blank=True)
    junyi_template = models.CharField(max_length=8, blank=True, help_text="Closest Junyi template, e.g. T005.")
    difficulty_value = models.FloatField(
        null=True, blank=True, help_text="The template's real Junyi struggle rate, frozen at publication."
    )
    source_code = models.CharField(max_length=32, blank=True, help_text="The item's code in PathGen 3.0, if any.")
    review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT
    )

    class Meta:
        ordering = ["revision", "author_order"]
        constraints = [
            models.UniqueConstraint(fields=["revision", "item_key"], name="question_unique_item_key"),
            models.UniqueConstraint(fields=["revision", "author_order"], name="question_unique_order"),
            models.CheckConstraint(
                condition=models.Q(difficulty_value__isnull=True)
                | (models.Q(difficulty_value__gte=0) & models.Q(difficulty_value__lte=1)),
                name="question_difficulty_value_range",
            ),
        ]

    def __str__(self):
        return f"{self.item_key}: {self.prompt[:50]}"

    def correct_choice(self):
        return next((choice for choice in self.choices.all() if choice.is_correct), None)

    @property
    def has_figure(self):
        return bool(self.figure_file or self.figure_path)

    @property
    def video_embed_url(self):
        if not self.video_id:
            return ""
        start = f"&start={self.video_start_seconds}" if self.video_start_seconds else ""
        return f"https://www.youtube-nocookie.com/embed/{self.video_id}?rel=0&enablejsapi=1{start}"


class AnswerChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    position = models.PositiveSmallIntegerField()
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["question", "position"]
        constraints = [
            models.UniqueConstraint(fields=["question", "position"], name="choice_unique_position"),
            models.UniqueConstraint(
                fields=["question"], condition=models.Q(is_correct=True), name="choice_one_correct"
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1) & models.Q(position__lte=4), name="choice_position_range"
            ),
        ]

    def __str__(self):
        return f"{'ABCD'[self.position - 1]}) {self.text}"

    @property
    def letter(self):
        return "ABCD"[self.position - 1]


class ExerciseAssignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Unpublished"

    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="assignments")
    classroom = models.ForeignKey(
        "classrooms.Classroom", on_delete=models.PROTECT, related_name="exercise_assignments"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    published_at = models.DateTimeField()
    unpublished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["exercise", "classroom"]
        constraints = [
            models.UniqueConstraint(fields=["exercise", "classroom"], name="assignment_unique_class"),
        ]
        indexes = [models.Index(fields=["classroom", "status"], name="assignment_class_status_idx")]

    def __str__(self):
        return f"{self.exercise} -> {self.classroom}"


# ---- Phase 5: sessions, answers, mastery, decisions, feedback (docs/database.md) ----------------

class ExerciseSession(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exercise_sessions")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="sessions")
    revision = models.ForeignKey(ExerciseRevision, on_delete=models.PROTECT, related_name="sessions")
    classroom = models.ForeignKey("classrooms.Classroom", on_delete=models.PROTECT, related_name="exercise_sessions")
    attempt_number = models.PositiveSmallIntegerField(help_text="1 = first session, 2 = the one retake.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    target_count = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    first_try_correct = models.PositiveSmallIntegerField(null=True, blank=True)
    corrected_on_retry = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["student", "exercise", "attempt_number"]
        constraints = [
            models.UniqueConstraint(fields=["student", "exercise", "attempt_number"], name="session_unique_attempt"),
            models.CheckConstraint(condition=models.Q(attempt_number__in=[1, 2]), name="session_attempt_1_or_2"),
        ]
        indexes = [
            models.Index(fields=["student", "started_at"], name="session_student_time_idx"),
            models.Index(fields=["classroom", "exercise"], name="session_class_exercise_idx"),
        ]

    def __str__(self):
        return f"{self.student} / {self.exercise} / session {self.attempt_number}"

    @property
    def is_completed(self):
        return self.status == self.Status.COMPLETED


class SessionQuestion(models.Model):
    class Outcome(models.TextChoices):
        CORRECT_FIRST = "correct_first", "Right on the first try"
        CORRECT_RETRY = "correct_retry", "Right on the retry"
        WRONG_RETRY = "wrong_retry", "Wrong on both tries"
        WRONG_MOVED_ON = "wrong_moved_on", "Wrong, then moved on"

    session = models.ForeignKey(ExerciseSession, on_delete=models.CASCADE, related_name="items")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="served")
    position = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    shown_at = models.DateTimeField(null=True, blank=True)
    hint_revealed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    answer_seconds = models.FloatField(
        null=True, blank=True, help_text="Active answering time, retry included; empty when not measured."
    )
    video_seconds = models.FloatField(
        null=True, blank=True, help_text="Time the question's video played, kept apart from answer_seconds."
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True)

    class Meta:
        ordering = ["session", "position"]
        constraints = [
            models.UniqueConstraint(fields=["session", "position"], name="sessionquestion_unique_position"),
            models.UniqueConstraint(fields=["session", "question"], name="sessionquestion_unique_question"),
        ]
        indexes = [models.Index(fields=["completed_at"], name="sessionquestion_done_idx")]

    def __str__(self):
        return f"{self.session} #{self.position}"

    @property
    def is_completed(self):
        return self.completed_at is not None

    @property
    def hint_used(self):
        return self.hint_revealed_at is not None


class AnswerAttempt(models.Model):
    session_question = models.ForeignKey(SessionQuestion, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField()
    choice = models.ForeignKey(AnswerChoice, on_delete=models.PROTECT, related_name="+")
    is_correct = models.BooleanField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    active_seconds = models.FloatField(null=True, blank=True)
    video_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["session_question", "attempt_number"]
        constraints = [
            models.UniqueConstraint(fields=["session_question", "attempt_number"], name="attempt_unique_number"),
            models.CheckConstraint(condition=models.Q(attempt_number__in=[1, 2]), name="attempt_1_or_2"),
        ]


class StudentSkillMastery(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="skill_mastery")
    skill = models.ForeignKey("curriculum.Skill", on_delete=models.PROTECT, related_name="+")
    mastery_probability = models.FloatField()
    evidence_count = models.PositiveIntegerField(default=0)
    bkt_version = models.CharField(max_length=32)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "skill"], name="mastery_unique_student_skill"),
            models.CheckConstraint(
                condition=models.Q(mastery_probability__gte=0) & models.Q(mastery_probability__lte=1),
                name="mastery_probability_range",
            ),
        ]


class MasteryUpdate(models.Model):
    session_question = models.OneToOneField(SessionQuestion, on_delete=models.CASCADE, related_name="mastery_update")
    first_answer = models.OneToOneField(AnswerAttempt, on_delete=models.CASCADE, related_name="mastery_update")
    skill = models.ForeignKey("curriculum.Skill", on_delete=models.PROTECT, related_name="+")
    prior = models.FloatField()
    posterior = models.FloatField()
    next_mastery = models.FloatField()
    observation = models.BooleanField(help_text="The first answer was right.")
    bkt_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class SelectionDecision(models.Model):
    """Why each question was served, saved before it was answered (docs/r_learning.md)."""

    session_question = models.OneToOneField(SessionQuestion, on_delete=models.CASCADE, related_name="decision")
    created_at = models.DateTimeField(auto_now_add=True)
    policy_version = models.CharField(max_length=32)
    bkt_version = models.CharField(max_length=32, blank=True)
    agent_version = models.CharField(max_length=32, blank=True)
    feature_schema_version = models.CharField(max_length=32)
    difficulty_mapping_version = models.CharField(max_length=64, blank=True)
    rule = models.CharField(max_length=40, help_text="Which rule chose the question.")
    fallback_reason = models.CharField(max_length=80, blank=True)
    model_ready = models.BooleanField(default=False)
    chosen_skill_code = models.CharField(max_length=32)
    preferred_direction = models.CharField(max_length=8, blank=True, help_text="easier, harder or empty.")
    selected_inputs = models.JSONField(null=True, blank=True)
    predicted_struggle = models.FloatField(null=True, blank=True)
    selection_probability = models.FloatField(default=1.0)
    candidates = models.JSONField(default=list)
    context = models.JSONField(default=dict, help_text="Mastery, recent behavior and the inputs only logged.")


class ExerciseFeedback(models.Model):
    """The summary saved at completion. Local Qwen may later replace only its words (docs/rag.md)."""

    class Source(models.TextChoices):
        KNOWLEDGE = "knowledge", "Approved lesson knowledge"
        BASIC = "basic", "Built-in text"
        GENERATED = "generated", "Qwen, from approved lesson knowledge"

    class Generation(models.TextChoices):
        NONE = "none", "Not used (no approved knowledge for the focus skill)"
        PENDING = "pending", "Can be generated"
        CLAIMED = "claimed", "Generating"
        DONE = "done", "Generated"
        FAILED = "failed", "Failed; the saved text stays"

    session = models.OneToOneField(ExerciseSession, on_delete=models.CASCADE, related_name="feedback")
    focus_skill = models.ForeignKey(
        "curriculum.Skill", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    strength_skill = models.ForeignKey(
        "curriculum.Skill", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    review_url = models.CharField(max_length=255, blank=True)
    text = models.TextField()
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.BASIC)
    knowledge_version = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    fallback_text = models.TextField(blank=True, help_text="The deterministic text, kept if Qwen's replaces it.")
    generation = models.CharField(max_length=16, choices=Generation.choices, default=Generation.NONE)
    claimed_at = models.DateTimeField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    model_version = models.CharField(max_length=80, blank=True)
    generation_note = models.CharField(max_length=160, blank=True, help_text="Why generation failed, if it did.")
