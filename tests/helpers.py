"""Small builders shared by the phase tests."""
from django.contrib.auth import get_user_model

from apps.assessments import services as assessment_services
from apps.assessments.models import Kind
from apps.assessments.seed import seed_locked_test
from apps.classrooms import services
from apps.curriculum.seed import seed_curriculum

User = get_user_model()
PASSWORD = "test-pass-4821"


def seed_all():
    seed_curriculum()
    seed_locked_test()


def make_admin(username="admin1"):
    return User.objects.create_superuser(username, password=PASSWORD)


def make_teacher(username="teacher1"):
    return services.create_teacher(username=username, password=PASSWORD, display_name=username.title())


def make_class(teacher, name="Grade 7 A"):
    return services.create_classroom(name=name, teacher=teacher)


def make_student(classroom, username="student1"):
    return services.create_student(username=username, password=PASSWORD, display_name=username.title(),
                                   classroom=classroom)


def answer_all(attempt, right=None):
    """Answer every item: correct for the first `right` items (all if None), wrong after."""
    selections = {}
    for number, item in enumerate(attempt.form.items.order_by("position")):
        correct = right is None or number < right
        selections[str(item.id)] = item.correct_index if correct else (item.correct_index + 1) % 4
    return selections


def submit_test(student, kind=Kind.PRETEST, right=None):
    attempt = assessment_services.start_attempt(student, kind)
    assessment_services.save_answers(attempt, answer_all(attempt, right))
    return assessment_services.submit_attempt(attempt)
