"""Phase 4: exercises from the question bank (PLAN.md, Phase 4 "Done when")."""
import json
import tempfile
from pathlib import Path

from django.test import TestCase
from django.urls import reverse

from apps.curriculum.models import Lesson, Skill
from apps.practice import importer, services
from apps.practice.models import AnswerChoice, Exercise, ExerciseAssignment, ExerciseRevision, Question

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test


def import_for(teacher, classrooms, **kwargs):
    return importer.import_bank(teacher=teacher, classrooms=classrooms, **kwargs)


class ImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)

    def test_import_makes_one_published_exercise_per_lesson(self):
        report = import_for(self.teacher, [self.classroom])
        self.assertEqual(len(report), 6)
        self.assertEqual(Exercise.objects.filter(status="published").count(), 6)
        counts = {e.lesson.code: e.active_revision.target_count for e in Exercise.objects.select_related("lesson", "active_revision")}
        self.assertEqual(counts["integer_foundation"], 5)
        self.assertEqual(sum(counts.values()), 25)
        self.assertEqual(ExerciseAssignment.objects.filter(classroom=self.classroom, status="active").count(), 6)

    def test_every_question_is_complete(self):
        import_for(self.teacher, [self.classroom])
        questions = Question.objects.select_related("skill", "revision__exercise__lesson").prefetch_related("choices")
        self.assertGreaterEqual(questions.count(), 105)
        for question in questions:
            with self.subTest(item=question.item_key):
                choices = list(question.choices.all())
                self.assertEqual(len(choices), 4)
                self.assertEqual(sum(choice.is_correct for choice in choices), 1)
                self.assertIn(question.difficulty, ("easy", "medium", "hard"))
                self.assertTrue(question.hint.strip())
                self.assertTrue(question.junyi_template)
                self.assertIsNotNone(question.difficulty_value)
                self.assertTrue(question.revision.exercise.lesson.skill_links.filter(skill=question.skill).exists())

    def test_every_skill_has_each_difficulty(self):
        import_for(self.teacher, [self.classroom])
        for skill in Skill.objects.all():
            with self.subTest(skill=skill.code):
                levels = set(Question.objects.filter(skill=skill).values_list("difficulty", flat=True))
                self.assertEqual(levels, {"easy", "medium", "hard"})

    def test_difficulty_numbers_come_from_the_junyi_templates(self):
        import_for(self.teacher, [self.classroom])
        templates = json.loads(importer.DIFFICULTY_FILE.read_text(encoding="utf-8"))["templates"]
        for question in Question.objects.all()[:20]:
            self.assertAlmostEqual(question.difficulty_value, templates[question.junyi_template])

    def test_repeat_import_changes_nothing(self):
        import_for(self.teacher, [self.classroom])
        report = import_for(self.teacher, [self.classroom])
        self.assertEqual({outcome for _code, _revision, outcome in report}, {"unchanged"})
        self.assertEqual(ExerciseRevision.objects.count(), 6)

    def test_import_refuses_a_pool_that_cannot_cover_its_skills(self):
        bank = json.loads(importer.BANK_FILE.read_text(encoding="utf-8"))
        foundation = next(e for e in bank["exercises"] if e["lesson"] == "integer_foundation")
        foundation["questions"] = [q for q in foundation["questions"] if q["skill"] != "INT_OPPOSITE_POS4"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bank.json"
            path.write_text(json.dumps(bank), encoding="utf-8")
            with self.assertRaises(importer.ImportProblem) as caught:
                import_for(self.teacher, [self.classroom], bank_path=path)
        self.assertIn("No question in the pool covers Opposites", str(caught.exception))
        # All or nothing: the other five lessons weren't imported either.
        self.assertEqual(Exercise.objects.count(), 0)

    def test_import_refuses_another_teachers_class(self):
        other_class = make_class(make_teacher("other"), "Other")
        with self.assertRaises(importer.ImportProblem):
            import_for(self.teacher, [other_class])
        self.assertEqual(Exercise.objects.count(), 0)


class PoolRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)

    def _revision(self, lesson_code="integer_addition", count=2, required=("INT_ADD_NEG",)):
        exercise = Exercise.objects.create(owner_teacher=self.teacher, lesson=Lesson.objects.get(code=lesson_code))
        revision = ExerciseRevision.objects.create(exercise=exercise, number=1, title="Test", target_count=count,
                                                   scope="single" if len(required) == 1 else "mixed")
        for code in required:
            revision.skill_links.create(skill=Skill.objects.get(code=code))
        return revision

    def _question(self, revision, order, skill="INT_ADD_NEG", choices=4, correct=1, hint="Think."):
        question = Question.objects.create(revision=revision, item_key=f"K{order}", author_order=order,
                                           prompt="Compute 1 + (-2).", skill=Skill.objects.get(code=skill),
                                           difficulty="easy", hint=hint)
        for position in range(1, choices + 1):
            AnswerChoice.objects.create(question=question, position=position, text=f"c{position}",
                                        is_correct=position <= correct)
        return question

    def test_a_valid_pool_publishes_and_freezes(self):
        revision = self._revision()
        self._question(revision, 1)
        self._question(revision, 2)
        services.publish_revision(revision, [self.classroom], self.teacher)
        revision.refresh_from_db()
        self.assertTrue(revision.is_published)
        with self.assertRaises(services.PublishError):
            services.assert_editable(revision)

    def test_problems_are_caught_before_publication(self):
        revision = self._revision(count=3)
        self._question(revision, 1, choices=3)
        self._question(revision, 2, hint="")
        self._question(revision, 3, skill="INT_SUB_NEG")
        problems = " ".join(services.validate_revision(revision))
        self.assertIn("exactly four answer choices", problems)
        self.assertIn("needs a hint", problems)
        self.assertIn("Subtraction isn't part of Adding Integers", problems)
        with self.assertRaises(services.PublishError):
            services.publish_revision(revision, [self.classroom], self.teacher)

    def test_pool_smaller_than_the_session_is_refused(self):
        revision = self._revision(count=5)
        self._question(revision, 1)
        self.assertIn("The pool has 1 questions, but a session needs 5.", services.validate_revision(revision))

    def test_too_many_required_skills_for_the_count(self):
        revision = self._revision("integer_foundation", count=3,
                                  required=("INT_NUMBER_LINE", "INT_OPPOSITE_POS4", "INT_ABS_COMPARE", "INT_ORDER_NEG"))
        problems = services.validate_revision(revision)
        self.assertIn("4 required skills can't all fit in 3 questions.", problems)


class StudentAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.assigned = make_class(cls.teacher, "Assigned")
        cls.unassigned = make_class(cls.teacher, "Not assigned")
        cls.student = make_student(cls.assigned, "in_class")
        cls.outsider = make_student(cls.unassigned, "outsider")
        import_for(cls.teacher, [cls.assigned])
        cls.exercise = Exercise.objects.get(lesson__code="integer_addition")

    def test_assigned_students_see_the_cards_after_the_pretest(self):
        self.client.force_login(self.student)
        lesson_url = Lesson.objects.get(code="integer_addition").get_absolute_url()
        exercise_url = reverse("practice:exercise", args=[self.exercise.id])
        self.assertRedirects(self.client.get(exercise_url), reverse("dashboards:learn"))
        submit_test(self.student)
        response = self.client.get(lesson_url)
        self.assertContains(response, "Adding integers practice")
        self.assertContains(response, exercise_url)
        page = self.client.get(exercise_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "4 questions")
        journey = self.client.get(reverse("dashboards:learn"))
        self.assertContains(journey, "0 of 1 practice done")

    def test_unassigned_classes_do_not_see_them(self):
        submit_test(self.outsider)
        self.client.force_login(self.outsider)
        lesson = self.client.get(Lesson.objects.get(code="integer_addition").get_absolute_url())
        self.assertContains(lesson, "No practice is assigned for this lesson yet.")
        self.assertEqual(self.client.get(reverse("practice:exercise", args=[self.exercise.id])).status_code, 404)

    def test_unpublished_assignments_disappear_for_new_visits(self):
        submit_test(self.student)
        ExerciseAssignment.objects.filter(exercise=self.exercise).update(status="inactive")
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("practice:exercise", args=[self.exercise.id])).status_code, 404)

    def test_teacher_pool_view_is_owner_only(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("practice:teacher_exercise", args=[self.exercise.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hint:")
        self.assertContains(response, "Draft, not yet checked")
        self.client.force_login(make_teacher("someone_else"))
        self.assertEqual(self.client.get(reverse("practice:teacher_exercise", args=[self.exercise.id])).status_code, 404)
        self.assertContains(self.client.get(reverse("dashboards:teacher", args=["exercises"])), "No exercises yet.")


class ReviewSheetAndAdminTests(TestCase):
    def test_review_sheet_lists_every_question_with_its_answer(self):
        from io import StringIO

        from django.core.management import call_command

        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "review.html"
            call_command("export_bank_review", out=str(out), stdout=StringIO())
            page = out.read_text(encoding="utf-8")
        bank = json.loads(importer.BANK_FILE.read_text(encoding="utf-8"))
        total = sum(len(exercise["questions"]) for exercise in bank["exercises"])
        self.assertEqual(page.count('class="q"'), total + 10)  # plus the 10 feedback texts
        self.assertEqual(page.count("✓ answer"), total)

    def test_django_admin_pages_open_for_the_superuser(self):
        seed_all()
        teacher = make_teacher()
        import_for(teacher, [make_class(teacher)])
        from .helpers import make_admin

        self.client.force_login(make_admin())
        for name in ("practice_question", "practice_exercise", "assessments_assessmentform",
                     "assessments_assessmentattempt", "classrooms_classroom", "curriculum_skill"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(f"admin:{name}_changelist")).status_code, 200)
        question = Question.objects.first()
        self.assertEqual(self.client.get(reverse("admin:practice_question_change", args=[question.id])).status_code, 200)
