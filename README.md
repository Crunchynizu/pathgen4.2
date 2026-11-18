# PathGen 4.2

A Grade 7 integers practice app: lessons, a pre/post test, teacher-authored adaptive practice driven by BKT and a struggle model trained on Junyi data, and short feedback from local Qwen. Django, SQLite in development, PostgreSQL in production, plain CSS and JavaScript (no npm).

- **Start here: `HANDOFF.md`** (what's done, what differs from the spec, what's left, what to check). AI coding agents: read `HANDOFF.md`, then `AGENTS.md`.
- Plan, dates and decisions: `PLAN.md`
- Spec: `docs/system.md` and `docs/build_order.md` (13 files in `docs/`)
- Online: `DEPLOY.md`

## Run it locally

**SQLite first, then PostgreSQL** (docs/database.md): development runs on a SQLite file until everything works; PostgreSQL is for the concurrency checks and production.

### With Docker (the spec's teammate setup)

```
copy .env.example .env          # then set SECRET_KEY
docker compose up --build
```
Open `http://localhost:8000`. The container migrates SQLite and loads the lessons, skills and locked test; the database and uploads live in named volumes, so they survive a restart. Then, in another terminal: `docker compose exec web python manage.py createsuperuser`.

With local Qwen as well (PowerShell): `$env:LLM_BASE_URL="http://llm:8080"; docker compose --profile llm up --build`. The first build downloads the 491 MB model and checks its SHA-256.

### Without Docker (Windows)

1. Python 3.13. Keep the virtual environment outside OneDrive:
   ```
   "C:\Program Files\Python313\python.exe" -m venv C:\Users\User\pathgen42-venv
   C:\Users\User\pathgen42-venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set `SECRET_KEY`. Leave `DATABASE_URL` out to use SQLite (`db.sqlite3`).
3. Migrate, load the content (below), make your admin, run:
   ```
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py runserver 0.0.0.0:8000
   ```
   (`python` here and below means `C:\Users\User\pathgen42-venv\Scripts\python.exe`.) On a phone on the same Wi-Fi, open `http://<laptop's IP>:8000`; allow Python through the firewall on private networks.

### Switching to PostgreSQL

Set `DATABASE_URL=postgres://...` in `.env` and run `migrate` and the content commands again. On Claude's setup the database is the portable cluster in `C:\Users\User\pathgen-db` (start it in PowerShell):
```
Start-Process -FilePath "C:\Users\User\pathgen-db\pgsql\bin\pg_ctl.exe" -ArgumentList '-D "C:\Users\User\pathgen-db\data" -l "C:\Users\User\pathgen-db\server.log" start' -WindowStyle Hidden
C:\Users\User\pathgen-db\pgsql\bin\psql.exe -h localhost -U pathgen_user -d postgres -c "create database pathgen42 owner pathgen_user"
```
Production refuses to start on anything but PostgreSQL.

## Load the content (every new database)

Safe to run again.

```
python manage.py seed_curriculum      # 6 lessons, 10 skills, scopes, review links
python manage.py seed_assessments     # the locked 30-item test as the pretest and the posttest
```

Then either the demo, or a real class.

**Demo, for checking the app** (labeled as demo, never real students):
```
python manage.py seed_demo --password <pick one>
```
It makes `demo_admin`, `demo_teacher`, `demo_s1` to `demo_s3`, and gives the demo class all six bank exercises.

**A real study class:**
```
python manage.py createsuperuser                        # your own admin account
# create the teacher in the admin console (/admin-console/accounts/), then:
python manage.py create_study_class --teacher <username> --class "Grade 7 - A" --prefix g7a --names names.txt --site-url https://<the app's address>
python manage.py import_bank --teacher <username> --class "Grade 7 - A"
```
`names.txt` has one student name per line. The login slips (HTML to print, plus a CSV) go to `private/`, which Git ignores; delete them after the study.

## Exercises

Two ways in, same tables and rules:

- **The teacher's editor** (`/teacher/exercises/new/`): lesson, title, questions per session, required skills, an ordered pool of text, picture (PNG/JPEG with a description) or YouTube questions (start time read from the link), hints and Easy/Medium/Hard. Save a draft any time; **Save and publish** checks the pool (size, coverage, four choices, one answer, hints, media) and opens the publish dialog to pick classes. Editing a published exercise makes a new draft; students who started keep the version they began. Unpublish stops new starts and retakes. A never-published draft can be deleted. Pictures are served only to people allowed to see the question.
- **The question bank** (`content/question_bank.json`): 118 questions (105 from PathGen 3.0, 13 new), loaded by `import_bank` as one exercise per lesson. A re-import never overwrites an exercise the teacher has edited and published.
- `python manage.py export_bank_review` writes `content/review/question_bank_review.html`, a printable sheet for the math teacher's check. After corrections: edit the JSON, set `"review_status": "approved"`, run `import_bank` again.
- Difficulty numbers: bank questions use the real Junyi struggle rate of their template (`model_artifacts/template_difficulty.json`); questions written in the editor use the spec's provisional Easy 0.15 / Medium 0.30 / Hard 0.50, reported as uncalibrated (docs/agent.md).

## Qwen feedback (optional)

After each practice the student sees the score and the approved note for their next focus straight away. If `LLM_BASE_URL` points at a llama.cpp server, the results page then asks once for Qwen2.5-0.5B to reword that note; anything slow, broken or ungrounded (a number not in the approved note, a link, markup) keeps the approved text.

```
python scripts/fetch_llm.py --cache C:\Users\User\pathgen-models     # 491 MB, checked by SHA-256
llama-server -m C:\Users\User\pathgen-models\qwen2.5-0.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8080 -c 2048 -np 2
# in .env:  LLM_BASE_URL=http://127.0.0.1:8080
python manage.py check_llm --example                 # real replies for the example knowledge, with timings
python manage.py check_llm --parallel 4              # the approved file, 4 finishes at once
```
`llama-server` is llama.cpp's server, build b12464 (the same build as `deploy/llm/Dockerfile`), from its GitHub releases. Keep the model outside OneDrive.

## Pages

| Who | Where |
|---|---|
| Everyone | `/login/`, `/profile/` |
| Admin | `/admin-console/overview/` (accounts, classes, lessons, assessments) |
| Teacher | `/teacher/overview/`; a class at `/teacher/classes/<id>/` (scores, skill gaps and pre/post charts with tables, open the posttest); `/teacher/exercises/` (drafts, published, **New exercise**), the editor at `/teacher/exercises/<id>/edit/` |
| Student | `/learn/` (the journey), `/learn/assessments/pretest/`, lessons at `/learn/lessons/<code>/`, practice at `/learn/exercises/<id>/` |
| Team | Django's own admin at `/django-admin/`, read-only, for checking data |

## Check it

```
python manage.py check
python manage.py test                                                  # on the database in .env
$env:DATABASE_URL="sqlite:///test.sqlite3"; python manage.py test      # the same suite on SQLite (PowerShell)
```
Both databases must pass (docs/build_order.md, Phase 7). `/health/` answers `{"status": "ok", "database": "ok"}` when the app can reach the database.

## After the study days

```
python manage.py export_study_data
```
writes `private/exports/<date>/`: students, every test answer and every practice answer as CSV (students appear as S001, S002 ...), `agent_retrain.csv` (the 12 model inputs saved when each question was chosen, with `struggle_on_next_question`, docs/agent.md), the file pathgen4.0-trainer's `update` step reads, and `report.md` with the paired pre/post t-test, Cohen's dz, normalized gain, scores by skill, and how the struggle model did on PathGen students (Brier, AUC). `pseudonym_key.csv` links keys to accounts: keep it private.

## Not here (see PLAN.md, "Where 4.2 differs from the spec")

The admin's assessment editor (the test is the locked, approved instrument), Google Fonts (the approved look uses system fonts), the optional dialogs, and the contextual bandit (a later pilot; v1 logs the decisions it needs).
