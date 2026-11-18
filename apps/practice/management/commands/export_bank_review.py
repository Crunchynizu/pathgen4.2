"""Write a printable review sheet of content/question_bank.json for the math teacher's check.

    manage.py export_bank_review [--out content/review/question_bank_review.html]

Shows every question with its answer key, skill, level, hint and what changed from 3.0.
Rebuild it after corrections; the JSON stays the source of truth.
"""
import html
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.curriculum.seed import LESSONS, SKILLS
from apps.practice.importer import BANK_FILE

SKILL_NAMES = {code: short for code, short, _name, _lesson in SKILLS}
LESSON_TITLES = {code: title for code, title, _summary in LESSONS}
LEVELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}


class Command(BaseCommand):
    help = "Write the question bank as a printable review sheet for a math teacher."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(BANK_FILE))
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "content" / "review" / "question_bank_review.html"))

    def handle(self, *args, **options):
        bank = json.loads(Path(options["file"]).read_text(encoding="utf-8"))
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        knowledge_path = Path(settings.BASE_DIR) / "content" / "lesson_knowledge.json"
        knowledge = json.loads(knowledge_path.read_text(encoding="utf-8")) if knowledge_path.exists() else None
        out.write_text(render(bank, knowledge), encoding="utf-8")
        total = sum(len(exercise["questions"]) for exercise in bank["exercises"])
        self.stdout.write(self.style.SUCCESS(f"Review sheet with {total} questions: {out}"))


def render_knowledge(knowledge):
    if not knowledge:
        return ""
    e = html.escape
    cards = "".join(
        f"""
<article class="q">
  <p class="meta"><b>{e(SKILL_NAMES.get(entry["skill_id"], entry["skill_id"]))}</b> · {e(entry["title"])}</p>
  <p>{e(entry["explanation"])}</p>
  <p class="hint"><b>Example:</b> {e(entry["worked_example"])}</p>
  <p class="check">☐ OK as is &nbsp; ☐ Change: ____________________________________________</p>
</article>"""
        for entry in knowledge["entries"]
    )
    return f"""
<section>
  <h2>Feedback after practice</h2>
  <p class="sub">After each practice, the student sees their score, then "Next focus: (skill)" with one of these short texts. Please check them like the questions.</p>
  {cards}
</section>"""


def render(bank, knowledge=None):
    e = html.escape
    questions = [q for exercise in bank["exercises"] for q in exercise["questions"]]
    new = sum(q["is_new"] for q in questions)
    drafted = sum(q["hint_source"] == "drafted" and not q["is_new"] for q in questions)
    reworded = sum(any(note.startswith("Prompt reworded") for note in q["review_notes"]) for q in questions)
    figures = sum(any(note.startswith("Was a figure") for note in q["review_notes"]) for q in questions)

    sections = []
    number = 0
    for exercise in bank["exercises"]:
        levels = Counter(q["difficulty"] for q in exercise["questions"])
        skills = ", ".join(SKILL_NAMES[code] for code in exercise["required_skills"])
        cards = []
        for q in exercise["questions"]:
            number += 1
            choices = "".join(
                f'<li class="{"ok" if c["correct"] else ""}">{e(c["text"])}{" <b>✓ answer</b>" if c["correct"] else ""}</li>'
                for c in q["choices"]
            )
            tags = []
            if q["is_new"]:
                tags.append('<span class="tag new">New question</span>')
            if q["hint_source"] == "drafted" and not q["is_new"]:
                tags.append('<span class="tag">New hint</span>')
            if any(note.startswith("Prompt reworded") for note in q["review_notes"]):
                tags.append('<span class="tag">Reworded</span>')
            notes = "".join(
                f"<li>{e(note)}</li>" for note in q["review_notes"]
                if not note.startswith("New question") and not note.startswith("3.0 had")
            )
            source = f' · 3.0 code {e(q["source_code"])}' if q["source_code"] else ""
            cards.append(f"""
<article class="q">
  <p class="meta"><b>{number}.</b> {e(SKILL_NAMES[q["skill"]])} · {LEVELS[q["difficulty"]]}{source} {"".join(tags)}</p>
  <p class="prompt">{e(q["prompt"])}</p>
  <ol type="A" class="choices">{choices}</ol>
  <p class="hint"><b>Hint:</b> {e(q["hint"])}</p>
  {f'<ul class="notes">{notes}</ul>' if notes else ""}
  <p class="check">☐ OK as is &nbsp; ☐ Change: ____________________________________________</p>
</article>""")
        sections.append(f"""
<section>
  <h2>{e(LESSON_TITLES[exercise["lesson"]])}</h2>
  <p class="sub">{len(exercise["questions"])} questions · {exercise["target_count"]} per practice session · skills: {e(skills)} ·
  {levels["easy"]} Easy, {levels["medium"]} Medium, {levels["hard"]} Hard</p>
  {"".join(cards)}
</section>""")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PathGen 4.2 practice questions: teacher check</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #15181b; margin: 0; background: #f8fafb; line-height: 1.45; }}
main {{ max-width: 46rem; margin: 0 auto; padding: 1rem; }}
h1 {{ font-size: 1.6rem; margin: .5rem 0; }}
h2 {{ font-size: 1.3rem; margin: 2rem 0 .25rem; color: #0b4a56; border-bottom: 3px solid #1d3557; padding-bottom: .25rem; }}
.sub {{ color: #57626d; font-size: .9rem; margin: 0 0 1rem; }}
.intro {{ background: #fff; border: 2px solid #1d3557; border-radius: 12px; padding: .75rem 1rem; }}
.intro li + li {{ margin-top: .35rem; }}
.q {{ background: #fff; border: 1px solid #c7cfd6; border-radius: 10px; padding: .75rem 1rem; margin: 0 0 .75rem; break-inside: avoid; }}
.meta {{ margin: 0; font-size: .85rem; color: #57626d; }}
.prompt {{ margin: .35rem 0; font-weight: 700; font-size: 1.05rem; }}
.choices {{ margin: .25rem 0 .5rem; padding-left: 1.6rem; }}
.choices .ok {{ color: #0f5132; font-weight: 700; }}
.hint {{ margin: .25rem 0; font-size: .92rem; }}
.notes {{ margin: .25rem 0; padding-left: 1.2rem; font-size: .85rem; color: #7a5500; }}
.check {{ margin: .5rem 0 0; font-size: .85rem; color: #57626d; }}
.tag {{ display: inline-block; margin-left: .25rem; padding: 0 .45rem; border-radius: 999px; font-size: .75rem; font-weight: 700; background: #d1f6fa; color: #0b4a56; }}
.tag.new {{ background: #fdf3df; color: #7a5500; }}
@media print {{ body {{ background: #fff; }} main {{ max-width: none; }} .q {{ border-color: #999; }} }}
</style></head><body><main>
<p class="sub">PathGen 4.2 · Grade 7 integers · draft {e(bank["bank_version"])}</p>
<h1>Practice questions: please check before students see them</h1>
<div class="intro">
<p>These are the practice questions for the six PathGen lessons: {len(questions)} in all. Students answer 4 or 5 per lesson, picked by the system from these pools. Most come from PathGen 3.0; {new} are new.</p>
<p><b>Please check, for each question:</b></p>
<ol>
<li>The answer marked ✓ is correct, and only one choice is correct.</li>
<li>The skill fits. Lesson 1 now has four skills (number line, opposites, absolute value, compare and order), and adding and subtracting are separate skills.</li>
<li>The level (Easy, Medium or Hard) fits Grade 7. The system uses it to give an easier or harder next question.</li>
<li>The hint helps a student who got it wrong, without giving the answer away. Students see it only after a wrong first answer, before their one retry. {drafted} of the hints are new; the rest come from 3.0.</li>
<li>The wording is clear. {figures} questions used to have a picture, but 3.0's pictures were blank, so they are text only now; {reworded} of them were reworded to put the numbers in the text.</li>
</ol>
<p>Tick "OK" or write the change. The pretest and posttest are not here: they stay exactly as approved. At the end are the 10 short feedback texts students see after practice.</p>
</div>
{"".join(sections)}
{render_knowledge(knowledge)}
</main></body></html>
"""
