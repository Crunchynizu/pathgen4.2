"""Shared pretest and posttest (docs/database.md, "Assessments").

The study uses the locked 30-item test for both forms (PLAN.md, "Settled").
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Kind(models.TextChoices):
    PRETEST = "pretest", "Pretest"
    POSTTEST = "posttest", "Posttest"


class AssessmentForm(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    revision = models.PositiveSmallIntegerField(default=1)
    title = models.CharField(max_length=160)
    state = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    locked = models.BooleanField(
        default=False, help_text="The approved locked test. Its items are never edited in the app."
    )
    source = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kind", "-revision"]
        constraints = [
            models.UniqueConstraint(fields=["kind", "revision"], name="assessmentform_unique_revision"),
            models.UniqueConstraint(
                fields=["kind"],
                condition=models.Q(state="published"),
                name="assessmentform_one_published_per_kind",
            ),
        ]

    def __str__(self):
        return f"{self.title} (rev {self.revision})"


class AssessmentItem(models.Model):
    form = models.ForeignKey(AssessmentForm, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField()
    skill = models.ForeignKey("curriculum.Skill", on_delete=models.PROTECT, related_name="assessment_items")
    prompt = models.TextField()
    choice_a = models.CharField(max_length=255)
    choice_b = models.CharField(max_length=255)
    choice_c = models.CharField(max_length=255)
    choice_d = models.CharField(max_length=255)
    correct_index = models.PositiveSmallIntegerField(help_text="0 = A, 1 = B, 2 = C, 3 = D. Server only.")
    source_code = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["form", "position"]
        constraints = [
            models.UniqueConstraint(fields=["form", "position"], name="assessmentitem_unique_position"),
            models.CheckConstraint(condition=models.Q(correct_index__lte=3), name="assessmentitem_index_range"),
        ]

    def __str__(self):
        return f"{self.form.kind} #{self.position}"

    @property
    def choices(self):
        return [self.choice_a, self.choice_b, self.choice_c, self.choice_d]


class ClassAssessmentRelease(models.Model):
    """The teacher opened the posttest for this class. One per class in the v1 unit."""

    classroom = models.OneToOneField(
        "classrooms.Classroom", on_delete=models.PROTECT, related_name="posttest_release"
    )
    posttest_form = models.ForeignKey(AssessmentForm, on_delete=models.PROTECT, related_name="releases")
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    opened_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Posttest open for {self.classroom}"


class AssessmentAttempt(models.Model):
    class State(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assessment_attempts"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    form = models.ForeignKey(AssessmentForm, on_delete=models.PROTECT, related_name="attempts")
    classroom = models.ForeignKey(
        "classrooms.Classroom", on_delete=models.PROTECT, related_name="assessment_attempts"
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.IN_PROGRESS)
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    correct_count = models.PositiveSmallIntegerField(null=True, blank=True)
    item_count = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["student", "kind"]
        constraints = [
            models.UniqueConstraint(fields=["student", "kind"], name="assessmentattempt_one_per_kind"),
        ]
        indexes = [models.Index(fields=["classroom", "kind"], name="attempt_class_kind_idx")]

    def __str__(self):
        return f"{self.student} {self.kind} ({self.state})"

    @property
    def is_submitted(self):
        return self.state == self.State.SUBMITTED

    @property
    def percent(self):
        if not self.is_submitted or not self.item_count:
            return None
        return round(100 * self.correct_count / self.item_count, 1)


class AssessmentAnswer(models.Model):
    attempt = models.ForeignKey(AssessmentAttempt, on_delete=models.CASCADE, related_name="answers")
    item = models.ForeignKey(AssessmentItem, on_delete=models.PROTECT, related_name="answers")
    selected_index = models.PositiveSmallIntegerField(null=True, blank=True)
    last_saved_at = models.DateTimeField(auto_now=True)
    is_correct = models.BooleanField(null=True, blank=True, help_text="Set by the server on final submission.")

    class Meta:
        ordering = ["attempt", "item__position"]
        constraints = [
            models.UniqueConstraint(fields=["attempt", "item"], name="assessmentanswer_unique_item"),
            models.CheckConstraint(
                condition=models.Q(selected_index__isnull=True) | models.Q(selected_index__lte=3),
                name="assessmentanswer_index_range",
            ),
        ]
