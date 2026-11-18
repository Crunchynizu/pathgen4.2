"""Create a whole study class at once and write a printable login sheet (PLAN.md, Phase 2).

    manage.py create_study_class --teacher <username> --class "Grade 7 - Section A" \
        --prefix g7a --names names.txt [--site-url https://...] [--out private/login_sheets]

`--names` is a UTF-8 text file with one student name per line (blank lines and lines starting
with # are skipped). Without it, use `--count 40` to make "Student 01" ... accounts.

Usernames are the prefix plus a number (g7a01, g7a02, ...), so they don't carry names. The sheet
and the CSV contain passwords: they are written under private/, which Git ignores.
Re-running skips usernames that already exist and never changes their passwords.
"""
import csv
import html
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.classrooms import services
from apps.classrooms.models import Classroom

User = get_user_model()

# Short, friendly words for starting passwords: word + 4 digits, e.g. "mango-4821".
WORDS = [
    "mango", "tiger", "river", "cloud", "pearl", "eagle", "lemon", "maple", "ocean", "piano",
    "comet", "coral", "daisy", "ember", "flute", "grape", "honey", "ivory", "jelly", "koala",
    "lotus", "melon", "noble", "olive", "panda", "quill", "robin", "sunny", "tulip", "violet",
    "whale", "zebra", "amber", "bison", "cedar", "delta", "fable", "gecko", "hazel", "igloo",
]


def make_password(user):
    for _ in range(50):
        password = f"{secrets.choice(WORDS)}-{secrets.randbelow(9000) + 1000}"
        try:
            validate_password(password, user)
        except ValidationError:
            continue
        return password
    raise CommandError("Could not make a password that passes the validators.")


class Command(BaseCommand):
    help = "Create a study class with many student accounts and write a printable login sheet."

    def add_arguments(self, parser):
        parser.add_argument("--teacher", required=True, help="Username of the class's teacher account.")
        parser.add_argument("--class", dest="class_name", required=True, help="Class name, made if missing.")
        parser.add_argument("--prefix", required=True, help="Username prefix, e.g. g7a -> g7a01, g7a02 ...")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--names", help="Text file with one student name per line.")
        group.add_argument("--count", type=int, help="Number of accounts without names.")
        parser.add_argument("--start", type=int, default=1, help="First number (default 1).")
        parser.add_argument("--site-url", default="", help="Printed on each slip, e.g. the Railway URL.")
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "private" / "login_sheets"))

    def handle(self, *args, **options):
        try:
            teacher = User.objects.get(username=options["teacher"], role=User.Role.TEACHER)
        except User.DoesNotExist as error:
            raise CommandError(f"No teacher account named {options['teacher']!r}.") from error

        prefix = options["prefix"].strip().lower()
        if not prefix or not prefix.replace("-", "").replace("_", "").isalnum():
            raise CommandError("Use letters and numbers for --prefix, e.g. g7a.")

        if options["names"]:
            path = Path(options["names"])
            if not path.exists():
                raise CommandError(f"No file at {path}.")
            names = [
                line.strip()
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        else:
            if options["count"] < 1:
                raise CommandError("--count must be at least 1.")
            names = [f"Student {number:02d}" for number in range(options["start"], options["start"] + options["count"])]
        if not names:
            raise CommandError("The names file has no names.")

        width = max(2, len(str(options["start"] + len(names) - 1)))
        created, skipped = [], []
        with transaction.atomic():
            classroom = Classroom.objects.filter(teacher=teacher, name__iexact=options["class_name"].strip()).first()
            if classroom is None:
                classroom = services.create_classroom(name=options["class_name"], teacher=teacher)
                self.stdout.write(f"Made class {classroom.name} for {teacher.username}.")
            for offset, name in enumerate(names):
                username = f"{prefix}{options['start'] + offset:0{width}d}"
                if User.objects.filter(username__iexact=username).exists():
                    skipped.append(username)
                    continue
                draft = User(username=username, display_name=name, role=User.Role.STUDENT)
                password = make_password(draft)
                services.create_student(username=username, password=password, display_name=name, classroom=classroom)
                created.append({"name": name, "username": username, "password": password})

        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {len(skipped)} existing usernames: {', '.join(skipped)}"))
        if not created:
            self.stdout.write("No new accounts, so no sheet was written.")
            return

        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        base = out_dir / f"{slugify(classroom.name) or 'class'}-{stamp}"
        with open(f"{base}.csv", "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["name", "username", "password"])
            writer.writeheader()
            writer.writerows(created)
        Path(f"{base}.html").write_text(login_sheet(classroom, created, options["site_url"]), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Made {len(created)} student accounts in {classroom.name}."))
        self.stdout.write(f"Login sheet: {base}.html (print it, cut along the lines)")
        self.stdout.write(f"Same list as CSV: {base}.csv")
        self.stdout.write("Both files hold passwords. Keep them private and delete them after the study.")


def login_sheet(classroom, rows, site_url):
    escape = html.escape
    site = escape(site_url) if site_url else "the PathGen link your teacher gives you"
    slips = "\n".join(
        f"""<div class="slip"><p class="brand">PathGen · {escape(classroom.name)}</p>
<p class="who">{escape(row['name'])}</p>
<p><span>Username</span><b>{escape(row['username'])}</b></p>
<p><span>Password</span><b>{escape(row['password'])}</b></p>
<p class="site">Open {site}, sign in, then start with the pretest.</p></div>"""
        for row in rows
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Login slips · {escape(classroom.name)}</title>
<style>
body {{ font-family: system-ui, Arial, sans-serif; margin: 12mm; color: #15181b; }}
h1 {{ font-size: 16px; margin: 0 0 8px; }}
.note {{ font-size: 12px; margin: 0 0 12px; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0; }}
.slip {{ border: 1px dashed #74808d; padding: 10px 12px; break-inside: avoid; }}
.slip p {{ margin: 2px 0; font-size: 13px; }}
.slip span {{ display: inline-block; width: 74px; color: #57626d; }}
.slip b {{ font-family: ui-monospace, Consolas, monospace; font-size: 15px; letter-spacing: .03em; }}
.brand {{ font-weight: 700; color: #087b90; }}
.who {{ font-weight: 700; font-size: 15px !important; }}
.site {{ color: #57626d; font-size: 11px !important; }}
@media print {{ .note {{ display: none; }} body {{ margin: 8mm; }} }}
</style></head><body>
<h1>Login slips · {escape(classroom.name)} · {len(rows)} students</h1>
<p class="note">Print, cut along the dashed lines, and hand each student their own slip. This page holds passwords: delete it after the study.</p>
<div class="grid">
{slips}
</div></body></html>
"""
