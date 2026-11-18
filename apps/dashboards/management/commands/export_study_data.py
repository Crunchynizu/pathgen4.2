"""manage.py export_study_data [--class "Grade 7 - A" ...] [--include-demo] [--out private/exports/<stamp>]

Writes the analysis files (CSV) and a report (report.md) for chapter 4. Students appear as S001,
S002, ...; pseudonym_key.csv links keys to accounts and must stay private (it goes to private/,
which Git ignores).
"""
import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.dashboards import study

README = """PathGen 4.2 study export ({stamp})

students.csv            one row per student: pre/post scores, change in percentage points, practice totals
assessment_answers.csv  every submitted pretest/posttest answer, with the item's skill
practice_answers.csv    every finished practice question: first answer, retry, hint, time, the selection
                        rule, the model's prediction and BKT mastery before/after
trainer_update.csv      the same answers in the format pathgen4.0-trainer's `update` step reads
agent_retrain.csv       the 12 model inputs saved when each question was chosen, with
                        struggle_on_next_question (docs/agent.md); first-ever questions are left out
report.md               the paired pre/post comparison, scores by skill, and how the model did on PathGen
pseudonym_key.csv       S001... -> username. PRIVATE: never put it in the thesis or a shared folder.
"""


def write_csv(path, rows, fields=None):
    fields = fields or (list(rows[0]) if rows else [])
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value, digits=2, suffix=""):
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def report(result, classes, stamp):
    p = result["paired"]
    lines = [
        f"# PathGen 4.2 study results ({stamp})",
        "",
        f"Classes: {', '.join(c.name for c in classes) or 'none'}. Students: {result['students']}. "
        f"With both tests submitted: {p['n']}.",
        "",
        "## Pretest and posttest (the same locked 30 items)",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Mean pretest | {fmt(p['mean_before'], 1, '%')} |",
        f"| Mean posttest | {fmt(p['mean_after'], 1, '%')} |",
        f"| Mean change | {fmt(p['mean_change'], 1, ' points')} |",
        f"| SD of the change | {fmt(p['sd_change'], 1)} |",
        f"| 95% CI of the change | {fmt(p['ci95'][0], 1) + ' to ' + fmt(p['ci95'][1], 1) if p['ci95'] else 'n/a'} |",
        f"| Paired t | {fmt(p['t'], 3)} (df {p['df'] if p['df'] is not None else 'n/a'}) |",
        f"| Two-sided p | {fmt(p['p'], 4)} |",
        f"| Cohen's dz | {fmt(p['cohens_dz'], 2)} |",
        f"| Mean normalized gain | {fmt(result['normalized_gain_mean'], 2)} |",
        "",
        "The t-test assumes the changes are roughly normal; with a small class, also report the",
        "spread (students.csv) and check outliers before reading the p-value.",
        "",
        "## Share correct by skill (students with both tests)",
        "",
        "| Skill | Pretest | Posttest |",
        "|---|---|---|",
    ]
    for skill, bucket in sorted(result["by_skill"].items()):
        pre = bucket["pretest"]
        post = bucket["posttest"]
        lines.append(
            f"| {skill} | {fmt(100 * pre[0] / pre[1] if pre[1] else None, 1, '%')} ({pre[1]} answers) "
            f"| {fmt(100 * post[0] / post[1] if post[1] else None, 1, '%')} ({post[1]} answers) |"
        )
    lines.append("")
    lines.append("INT_OPPOSITE_POS4 has no item on the locked test, so it is not measured here.")
    q = result["practice"]
    lines += [
        "",
        "## Practice and the struggle model on PathGen students",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Practice answers | {q['answers']} |",
        f"| Right on the first try | {fmt(q['first_try_rate'] * 100 if q['first_try_rate'] is not None else None, 1, '%')} |",
        f"| Struggled (wrong first, retry or hint) | {fmt(q['struggle_rate'] * 100 if q['struggle_rate'] is not None else None, 1, '%')} |",
        f"| Questions picked with a model score | {q['scored_by_model']} |",
        f"| Picks that used the teacher-order fallback | {q['fallbacks']} |",
        f"| Mean predicted struggle (scored picks) | {fmt(q['mean_predicted'], 3)} |",
        f"| Observed struggle (scored picks) | {fmt(q['observed_struggle_when_scored'], 3)} |",
        f"| Brier score | {fmt(q['brier'], 3)} |",
        f"| AUC | {fmt(q['auc'], 3)} |",
        "",
        "First questions of a student's first-ever practice have no score: the model needs one earlier answer.",
    ]
    return "\n".join(lines) + "\n"


class Command(BaseCommand):
    help = "Export pseudonymous study data and a results report for chapter 4."

    def add_arguments(self, parser):
        parser.add_argument("--class", dest="classes", action="append")
        parser.add_argument("--include-demo", action="store_true")
        parser.add_argument("--out")

    def handle(self, *args, **options):
        classrooms = study.classes(options["classes"], options["include_demo"])
        if options["classes"] and len(classrooms) != len(set(options["classes"])):
            raise CommandError("Some class names don't exist.")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        out = Path(options["out"] or Path(settings.BASE_DIR) / "private" / "exports" / stamp)
        out.mkdir(parents=True, exist_ok=True)

        keyed = study.students(classrooms)
        students = study.student_rows(keyed)
        assessments = study.assessment_rows(keyed)
        practice = study.practice_rows(keyed)
        write_csv(out / "students.csv", students)
        write_csv(out / "assessment_answers.csv", assessments,
                  ["student_key", "kind", "position", "item_code", "skill", "selected", "correct"])
        write_csv(out / "practice_answers.csv", [{k: v for k, v in row.items() if not k.startswith("_")}
                                                 for row in practice])
        write_csv(out / "agent_retrain.csv", study.retrain_rows(practice), study.RETRAIN_FIELDS)
        write_csv(out / "trainer_update.csv", study.trainer_rows(practice),
                  ["user_id", "answered_at", "skill", "template_id", "correct", "hint_used"])
        write_csv(out / "pseudonym_key.csv", [
            {"student_key": key, "username": p.user.username, "name": p.user.display_name, "class": p.classroom.name}
            for key, p in keyed
        ])
        (out / "report.md").write_text(report(study.analysis(students, assessments, practice), classrooms, stamp),
                                       encoding="utf-8")
        (out / "README.txt").write_text(README.format(stamp=stamp), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Exported {len(students)} students, {len(practice)} practice answers to {out}"
        ))
        self.stdout.write("pseudonym_key.csv links keys to accounts: keep it private.")
