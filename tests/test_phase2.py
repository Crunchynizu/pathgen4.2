"""Phase 2: accounts, classes and curriculum (docs/build_order.md and PLAN.md, "Done when")."""
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.classrooms import services
from apps.classrooms.models import Classroom, StudentProfile
from apps.curriculum.models import Lesson, LessonSkill, Skill, SkillPrerequisite
from apps.curriculum.seed import seed_curriculum

from .helpers import PASSWORD, make_admin, make_class, make_student, make_teacher, seed_all

User = get_user_model()


class SignInAndRolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.admin = make_admin()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)
        cls.student = make_student(cls.classroom)

    def test_each_role_lands_on_its_own_page(self):
        cases = [
            (self.admin, reverse("dashboards:admin", args=["overview"])),
            (self.teacher, reverse("dashboards:teacher", args=["overview"])),
            (self.student, reverse("dashboards:learn")),
        ]
        for user, landing in cases:
            with self.subTest(role=user.role):
                response = self.client.post(reverse("accounts:login"), {"username": user.username, "password": PASSWORD})
                self.assertRedirects(response, landing, fetch_redirect_response=False)
                self.assertEqual(self.client.get(landing).status_code, 200)
                self.client.post(reverse("accounts:logout"))

    def test_wrong_password_shows_an_error_in_the_form(self):
        response = self.client.post(reverse("accounts:login"), {"username": "student1", "password": "nope-nope"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check them and try again.")

    def test_signed_out_visitors_go_to_sign_in(self):
        response = self.client.get(reverse("dashboards:learn"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_sign_out_needs_post(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertEqual(self.client.get(reverse("dashboards:learn")).status_code, 302)

    def test_roles_cannot_open_each_others_pages(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("dashboards:teacher", args=["overview"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboards:admin", args=["overview"])).status_code, 403)
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("dashboards:admin", args=["accounts"])).status_code, 403)
        self.assertEqual(self.client.post(reverse("classrooms:create_teacher"), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboards:learn")).status_code, 403)

    def test_profile_changes_own_name_and_password(self):
        for user in (self.teacher, self.student):
            with self.subTest(role=user.role):
                self.client.force_login(user)
                response = self.client.post(reverse("accounts:profile"), {"form": "name", "display_name": "New Name"})
                self.assertRedirects(response, reverse("accounts:profile"))
                user.refresh_from_db()
                self.assertEqual(user.display_name, "New Name")
                response = self.client.post(reverse("accounts:profile"), {
                    "form": "password", "old_password": PASSWORD,
                    "new_password1": "brand-new-7731", "new_password2": "brand-new-7731",
                })
                self.assertRedirects(response, reverse("accounts:profile"))
                user.refresh_from_db()
                self.assertTrue(user.check_password("brand-new-7731"))
                # Still signed in after the change.
                self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
                user.set_password(PASSWORD)
                user.save()


class ProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.admin = make_admin()

    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_creates_teacher_then_class_then_student(self):
        response = self.client.post(reverse("classrooms:create_teacher"), {
            "teacher-display_name": "Ms. Cruz", "teacher-username": "mcruz", "teacher-password": "teach-pass-9913",
        })
        self.assertRedirects(response, reverse("dashboards:admin", args=["accounts"]))
        teacher = User.objects.get(username="mcruz")
        self.assertTrue(teacher.is_teacher)

        response = self.client.post(reverse("classrooms:create_classroom"), {"class-name": "7-Rizal", "class-teacher": teacher.id})
        self.assertRedirects(response, reverse("dashboards:admin", args=["classes"]))
        classroom = Classroom.objects.get(name="7-Rizal")
        self.assertEqual(classroom.teacher, teacher)

        response = self.client.post(reverse("classrooms:create_student"), {
            "student-display_name": "Ana", "student-username": "ana7", "student-password": "learn-pass-5521",
            "student-classroom": classroom.id,
        })
        self.assertRedirects(response, reverse("dashboards:admin", args=["accounts"]))
        student = User.objects.get(username="ana7")
        self.assertTrue(student.is_student)
        self.assertEqual(student.student_profile.classroom, classroom)

    def test_errors_reopen_the_dialog_with_values_kept(self):
        make_teacher("taken")
        response = self.client.post(reverse("classrooms:create_teacher"), {
            "teacher-display_name": "Someone", "teacher-username": "taken", "teacher-password": "teach-pass-9913",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "That username is taken.", status_code=400)
        self.assertContains(response, "data-open-on-load", status_code=400)
        self.assertContains(response, 'value="Someone"', status_code=400)

    def test_weak_password_is_refused(self):
        response = self.client.post(reverse("classrooms:create_teacher"), {
            "teacher-display_name": "T", "teacher-username": "weak", "teacher-password": "12345678",
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="weak").exists())

    def test_class_teacher_must_be_a_teacher(self):
        teacher = make_teacher()
        student = make_student(make_class(teacher))
        with self.assertRaises(ValidationError):
            services.create_classroom(name="Bad", teacher=student)

    def test_a_student_is_in_exactly_one_class(self):
        teacher = make_teacher()
        first, second = make_class(teacher, "A"), make_class(teacher, "B")
        student = make_student(first)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StudentProfile.objects.create(user=student, classroom=second)

    def test_failed_student_creation_leaves_no_account(self):
        teacher = make_teacher()
        classroom = make_class(teacher)
        with self.assertRaises(ValidationError):
            services.create_student(username="kid", password="1", display_name="Kid", classroom=classroom)
        self.assertFalse(User.objects.filter(username="kid").exists())

    def test_every_admin_section_renders_including_empty_states(self):
        for section in ("overview", "accounts", "classes", "lessons", "assessments"):
            with self.subTest(section=section):
                self.assertEqual(self.client.get(reverse("dashboards:admin", args=[section])).status_code, 200)
        response = self.client.get(reverse("dashboards:admin", args=["classes"]))
        self.assertContains(response, "create a teacher account")
        self.assertEqual(self.client.get("/admin-console/nope/").status_code, 404)


class OwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.mine, cls.other = make_teacher("mine"), make_teacher("other")
        cls.my_class = make_class(cls.mine, "Mine")
        cls.other_class = make_class(cls.other, "Theirs")
        cls.my_student = make_student(cls.my_class, "s_mine")
        cls.other_student = make_student(cls.other_class, "s_other")

    def test_teacher_sees_only_their_own_classes(self):
        self.client.force_login(self.mine)
        self.assertEqual(self.client.get(reverse("dashboards:teacher_class", args=[self.my_class.id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboards:teacher_class", args=[self.other_class.id])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("dashboards:teacher_student", args=[self.other_class.id, self.other_student.id])).status_code, 404
        )
        # A student of another class can't be reached through my class either.
        self.assertEqual(
            self.client.get(reverse("dashboards:teacher_student", args=[self.my_class.id, self.other_student.id])).status_code, 404
        )
        response = self.client.get(reverse("dashboards:teacher", args=["classes"]))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")

    def test_teacher_sections_render(self):
        self.client.force_login(self.mine)
        for section in ("overview", "classes", "exercises"):
            with self.subTest(section=section):
                self.assertEqual(self.client.get(reverse("dashboards:teacher", args=[section])).status_code, 200)

    def test_teacher_without_classes_sees_the_empty_state(self):
        lonely = make_teacher("lonely")
        self.client.force_login(lonely)
        self.assertContains(self.client.get(reverse("dashboards:teacher", args=["overview"])), "don't have a class yet")


class CurriculumTests(TestCase):
    def test_repeat_seed_leaves_six_lessons_and_ten_skills(self):
        seed_curriculum()
        first = (LessonSkill.objects.count(), SkillPrerequisite.objects.count())
        seed_curriculum()
        self.assertEqual(Lesson.objects.count(), 6)
        self.assertEqual(Skill.objects.count(), 10)
        self.assertEqual((LessonSkill.objects.count(), SkillPrerequisite.objects.count()), first)

    def test_codes_and_scopes_match_the_spec(self):
        seed_curriculum()
        self.assertEqual(
            list(Lesson.objects.values_list("code", flat=True)),
            ["integer_foundation", "integer_addition", "integer_subtraction", "integer_multiplication",
             "integer_division", "integer_expressions_applications"],
        )
        foundation = Lesson.objects.get(code="integer_foundation")
        self.assertEqual(
            [skill.code for skill in foundation.taught_skills()],
            ["INT_NUMBER_LINE", "INT_OPPOSITE_POS4", "INT_ABS_COMPARE", "INT_ORDER_NEG"],
        )
        review = LessonSkill.objects.filter(scope="review")
        self.assertEqual({link.lesson.code for link in review}, {"integer_expressions_applications"})
        self.assertEqual(review.count(), 4)
        self.assertTrue(SkillPrerequisite.objects.filter(skill__code="INT_SUB_NEG", prerequisite__code="INT_OPPOSITE_POS4").exists())

    def test_a_skill_cannot_be_its_own_prerequisite(self):
        seed_curriculum()
        skill = Skill.objects.get(code="INT_ADD_NEG")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SkillPrerequisite.objects.create(skill=skill, prerequisite=skill)

    def test_the_six_lesson_pages_render_with_skill_anchors(self):
        seed_curriculum()
        teacher = make_teacher()
        self.client.force_login(teacher)
        for lesson in Lesson.objects.all():
            with self.subTest(lesson=lesson.code):
                response = self.client.get(lesson.get_absolute_url())
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, f"lessons/{lesson.code}.html")
                for skill in lesson.taught_skills():
                    self.assertContains(response, f'id="{skill.anchor}"')
        self.assertEqual(Skill.objects.get(code="INT_ADD_NEG").anchor, "skill-int-add-neg")


class StudyClassCommandTests(TestCase):
    def test_makes_a_whole_class_and_a_login_sheet(self):
        seed_all()
        teacher = make_teacher("adviser_t")
        with tempfile.TemporaryDirectory() as folder:
            names = Path(folder) / "names.txt"
            names.write_text("# Section A\nJuan Dela Cruz\nMaria Santos\n\nPedro Reyes\n", encoding="utf-8")
            out = StringIO()
            call_command("create_study_class", teacher="adviser_t", class_name="7-A", prefix="g7a",
                         names=str(names), out=folder, stdout=out)
            self.assertEqual(StudentProfile.objects.filter(classroom__name="7-A").count(), 3)
            self.assertTrue(User.objects.filter(username="g7a01", display_name="Juan Dela Cruz").exists())
            sheets = list(Path(folder).glob("7-a-*.html"))
            self.assertEqual(len(sheets), 1)
            html = sheets[0].read_text(encoding="utf-8")
            self.assertIn("g7a03", html)
            self.assertIn("Maria Santos", html)
            # Running again skips the existing usernames and writes no new sheet.
            out = StringIO()
            call_command("create_study_class", teacher="adviser_t", class_name="7-A", prefix="g7a",
                         names=str(names), out=folder, stdout=out)
            self.assertIn("Skipped 3", out.getvalue())
            self.assertEqual(StudentProfile.objects.filter(classroom__name="7-A").count(), 3)

    def test_count_without_names(self):
        seed_all()
        make_teacher("t2")
        with tempfile.TemporaryDirectory() as folder:
            call_command("create_study_class", teacher="t2", class_name="Pilot", prefix="p", count=5, out=folder,
                         stdout=StringIO())
        self.assertEqual(StudentProfile.objects.filter(classroom__name="Pilot").count(), 5)
        self.assertTrue(User.objects.filter(username="p05", display_name="Student 05").exists())
