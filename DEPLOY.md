# Putting PathGen 4.2 online (Railway)

About 30 minutes. You need a GitHub account and a Railway account. Nothing here needs the Railway or GitHub command-line tools.

What runs on Railway (docs/tech_stack.md, "Railway production"):

| Service | Built from | Notes |
|---|---|---|
| The app | `Dockerfile` (via `railway.toml`) | Django + Gunicorn; static files are inside the image |
| PostgreSQL | Railway's database | Production is always PostgreSQL |
| A volume on the app | Railway volume at `/data` | Teachers' uploaded pictures (`MEDIA_ROOT=/data/media`) |
| Qwen (optional) | `deploy/llm/Dockerfile` | Private llama.cpp service for the feedback wording; the app works without it |

## 1. Put the code on GitHub (private repo)

1. On github.com, make a new **private** repository, for example `pathgen4.2`. Don't add a README.
2. In PowerShell, in the `pathgen4.2` folder:
   ```
   git init
   git add .
   git commit -m "PathGen 4.2"
   git branch -M main
   git remote add origin https://github.com/<your-account>/pathgen4.2.git
   git push -u origin main
   ```
   `.gitignore` already keeps out `.env`, `db.sqlite3`, `media/`, `private/` (login slips, exports), `staticfiles/`, model files and caches. Check `git status` shows no `.env` before pushing.

## 2. Make the Railway project

1. railway.com → **New Project** → **Deploy from GitHub repo** → pick the repo. Railway reads `railway.toml` and builds the `Dockerfile`.
2. In the same project: **New** → **Database** → **PostgreSQL**.
3. Open the app service → **Variables**, and add:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (pick it from the list: the private connection) |
   | `SECRET_KEY` | a long random text (run `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
   | `ALLOWED_HOSTS` | the domain from step 5, e.g. `pathgen42.up.railway.app` |
   | `CSRF_TRUSTED_ORIGINS` | the same with https, e.g. `https://pathgen42.up.railway.app` |

   `DJANGO_SETTINGS_MODULE=config.settings.production` and `MEDIA_ROOT=/data/media` are already set in the image.
4. App service → right-click → **Attach volume**, mount path `/data`.
5. App service → **Settings** → **Networking** → **Generate Domain**. Put that domain into the two variables above.
6. Deploy. Each deploy runs the migrations and both seeds (6 lessons, 10 skills, the locked test) before starting, and checks `/health/`.
7. Open `https://<domain>/health/`. It should say `{"status": "ok", "database": "ok"}`.

## 3. Accounts and practice, from your laptop

Run these on your laptop against Railway's database. In Railway, open the **Postgres** service → **Variables** → copy `DATABASE_PUBLIC_URL`. Then in PowerShell, in the `pathgen4.2` folder:

```
$env:DATABASE_URL = "<paste DATABASE_PUBLIC_URL here>"
$py = "C:\Users\User\pathgen42-venv\Scripts\python.exe"
& $py manage.py createsuperuser
```

Sign in at `https://<domain>/login/` as that admin and create the teacher account on **Accounts**. Then:

```
& $py manage.py create_study_class --teacher <teacher username> --class "Grade 7 - A" --prefix g7a --names names.txt --site-url https://<domain>
& $py manage.py import_bank --teacher <teacher username> --class "Grade 7 - A"
```

The login slips are written to `private/login_sheets/` on your laptop. Close PowerShell afterwards so the database address doesn't stay in that window.

Teachers can also make their own exercises in the app (**Exercises → New exercise**). Pictures they upload go to the volume, so test once that a picture still shows after a redeploy.

For the groupmate or adviser walk-through, use a separate demo class: `& $py manage.py seed_demo --password <pick one>`. Real study classes should not share the database with demo accounts on the study days; if you can, delete the demo class's students before day 1 or use a second Railway project for demos.

## 4. Optional: the Qwen feedback service

Without it, students see the approved feedback text from `content/lesson_knowledge.json`. With it, local Qwen rewords that text after each practice (docs/rag.md). It needs about 1 GB of memory; check the Railway plan first.

1. In the same project: **New** → **GitHub repo** → the same repo again. In this new service's **Settings**: root directory `deploy/llm`, config file `/deploy/llm/railway.toml`. Don't generate a domain: it stays private.
2. Its **Variables**: `LLAMA_ARG_HOST` = `::` (Railway's private network).
3. Deploy. The build downloads the model from the official Qwen repository and checks its SHA-256; a wrong file stops the build.
4. In the **app** service, add `LLM_BASE_URL` = `http://${{<qwen service name>.RAILWAY_PRIVATE_DOMAIN}}:8080`, and redeploy the app.
5. Check it by finishing one practice as a demo student: a few seconds after the results appear, the note under "Next focus" changes to Qwen's wording. (The private address can't be reached from your laptop, so `check_llm` is for local runs; see README.) If the note doesn't change, the approved text stays and nothing else is affected.

To turn it off, delete `LLM_BASE_URL` from the app's variables.

## 5. Before each school day

- Open `/health/` on mobile data and on the school Wi-Fi.
- Sign in as one study account on a phone and check the journey page.
- After day 3: `& $py manage.py export_study_data` (with `DATABASE_URL` set as above) writes the CSV files and `report.md` for chapter 4 into `private/exports/`.

## Backups and rollback

- **Database:** Railway → Postgres → **Backups** (on plans that have them). Before each school day, or at least before day 1 and after day 3, also run `export_study_data` from the laptop: it is a full copy of what chapter 4 needs.
- **Pictures:** they live on the `/data` volume. Railway keeps the volume across deploys; don't delete the app service.
- **Rollback:** Railway → app service → **Deployments** → pick the last good one → **Redeploy**. Migrations only add things, so an older deploy still reads the database.
- Never run `flush` or other reset commands against the production database.

## If a deploy fails

- "must be set in production" or "must point at PostgreSQL": a variable from step 2.3 is missing or wrong.
- "DisallowedHost" or CSRF errors: `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` don't match the domain exactly.
- Health check fails: open the deploy logs; the pre-deploy step prints the migration and seed output.
- The Docker build fails: the build log shows the step. As a stopgap, in the app service's settings set the builder to Railpack and the start command to `python manage.py collectstatic --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --worker-class gthread --workers 3 --threads 4 --timeout 90`, and add the variable `DJANGO_SETTINGS_MODULE` = `config.settings.production`. The pre-deploy steps stay the same.
