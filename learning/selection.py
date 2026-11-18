"""The fixed question selection rules (docs/special_algo.md, sections 1 and 2). Pure, no Django.

1. Coverage: a candidate must leave enough slots and questions for every required skill not yet covered.
2. First-ever question: teacher pool order. Otherwise pick the skill: uncovered required skills when
   every slot left is needed for them, else the lowest-mastery eligible skill (ties: teacher order).
3. Retake: prefer items not seen in the first session.
4. Two struggles in a row on the skill -> prefer easier; two independent successes -> prefer harder.
5. Rank by distance of the predicted struggle chance to 0.30; ties and fallbacks use teacher order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .agent import AgentConfigError, predict
from .features import model_inputs, snapshot

POLICY_VERSION = "pg42-rules-v1"
TARGET_STRUGGLE = 0.30
LEVELS = {"easy": 0, "medium": 1, "hard": 2}


class SelectionError(Exception):
    """No legal question: a broken pool. Progress is kept; the page shows a recoverable error."""


@dataclass(frozen=True)
class Candidate:
    id: int
    item_key: str
    skill: str
    difficulty: str
    difficulty_value: float | None
    order: int


@dataclass
class Situation:
    pool: list
    required: list            # required skill codes, curriculum order
    target_count: int
    served_ids: set
    covered: set              # skills of completed questions in this session
    single_skill: bool
    history: list             # features.Encounter, oldest first, all exercises
    mastery: dict             # skill code -> current mastery (saved, or the fitted prior)
    seen_keys: set = field(default_factory=set)  # retake: item keys served in the first session


@dataclass
class Choice:
    candidate: Candidate
    rule: str
    direction: str = ""
    fallback_reason: str = ""
    model_ready: bool = False
    predicted: float | None = None
    inputs: dict | None = None
    candidates: list = field(default_factory=list)
    context: dict = field(default_factory=dict)


def _teacher_order(candidates):
    return sorted(candidates, key=lambda c: (c.order, c.id))


def eligible(situation: Situation):
    unused = _teacher_order(c for c in situation.pool if c.id not in situation.served_ids)
    remaining = situation.target_count - len(situation.served_ids)
    if remaining <= 0:
        raise SelectionError("This session already has all its questions.")
    uncovered = [s for s in situation.required if s not in situation.covered]

    def keeps_coverage(candidate):
        need = [s for s in uncovered if s != candidate.skill]
        if len(need) > remaining - 1:
            return False
        others = [c for c in unused if c.id != candidate.id]
        return all(any(c.skill == s for c in others) for s in need)

    return [c for c in unused if keeps_coverage(c)], remaining, uncovered


def _direction(history, skill):
    last_two = [e for e in history if e.skill == skill][-2:]
    if len(last_two) < 2:
        return "", None
    reference = LEVELS.get(last_two[-1].difficulty)
    if all(e.struggled for e in last_two):
        return "easier", reference
    if all(not e.struggled for e in last_two):
        return "harder", reference
    return "", reference


def _apply_direction(candidates, direction, reference):
    if not direction or reference is None:
        return candidates
    if direction == "easier":
        preferred = [c for c in candidates if LEVELS[c.difficulty] < reference]
        target = min(LEVELS[c.difficulty] for c in candidates)
    else:
        preferred = [c for c in candidates if LEVELS[c.difficulty] > reference]
        target = max(LEVELS[c.difficulty] for c in candidates)
    # If no easier (harder) item is left, keep the closest level in that direction.
    return preferred or [c for c in candidates if LEVELS[c.difficulty] == target]


def choose(situation: Situation, agent=None) -> Choice:
    options, remaining, uncovered = eligible(situation)
    if not options:
        raise SelectionError("No question in the pool can keep the required skills covered.")

    history = situation.history
    window = agent.window if agent else 5
    context = {
        "remaining_slots": remaining,
        "uncovered_required": uncovered,
        "mastery": {skill: round(value, 6) for skill, value in situation.mastery.items()},
        "history_length": len(history),
        "recent": [{"skill": e.skill, "correct": e.correct, "hint": int(e.hint_used)} for e in history[-window:]],
        "retake": bool(situation.seen_keys),
    }

    def spec_inputs(candidate):
        """The 12 saved inputs (docs/agent.md), kept even when the model can't score."""
        return snapshot(history, candidate_skill=candidate.skill, candidate_difficulty=candidate.difficulty_value,
                        mastery=situation.mastery[candidate.skill], window=window)

    # Score every eligible candidate when the model can run, for the decision log.
    scores, fallback = {}, ""
    if not history:
        fallback = "no_history"
    elif agent is None:
        fallback = "model_unavailable"
    else:
        for candidate in options:
            if candidate.difficulty_value is None:
                fallback = "missing_difficulty"
                scores = {}
                break
            inputs = model_inputs(
                history,
                candidate_skill=candidate.skill,
                candidate_difficulty=candidate.difficulty_value,
                mastery=situation.mastery[candidate.skill],
                window=window,
            )
            try:
                scores[candidate.id] = (predict(agent, inputs), inputs)
            except AgentConfigError:
                fallback, scores = "model_error", {}
                break

    def log(final_ids):
        return [
            {
                "question_id": c.id,
                "item_key": c.item_key,
                "skill": c.skill,
                "difficulty": c.difficulty,
                "difficulty_value": c.difficulty_value,
                "prediction": round(scores[c.id][0], 6) if c.id in scores else None,
                "in_final_set": c.id in final_ids,
            }
            for c in options
        ]

    # Rule 1: the first-ever tracked question.
    if not history:
        chosen = options[0]
        return Choice(chosen, "first_ever_teacher_order", fallback_reason=fallback,
                      candidates=log({chosen.id}), context=context)

    # Rule 2: the skill.
    skills_available = {c.skill for c in options}
    if situation.single_skill:
        rule = "single_skill"
        skill_options = [s for s in situation.required if s in skills_available] or sorted(skills_available)
    elif uncovered and remaining == len(uncovered):
        rule = "coverage"
        skill_options = [s for s in uncovered if s in skills_available]
    else:
        rule = "lowest_mastery"
        skill_options = sorted(skills_available)
    first_item = {}
    for c in options:
        first_item.setdefault(c.skill, c.order)
    skill = min(skill_options, key=lambda s: (situation.mastery.get(s, 1.0), first_item[s]))
    pool = [c for c in options if c.skill == skill]

    # Rule 3: a retake prefers items the student hasn't seen in the first session.
    if situation.seen_keys:
        unseen = [c for c in pool if c.item_key not in situation.seen_keys]
        pool = unseen or pool

    # Rule 4: easier after two struggles, harder after two independent successes.
    direction, reference = _direction(history, skill)
    pool = _apply_direction(pool, direction, reference)
    context["reference_level"] = reference

    # Rule 5: closest predicted struggle to 0.30; teacher order on ties or without the model.
    if scores and all(c.id in scores for c in pool):
        ranked = sorted(pool, key=lambda c: (abs(scores[c.id][0] - TARGET_STRUGGLE), c.order, c.id))
        chosen = ranked[0]
        probability, inputs = scores[chosen.id]
        context["model_inputs"] = inputs
        return Choice(chosen, rule, direction=direction, model_ready=True, predicted=probability,
                      inputs=spec_inputs(chosen), candidates=log({c.id for c in pool}), context=context)
    chosen = _teacher_order(pool)[0]
    return Choice(chosen, rule, direction=direction, fallback_reason=fallback or "model_not_scored",
                  inputs=spec_inputs(chosen), candidates=log({c.id for c in pool}), context=context)
