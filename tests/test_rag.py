"""Local Qwen feedback (docs/build_order.md Phase 6; docs/rag.md "Runtime sequence").

A fake llama.cpp server stands in for Qwen here. The real model is checked by
`manage.py check_llm` against a running server (README, "Qwen feedback").
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.practice import engine, feedback
from apps.practice.importer import import_bank
from apps.practice.models import Exercise, ExerciseFeedback, ExerciseSession
from learning.feedback import service
from learning.feedback.retrieval import Entry

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test

SUB = Entry("INT_SUB_NEG", "integer_subtraction", "skill-int-sub-neg", "Adding the opposite",
            "To subtract an integer, add its opposite.", "3 - (-5) = 3 + 5 = 8, and 2 - 6 = 2 + (-6) = -4.")
GOOD = ("Great work on Division! For subtraction, add the opposite: 3 - (-5) becomes 3 + 5, which is 8. "
        "Try that idea on your next practice.")


class FakeQwen:
    """A tiny HTTP server with llama.cpp's chat endpoint. `reply` and `delay` can change per test."""

    def __init__(self):
        self.reply, self.delay, self.calls, self.prompts = GOOD, 0.0, 0, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.calls += 1
                fake.prompts.append(body["messages"])
                time.sleep(fake.delay)
                data = json.dumps({"choices": [{"message": {"role": "assistant", "content": fake.reply}}]})
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data.encode())
                except ConnectionError:
                    pass  # the app gave up first (the timeout test)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class OutputCheckTests(SimpleTestCase):
    def test_good_text_passes_and_is_trimmed(self):
        self.assertEqual(service.clean(f'  "{GOOD}"  ', SUB), GOOD)
        long = GOOD + " One more. And another sentence here."
        self.assertEqual(service.clean(long, SUB).count("."), GOOD.count("."))  # 3 sentences at most

    def test_bad_text_is_refused(self):
        bad = {
            "invented numbers": "Subtracting is easy: 7 - 10 = -3, so always add the opposite to it.",
            "a link": "Read more at https://example.com about adding the opposite, then try again.",
            "markup": "**Next focus**: add the opposite, as in 3 - (-5) = 8. Keep practicing it.",
            "too short": "Good job.",
            "cut off": "To subtract an integer you add its opposite, like 3 - (-5) which",
        }
        for name, text in bad.items():
            with self.assertRaises(service.InvalidOutput, msg=name):
                service.clean(text, SUB)

    def test_prompt_has_only_the_minimum_facts(self):
        messages = service.messages(service.Facts("Subtraction", "Division", True), SUB)
        user = messages[1]["content"]
        self.assertIn("Next focus: Subtraction.", user)
        self.assertIn("add its opposite", user)
        self.assertNotIn("first try", user.split("Strength")[0])  # no score is sent


@override_settings(LLM_TIMEOUT_SECONDS=1.0)
class GenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher("t_rag")
        cls.classroom = make_class(cls.teacher, "Grade 7 - RAG")
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom], only=["integer_subtraction"])
        cls.exercise = Exercise.objects.get(lesson__code="integer_subtraction")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.qwen = FakeQwen()

    @classmethod
    def tearDownClass(cls):
        cls.qwen.close()
        super().tearDownClass()

    def setUp(self):
        feedback.knowledge.cache_clear()
        self.qwen.reply, self.qwen.delay, self.qwen.calls, self.qwen.prompts = GOOD, 0.0, 0, []
        self.student = make_student(self.classroom, f"r{self._testMethodName[-12:]}")
        submit_test(self.student)
        self.client.force_login(self.student)

    def finished(self, right=1):
        engine.start(self.student, self.exercise)
        session = ExerciseSession.objects.get(student=self.student, exercise=self.exercise)
        for number in range(session.target_count):
            item = engine.current_item(session)
            ok = number < right
            choice = item.question.choices.get(is_correct=ok) if ok else item.question.choices.filter(is_correct=False).first()
            engine.answer(session, item.id, choice.id)
            if not ok:
                engine.move_on(session, item.id)
        session.refresh_from_db()
        return session

    def ask(self, session):
        return self.client.post(reverse("practice:feedback", args=[self.exercise.id]), {"session": session.id})

    def test_qwen_rewords_the_approved_note_once(self):
        session = self.finished()
        saved = session.feedback
        fallback = saved.text
        self.assertEqual(saved.generation, "pending")
        with self.settings(LLM_BASE_URL=self.qwen.url):
            page = self.client.get(reverse("practice:exercise", args=[self.exercise.id]))
            self.assertContains(page, "data-generate=")
            self.assertContains(page, "1<span>/4</span>")  # the score shows while feedback is pending
            data = self.ask(session).json()
            again = self.ask(session).json()
        self.assertTrue(data["generated"])
        self.assertEqual(data["text"], GOOD)
        self.assertEqual(again["text"], GOOD)
        self.assertEqual(self.qwen.calls, 1)  # claimed once
        saved.refresh_from_db()
        self.assertEqual((saved.source, saved.generation, saved.fallback_text), ("generated", "done", fallback))
        self.assertIn("llama.cpp b12464", saved.model_version)
        prompt = json.dumps(self.qwen.prompts[0])
        for private in (self.student.username, self.student.display_name):
            self.assertNotIn(private, prompt)
        page = self.client.get(reverse("practice:exercise", args=[self.exercise.id]))
        self.assertContains(page, "Great work on Division!")
        self.assertNotContains(page, "data-generate=")
        self.assertContains(page, "Review Subtraction in the lesson")  # the server's link stays

    def test_slow_failed_or_unusable_replies_keep_the_saved_text(self):
        for case in ("slow", "invented", "down"):
            with self.subTest(case):
                ExerciseSession.objects.filter(student=self.student).delete()
                session = self.finished()
                saved = session.feedback
                url = self.qwen.url if case != "down" else "http://127.0.0.1:9"
                self.qwen.delay = 2.0 if case == "slow" else 0.0
                self.qwen.reply = "Subtract by adding: 10 - 4 = 6. Easy!!! Keep going with it." if case == "invented" else GOOD
                with self.settings(LLM_BASE_URL=url):
                    data = self.ask(session).json()
                self.assertFalse(data["generated"])
                saved.refresh_from_db()
                self.assertEqual(saved.generation, "failed")
                self.assertEqual(saved.text, saved.fallback_text)
                self.assertEqual(saved.source, "knowledge")
                self.assertTrue(saved.generation_note)

    def test_off_without_a_server_or_without_knowledge(self):
        session = self.finished()
        with self.settings(LLM_BASE_URL=""):
            self.assertNotContains(self.client.get(reverse("practice:exercise", args=[self.exercise.id])),
                                   "data-generate=")
            self.assertFalse(self.ask(session).json()["generated"])
        session.feedback.refresh_from_db()
        self.assertEqual(session.feedback.generation, "pending")  # can still be generated later
        self.assertEqual(self.qwen.calls, 0)

        ExerciseSession.objects.filter(student=self.student).delete()
        feedback.knowledge.cache_clear()
        with mock.patch.object(feedback, "KNOWLEDGE_FILE", Path("does-not-exist.json")):
            session = self.finished()
        self.assertEqual(session.feedback.generation, "none")
        with self.settings(LLM_BASE_URL=self.qwen.url):
            self.assertFalse(self.ask(session).json()["generated"])
        self.assertEqual(self.qwen.calls, 0)

    def test_a_claimed_job_is_not_run_twice(self):
        session = self.finished()
        ExerciseFeedback.objects.filter(session=session).update(generation="claimed")
        with self.settings(LLM_BASE_URL=self.qwen.url):
            self.assertFalse(self.ask(session).json()["generated"])
        self.assertEqual(self.qwen.calls, 0)

    def test_only_the_student_can_ask_for_their_own_feedback(self):
        session = self.finished()
        other = make_student(self.classroom, "r_other")
        self.client.force_login(other)
        with self.settings(LLM_BASE_URL=self.qwen.url):
            self.assertEqual(self.ask(session).status_code, 404)
            self.client.force_login(self.student)
            self.assertEqual(self.client.get(reverse("practice:feedback", args=[self.exercise.id])).status_code, 405)
        self.assertEqual(self.qwen.calls, 0)
