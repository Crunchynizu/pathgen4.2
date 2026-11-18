"""manage.py import_bank --teacher <username> --class "<class name>" [--class ...]

Loads content/question_bank.json as one published exercise per lesson, owned by the teacher
and assigned to the named classes (which must be theirs). Refuses the whole import if any pool
fails the publication checks. Safe to repeat.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.classrooms.models import Classroom
from apps.practice.importer import BANK_FILE, DIFFICULTY_FILE, ImportProblem, import_bank

User = get_user_model()


class Command(BaseCommand):
    help = "Import the question bank as published exercises for a teacher's classes."

    def add_arguments(self, parser):
        parser.add_argument("--teacher", required=True)
        parser.add_argument("--class", dest="classes", action="append", required=True,
                            help="A class name of that teacher. Repeat for more classes.")
        parser.add_argument("--file", default=str(BANK_FILE))
        parser.add_argument("--difficulty", default=str(DIFFICULTY_FILE))
        parser.add_argument("--only", action="append", help="Import only this lesson code. Repeatable.")

    def handle(self, *args, **options):
        try:
            teacher = User.objects.get(username=options["teacher"], role=User.Role.TEACHER)
        except User.DoesNotExist as error:
            raise CommandError(f"No teacher account named {options['teacher']!r}.") from error
        classrooms = []
        for name in options["classes"]:
            classroom = Classroom.objects.filter(teacher=teacher, name__iexact=name.strip()).first()
            if classroom is None:
                raise CommandError(f"{teacher.username} has no class named {name!r}.")
            classrooms.append(classroom)

        try:
            report = import_bank(
                teacher=teacher,
                classrooms=classrooms,
                bank_path=options["file"],
                difficulty_path=options["difficulty"],
                only=options["only"],
            )
        except ImportProblem as error:
            raise CommandError("Nothing was imported:\n- " + "\n- ".join(error.problems)) from error

        drafts = 0
        for lesson_code, revision, outcome in report:
            count = revision.questions.count()
            drafts += revision.questions.filter(review_status="draft").count()
            self.stdout.write(
                f"{lesson_code}: {revision.title}, rev {revision.number} ({outcome}), "
                f"{count} questions, {revision.target_count} per session"
            )
        names = ", ".join(classroom.name for classroom in classrooms)
        self.stdout.write(self.style.SUCCESS(f"Assigned to: {names}"))
        if drafts:
            self.stdout.write(self.style.WARNING(
                f"{drafts} questions are still drafts, not yet checked by a math teacher."
            ))
