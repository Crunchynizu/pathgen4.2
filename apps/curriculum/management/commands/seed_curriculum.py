from django.core.management.base import BaseCommand

from apps.curriculum.seed import seed_curriculum


class Command(BaseCommand):
    help = "Create or update the 6 lessons, 10 skills, lesson scopes and prerequisites. Safe to repeat."

    def handle(self, *args, **options):
        counts = seed_curriculum()
        self.stdout.write(
            self.style.SUCCESS(
                "Curriculum ready: {lessons} lessons, {skills} skills, {lesson_skills} lesson-skill links, "
                "{prerequisites} prerequisite links.".format(**counts)
            )
        )
