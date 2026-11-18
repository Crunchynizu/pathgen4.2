# Fitted model files

Fitted on Mon 16 Nov 2026 with `thesis/pathgen4.0-trainer`, run at `skill_level: fine_skill` (the 10 skills) with the BKT limits on (guess ≤ 0.3, slip ≤ 0.1, learn ≤ 0.3). Settings: `trainer_config.json`. Checksums: `manifest.json`.

| File | What it is | Used by |
|---|---|---|
| `bkt_params.json` | BKT numbers for each of the 10 skills | Phase 5: mastery updates |
| `struggle_model.json` | The 8-input struggle model (logistic regression, plain JSON, no pickle) | Phase 5: scoring candidate questions |
| `template_difficulty.json` | The real Junyi struggle rate of each of the 16 templates | Phase 4: each question's difficulty number, frozen when it is published |
| `bkt_report.md`, `validation_report.md`, `validation_metrics.json` | The fit's checks, for chapter 4 | People |

## The numbers in short (validation students)

- BKT beats always predicting the average on all 10 skills. With 0 of 6 right, mastery ends between 0.03 and 0.34 on every skill.
- The struggle model: AUC 0.752, mean log loss 0.425. BKT alone: AUC 0.719, log loss 0.442. Skill base rate: AUC 0.652. Boosted trees, fitted only for comparison: AUC 0.773.
- The test students haven't been scored yet. `run.py evaluate` runs once, when the model is final.

The three files are a set. If the groupmate's rerun with limits replaces them, replace all three together, then re-import the bank so the frozen difficulty numbers match.
