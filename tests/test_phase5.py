"""Phase 5: BKT, the struggle model, selection rules, practice screen and decision logs
(docs/build_order.md Phase 5 "Done when", docs/special_algo.md acceptance cases)."""
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.practice import engine
from apps.practice.importer import import_bank
from apps.practice.models import (
    Exercise,
    ExerciseFeedback,
    ExerciseSession,
    MasteryUpdate,
    SelectionDecision,
    SessionQuestion,
    StudentSkillMastery,
)
from learning import agent as agent_lib
from learning import bkt as bkt_lib
from learning.features import SPEC_FEATURES, Encounter, model_inputs
from learning.selection import Candidate, SelectionError, Situation, choose

from .helpers import make_class, make_student, make_teacher, seed_all, submit_test


def enc(skill, ok=True, level="medium", hint=False, attempts=1):
    return Encounter(skill=skill, difficulty=level, first_correct=ok, hint_used=hint, attempts=attempts, seconds=10.0)


def cand(id_, skill, level="medium", value=0.2, key=None):
    return Candidate(id=id_, item_key=key or f"K{id_}", skill=skill, difficulty=level, difficulty_value=value, order=id_)


class BktTests(SimpleTestCase):
    def test_known_numbers(self):
        params = bkt_lib.Params(prior=0.5, learn=0.1, guess=0.2, slip=0.1)
        posterior, next_mastery = bkt_lib.update(0.5, True, params)
        self.assertAlmostEqual(posterior, 0.45 / (0.45 + 0.1))
        self.assertAlmostEqual(next_mastery, posterior + (1 - posterior) * 0.1)
        posterior, _ = bkt_lib.update(0.5, False, params)
        self.assertAlmostEqual(posterior, 0.05 / (0.05 + 0.4))
        self.assertAlmostEqual(bkt_lib.p_correct(0.5, params), 0.5 * 0.9 + 0.5 * 0.2)

    def test_fitted_file_loads_with_the_limits(self):
        bkt = bkt_lib.load(settings.MODEL_ARTIFACTS_DIR)
        self.assertEqual(set(bkt.params), set(bkt_lib.SKILLS))
        for params in bkt.params.values():
            self.assertLessEqual(params.guess, 0.3 + 1e-9)
            self.assertLessEqual(params.slip, 0.1 + 1e-9)
            self.assertLessEqual(params.learn, 0.3 + 1e-9)

    def test_zero_right_never_looks_strong(self):
        bkt = bkt_lib.load(settings.MODEL_ARTIFACTS_DIR)
        for code, params in bkt.params.items():
            mastery = params.prior
            for _ in range(6):
                _, mastery = bkt_lib.update(mastery, False, params)
            self.assertLess(mastery, 0.75, code)


class AgentTests(SimpleTestCase):
    def test_model_loads_and_gives_probabilities(self):
        agent = agent_lib.load(settings.MODEL_ARTIFACTS_DIR)
        history = [enc("INT_ADD_NEG", True), enc("INT_ADD_NEG", False)]
        inputs = model_inputs(history, candidate_skill="INT_SUB_NEG", candidate_difficulty=0.35, mastery=0.4,
                              window=agent.window)
        probability = agent_lib.predict(agent, inputs)
        self.assertTrue(0 < probability < 1)
        # Harder template and lower mastery both raise the predicted struggle.
        harder = agent_lib.predict(agent, {**inputs, "candidate_difficulty": 0.5})
        weaker = agent_lib.predict(agent, {**inputs, "candidate_skill_bkt_mastery": 0.1})
        self.assertGreater(harder, probability)
        self.assertGreater(weaker, probability)

    def test_inputs_follow_the_trainer_recipe(self):
        history = [enc("INT_ADD_NEG", True), enc("INT_SUB_NEG", False, hint=True, attempts=2), enc("INT_ADD_NEG", True)]
        inputs = model_inputs(history, candidate_skill="INT_ADD_NEG", candidate_difficulty=0.2, mastery=0.7, window=5)
        self.assertEqual(inputs["last_correct"], 1)
        self.assertEqual(inputs["recent_correct_rate"], 2 / 3)
        self.assertEqual(inputs["recent_hint_rate"], 1 / 3)
        self.assertEqual(inputs["candidate_skill_prior_encounters"], 2)

    def test_a_changed_model_file_is_refused(self):
        import shutil
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            for name in ("struggle_model.json", "template_difficulty.json", "manifest.json"):
                shutil.copy(Path(settings.MODEL_ARTIFACTS_DIR) / name, Path(folder) / name)
            path = Path(folder) / "struggle_model.json"
            path.write_text(path.read_text().replace('"format": 1', '"format": 1 '), encoding="utf-8")
            with self.assertRaises(agent_lib.AgentConfigError):
                agent_lib.load(folder)


class SelectionRuleTests(SimpleTestCase):
    """docs/special_algo.md acceptance cases, on the pure rules."""

    def setUp(self):
        self.agent = agent_lib.load(settings.MODEL_ARTIFACTS_DIR)

    def situation(self, pool, required, count, **kwargs):
        defaults = {"served_ids": set(), "covered": set(), "single_skill": len(required) == 1,
                    "history": [], "mastery": {s: 0.5 for s in {c.skill for c in pool}}, "seen_keys": set()}
        defaults.update(kwargs)
        return Situation(pool=pool, required=required, target_count=count, **defaults)

    def test_first_ever_question_uses_teacher_order(self):
        pool = [cand(3, "INT_ADD_NEG"), cand(1, "INT_ADD_NEG"), cand(2, "INT_ADD_NEG")]
        choice = choose(self.situation(pool, ["INT_ADD_NEG"], 2), self.agent)
        self.assertEqual((choice.candidate.id, choice.rule, choice.fallback_reason), (1, "first_ever_teacher_order", "no_history"))

    def test_five_slots_cover_four_required_skills(self):
        skills = ["INT_NUMBER_LINE", "INT_OPPOSITE_POS4", "INT_ABS_COMPARE", "INT_ORDER_NEG"]
        pool = [cand(i * 10 + j, s) for i, s in enumerate(skills) for j in range(3)]
        mastery = {"INT_NUMBER_LINE": 0.1, "INT_OPPOSITE_POS4": 0.9, "INT_ABS_COMPARE": 0.9, "INT_ORDER_NEG": 0.9}
        served, covered, history = set(), set(), [enc("INT_ADD_NEG")]
        for _ in range(5):
            choice = choose(self.situation(pool, skills, 5, served_ids=served, covered=covered, history=history,
                                           mastery=mastery), self.agent)
            served.add(choice.candidate.id)
            covered.add(choice.candidate.skill)
            history.append(enc(choice.candidate.skill))
        self.assertEqual(covered, set(skills))

    def test_lowest_mastery_skill_comes_first_when_slots_allow(self):
        skills = ["INT_EXPR_NEG", "INT_CONTEXT"]
        pool = [cand(1, "INT_EXPR_NEG"), cand(2, "INT_EXPR_NEG"), cand(3, "INT_CONTEXT"), cand(4, "INT_CONTEXT")]
        choice = choose(self.situation(pool, skills, 4, history=[enc("INT_ADD_NEG")],
                                       mastery={"INT_EXPR_NEG": 0.8, "INT_CONTEXT": 0.2}), self.agent)
        self.assertEqual((choice.candidate.skill, choice.rule), ("INT_CONTEXT", "lowest_mastery"))

    def test_coverage_wins_when_every_slot_is_needed(self):
        skills = ["INT_EXPR_NEG", "INT_CONTEXT"]
        pool = [cand(1, "INT_EXPR_NEG"), cand(2, "INT_EXPR_NEG"), cand(3, "INT_CONTEXT")]
        choice = choose(self.situation(pool, skills, 2, served_ids={1}, covered={"INT_EXPR_NEG"},
                                       history=[enc("INT_EXPR_NEG")],
                                       mastery={"INT_EXPR_NEG": 0.0, "INT_CONTEXT": 0.99}), self.agent)
        self.assertEqual((choice.candidate.id, choice.rule), (3, "coverage"))

    def test_repeated_subtraction_errors_prefer_easier(self):
        pool = [cand(1, "INT_SUB_NEG", "easy"), cand(2, "INT_SUB_NEG", "medium"), cand(3, "INT_SUB_NEG", "hard")]
        history = [enc("INT_SUB_NEG", False, "hard"), enc("INT_SUB_NEG", False, "hard")]
        choice = choose(self.situation(pool, ["INT_SUB_NEG"], 4, history=history), self.agent)
        self.assertEqual(choice.direction, "easier")
        self.assertIn(choice.candidate.difficulty, ("easy", "medium"))

    def test_repeated_errors_with_no_easier_option_keep_the_easiest_left(self):
        pool = [cand(2, "INT_SUB_NEG", "medium"), cand(3, "INT_SUB_NEG", "hard")]
        history = [enc("INT_SUB_NEG", False, "easy"), enc("INT_SUB_NEG", False, "easy")]
        choice = choose(self.situation(pool, ["INT_SUB_NEG"], 4, history=history), self.agent)
        self.assertEqual((choice.direction, choice.candidate.difficulty), ("easier", "medium"))

    def test_repeated_independent_success_prefers_harder(self):
        pool = [cand(1, "INT_MULT_NEG", "easy"), cand(2, "INT_MULT_NEG", "medium"), cand(3, "INT_MULT_NEG", "hard")]
        history = [enc("INT_MULT_NEG", True, "easy"), enc("INT_MULT_NEG", True, "easy")]
        choice = choose(self.situation(pool, ["INT_MULT_NEG"], 4, history=history), self.agent)
        self.assertEqual(choice.direction, "harder")
        self.assertIn(choice.candidate.difficulty, ("medium", "hard"))

    def test_ranking_uses_the_model_and_logs_every_candidate(self):
        pool = [cand(1, "INT_EXPR_NEG", "easy", 0.31), cand(2, "INT_EXPR_NEG", "medium", 0.50),
                cand(3, "INT_EXPR_NEG", "hard", 0.54)]
        choice = choose(self.situation(pool, ["INT_EXPR_NEG"], 4, history=[enc("INT_ADD_NEG")]), self.agent)
        self.assertTrue(choice.model_ready)
        predictions = {c["question_id"]: c["prediction"] for c in choice.candidates}
        best = min(predictions, key=lambda i: (abs(predictions[i] - 0.30), i))
        self.assertEqual(choice.candidate.id, best)
        self.assertEqual(list(choice.inputs), list(SPEC_FEATURES))
        self.assertEqual(len(choice.context["model_inputs"]), 8)
        self.assertAlmostEqual(choice.predicted, predictions[best], places=5)

    def test_deterministic_fallback_without_the_model(self):
        pool = [cand(2, "INT_DIV_NEG"), cand(1, "INT_DIV_NEG")]
        situation = self.situation(pool, ["INT_DIV_NEG"], 2, history=[enc("INT_DIV_NEG")])
        first = choose(situation, None)
        self.assertEqual((first.candidate.id, first.fallback_reason, first.model_ready), (1, "model_unavailable", False))
        self.assertEqual(choose(situation, None).candidate.id, 1)

    def test_retake_prefers_unseen_without_losing_coverage(self):
        skills = ["INT_EXPR_NEG", "INT_CONTEXT"]
        pool = [cand(1, "INT_EXPR_NEG", key="A"), cand(2, "INT_EXPR_NEG", key="B"), cand(3, "INT_CONTEXT", key="C")]
        situation = self.situation(pool, skills, 2, history=[enc("INT_ADD_NEG")], seen_keys={"A", "C"},
                                   mastery={"INT_EXPR_NEG": 0.1, "INT_CONTEXT": 0.9})
        choice = choose(situation, self.agent)
        self.assertEqual(choice.candidate.item_key, "B")
        situation.served_ids, situation.covered = {2}, {"INT_EXPR_NEG"}
        self.assertEqual(choose(situation, self.agent).candidate.item_key, "C")  # seen, but coverage needs it

    def test_a_broken_pool_raises_a_recoverable_error(self):
        pool = [cand(1, "INT_EXPR_NEG")]
        with self.assertRaises(SelectionError):
            choose(self.situation(pool, ["INT_EXPR_NEG", "INT_CONTEXT"], 2), self.agent)


class PracticeFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_all()
        cls.teacher = make_teacher()
        cls.classroom = make_class(cls.teacher)
        import_bank(teacher=cls.teacher, classrooms=[cls.classroom])
        cls.foundation = Exercise.objects.get(lesson__code="integer_foundation")
        cls.division = Exercise.objects.get(lesson__code="integer_division")

    def setUp(self):
        self.student = make_student(self.classroom, f"s{self._testMethodName[-12:]}")
        submit_test(self.student)
        self.client.force_login(self.student)

    def page(self, exercise):
        return reverse("practice:exercise", args=[exercise.id])

    def current(self, exercise):
        session = ExerciseSession.objects.get(student=self.student, exercise=exercise, status="in_progress")
        return session, engine.current_item(session)

    def post_answer(self, exercise, correct=True, seconds="12.5"):
        session, item = self.current(exercise)
        choice = item.question.choices.get(is_correct=correct) if correct else item.question.choices.filter(is_correct=False).first()
        return self.client.post(reverse("practice:answer", args=[exercise.id]),
                                {"item": item.id, "choice": choice.id, "active_seconds": seconds}), item

    def test_a_full_mixed_session_covers_every_skill_and_finishes_at_its_length(self):
        self.client.post(reverse("practice:start", args=[self.foundation.id]))
        for number in range(5):
            response, item = self.post_answer(self.foundation, correct=number % 2 == 0)
            if number % 2:
                self.client.post(reverse("practice:move_on", args=[self.foundation.id]), {"item": item.id})
        session = ExerciseSession.objects.get(student=self.student, exercise=self.foundation)
        self.assertTrue(session.is_completed)
        self.assertEqual(session.items.count(), 5)  # no early finish, no extra question
        skills = set(session.items.values_list("question__skill__code", flat=True))
        self.assertEqual(skills, {"INT_NUMBER_LINE", "INT_OPPOSITE_POS4", "INT_ABS_COMPARE", "INT_ORDER_NEG"})
        self.assertEqual(session.first_try_correct, 3)
        self.assertEqual(SelectionDecision.objects.filter(session_question__session=session).count(), 5)
        self.assertEqual(MasteryUpdate.objects.filter(session_question__session=session).count(), 5)
        self.assertTrue(ExerciseFeedback.objects.filter(session=session).exists())
        results = self.client.get(self.page(self.foundation))
        self.assertContains(results, "Right on the first try")
        self.assertContains(results, "Do it one more time")

    def test_one_bkt_update_per_first_answer_and_retry_rules(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        response, item = self.post_answer(self.division, correct=False)
        self.assertRedirects(response, self.page(self.division))
        page = self.client.get(self.page(self.division))
        self.assertContains(page, "Not quite")
        self.assertContains(page, "Show the hint")
        self.assertNotContains(page, item.question.hint)  # the hint stays hidden until asked for
        self.client.post(reverse("practice:hint", args=[self.division.id]), {"item": item.id})
        self.assertContains(self.client.get(self.page(self.division)), item.question.hint)
        # The same wrong choice can't be the retry; a different one is the one retry.
        first_choice = item.attempts.get().choice
        self.client.post(reverse("practice:answer", args=[self.division.id]), {"item": item.id, "choice": first_choice.id})
        self.assertEqual(item.attempts.count(), 1)
        right = item.question.choices.get(is_correct=True)
        response = self.client.post(reverse("practice:answer", args=[self.division.id]), {"item": item.id, "choice": right.id})
        self.assertRedirects(response, self.page(self.division) + f"?done={item.id}")
        item.refresh_from_db()
        self.assertEqual(item.outcome, SessionQuestion.Outcome.CORRECT_RETRY)
        self.assertTrue(item.hint_used)
        # One update, from the wrong first answer; the right retry adds no evidence.
        update = MasteryUpdate.objects.get(session_question=item)
        self.assertFalse(update.observation)
        mastery = StudentSkillMastery.objects.get(student=self.student, skill__code="INT_DIV_NEG")
        self.assertEqual(mastery.evidence_count, 1)
        self.assertAlmostEqual(mastery.mastery_probability, update.next_mastery)
        # Other skills are untouched.
        self.assertEqual(StudentSkillMastery.objects.filter(student=self.student).count(), 1)

    def test_repeated_requests_change_nothing(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        self.client.post(reverse("practice:start", args=[self.division.id]))
        self.assertEqual(ExerciseSession.objects.filter(student=self.student).count(), 1)
        session, item = self.current(self.division)
        right = item.question.choices.get(is_correct=True)
        wrong = item.question.choices.filter(is_correct=False).first()
        for _ in range(2):
            self.client.post(reverse("practice:answer", args=[self.division.id]), {"item": item.id, "choice": right.id})
        self.client.post(reverse("practice:answer", args=[self.division.id]), {"item": item.id, "choice": wrong.id})
        self.assertEqual(item.attempts.count(), 1)
        self.assertEqual(MasteryUpdate.objects.filter(session_question__session=session).count(), 1)
        self.assertEqual(session.items.count(), 2)  # exactly one next question

    def test_resume_returns_to_the_saved_question(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        _response, item = self.post_answer(self.division, correct=False)
        self.client.logout()
        self.client.force_login(self.student)
        page = self.client.get(self.page(self.division))
        self.assertContains(page, item.question.prompt)
        self.assertContains(page, "your first answer")

    def test_the_page_never_shows_the_key_before_the_answer(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        page = self.client.get(self.page(self.division))
        self.assertNotContains(page, "right answer")
        self.assertNotContains(page, "is-correct")

    def test_one_retake_preferring_unseen_items(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        for _ in range(4):
            self.post_answer(self.division)
        first = ExerciseSession.objects.get(student=self.student, exercise=self.division, attempt_number=1)
        self.client.post(reverse("practice:start", args=[self.division.id]), {"retake": "1"})
        for _ in range(4):
            self.post_answer(self.division)
        second = ExerciseSession.objects.get(student=self.student, exercise=self.division, attempt_number=2)
        self.assertTrue(second.is_completed)
        first_keys = set(first.items.values_list("question__item_key", flat=True))
        second_keys = set(second.items.values_list("question__item_key", flat=True))
        self.assertFalse(first_keys & second_keys)  # 15 items: plenty unseen
        self.client.post(reverse("practice:start", args=[self.division.id]), {"retake": "1"})
        self.assertEqual(ExerciseSession.objects.filter(student=self.student, exercise=self.division).count(), 2)
        self.assertContains(self.client.get(self.page(self.division)), "used your one retake")

    def test_decisions_record_inputs_before_the_answer(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        self.post_answer(self.division)
        session, item = self.current(self.division)
        decision = item.decision
        self.assertTrue(decision.model_ready)
        # docs/agent.md: the 12 inputs in the spec's order; the model read 8 of them.
        # (PostgreSQL's jsonb keeps the names, not their order; the export writes the spec's order.)
        self.assertEqual(set(decision.selected_inputs), set(SPEC_FEATURES))
        self.assertEqual(decision.feature_schema_version, "pg42-12inputs-v1")
        self.assertEqual(decision.selected_inputs["candidate_skill_prior_encounters"], 1)
        self.assertEqual(decision.selected_inputs["last_duration_sec"], 12.5)
        self.assertEqual(decision.selected_inputs["last_attempt_count"], 1)
        self.assertEqual(len(decision.context["model_inputs"]), 8)
        self.assertEqual(decision.selection_probability, 1.0)
        first_decision = session.items.get(position=1).decision
        self.assertEqual(first_decision.rule, "first_ever_teacher_order")
        self.assertIsNone(first_decision.selected_inputs)  # no history yet

    def test_model_failure_falls_back_to_teacher_order(self):
        engine.get_agent.cache_clear()
        original = engine.agent_lib.load
        engine.agent_lib.load = lambda directory: (_ for _ in ()).throw(OSError("missing"))
        try:
            with self.assertLogs("apps.practice.engine", level="ERROR"):
                self.client.post(reverse("practice:start", args=[self.division.id]))
                self.post_answer(self.division)
            _session, item = self.current(self.division)
            self.assertEqual(item.decision.fallback_reason, "model_unavailable")
            self.assertFalse(item.decision.model_ready)
            # The inputs are still saved for evaluation (docs/agent.md, "Data provenance").
            self.assertEqual(set(item.decision.selected_inputs), set(SPEC_FEATURES))
        finally:
            engine.agent_lib.load = original
            engine.get_agent.cache_clear()

    def test_unassigned_students_cannot_start(self):
        other = make_student(make_class(make_teacher("t_other"), "Other"), "outsider5")
        submit_test(other)
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("practice:start", args=[self.division.id])).status_code, 404)
        self.assertFalse(ExerciseSession.objects.filter(student=other).exists())

    def test_labels_and_cards_follow_practice(self):
        self.client.post(reverse("practice:start", args=[self.division.id]))
        for _ in range(4):
            self.post_answer(self.division, correct=False)
            _s, item = self.current(self.division) if ExerciseSession.objects.filter(
                student=self.student, status="in_progress").exists() else (None, None)
            if item and item.attempts.exists():
                self.client.post(reverse("practice:move_on", args=[self.division.id]), {"item": item.id})
        journey = self.client.get(reverse("dashboards:learn"))
        self.assertContains(journey, "Needs practice")
        lesson = self.client.get(self.division.lesson.get_absolute_url())
        self.assertContains(lesson, "Done: 0 of 4 right on the first try")
