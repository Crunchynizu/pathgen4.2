"""Phase 7: teacher results, the study export and analysis (PLAN.md, Phase 7)."""
import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.assessments.models import Kind
from apps.assessments.services import open_posttest
from apps.practice import engine
from apps.practice.importer import import_bank
from apps.practice.models import Exercise, ExerciseSession
from learning import stats

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test


class StatsTests(SimpleTestCase):
    def test_paired_t_matches_scipy(self):
        result = stats.paired([50, 60, 70, 80, 45, 90], [60, 65, 80, 85, 50, 88])
        self.assertAlmostEqual(result["t"], 3.0508510792387598, places=10)   # scipy.stats.ttest_rel
        self.assertAlmostEqual(result["p"], 0.028396725127640413, places=10)
        self.assertAlmostEqual(stats.t_critical(10), 2.2281388519649385, places=8)

    def test_gain_brier_auc(self):
        self.assertAlmostEqual(stats.normalized_gain(40, 70), 0.5)
        self.assertIsNone(stats.normalized_gain(100, 100))
        self.assertAlmostEqual(stats.brier([0.2, 0.8], [0, 1]), 0.04)
        self.assertEqual(stats.auc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]), 0.75)


def finish(student, exercise, right):
    engine.start(student, exercise)
    session = ExerciseSession.objects.get(student=student, exercise=exercise, attempt_number=1)
    for number in range(session.target_count):
        item = engine.current_item(session)
        ok = number < right
        choice = item.question.choices.get(is_correct=True) if ok else item.question.choices.filter(is_correct=False).first()
        engine.answer(session, item.id, choice.id, active_seconds=8)
        if not ok:
            engine.reveal_hint(session, item.id)
            engine.answer(session, item.id, item.question.choices.get(is_correct=True).id, active_seconds=5)
    return session


class TeacherResultsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher, "7-Rizal")
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom])
        cls.division = Exercise.objects.get(lesson__code="integer_division")
        cls.student = make_student(cls.classroom, "ana")
        submit_test(cls.student, right=12)
        finish(cls.student, cls.division, right=1)

    def test_class_page_shows_practice_and_skill_gaps(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("dashboards:teacher_class", args=[self.classroom.id]))
        self.assertContains(page, "1 of 6")
        self.assertContains(page, "1/4")
        self.assertContains(page, "Skill gaps")
        self.assertContains(page, "<td>Division</td><td><strong>1</strong></td>", html=False)

    def test_student_page_shows_sessions_and_mastery(self):
        self.client.force_login(self.teacher)
        page = self.client.get(reverse("dashboards:teacher_student", args=[self.classroom.id, self.student.id]))
        self.assertContains(page, "Dividing integers practice")
        self.assertContains(page, "1/4")
        self.assertContains(page, "mastery 0.")


class ExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher, "7-Rizal")
        cls.demo = make_class(cls.teacher, "DEMO class")
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom])
        division = Exercise.objects.get(lesson__code="integer_division")
        open_posttest(cls.classroom, cls.teacher)
        for number, (pre, post) in enumerate([(10, 20), (15, 18), (12, 21)], start=1):
            student = make_student(cls.classroom, f"real{number}")
            submit_test(student, right=pre)
            finish(student, division, right=number)
            submit_test(student, kind=Kind.POSTTEST, right=post)
        make_student(cls.demo, "demo_kid")

    def test_export_writes_pseudonymous_files_and_a_report(self):
        with tempfile.TemporaryDirectory() as folder:
            call_command("export_study_data", out=folder, stdout=StringIO())
            files = {p.name for p in Path(folder).iterdir()}
            self.assertTrue({"students.csv", "assessment_answers.csv", "practice_answers.csv", "trainer_update.csv",
                             "agent_retrain.csv", "pseudonym_key.csv", "report.md", "README.txt"} <= files)
            with open(Path(folder) / "students.csv", encoding="utf-8-sig") as handle:
                students = list(csv.DictReader(handle))
            self.assertEqual([row["student_key"] for row in students], ["S001", "S002", "S003"])  # demo left out
            self.assertEqual([row["change_points"] for row in students], ["33.3", "10.0", "30.0"])
            text = (Path(folder) / "students.csv").read_text(encoding="utf-8-sig")
            self.assertNotIn("real1", text)
            with open(Path(folder) / "practice_answers.csv", encoding="utf-8-sig") as handle:
                practice = list(csv.DictReader(handle))
            self.assertEqual(len(practice), 12)
            self.assertTrue(all(row["struggle"] in ("0", "1") for row in practice))
            self.assertNotIn("_inputs", practice[0])
            with open(Path(folder) / "agent_retrain.csv", encoding="utf-8-sig") as handle:
                retrain = list(csv.DictReader(handle))
            # Each student's first-ever question has no history, so it has no row (docs/agent.md).
            self.assertEqual(len(retrain), 12 - 3)
            self.assertIn("recent_median_duration_sec", retrain[0])
            self.assertTrue(all(row["struggle_on_next_question"] in ("0", "1") for row in retrain))
            with open(Path(folder) / "assessment_answers.csv", encoding="utf-8-sig") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 3 * 60)
            report = (Path(folder) / "report.md").read_text(encoding="utf-8")
            self.assertIn("With both tests submitted: 3", report)
            self.assertIn("Paired t", report)
            self.assertIn("| AUC |", report)
