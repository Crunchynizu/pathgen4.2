"""The struggle model (docs/agent.md, adapted by PLAN.md: 8 inputs, plain JSON, no pickle).

A logistic regression fitted by pathgen4.0-trainer on the Junyi log. It returns the chance that a
student struggles (first answer wrong, or hint used) on a candidate question. The selection rules
in selection.py decide what to do with it. Pure functions, no Django.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from .features import FEATURES, NUMERIC

MODEL_FILE = "struggle_model.json"
DIFFICULTY_FILE = "template_difficulty.json"
MANIFEST_FILE = "manifest.json"


class AgentConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Agent:
    model: dict
    window: int
    version: str             # "agent-" + first 12 hex of the model file's SHA-256
    difficulty_version: str  # "td-" + first 12 hex of the difficulty file's SHA-256


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AgentConfigError(f"{name} must be a finite number.")
    return float(value)


def load(directory) -> Agent:
    """Read the model, check it against manifest.json's checksums and the input list."""
    directory = Path(directory)
    raw = (directory / MODEL_FILE).read_bytes()
    difficulty_raw = (directory / DIFFICULTY_FILE).read_bytes()
    manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
    for name, data in ((MODEL_FILE, raw), (DIFFICULTY_FILE, difficulty_raw)):
        if manifest.get("files", {}).get(name) != hashlib.sha256(data).hexdigest():
            raise AgentConfigError(f"{name} doesn't match the checksum in {MANIFEST_FILE}.")
    model = json.loads(raw)
    if model.get("type") != "logistic regression" or model.get("format") != 1:
        raise AgentConfigError("The struggle model must be a format-1 logistic regression.")
    if model.get("skill_level") != "fine_skill":
        raise AgentConfigError("The struggle model must be the 10-skill fit.")
    if list(model.get("numeric_features", [])) != list(NUMERIC):
        raise AgentConfigError("The struggle model was saved with different inputs.")
    for key in ("mean", "scale"):
        values = model.get(key) or []
        if len(values) != len(NUMERIC) or any(_finite(v, key) == 0 and key == "scale" for v in values):
            raise AgentConfigError(f"The struggle model's {key} is invalid.")
    _finite(model.get("intercept"), "intercept")
    for skill in model.get("skills", []):
        _finite(model.get("skill_coef", {}).get(skill), f"skill_coef[{skill}]")
    for name in NUMERIC:
        _finite(model.get("numeric_coef", {}).get(name), f"numeric_coef[{name}]")
    window = model.get("recent_window")
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise AgentConfigError("recent_window must be a positive integer.")
    return Agent(
        model=model,
        window=window,
        version="agent-" + hashlib.sha256(raw).hexdigest()[:12],
        difficulty_version="td-" + hashlib.sha256(difficulty_raw).hexdigest()[:12],
    )


def predict(agent: Agent, inputs: dict) -> float:
    """P(struggle) for one candidate (the trainer's predict_one). Raises on bad input."""
    model = agent.model
    if set(inputs) != set(FEATURES):
        raise AgentConfigError("The inputs don't match the model's 8 inputs.")
    if inputs["candidate_skill"] not in model["skill_coef"]:
        raise AgentConfigError(f"The model doesn't know {inputs['candidate_skill']}.")
    z = model["intercept"] + model["skill_coef"][inputs["candidate_skill"]]
    for name, mean, scale in zip(model["numeric_features"], model["mean"], model["scale"]):
        x = _finite(inputs[name], name)
        if name in model["log1p"]:
            x = math.log1p(x)
        z += model["numeric_coef"][name] * (x - mean) / scale
    probability = 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))
    if not 0.0 <= probability <= 1.0 or not math.isfinite(probability):
        raise AgentConfigError("The model returned an invalid probability.")
    return probability
