"""Phase 6: lesson pages and feedback (PLAN.md, Phase 6 "Done when")."""
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.curriculum.models import Lesson, Skill
from apps.practice import engine, feedback
from apps.practice.importer import import_bank
from apps.practice.models import Exercise, ExerciseFeedback, ExerciseSession
from learning.feedback.retrieval import KnowledgeError, load

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test

LOCKED = Path(__file__).resolve().parent.parent / "content" / "locked_test.json"


class LessonPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.student = make_student(make_class(cls.teacher))
        submit_test(cls.student)

    def test_all_six_pages_show_their_content_and_anchors(self):
        self.client.force_login(self.student)
        for lesson in Lesson.objects.all():
            with self.subTest(lesson=lesson.code):
                page = self.client.get(lesson.get_absolute_url())
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, "2-minute recap")
                self.assertContains(page, "js/lesson.js")
                self.assertNotContains(page, "The full lesson is on its way")
                for skill in lesson.taught_skills():
                    self.assertContains(page, f'id="{skill.anchor}"', count=1)

    def test_pages_do_not_teach_the_posttest_items(self):
        """3.0's lesson examples repeated posttest items 16 and 18; 4.2's pages must not."""
        items = json.loads(LOCKED.read_text(encoding="utf-8"))["items"]
        self.client.force_login(self.student)
        html = " ".join(self.client.get(l.get_absolute_url()).content.decode() for l in Lesson.objects.all())
        for item in items:
            expression = re.sub(r"^[A-Za-z :,]+", "", item["prompt"]).strip(" ?.=")
            if len(expression) >= 12 and any(ch.isdigit() for ch in expression):
                self.assertNotIn(expression, html, item["source_code"])
        self.assertNotIn("-7 degrees", html)


class KnowledgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()

    def lesson_of_skill(self):
        return dict(Skill.objects.values_list("code", "lesson__code"))

    def test_the_draft_file_is_valid_and_its_sections_exist(self):
        entries, version = load(feedback.KNOWLEDGE_FILE, self.lesson_of_skill())
        self.assertEqual(len(entries), 10)
        self.assertTrue(version)
        self.client.force_login(make_teacher())
        for code, entry in entries.items():
            page = self.client.get(reverse("curriculum:lesson", args=[entry.lesson_code]))
            self.assertContains(page, f'id="{entry.section_id}"')

    def test_bad_files_are_refused(self):
        good = json.loads(feedback.KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        cases = {
            "wrong lesson": lambda d: d["entries"][0].update(lesson_code="integer_division"),
            "bad anchor": lambda d: d["entries"][0].update(section_id="skill-nope"),
            "duplicate": lambda d: d["entries"].append(dict(d["entries"][0])),
            "empty text": lambda d: d["entries"][0].update(explanation=" "),
            "schema": lambda d: d.update(schema_version=2),
        }
        for name, change in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder:
                data = json.loads(json.dumps(good))
                change(data)
                path = Path(folder) / "k.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(KnowledgeError):
                    load(path, self.lesson_of_skill())


class ResultsFeedbackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom])
        cls.exercise = Exercise.objects.get(lesson__code="integer_subtraction")

    def setUp(self):
        feedback.knowledge.cache_clear()
        self.student = make_student(self.classroom, f"f{self._testMethodName[-14:]}")
        submit_test(self.student)
        self.client.force_login(self.student)

    def tearDown(self):
        feedback.knowledge.cache_clear()

    def run_session(self, right):
        engine.start(self.student, self.exercise)
        session = ExerciseSession.objects.get(student=self.student, exercise=self.exercise)
        for number in range(session.target_count):
            item = engine.current_item(session)
            ok = number < right
            choice = item.question.choices.get(is_correct=True) if ok else item.question.choices.filter(is_correct=False).first()
            engine.answer(session, item.id, choice.id)
            if not ok:
                engine.move_on(session, item.id)
        session.refresh_from_db()
        return session

    def test_results_use_the_approved_knowledge(self):
        session = self.run_session(right=1)
        saved = ExerciseFeedback.objects.get(session=session)
        self.assertEqual(saved.source, "knowledge")
        self.assertEqual(saved.focus_skill.code, "INT_SUB_NEG")
        self.assertIn("add its opposite", saved.text)
        self.assertTrue(saved.review_url.endswith("#skill-int-sub-neg"))
        page = self.client.get(reverse("practice:exercise", args=[self.exercise.id]))
        self.assertContains(page, "1<span>/4</span>")
        self.assertContains(page, "Review Subtraction in the lesson")

    def test_results_work_without_the_knowledge_file(self):
        with mock.patch.object(feedback, "KNOWLEDGE_FILE", Path("does-not-exist.json")):
            session = self.run_session(right=4)
        saved = ExerciseFeedback.objects.get(session=session)
        self.assertEqual(saved.source, "basic")
        self.assertIn("4 right on the first try", saved.text)
        self.assertContains(self.client.get(reverse("practice:exercise", args=[self.exercise.id])), "4<span>/4</span>")

    def test_feedback_is_saved_once(self):
        session = self.run_session(right=2)
        first = ExerciseFeedback.objects.get(session=session)
        again = feedback.save_for(session, engine.mastery_of(self.student))
        self.assertEqual(first.pk, again.pk)
