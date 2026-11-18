"""Labeled demo accounts for local checks and the groupmate/adviser walk-through.

    manage.py seed_demo --password <a password for all demo accounts>

Makes (or keeps) demo_admin, "Demo Teacher" (demo_teacher), the class "DEMO class (not real students)" with
three students demo_s1..demo_s3, and imports the question bank for that class. Real study
accounts come from create_study_class on a fresh database, never from this command.
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.classrooms import services
from apps.classrooms.models import Classroom

User = get_user_model()
CLASS_NAME = "DEMO class (not real students)"


class Command(BaseCommand):
    help = "Create labeled demo accounts and give their class the question bank. Safe to repeat."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for every new demo account.")

    def handle(self, *args, **options):
        password = options["password"]
        with transaction.atomic():
            if not User.objects.filter(username="demo_admin").exists():
                User.objects.create_superuser("demo_admin", password=password, display_name="Demo Admin")
            teacher = User.objects.filter(username="demo_teacher").first()
            if teacher is None:
                teacher = services.create_teacher(username="demo_teacher", password=password,
                                                  display_name="Demo Teacher")
            classroom = Classroom.objects.filter(teacher=teacher, name=CLASS_NAME).first()
            if classroom is None:
                classroom = services.create_classroom(name=CLASS_NAME, teacher=teacher)
            for number in range(1, 4):
                username = f"demo_s{number}"
                if not User.objects.filter(username=username).exists():
                    services.create_student(username=username, password=password,
                                            display_name=f"Demo Student {number}", classroom=classroom)
        call_command("import_bank", teacher="demo_teacher", classes=[CLASS_NAME], stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS(
            "Demo ready: demo_admin, demo_teacher, demo_s1, demo_s2, demo_s3 (new accounts use the password you gave)."
        ))
