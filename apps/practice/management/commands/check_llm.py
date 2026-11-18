"""Ask the real local Qwen for feedback and check the answers (docs/build_order.md Phase 6, step 3).

    manage.py check_llm --url http://127.0.0.1:8080                 the approved knowledge file
    manage.py check_llm --url http://127.0.0.1:8080 --example       the labeled example file
    manage.py check_llm --url ... --parallel 4                      several finishes at once

Prints each reply, whether it passed the output checks, and how long it took. Uses no student data.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.curriculum.models import Skill
from apps.practice.feedback import KNOWLEDGE_FILE
from learning.feedback import llm, service
from learning.feedback.retrieval import KnowledgeError, load

EXAMPLE_FILE = Path(settings.BASE_DIR) / "content" / "lesson_knowledge.example.json"


class Command(BaseCommand):
    help = "Check that the local Qwen server answers with feedback that passes PathGen's checks."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=settings.LLM_BASE_URL or "http://127.0.0.1:8080")
        parser.add_argument("--example", action="store_true", help="use lesson_knowledge.example.json")
        parser.add_argument("--skill", default=None, help="one skill code (default: every entry)")
        parser.add_argument("--parallel", type=int, default=1, help="requests sent at the same time")

    def handle(self, *args, **options):
        url = options["url"]
        if not llm.healthy(url):
            raise CommandError(f"No healthy llama.cpp server at {url} (GET /health).")
        lesson_of_skill = dict(Skill.objects.values_list("code", "lesson__code"))
        path = EXAMPLE_FILE if options["example"] else KNOWLEDGE_FILE
        try:
            entries, version = load(path, lesson_of_skill)
        except (FileNotFoundError, KnowledgeError) as error:
            raise CommandError(f"{path.name}: {error}") from error
        names = dict(Skill.objects.values_list("code", "short_name"))
        chosen = [entries[options["skill"]]] if options["skill"] else list(entries.values())
        self.stdout.write(f"{path.name} ({version}), {len(chosen)} entr{'y' if len(chosen) == 1 else 'ies'}, "
                          f"{options['parallel']} at a time, timeout {settings.LLM_TIMEOUT_SECONDS:g} s\n")

        def ask(entry):
            facts = service.Facts(focus=names.get(entry.skill_id, entry.skill_id), strength="Addition",
                                  needed_retries=True)
            started = time.perf_counter()
            try:
                raw = llm.complete(url, service.messages(facts, entry), model=settings.LLM_MODEL,
                                   timeout=settings.LLM_TIMEOUT_SECONDS, max_tokens=settings.LLM_MAX_TOKENS)
            except llm.LlmError as error:
                return entry, None, f"FAILED: {error}", time.perf_counter() - started
            seconds = time.perf_counter() - started
            try:
                return entry, service.clean(raw, entry), "passed", seconds
            except service.InvalidOutput as error:
                return entry, raw, f"refused ({error}): the saved text would be shown", seconds

        jobs = [entry for entry in chosen for _ in range(options["parallel"])]
        with ThreadPoolExecutor(max_workers=options["parallel"]) as pool:
            results = list(pool.map(ask, jobs))
        passed = 0
        for entry, text, verdict, seconds in results:
            passed += verdict == "passed"
            self.stdout.write(f"- {entry.skill_id} · {seconds:.1f} s · {verdict}\n  {text or ''}\n")
        times = sorted(r[3] for r in results)
        self.stdout.write(self.style.SUCCESS(
            f"{passed} of {len(results)} passed. Time: median {times[len(times) // 2]:.1f} s, slowest {times[-1]:.1f} s."
        ))
