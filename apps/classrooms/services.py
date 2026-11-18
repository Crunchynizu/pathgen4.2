"""Account and class provisioning. Every write checks roles across tables (docs/database.md)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Classroom, StudentProfile

User = get_user_model()


def _new_user(*, username, password, display_name, role):
    username = username.strip()
    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({"username": "That username is taken."})
    user = User(username=username, display_name=display_name.strip(), role=role)
    validate_password(password, user)
    user.set_password(password)
    user.full_clean(exclude=["password"])
    user.save()
    return user


@transaction.atomic
def create_teacher(*, username, password, display_name):
    return _new_user(username=username, password=password, display_name=display_name, role=User.Role.TEACHER)


@transaction.atomic
def create_classroom(*, name, teacher):
    if not teacher.is_teacher:
        raise ValidationError({"teacher": "Choose a teacher account."})
    name = name.strip()
    if Classroom.objects.filter(teacher=teacher, name__iexact=name).exists():
        raise ValidationError({"name": "This teacher already has a class with that name."})
    return Classroom.objects.create(name=name, teacher=teacher)


@transaction.atomic
def create_student(*, username, password, display_name, classroom):
    """The account and its profile are made together, or not at all."""
    user = _new_user(username=username, password=password, display_name=display_name, role=User.Role.STUDENT)
    StudentProfile.objects.create(user=user, classroom=classroom)
    return user


def classroom_of(student):
    """The student's one class, or None if the account has no profile."""
    profile = StudentProfile.objects.select_related("classroom__teacher").filter(user=student).first()
    return profile.classroom if profile else None


def teacher_classrooms(teacher):
    return Classroom.objects.filter(teacher=teacher)
