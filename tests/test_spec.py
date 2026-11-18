"""The spec's inventory (docs/pages.md, docs/modals.md, docs/file_structure.md, docs/tech_stack.md):
every main template, every required dialog, the deploy files, and the charts with their tables."""
import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from apps.practice.importer import import_bank

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test

BASE = Path(settings.BASE_DIR)
MAIN_TEMPLATES = [
    "accounts/login.html", "accounts/profile.html", "dashboards/admin_dashboard.html",
    "dashboards/teacher_dashboard.html", "practice/exercise_editor.html", "dashboards/student_dashboard.html",
    "lessons/integer_foundation.html", "lessons/integer_addition.html", "lessons/integer_subtraction.html",
    "lessons/integer_multiplication.html", "lessons/integer_division.html",
    "lessons/integer_expressions_applications.html", "practice/exercise.html", "assessments/assessment.html",
]
# docs/modals.md, the 11 required dialogs, by the id each one has on its page.
REQUIRED_DIALOGS = {
    "create_teacher.html": "dialog-create-teacher", "create_class.html": "dialog-create-class",
    "create_student.html": "dialog-create-student", "publish_exercise.html": "dialog-publish",
    "delete_exercise.html": "dialog-delete", "unpublish_exercise.html": "dialog-unpublish",
    "open_posttest.html": "dialog-open-posttest", "start_assessment.html": "dialog-start-assessment",
    "submit_assessment.html": "dialog-submit-assessment", "start_retake.html": "dialog-retake",
    "discard_changes.html": "dialog-discard",
}


class InventoryTests(TestCase):
    def test_all_14_main_templates_exist(self):
        for name in MAIN_TEMPLATES:
            self.assertTrue((BASE / "templates" / name).exists(), name)

    def test_all_11_required_dialogs_exist(self):
        folder = BASE / "templates" / "includes" / "dialogs"
        for name, dialog_id in REQUIRED_DIALOGS.items():
            text = (folder / name).read_text(encoding="utf-8")
            self.assertIn(f'id="{dialog_id}"', text, name)

    def test_repository_files_of_the_spec(self):
        for name in ("HANDOFF.md", "AGENTS.md", "README.md", ".env.example", ".dockerignore", "Dockerfile", "compose.yaml",
                     "railway.toml", "deploy/llm/Dockerfile", "scripts/fetch_llm.py",
                     "content/lesson_knowledge.example.json", "learning/feedback/llm.py",
                     "learning/feedback/service.py", "learning/feedback/retrieval.py"):
            self.assertTrue((BASE / name).exists(), name)
        self.assertEqual(len(list((BASE / "docs").glob("*.md"))), 13)
        dockerfile = (BASE / "deploy" / "llm" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db", dockerfile)

    def test_browser_libraries_are_checked_in_no_npm(self):
        self.assertTrue((BASE / "static/vendor/chartjs-4.6.1/chart.umd.min.js").exists())
        self.assertTrue((BASE / "static/vendor/animateicons-0.2.0/lucide.js").exists())
        self.assertFalse((BASE / "package.json").exists())


class ChartTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher("t_charts")
        cls.classroom = make_class(cls.teacher, "Grade 7 - Charts")
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom], only=["integer_division"])
        cls.students = [make_student(cls.classroom, f"c{n}") for n in range(3)]
        for number, student in enumerate(cls.students):
            submit_test(student, right=10 + number)
        from apps.assessments.services import open_posttest
        open_posttest(cls.classroom, cls.teacher)
        for number, student in enumerate(cls.students[:2]):
            submit_test(student, kind="posttest", right=20 + number)

    def test_class_page_has_both_charts_and_their_tables(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("dashboards:teacher_class", args=[self.classroom.id]))
        self.assertContains(page, 'data-chart="chart-gaps"')
        self.assertContains(page, 'data-chart="chart-scores"')
        self.assertContains(page, "chartjs-4.6.1/chart.umd.min.js")
        self.assertContains(page, "for the 2 students who submitted both tests")
        data = json.loads(json.dumps(page.context["charts"]))
        self.assertEqual(len(data["gaps"]["labels"]), 10)
        self.assertEqual([s["label"] for s in data["scores"]["series"]], ["Pretest", "Posttest"])
        rows = page.context["by_skill"]
        self.assertTrue(all(0 <= row["pre"] <= 100 and 0 <= row["post"] <= 100 for row in rows))
        self.assertContains(page, "<caption class=\"sr-only\">Pretest and posttest percent correct by skill")

    def test_icons_are_decorative(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("dashboards:teacher", args=["overview"]))
        self.assertContains(page, '<animate-icons class="icon" name="layout-dashboard" size="20" aria-hidden="true">')
        self.assertContains(page, "<span>Overview</span>")
