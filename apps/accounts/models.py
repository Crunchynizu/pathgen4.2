"""One user model for every role (docs/database.md, "Accounts, classes, curriculum")."""
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class PathgenUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Django's own superuser is also the application admin.
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    # No default: every account gets an explicit role.
    role = models.CharField(max_length=16, choices=Role.choices)
    display_name = models.CharField(max_length=150, blank=True)

    objects = PathgenUserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["admin", "teacher", "student"]),
                name="accounts_user_role_valid",
            ),
        ]

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_app_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT
