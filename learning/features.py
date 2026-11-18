"""The model's input recipe (pathgen4.0-trainer, trainer/features.py, student_rows).

History = the student's earlier completed tracked encounters, across exercises, in completion
order. One encounter per served question, even with a retry. Pure functions, no Django.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

FEATURE_SCHEMA_VERSION = "pg42-12inputs-v1"

# The 12 inputs of docs/agent.md ("Exact feature contract"), in its order. Every served question
# saves them (SelectionDecision.selected_inputs) for evaluation and the after-study retrain.
SPEC_FEATURES = (
    "candidate_skill_id",
    "candidate_difficulty",
    "last_correct",
    "last_attempt_count",
    "last_hint_used",
    "last_duration_sec",
    "recent_correct_rate",
    "recent_hint_rate",
    "recent_mean_attempts",
    "recent_median_duration_sec",
    "candidate_skill_prior_encounters",
    "candidate_skill_bkt_mastery",
)

# The fitted model (PLAN.md, "Settled") reads 8 of them: the 4 attempt and time inputs shift between
# Junyi (unlimited attempts, any-time hints) and PathGen (2 attempts, hint after a wrong answer).
FEATURES = (
    "candidate_skill",                   # skill of the candidate question
    "candidate_difficulty",              # struggle rate of its Junyi template (higher = harder)
    "last_correct",                      # previous encounter right on the first try, no hint
    "last_hint_used",                    # previous encounter used the hint
    "recent_correct_rate",               # share right over the last `window` encounters
    "recent_hint_rate",                  # share with a hint over the same encounters
    "candidate_skill_prior_encounters",  # earlier encounters on the candidate's skill
    "candidate_skill_bkt_mastery",       # saved BKT mastery of that skill, or its fitted prior
)
NUMERIC = FEATURES[1:]


@dataclass(frozen=True)
class Encounter:
    skill: str
    difficulty: str          # easy / medium / hard (for the easier/harder rule)
    first_correct: bool
    hint_used: bool
    attempts: int
    seconds: float | None    # active answering time, None if not measured

    @property
    def correct(self) -> int:
        """Right on the first try without a hint: the trainer's rule (Junyi counts a hinted answer as wrong)."""
        return 1 if self.first_correct and not self.hint_used else 0

    @property
    def struggled(self) -> bool:
        """docs/special_algo.md: an incorrect first answer, a retry, or hint use."""
        return (not self.first_correct) or self.attempts > 1 or self.hint_used


def model_inputs(history, *, candidate_skill: str, candidate_difficulty: float, mastery: float, window: int) -> dict:
    """The 8 inputs for one candidate. Needs at least one earlier encounter."""
    if not history:
        raise ValueError("The struggle model needs at least one earlier answer.")
    recent = history[-window:]
    last = history[-1]
    return {
        "candidate_skill": candidate_skill,
        "candidate_difficulty": float(candidate_difficulty),
        "last_correct": last.correct,
        "last_hint_used": int(last.hint_used),
        "recent_correct_rate": sum(e.correct for e in recent) / len(recent),
        "recent_hint_rate": sum(int(e.hint_used) for e in recent) / len(recent),
        "candidate_skill_prior_encounters": sum(1 for e in history if e.skill == candidate_skill),
        "candidate_skill_bkt_mastery": float(mastery),
    }


def snapshot(history, *, candidate_skill: str, candidate_difficulty, mastery: float, window: int) -> dict | None:
    """All 12 spec inputs for one candidate, in order; None without history (rule 1 then applies).

    Missing values stay None (null in the saved JSON): durations that weren't measured, or a
    question without a difficulty number.
    """
    if not history:
        return None
    timing = logged_only(history, window)
    recent = history[-window:]
    last = history[-1]
    values = {
        "candidate_skill_id": candidate_skill,
        "candidate_difficulty": None if candidate_difficulty is None else float(candidate_difficulty),
        "last_correct": int(last.first_correct),
        "last_attempt_count": timing["last_attempt_count"],
        "last_hint_used": int(last.hint_used),
        "last_duration_sec": timing["last_duration_sec"],
        "recent_correct_rate": sum(int(e.first_correct) for e in recent) / len(recent),
        "recent_hint_rate": sum(int(e.hint_used) for e in recent) / len(recent),
        "recent_mean_attempts": timing["recent_mean_attempts"],
        "recent_median_duration_sec": timing["recent_median_duration_sec"],
        "candidate_skill_prior_encounters": sum(1 for e in history if e.skill == candidate_skill),
        "candidate_skill_bkt_mastery": float(mastery),
    }
    return {name: values[name] for name in SPEC_FEATURES}


def logged_only(history, window: int) -> dict:
    """The spec's 4 attempt/time inputs: saved for the after-study retrain, not model inputs (PLAN.md)."""
    if not history:
        return {"last_attempt_count": None, "last_duration_sec": None,
                "recent_mean_attempts": None, "recent_median_duration_sec": None}
    recent = history[-window:]
    durations = [e.seconds for e in recent if e.seconds is not None]
    return {
        "last_attempt_count": history[-1].attempts,
        "last_duration_sec": history[-1].seconds,
        "recent_mean_attempts": sum(e.attempts for e in recent) / len(recent),
        "recent_median_duration_sec": median(durations) if durations else None,
    }
