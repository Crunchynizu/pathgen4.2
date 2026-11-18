"""Phase 3: pretest/posttest and the journey gate (docs/build_order.md and PLAN.md, "Done when")."""
from django.test import TestCase
from django.urls import reverse

from apps.assessments import services
from apps.assessments.models import AssessmentAttempt, AssessmentForm, ClassAssessmentRelease, Kind
from apps.assessments.seed import seed_locked_test
from apps.curriculum.models import Lesson

from .helpers import answer_all, make_class, make_student, make_teacher, seed_all, submit_test


class LockedTestSeedTests(TestCase):
    def test_both_forms_hold_the_locked_30_items(self):
        seed_all()
        for kind in (Kind.PRETEST, Kind.POSTTEST):
            form = AssessmentForm.objects.get(kind=kind, state="published")
            self.assertTrue(form.locked)
            self.assertEqual(form.items.count(), 30)
        self.assertEqual(seed_locked_test(), {"pretest": "unchanged", "posttest": "unchanged"})

    def test_coverage_reports_opposites_as_not_measured(self):
        seed_all()
        _counts, missing = services.coverage(AssessmentForm.objects.get(kind=Kind.PRETEST))
        self.assertEqual([skill.code for skill in missing], ["INT_OPPOSITE_POS4"])


class JourneyGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)
        cls.student = make_student(cls.classroom)

    def setUp(self):
        self.client.force_login(self.student)

    def test_lessons_stay_locked_until_the_pretest_is_submitted(self):
        lesson = Lesson.objects.get(code="integer_addition")
        self.assertRedirects(self.client.get(lesson.get_absolute_url()), reverse("dashboards:learn"))
        journey = self.client.get(reverse("dashboards:learn"))
        self.assertContains(journey, "Start the pretest")
        self.assertContains(journey, "Opens after the pretest")

        attempt = services.start_attempt(self.student, Kind.PRETEST)
        services.save_answers(attempt, answer_all(attempt, right=10))
        # An unsubmitted pretest still keeps the lessons locked.
        self.assertRedirects(self.client.get(lesson.get_absolute_url()), reverse("dashboards:learn"))
        services.submit_attempt(attempt)
        for each in Lesson.objects.all():
            with self.subTest(lesson=each.code):
                self.assertEqual(self.client.get(each.get_absolute_url()).status_code, 200)

    def test_start_save_submit_through_the_pages(self):
        url = reverse("assessments:take", args=["pretest"])
        self.assertContains(self.client.get(url), "dialog-start-assessment")
        self.assertRedirects(self.client.post(reverse("assessments:start", args=["pretest"])), url)
        self.assertRedirects(self.client.post(reverse("assessments:start", args=["pretest"])), url)
        self.assertEqual(AssessmentAttempt.objects.filter(student=self.student).count(), 1)

        attempt = AssessmentAttempt.objects.get(student=self.student)
        page = self.client.get(url)
        self.assertContains(page, "Question 30 of 30")
        # The answer key never reaches the student's page (two locked prompts use the word "correct").
        for leak in ("is-correct", "is_correct", "correct_index", "data-correct", "(correct answer)"):
            self.assertNotContains(page, leak)

        selections = {f"item-{k}": v for k, v in answer_all(attempt).items()}
        partial = dict(list(selections.items())[:29])
        response = self.client.post(reverse("assessments:save", args=["pretest"]), partial,
                                    headers={"x-requested-with": "fetch"})
        self.assertEqual(response.json()["saved"], True)

        response = self.client.post(reverse("assessments:submit", args=["pretest"]), partial)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Start with question 30", status_code=400)
        attempt.refresh_from_db()
        self.assertFalse(attempt.is_submitted)
        self.assertEqual(attempt.answers.exclude(selected_index=None).count(), 29)

        response = self.client.post(reverse("assessments:submit", args=["pretest"]), selections)
        self.assertRedirects(response, url)
        attempt.refresh_from_db()
        self.assertEqual((attempt.correct_count, attempt.item_count), (30, 30))
        self.assertContains(self.client.get(url), "You got <strong>30</strong> out of 30")

    def test_scores_are_stable_on_repeat_requests(self):
        attempt = submit_test(self.student, right=12)
        self.assertEqual(attempt.correct_count, 12)
        wrong = {key: (value + 1) % 4 for key, value in answer_all(attempt).items()}
        self.assertFalse(services.save_answers(attempt, wrong))
        again = services.submit_attempt(attempt)
        self.assertEqual((again.correct_count, again.submitted_at), (12, attempt.submitted_at))
        response = self.client.post(reverse("assessments:submit", args=["pretest"]),
                                    {f"item-{k}": v for k, v in wrong.items()})
        self.assertRedirects(response, reverse("assessments:take", args=["pretest"]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.correct_count, 12)
        response = self.client.post(reverse("assessments:save", args=["pretest"]), {},
                                    headers={"x-requested-with": "fetch"})
        self.assertEqual(response.status_code, 409)

    def test_bad_values_are_ignored(self):
        attempt = services.start_attempt(self.student, Kind.PRETEST)
        item = attempt.form.items.first()
        services.save_answers(attempt, {str(item.id): "7", "999999": "1", "x": "y"})
        self.assertEqual(attempt.answers.count(), 0)


class PosttestReleaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher, cls.other = make_teacher("t1"), make_teacher("t2")
        cls.classroom = make_class(cls.teacher, "A")
        cls.other_class = make_class(cls.other, "B")
        cls.student = make_student(cls.classroom, "s1")
        cls.late = make_student(cls.classroom, "s2")
        cls.elsewhere = make_student(cls.other_class, "s3")

    def test_posttest_appears_only_after_the_teacher_opens_it(self):
        submit_test(self.student, right=15)
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("dashboards:learn")), "Waiting for your teacher")
        self.assertContains(self.client.get(reverse("assessments:take", args=["posttest"])), "Waiting for your teacher")
        self.assertRedirects(self.client.post(reverse("assessments:start", args=["posttest"])), reverse("dashboards:learn"))
        self.assertFalse(AssessmentAttempt.objects.filter(student=self.student, kind=Kind.POSTTEST).exists())

        self.client.force_login(self.teacher)
        response = self.client.post(reverse("assessments:open_posttest", args=[self.classroom.id]))
        self.assertRedirects(response, reverse("dashboards:teacher_class", args=[self.classroom.id]))
        self.client.post(reverse("assessments:open_posttest", args=[self.classroom.id]))
        self.assertEqual(ClassAssessmentRelease.objects.filter(classroom=self.classroom).count(), 1)

        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse("dashboards:learn")), "Start the posttest")
        submit_test(self.student, kind=Kind.POSTTEST, right=24)
        response = self.client.get(reverse("assessments:take", args=["posttest"]))
        self.assertContains(response, "Score change")
        self.assertContains(response, "+30.0 percentage points")
        # Lessons stay open after the unit.
        self.assertEqual(self.client.get(Lesson.objects.first().get_absolute_url()).status_code, 200)

    def test_release_is_scoped_to_the_teachers_own_class(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.post(reverse("assessments:open_posttest", args=[self.other_class.id])).status_code, 404)
        self.assertFalse(ClassAssessmentRelease.objects.filter(classroom=self.other_class).exists())
        with self.assertRaises(services.AssessmentError):
            services.open_posttest(self.other_class, self.teacher)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse("assessments:open_posttest", args=[self.classroom.id])).status_code, 403)

    def test_posttest_needs_a_submitted_pretest_even_when_open(self):
        services.open_posttest(self.classroom, self.teacher)
        with self.assertRaises(services.AssessmentError):
            services.start_attempt(self.late, Kind.POSTTEST)
        submit_test(self.late)
        self.assertEqual(services.start_attempt(self.late, Kind.POSTTEST).kind, Kind.POSTTEST)
        # A student of another class doesn't get this class's release.
        submit_test(self.elsewhere)
        with self.assertRaises(services.AssessmentError):
            services.start_attempt(self.elsewhere, Kind.POSTTEST)

    def test_teacher_class_page_shows_scores_and_change(self):
        submit_test(self.student, right=15)
        services.open_posttest(self.classroom, self.teacher)
        submit_test(self.student, kind=Kind.POSTTEST, right=21)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("dashboards:teacher_class", args=[self.classroom.id]))
        self.assertContains(response, "15/30")
        self.assertContains(response, "21/30")
        self.assertContains(response, "+20.0 pts")
        self.assertContains(response, "Open since")
