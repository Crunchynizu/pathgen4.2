from django.core.management.base import BaseCommand, CommandError

from apps.assessments.models import AssessmentForm
from apps.assessments.seed import SeedError, seed_locked_test
from apps.assessments.services import coverage


class Command(BaseCommand):
    help = "Load the locked 30-item test as the published pretest and posttest. Safe to repeat."

    def handle(self, *args, **options):
        try:
            results = seed_locked_test()
        except SeedError as error:
            raise CommandError(str(error)) from error
        for kind, result in results.items():
            self.stdout.write(f"{kind}: {result}")
        form = AssessmentForm.objects.get(kind="pretest", revision=1)
        _counts, missing = coverage(form)
        if missing:
            names = ", ".join(skill.short_name for skill in missing)
            self.stdout.write(self.style.WARNING(f"Not measured by the locked test: {names} (reported, not enforced)."))
        self.stdout.write(self.style.SUCCESS("Pretest and posttest ready."))
