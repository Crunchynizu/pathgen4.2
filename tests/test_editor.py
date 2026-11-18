"""The teacher exercise editor (docs/build_order.md Phase 4 "Done when"; docs/modals.md #4-#6, #11).

A teacher can publish a valid pool to chosen classes, students in those classes see it after the
pretest, and other classes don't. All three question formats, invalid pool and media rejection,
and published version stability.
"""
import io
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.curriculum.models import Lesson, Skill
from apps.practice import authoring, engine
from apps.practice.models import (
    Exercise,
    ExerciseAssignment,
    ExerciseRevision,
    ExerciseSession,
    Question,
)

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test

MEDIA = tempfile.mkdtemp(prefix="pathgen-test-media-")


def png(size=(40, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (12, 160, 200)).save(buffer, format="PNG")
    return SimpleUploadedFile("number-line.png", buffer.getvalue(), content_type="image/png")


def question(prompt, *, skill, correct=1, level="medium", fmt="text", hint="Think about the signs.", **extra):
    data = {"format": fmt, "prompt": prompt, "choice_1": "1", "choice_2": "2", "choice_3": "3", "choice_4": "4",
            "correct": str(correct), "skill": str(skill.id), "difficulty": level, "hint": hint}
    data.update(extra)
    return data


def editor_post(title, count, required, questions, *, existing=0, action="save"):
    data = {"title": title, "target_count": str(count), "action": action,
            "q-TOTAL_FORMS": str(len(questions)), "q-INITIAL_FORMS": str(existing),
            "q-MIN_NUM_FORMS": "0", "q-MAX_NUM_FORMS": "1000"}
    data["required_skills"] = [str(skill.id) for skill in required]
    for index, entry in enumerate(questions):
        for key, value in entry.items():
            data[f"q-{index}-{key}"] = value
        data.setdefault(f"q-{index}-ORDER", str(index + 1))
    return data


class LinkParsingTests(SimpleTestCase):
    def test_youtube_links_and_timestamps(self):
        cases = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s": ("dQw4w9WgXcQ", 65),
            "https://youtu.be/dQw4w9WgXcQ?t=90": ("dQw4w9WgXcQ", 90),
            "youtube.com/shorts/dQw4w9WgXcQ": ("dQw4w9WgXcQ", None),
            "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?start=12": ("dQw4w9WgXcQ", 12),
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ#t=1:02:03": ("dQw4w9WgXcQ", 3723),
        }
        for url, expected in cases.items():
            self.assertEqual(authoring.parse_youtube(url), expected, url)
        for bad in ("https://vimeo.com/123", "https://youtube.com/watch?v=short", "not a link", ""):
            with self.assertRaises(ValidationError):
                authoring.parse_youtube(bad)

    def test_timestamps(self):
        self.assertEqual(authoring.parse_timestamp("1h2m3s"), 3723)
        self.assertEqual(authoring.parse_timestamp("75"), 75)
        self.assertEqual(authoring.parse_timestamp("2:05"), 125)
        self.assertIsNone(authoring.parse_timestamp("soon"))


@override_settings(MEDIA_ROOT=MEDIA)
class EditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher("t_editor")
        cls.mine = make_class(cls.teacher, "Grade 7 - Mine")
        cls.other_teacher = make_teacher("t_elsewhere")
        cls.theirs = make_class(cls.other_teacher, "Grade 7 - Theirs")
        cls.student = make_student(cls.mine, "s_mine")
        cls.outsider = make_student(cls.theirs, "s_theirs")
        for student in (cls.student, cls.outsider):
            submit_test(student)
        cls.division = Lesson.objects.get(code="integer_division")
        cls.div = Skill.objects.get(code="INT_DIV_NEG")
        cls.foundation = Lesson.objects.get(code="integer_foundation")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.teacher)

    def create(self, lesson=None, title="Dividing integers", count=3):
        response = self.client.post(reverse("practice:editor_new"),
                                    {"lesson": (lesson or self.division).id, "title": title, "target_count": count})
        exercise = Exercise.objects.filter(owner_teacher=self.teacher).latest("id")
        self.assertRedirects(response, reverse("practice:editor", args=[exercise.id]))
        return exercise

    def save(self, exercise, questions, count=3, required=None, existing=0, action="save", title="Dividing integers"):
        data = editor_post(title, count, required or [self.div], questions, existing=existing, action=action)
        return self.client.post(reverse("practice:editor", args=[exercise.id]), data)

    def three_formats(self):
        return [
            question("-12 ÷ 3 = ?", skill=self.div, correct=1, level="easy"),
            question("Use the picture: -20 ÷ -4 = ?", skill=self.div, fmt="figure", figure=png(),
                     figure_description="A number line from -20 to 0 cut into 4 equal jumps.", correct=3),
            question("Watch, then answer: 18 ÷ -6 = ?", skill=self.div, fmt="video",
                     video_url="https://youtu.be/dQw4w9WgXcQ?t=1m5s", correct=2, level="hard"),
        ]

    def publish(self, exercise, classes):
        return self.client.post(reverse("practice:publish", args=[exercise.id]),
                                {"classes": [c.id for c in classes]})

    # ---- Creating, saving and publishing ----

    def test_new_draft_saves_three_formats_and_publishes_to_chosen_classes(self):
        exercise = self.create()
        revision = authoring.draft_of(exercise)
        self.assertEqual(list(revision.required_skills.values_list("code", flat=True)), ["INT_DIV_NEG"])
        self.assertEqual(revision.scope, ExerciseRevision.Scope.SINGLE)
        self.assertContains(self.client.get(reverse("practice:editor", args=[exercise.id])), "Question pool")

        response = self.save(exercise, self.three_formats(), action="publish")
        self.assertRedirects(response, reverse("practice:editor", args=[exercise.id]) + "?dialog=publish",
                             fetch_redirect_response=False)
        questions = list(revision.questions.order_by("author_order"))
        self.assertEqual([q.format for q in questions], ["text", "figure", "video"])
        self.assertTrue(questions[1].figure_file.name.startswith("figures/"))
        self.assertEqual((questions[2].video_id, questions[2].video_start_seconds), ("dQw4w9WgXcQ", 65))
        self.assertEqual([q.difficulty_value for q in questions], [0.15, 0.30, 0.50])  # provisional, docs/agent.md
        self.assertTrue(all(q.choices.count() == 4 for q in questions))
        self.assertContains(self.client.get(reverse("practice:editor", args=[exercise.id]) + "?dialog=publish"),
                            "Publish exercise")

        self.publish(exercise, [self.mine])
        exercise.refresh_from_db()
        self.assertEqual(exercise.status, Exercise.Status.PUBLISHED)
        self.assertEqual(exercise.active_revision, revision)
        self.assertTrue(ExerciseRevision.objects.get(pk=revision.pk).is_published)

        # Students in the chosen class see and can start it; other classes can't.
        self.client.force_login(self.student)
        lesson_page = self.client.get(self.division.get_absolute_url())
        self.assertContains(lesson_page, "Dividing integers")
        self.client.post(reverse("practice:start", args=[exercise.id]))
        self.assertTrue(ExerciseSession.objects.filter(student=self.student, exercise=exercise).exists())
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("practice:exercise", args=[exercise.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse("practice:start", args=[exercise.id])).status_code, 404)

    def test_invalid_pool_is_rejected_at_publish(self):
        exercise = self.create(count=4)
        self.save(exercise, [question("-8 ÷ 2 = ?", skill=self.div), question("9 ÷ -3 = ?", skill=self.div, hint="")],
                  count=4)
        page = self.client.get(reverse("practice:editor", args=[exercise.id]))
        self.assertContains(page, "The pool has 2 questions, but a session needs 4.")
        self.assertContains(page, "needs a hint")
        self.assertNotContains(page, 'id="dialog-publish"')
        response = self.publish(exercise, [self.mine])
        self.assertRedirects(response, reverse("practice:editor", args=[exercise.id]))
        self.assertFalse(ExerciseAssignment.objects.filter(exercise=exercise).exists())
        exercise.refresh_from_db()
        self.assertIsNone(exercise.active_revision)

    def test_mixed_exercise_needs_each_required_skill(self):
        exercise = self.create(lesson=self.foundation, title="Foundations mix", count=2)
        draft = authoring.draft_of(exercise)
        self.assertEqual(draft.scope, ExerciseRevision.Scope.MIXED)
        line, opposite = Skill.objects.get(code="INT_NUMBER_LINE"), Skill.objects.get(code="INT_OPPOSITE_POS4")
        self.save(exercise, [question("Where is -3?", skill=line), question("Which is on the left?", skill=line)],
                  count=2, required=[line, opposite], title="Foundations mix")
        self.assertContains(self.client.get(reverse("practice:editor", args=[exercise.id])),
                            "No question in the pool covers")
        # A skill from another lesson is refused by the form.
        response = self.save(exercise, [question("x", skill=self.div)], count=1, required=[line], existing=2,
                             title="Foundations mix")
        self.assertEqual(response.status_code, 400)

    def test_bad_media_is_caught_in_the_editor(self):
        exercise = self.create()
        fake = SimpleUploadedFile("trick.png", b"not really a picture", content_type="image/png")
        response = self.save(exercise, [
            question("a", skill=self.div, fmt="figure", figure=fake, figure_description="x"),
            question("b", skill=self.div, fmt="video", video_url="https://vimeo.com/1234"),
        ])
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "isn&#x27;t a picture PathGen can read", status_code=400)
        self.assertContains(response, "isn&#x27;t a YouTube video link", status_code=400)
        self.assertFalse(authoring.draft_of(exercise).questions.exists())

    # ---- Versions ----

    def published_exercise(self):
        exercise = self.create()
        self.save(exercise, self.three_formats())
        self.publish(exercise, [self.mine])
        exercise.refresh_from_db()
        return exercise

    def test_published_versions_stay_frozen_and_sessions_keep_theirs(self):
        exercise = self.published_exercise()
        first = exercise.active_revision
        self.client.force_login(self.student)
        self.client.post(reverse("practice:start", args=[exercise.id]))
        session = ExerciseSession.objects.get(student=self.student, exercise=exercise)

        self.client.force_login(self.teacher)
        page = self.client.get(reverse("practice:editor", args=[exercise.id]))
        self.assertContains(page, "Edit in a new draft")
        with self.assertRaises(authoring.AuthoringError):
            authoring.save_draft(self.teacher, exercise.id, first.id, title="x", target_count=3,
                                 required_skills=[self.div], questions=[])
        self.client.post(reverse("practice:start_draft", args=[exercise.id]))
        draft = authoring.draft_of(exercise)
        self.assertEqual(draft.number, first.number + 1)
        old = list(first.questions.order_by("author_order"))
        copied = list(draft.questions.order_by("author_order"))
        self.assertEqual([q.item_key for q in copied], [q.item_key for q in old])  # stable keys
        self.assertEqual(copied[1].figure_file.name, old[1].figure_file.name)  # same file, kept

        edited = self.three_formats()
        edited[0]["prompt"] = "-15 ÷ 3 = ?"
        for index, q in enumerate(copied):
            edited[index]["source_id"] = str(q.id)
        edited[1].pop("figure")
        edited[1]["keep_figure"] = "True"
        self.save(exercise, edited, existing=3)
        self.publish(exercise, [self.mine])
        exercise.refresh_from_db()
        self.assertEqual(exercise.active_revision, draft)
        self.assertEqual(Question.objects.get(revision=first, author_order=1).prompt, "-12 ÷ 3 = ?")
        self.assertEqual(Question.objects.get(revision=draft, author_order=1).prompt, "-15 ÷ 3 = ?")
        self.assertEqual(Question.objects.get(revision=draft, author_order=2).figure_file.name,
                         old[1].figure_file.name)
        session.refresh_from_db()
        self.assertEqual(session.revision, first)  # the started session keeps version 1

    def test_unpublish_stops_new_starts_but_started_sessions_finish(self):
        exercise = self.published_exercise()
        self.client.force_login(self.student)
        self.client.post(reverse("practice:start", args=[exercise.id]))
        session = ExerciseSession.objects.get(student=self.student, exercise=exercise)

        self.client.force_login(self.teacher)
        page = self.client.get(reverse("practice:editor", args=[exercise.id]))
        self.assertContains(page, "Unpublish exercise")
        self.assertContains(page, "1 session already in progress can finish")
        self.client.post(reverse("practice:unpublish", args=[exercise.id]))
        exercise.refresh_from_db()
        self.assertEqual(exercise.status, Exercise.Status.UNPUBLISHED)
        self.assertFalse(ExerciseAssignment.objects.filter(exercise=exercise, status="active").exists())

        # The student can still finish the started session...
        self.client.force_login(self.student)
        for _ in range(3):
            item = engine.current_item(session)
            choice = item.question.choices.get(is_correct=True)
            self.client.post(reverse("practice:answer", args=[exercise.id]), {"item": item.id, "choice": choice.id})
        session.refresh_from_db()
        self.assertTrue(session.is_completed)
        # ...but not take the retake, and a new student can't start.
        self.client.post(reverse("practice:start", args=[exercise.id]), {"retake": "1"})
        self.assertEqual(ExerciseSession.objects.filter(student=self.student, exercise=exercise).count(), 1)
        newcomer = make_student(self.mine, "s_new")
        submit_test(newcomer)
        self.client.force_login(newcomer)
        self.assertEqual(self.client.post(reverse("practice:start", args=[exercise.id])).status_code, 404)

    def test_delete_only_a_never_published_draft(self):
        draft_only = self.create(title="Scratch")
        self.assertContains(self.client.get(reverse("practice:editor", args=[draft_only.id])), "Delete draft")
        self.client.post(reverse("practice:delete", args=[draft_only.id]))
        self.assertFalse(Exercise.objects.filter(pk=draft_only.pk).exists())

        published = self.published_exercise()
        self.assertNotContains(self.client.get(reverse("practice:editor", args=[published.id])), 'id="dialog-delete"')
        self.client.post(reverse("practice:delete", args=[published.id]))
        self.assertTrue(Exercise.objects.filter(pk=published.pk).exists())

    # ---- Permissions and media ----

    def test_other_teachers_and_classes_are_refused(self):
        exercise = self.create()
        self.save(exercise, self.three_formats())
        response = self.publish(exercise, [self.theirs])
        self.assertRedirects(response, reverse("practice:editor", args=[exercise.id]))
        self.assertFalse(ExerciseAssignment.objects.filter(exercise=exercise).exists())

        self.client.force_login(self.other_teacher)
        for name in ("editor", "start_draft", "publish", "unpublish", "delete"):
            method = self.client.get if name == "editor" else self.client.post
            self.assertEqual(method(reverse(f"practice:{name}", args=[exercise.id])).status_code, 404, name)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("practice:editor_new")).status_code, 403)

    def test_figures_are_served_only_to_people_who_may_see_them(self):
        exercise = self.published_exercise()
        name = exercise.active_revision.questions.get(format="figure").figure_file.name
        url = reverse("practice:figure", args=[name])
        self.assertEqual(self.client.get(url).status_code, 200)  # owner
        self.client.force_login(self.student)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.other_teacher)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.get(reverse("practice:figure", args=["figures/../../manage.py"])).status_code, 302)

    def test_video_time_is_kept_apart_from_answer_time(self):
        exercise = self.published_exercise()
        self.client.force_login(self.student)
        self.client.post(reverse("practice:start", args=[exercise.id]))
        session = ExerciseSession.objects.get(student=self.student, exercise=exercise)
        video_item = None
        for _ in range(3):
            item = engine.current_item(session)
            choice = item.question.choices.get(is_correct=True)
            self.client.post(reverse("practice:answer", args=[exercise.id]),
                             {"item": item.id, "choice": choice.id, "active_seconds": "14.5", "video_seconds": "30"})
            if item.question.format == "video":
                video_item = item
        video_item.refresh_from_db()
        self.assertEqual((video_item.answer_seconds, video_item.video_seconds), (14.5, 30.0))
        others = session.items.exclude(pk=video_item.pk)
        self.assertTrue(all(i.video_seconds is None for i in others))
        page = self.client.get(reverse("practice:exercise", args=[exercise.id]) + f"?done={video_item.id}")
        self.assertEqual(page.status_code, 200)

    def test_student_page_shows_the_figure_and_video(self):
        exercise = self.create(count=2)
        self.save(exercise, self.three_formats()[1:], count=2)
        self.publish(exercise, [self.mine])
        self.client.force_login(self.student)
        self.client.post(reverse("practice:start", args=[exercise.id]))
        page = self.client.get(reverse("practice:exercise", args=[exercise.id]))
        self.assertContains(page, 'alt="A number line from -20 to 0 cut into 4 equal jumps."')
        self.assertNotContains(page, "youtube-nocookie.com/embed")  # the first question is the figure one
        session = ExerciseSession.objects.get(student=self.student, exercise=exercise)
        item = engine.current_item(session)
        self.client.post(reverse("practice:answer", args=[exercise.id]),
                         {"item": item.id, "choice": item.question.choices.get(is_correct=True).id})
        page = self.client.get(reverse("practice:exercise", args=[exercise.id]))
        self.assertContains(page, "youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0&amp;enablejsapi=1&amp;start=65")
        self.assertContains(page, 'name="video_seconds"')

    def test_reimport_keeps_a_teachers_edited_bank_exercise(self):
        from apps.practice.importer import import_bank

        import_bank(teacher=self.teacher, classrooms=[self.mine], only=["integer_division"])
        exercise = Exercise.objects.get(owner_teacher=self.teacher, source_key="bank:integer_division")
        self.client.post(reverse("practice:start_draft", args=[exercise.id]))
        draft = authoring.draft_of(exercise)
        self.publish(exercise, [self.mine])
        report = import_bank(teacher=self.teacher, classrooms=[self.mine], only=["integer_division"])
        exercise.refresh_from_db()
        self.assertEqual(exercise.active_revision, draft)
        self.assertEqual(report[0][2], "kept the teacher's edited version")
