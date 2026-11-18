"""Load the locked 30-item test into a published pretest and posttest (PLAN.md, "Settled").

Repeatable: an existing form with the same items is left alone. A form that students already
started is never changed; a different file then stops with an error instead.
"""
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.curriculum.models import Skill

from .models import AssessmentForm, AssessmentItem, Kind

LOCKED_TEST = Path(settings.BASE_DIR) / "content" / "locked_test.json"


class SeedError(Exception):
    pass


def load_locked_test(path=LOCKED_TEST):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["items"]
    if len(items) != 30:
        raise SeedError(f"The locked test should have 30 items, found {len(items)}.")
    for item in items:
        if len(item["choices"]) != 4 or not 0 <= item["correct_index"] <= 3:
            raise SeedError(f"Item {item['position']} needs 4 choices and one correct answer.")
    return data


def _same_items(form, items):
    stored = [
        (i.position, i.skill.code, i.prompt, i.choices, i.correct_index)
        for i in form.items.select_related("skill").order_by("position")
    ]
    wanted = [(i["position"], i["skill"], i["prompt"], i["choices"], i["correct_index"]) for i in items]
    return stored == wanted


@transaction.atomic
def seed_locked_test(path=LOCKED_TEST):
    data = load_locked_test(path)
    skills = {skill.code: skill for skill in Skill.objects.all()}
    missing = {item["skill"] for item in data["items"]} - set(skills)
    if missing:
        raise SeedError(f"Run seed_curriculum first. Missing skills: {', '.join(sorted(missing))}")

    results = {}
    for kind, label in ((Kind.PRETEST, "Pretest"), (Kind.POSTTEST, "Posttest")):
        form, created = AssessmentForm.objects.get_or_create(
            kind=kind,
            revision=1,
            defaults={
                "title": f"{label}: {data['title']}",
                "state": AssessmentForm.State.PUBLISHED,
                "published_at": timezone.now(),
                "locked": True,
                "source": f"{data['source_file']} sha256 {data['source_file_sha256'][:12]}",
            },
        )
        if not created and _same_items(form, data["items"]):
            results[kind] = "unchanged"
            continue
        if not created and form.attempts.exists():
            raise SeedError(f"The {kind} already has attempts, so its items can't change.")
        form.items.all().delete()
        AssessmentItem.objects.bulk_create(
            AssessmentItem(
                form=form,
                position=item["position"],
                skill=skills[item["skill"]],
                prompt=item["prompt"],
                choice_a=item["choices"][0],
                choice_b=item["choices"][1],
                choice_c=item["choices"][2],
                choice_d=item["choices"][3],
                correct_index=item["correct_index"],
                source_code=item.get("source_code", ""),
            )
            for item in data["items"]
        )
        results[kind] = "created" if created else "replaced"
    return results
