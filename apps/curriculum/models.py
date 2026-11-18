"""The fixed curriculum: 6 lessons, 10 skills, scopes and prerequisites (docs/system.md).

Rows are created by `manage.py seed_curriculum`, keyed by their stable codes.
"""
from django.db import models
from django.urls import reverse


def skill_anchor(code):
    """Section anchor on a lesson page: "skill-" + lowercase code, "_" -> "-" (docs/file_structure.md)."""
    return "skill-" + code.lower().replace("_", "-")


class Lesson(models.Model):
    class ContentStatus(models.TextChoices):
        PLACEHOLDER = "placeholder", "Placeholder"
        DELIVERED = "delivered", "Delivered"

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(unique=True)
    template_name = models.CharField(max_length=120)
    content_status = models.CharField(
        max_length=16, choices=ContentStatus.choices, default=ContentStatus.PLACEHOLDER
    )
    summary = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("curriculum:lesson", args=[self.code])

    def taught_skills(self):
        return Skill.objects.filter(
            lesson_links__lesson=self, lesson_links__scope=LessonSkill.Scope.TAUGHT
        ).order_by("sort_order")


class Skill(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    short_name = models.CharField(max_length=60)
    sort_order = models.PositiveSmallIntegerField(unique=True)
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.PROTECT,
        related_name="canonical_skills",
        help_text="The lesson that teaches this skill.",
    )

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.short_name

    @property
    def anchor(self):
        return skill_anchor(self.code)

    def review_url(self):
        return f"{self.lesson.get_absolute_url()}#{self.anchor}"


class LessonSkill(models.Model):
    class Scope(models.TextChoices):
        TAUGHT = "taught", "Taught"
        REVIEW = "review", "Cumulative review"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="skill_links")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="lesson_links")
    scope = models.CharField(max_length=16, choices=Scope.choices)

    class Meta:
        ordering = ["lesson__sort_order", "skill__sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["lesson", "skill"], name="lessonskill_unique_pair"),
        ]

    def __str__(self):
        return f"{self.lesson.code}: {self.skill.code} ({self.scope})"


class SkillPrerequisite(models.Model):
    """A review suggestion, not an access rule: practise `prerequisite` before `skill`."""

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="prerequisite_links")
    prerequisite = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="dependent_links")

    class Meta:
        ordering = ["skill__sort_order", "prerequisite__sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["skill", "prerequisite"], name="prerequisite_unique_pair"),
            models.CheckConstraint(
                condition=~models.Q(skill=models.F("prerequisite")), name="prerequisite_not_self"
            ),
        ]

    def __str__(self):
        return f"{self.prerequisite.code} -> {self.skill.code}"

    def review_url(self):
        """The review section on the prerequisite's own lesson."""
        return self.prerequisite.review_url()
