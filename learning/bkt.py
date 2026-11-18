"""Bayesian Knowledge Tracing (docs/bkt.md). Pure functions, no Django.

The fitted numbers come from model_artifacts/bkt_params.json (10 skills, limits on), written by
pathgen4.0-trainer. Only the first answer to a tracked practice question is an observation.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

SKILLS = (
    "INT_NUMBER_LINE", "INT_OPPOSITE_POS4", "INT_ABS_COMPARE", "INT_ORDER_NEG", "INT_ADD_NEG",
    "INT_SUB_NEG", "INT_MULT_NEG", "INT_DIV_NEG", "INT_EXPR_NEG", "INT_CONTEXT",
)
FILE = "bkt_params.json"


class BktConfigError(ValueError):
    """Missing or invalid fitted numbers. Never invent replacement values."""


@dataclass(frozen=True)
class Params:
    prior: float  # P(L0)
    learn: float  # P(T)
    guess: float  # P(G)
    slip: float   # P(S)


@dataclass(frozen=True)
class Bkt:
    params: dict  # skill code -> Params
    version: str  # "bkt-" + first 12 hex of the file's SHA-256


def _probability(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise BktConfigError(f"{name} must be a probability.")
    return float(value)


def load(directory) -> Bkt:
    raw = (Path(directory) / FILE).read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BktConfigError(f"{FILE} is not valid JSON.") from error
    if payload.get("skill_level") != "fine_skill":
        raise BktConfigError(f"{FILE} must be the 10-skill fit (skill_level fine_skill).")
    table = payload.get("skills") or {}
    params = {}
    for code in SKILLS:
        row = table.get(code)
        if not isinstance(row, dict):
            raise BktConfigError(f"{FILE} has no numbers for {code}.")
        params[code] = Params(
            prior=_probability(row.get("p_l0"), f"{code} p_l0"),
            learn=_probability(row.get("p_t"), f"{code} p_t"),
            guess=_probability(row.get("p_g"), f"{code} p_g"),
            slip=_probability(row.get("p_s"), f"{code} p_s"),
        )
    return Bkt(params=params, version="bkt-" + hashlib.sha256(raw).hexdigest()[:12])


def p_correct(mastery: float, params: Params) -> float:
    """Predicted chance of a right first answer before answering."""
    return mastery * (1 - params.slip) + (1 - mastery) * params.guess


def update(mastery: float, correct: bool, params: Params) -> tuple[float, float]:
    """(posterior after the observation, next mastery after the learning step)."""
    if correct:
        known, unknown = mastery * (1 - params.slip), (1 - mastery) * params.guess
    else:
        known, unknown = mastery * params.slip, (1 - mastery) * (1 - params.guess)
    total = known + unknown
    posterior = known / total if total > 0 else mastery
    return posterior, posterior + (1 - posterior) * params.learn
