"""Study data for chapter 4: pre/post scores and practice logs, with pseudonymous student keys.

Demo classes (names starting with "DEMO") are left out unless asked for.
"""
import json

from apps.assessments.models import AssessmentAnswer, AssessmentAttempt, Kind
from apps.assessments.services import score_change
from apps.classrooms.models import Classroom, StudentProfile
from apps.practice.models import ExerciseAssignment, ExerciseSession, SessionQuestion
from learning import stats
from learning.features import SPEC_FEATURES

LETTERS = "ABCD"


def classes(names=None, include_demo=False):
    queryset = Classroom.objects.order_by("name")
    if names:
        queryset = queryset.filter(name__in=names)
    elif not include_demo:
        queryset = queryset.exclude(name__istartswith="DEMO")
    return list(queryset)


def students(classrooms):
    """[(key, profile)] with keys S001, S002 ... in class then username order."""
    profiles = StudentProfile.objects.filter(classroom__in=classrooms).select_related("user", "classroom").order_by(
        "classroom__name", "user__username"
    )
    return [(f"S{number:03d}", profile) for number, profile in enumerate(profiles, start=1)]


def _attempts(users):
    found = {}
    for attempt in AssessmentAttempt.objects.filter(student__in=users, state=AssessmentAttempt.State.SUBMITTED):
        found[(attempt.student_id, attempt.kind)] = attempt
    return found


def student_rows(keyed):
    users = [profile.user for _key, profile in keyed]
    attempts = _attempts(users)
    assigned = {}
    for assignment in ExerciseAssignment.objects.filter(classroom__in={p.classroom for _k, p in keyed}, status="active"):
        assigned.setdefault(assignment.classroom_id, set()).add(assignment.exercise_id)
    sessions = {}
    for session in ExerciseSession.objects.filter(student__in=users, status="completed"):
        sessions.setdefault(session.student_id, []).append(session)
    rows = []
    for key, profile in keyed:
        pre = attempts.get((profile.user_id, Kind.PRETEST))
        post = attempts.get((profile.user_id, Kind.POSTTEST))
        own = sessions.get(profile.user_id, [])
        firsts = [s for s in own if s.attempt_number == 1]
        rows.append({
            "student_key": key,
            "class": profile.classroom.name,
            "pretest_correct": pre.correct_count if pre else "",
            "pretest_items": pre.item_count if pre else "",
            "pretest_percent": pre.percent if pre else "",
            "posttest_correct": post.correct_count if post else "",
            "posttest_items": post.item_count if post else "",
            "posttest_percent": post.percent if post else "",
            "change_points": score_change(pre, post) if pre and post else "",
            "exercises_assigned": len(assigned.get(profile.classroom_id, set())),
            "exercises_finished": len({s.exercise_id for s in own}),
            "retakes_finished": sum(1 for s in own if s.attempt_number == 2),
            "first_try_right": sum(s.first_try_correct or 0 for s in firsts),
            "first_try_asked": sum(s.target_count for s in firsts),
        })
    return rows


def assessment_rows(keyed):
    key_of = {profile.user_id: key for key, profile in keyed}
    answers = AssessmentAnswer.objects.filter(
        attempt__student_id__in=key_of, attempt__state=AssessmentAttempt.State.SUBMITTED
    ).select_related("attempt", "item__skill").order_by("attempt__student_id", "attempt__kind", "item__position")
    return [
        {
            "student_key": key_of[a.attempt.student_id],
            "kind": a.attempt.kind,
            "position": a.item.position,
            "item_code": a.item.source_code,
            "skill": a.item.skill.code,
            "selected": LETTERS[a.selected_index] if a.selected_index is not None else "",
            "correct": int(bool(a.is_correct)),
        }
        for a in answers
    ]


def practice_rows(keyed):
    key_of = {profile.user_id: key for key, profile in keyed}
    items = (
        SessionQuestion.objects.filter(session__student_id__in=key_of, completed_at__isnull=False)
        .select_related("session__classroom", "session__exercise__lesson", "session__revision", "question__skill",
                        "decision", "mastery_update")
        .prefetch_related("attempts")
        .order_by("session__student_id", "completed_at", "id")
    )
    rows = []
    for item in items:
        attempts = sorted(item.attempts.all(), key=lambda a: a.attempt_number)
        decision = getattr(item, "decision", None)
        update = getattr(item, "mastery_update", None)
        first_correct = bool(attempts and attempts[0].is_correct)
        rows.append({
            "student_key": key_of[item.session.student_id],
            "class": item.session.classroom.name,
            "lesson": item.session.exercise.lesson.code,
            "exercise": item.session.revision.title,
            "revision": item.session.revision.number,
            "session_attempt": item.session.attempt_number,
            "position": item.position,
            "item_key": item.question.item_key,
            "skill": item.question.skill.code,
            "difficulty": item.question.difficulty,
            "junyi_template": item.question.junyi_template,
            "difficulty_value": item.question.difficulty_value,
            "first_answered_at": attempts[0].submitted_at.isoformat() if attempts else "",
            "completed_at": item.completed_at.isoformat(),
            "first_correct": int(first_correct),
            "attempts": len(attempts),
            "hint_used": int(item.hint_used),
            "retry_correct": int(len(attempts) > 1 and attempts[1].is_correct) if len(attempts) > 1 else "",
            "outcome": item.outcome,
            "answer_seconds": item.answer_seconds if item.answer_seconds is not None else "",
            "struggle": int((not first_correct) or len(attempts) > 1 or item.hint_used),
            "rule": decision.rule if decision else "",
            "fallback_reason": decision.fallback_reason if decision else "",
            "model_ready": int(decision.model_ready) if decision else "",
            "predicted_struggle": decision.predicted_struggle if decision and decision.predicted_struggle is not None else "",
            "agent_version": decision.agent_version if decision else "",
            "mastery_before": update.prior if update else "",
            "mastery_after": update.next_mastery if update else "",
            "selected_inputs": json.dumps(decision.selected_inputs) if decision and decision.selected_inputs else "",
            "_inputs": decision.selected_inputs if decision else None,
        })
    return rows


def retrain_rows(practice):
    """docs/agent.md, "Data provenance and later retraining": the 12 inputs saved when each question
    was chosen, joined to what happened on it. Rows without usable history are left out. The key and
    times are for grouping and order only, never predictors."""
    rows = []
    for row in practice:
        inputs = row.get("_inputs")
        if not inputs:
            continue
        out = {"student_key": row["student_key"], "first_answered_at": row["first_answered_at"],
               "completed_at": row["completed_at"], "lesson": row["lesson"], "item_key": row["item_key"]}
        out.update({name: "" if inputs.get(name) is None else inputs.get(name) for name in SPEC_FEATURES})
        out["struggle_on_next_question"] = row["struggle"]
        out["model_ready"] = row["model_ready"]
        out["predicted_struggle"] = row["predicted_struggle"]
        rows.append(out)
    return rows


RETRAIN_FIELDS = (["student_key", "first_answered_at", "completed_at", "lesson", "item_key"] + list(SPEC_FEATURES)
                  + ["struggle_on_next_question", "model_ready", "predicted_struggle"])


def trainer_rows(practice):
    """The format pathgen4.0-trainer's `update` step reads (README, "After the study")."""
    return [
        {
            "user_id": row["student_key"],
            "answered_at": row["first_answered_at"],
            "skill": row["skill"],
            "template_id": row["junyi_template"],
            "correct": int(row["first_correct"] and not row["hint_used"]),
            "hint_used": row["hint_used"],
        }
        for row in practice
    ]


def analysis(student_table, assessment_table, practice):
    paired_rows = [r for r in student_table if r["pretest_percent"] != "" and r["posttest_percent"] != ""]
    pre = [100 * r["pretest_correct"] / r["pretest_items"] for r in paired_rows]
    post = [100 * r["posttest_correct"] / r["posttest_items"] for r in paired_rows]
    result = {"students": len(student_table), "paired": stats.paired(pre, post)}
    gains = [g for g in (stats.normalized_gain(a, b) for a, b in zip(pre, post)) if g is not None]
    result["normalized_gain_mean"] = sum(gains) / len(gains) if gains else None

    paired_keys = {r["student_key"] for r in paired_rows}
    by_skill = {}
    for row in assessment_table:
        if row["student_key"] not in paired_keys:
            continue
        bucket = by_skill.setdefault(row["skill"], {"pretest": [0, 0], "posttest": [0, 0]})
        bucket[row["kind"]][0] += row["correct"]
        bucket[row["kind"]][1] += 1
    result["by_skill"] = by_skill

    scored = [r for r in practice if r["predicted_struggle"] != ""]
    predictions = [float(r["predicted_struggle"]) for r in scored]
    outcomes = [r["struggle"] for r in scored]
    result["practice"] = {
        "answers": len(practice),
        "first_try_rate": (sum(r["first_correct"] for r in practice) / len(practice)) if practice else None,
        "struggle_rate": (sum(r["struggle"] for r in practice) / len(practice)) if practice else None,
        "scored_by_model": len(scored),
        "fallbacks": sum(1 for r in practice if r["fallback_reason"]),
        "mean_predicted": (sum(predictions) / len(predictions)) if predictions else None,
        "observed_struggle_when_scored": (sum(outcomes) / len(outcomes)) if outcomes else None,
        "brier": stats.brier(predictions, outcomes),
        "auc": stats.auc(predictions, outcomes),
    }
    return result
