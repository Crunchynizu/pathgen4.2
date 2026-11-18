"""Classes and student profiles (docs/database.md, "Accounts, classes, curriculum").

Role checks that span tables live in services.py, as the spec asks.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Classroom(models.Model):
    name = models.CharField(max_length=120)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="classrooms",
        limit_choices_to={"role": "teacher"},
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["teacher", "name"], name="classroom_name_unique_per_teacher"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.teacher_id and not self.teacher.is_teacher:
            raise ValidationError({"teacher": "The class teacher must have a teacher account."})


class StudentProfile(models.Model):
    """A student belongs to exactly one class. Made together with the account (services.py)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="student_profile",
        limit_choices_to={"role": "student"},
    )
    classroom = models.ForeignKey(Classroom, on_delete=models.PROTECT, related_name="students")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["classroom", "user__username"]

    def __str__(self):
        return f"{self.user} ({self.classroom})"

    def clean(self):
        if self.user_id and not self.user.is_student:
            raise ValidationError({"user": "Only student accounts can have a student profile."})
