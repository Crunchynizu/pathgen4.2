"""Per-skill progress labels (docs/special_algo.md §4, "V1 label defaults").

Display thresholds only, not grades or access rules.
"""
DOING_WELL_AT = 0.75

NOT_YET = "Not yet practiced"
NEEDS_PRACTICE = "Needs practice"
DOING_WELL = "Doing well"


def label(mastery_probability, evidence_count):
    if not evidence_count or mastery_probability is None:
        return NOT_YET
    return DOING_WELL if mastery_probability >= DOING_WELL_AT else NEEDS_PRACTICE


def tone(text):
    """A CSS hook; the label text itself carries the meaning, not the color."""
    return {NOT_YET: "none", NEEDS_PRACTICE: "needs", DOING_WELL: "well"}[text]
