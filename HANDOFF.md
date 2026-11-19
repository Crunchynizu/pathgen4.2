# PathGen 4.2: where things stand

**Read this first**, whether you are a person or an AI coding agent working on this repo. It covers what is built, where 4.2 differs from the spec and why, what is still open, and what each person should check. Then see `README.md` (how to run it), `DEPLOY.md` (how to put it online), `docs/` (the 13-file spec) and `AGENTS.md` (working rules).

If you change something, update this file in the same commit.

## In one paragraph

PathGen 4.2 is a fresh Django build of the spec in `docs/` (pathgendocs2). It reuses PathGen 3.0's approved content (questions, lesson material, interactives, the gamified look and the locked pre/post test), but none of 3.0's code. Students take the pretest, open six lessons, and do adaptive practice. Each first answer updates BKT, and a struggle model plus fixed rules pick the next question. After practice, students get short feedback; after the posttest they see both scores. Teachers write and publish exercises, open the posttest, and see class results. Every phase of `docs/build_order.md` is built except going online. The test suite (123 tests) passes on both SQLite and PostgreSQL.

## What is done, by phase (`docs/build_order.md`)

### Phase 1: project, Docker, repository
- Six Django apps, a custom User with a required role (admin, teacher or student), split settings, a `/health/` route, and the shared stylesheet with the six breakpoints.
- **SQLite first in development, PostgreSQL in production.** Without `DATABASE_URL` the app uses `db.sqlite3`. Production refuses to start on anything but PostgreSQL.
- `Dockerfile`, `compose.yaml` (SQLite and uploads in named volumes, an optional `llm` profile for Qwen), `railway.toml`, `.dockerignore`, `AGENTS.md`.
- Browser libraries are checked in: Chart.js 4.6.1 and AnimateIcons Lucide 0.2.0, under `static/vendor/`. No npm.

### Phase 2: accounts, classes, curriculum
- Sign-in and sign-out, landing pages by role, and a profile page (own name and password).
- **Admin console:** create teacher, create class, create student (dialogs 1–3).
- **Teacher pages:** My Classes, then a class, then a student. A teacher can't open another teacher's class.
- **Curriculum seed:** 6 lessons, 10 skills, the review scope for Expressions and Applications, and 14 prerequisite links (used for review suggestions only; they never lock anything).
- `create_study_class` makes a whole class from a list of names and prints login slips.

### Phase 3: pre/post test and the journey
- The locked 30-item test, used as both the pretest and the posttest.
- The start and submit dialogs (8, 9), answers saved as the student goes, grading on the server, and a submit that is safe to repeat.
- Lessons open only after the pretest is submitted. The posttest appears only after the teacher opens it (dialog 7). Afterwards the student sees both scores and the change in percentage points.

### Phase 4: exercises
- **Teacher exercise editor** (`/teacher/exercises/new/`):
  - lesson, title, questions per session, required skills, and an ordered question pool;
  - questions can be text, a picture (PNG or JPEG with a description) or a YouTube video, with the start time taken from the link;
  - hints and Easy/Medium/Hard.
- **Drafts:** save, publish (dialog 4), delete a never-published draft (dialog 5), unpublish (dialog 6), and the discard-unsaved-changes guard (dialog 11).
  - Published versions are frozen. Editing makes a new draft, and students who already started keep their version.
  - Uploaded pictures are served only to people allowed to see the question.
- **Question bank:** `content/question_bank.json` has 118 questions (105 from 3.0, 13 new). `import_bank` loads it as one exercise per lesson. A re-import never overwrites an exercise a teacher has edited.

### Phase 5: BKT, struggle model, adaptive practice, decision log
- **BKT:** one update per first answer, using fitted starting values for each of the 10 skills.
- **Struggle model:** fitted on Junyi at the 10-skill level. On validation students its AUC is 0.752, against 0.719 for BKT alone.
- **The selection rules** (`docs/special_algo.md`):
  - keep the required skills covered;
  - the first-ever question comes in teacher order;
  - pick the lowest-mastery skill;
  - a retake prefers questions not seen before;
  - after two struggles give an easier question, after two easy successes a harder one;
  - aim for a predicted struggle chance of 0.30.
- If the model can't run, practice falls back to the teacher's order, and the fallback is logged.
- **Practice screen:** start and resume; after a wrong first answer, a hint and one retry, or move on; results; one retake (dialog 10).
- **Logs:** every served question saves its decision (all 12 spec inputs, the candidates, the prediction, the rule used). Every first answer saves its BKT update.

### Phase 6: lessons and feedback
- **Six lesson pages:** a 2–3 minute recap first, then a section per skill with 3.0's interactives (number line, chips, sign table, thermometer, spot the mistake).
- **Feedback text:** `content/lesson_knowledge.json` has 10 draft feedback texts. The results screen shows the first-try score, how many were fixed on the retry, a strength (if earned), the next focus, and a link to that part of the lesson.
- **Qwen2.5-0.5B on llama.cpp (optional):**
  - It rewords the approved text after practice.
  - The job is claimed once, and the model runs outside any database write.
  - If it is slow, broken, or adds a number that isn't in the approved text, the approved text stays.
  - It is off unless `LLM_BASE_URL` is set.

### Phase 7: reports and checks
- **Teacher's class page:**
  - scores;
  - practice finished;
  - first-try scores;
  - skill gaps;
  - pretest vs posttest by skill.
  - Each chart has a table under it.
- **Export:** `export_study_data` writes the chapter 4 files with pseudonyms (S001, S002, …):
  - every answer;
  - the paired t-test, Cohen's dz, normalized gain and scores by skill;
  - how well the model predicted (Brier score, AUC);
  - `agent_retrain.csv` for a later retrain.
- The production settings pass Django's deployment check.

### Look and feel (a second pass, after the team's review)
Feedback: the first look felt minimal and "AI generated". The second pass took inspiration from Khan Academy and Dribbble learning apps for students, and from professional dashboards for staff. It changed CSS and templates only; no rule, label or graded content changed.
- **Students** keep the gamified feel: chunky pressable buttons, the journey trail, and the bouncing "next" step. There are still no points, badges or streaks.
  - Each lesson has its own color (`.tone-1` … `.tone-6` in `static/css/app.css`, cyan to coral) and its math sign as a mark (±, +, −, ×, ÷, ( )). The marks are set in `LESSON_GLYPHS`, `apps/dashboards/templatetags/icons.py`.
  - **Journey:** a navy hero with the greeting, two progress bars (practice done, skills doing well) and an "Up next" card for the first lesson with practice left. Each lesson card has a progress bar and a skill square per skill: green for doing well, amber for needs practice, hollow for not yet. There is a legend, and the words stay on the skill list.
  - **Lesson pages:** a hero in the lesson's color, and an "In this lesson" menu from 1024px.
  - **Practice:** lettered answer tiles and a progress bar in the lesson's color.
  - **Login:** a split screen with a navy art panel.
  - **More color** (`body.learner` in `app.css`): soft colored page background, a six-color strip on the top bar, lesson cards and worked examples tinted in their lesson's color, sunny "Try it" and hint boxes, one color per answer letter in practice, and a colored profile banner.
- **Teachers and admins** (`body.staff`): a navy sidebar with the user's initials, thin borders, flat buttons and quieter tables. The teacher overview shows four figures per class.
- **Not frozen:** the team is still checking and adjusting the look. Colors and shadows are tokens at the top of `static/css/app.css`. The student color layer is the `body.learner` section, and the staff look is the `body.staff` section. Change the look freely, but keep the pretest and posttest identical to each other, and run the tests after.
- **Pretest and posttest:** both still share one template, so they look identical. They have no gamified extras, only the new shared colors and answer tiles.
- **Still the approved basics:** system fonts and the cyan/navy palette. Text meets 4.5:1 contrast. The exceptions are the big lesson signs and icons on the lighter lesson colors, which only need 3:1 because they are large.

### Phase 8: online (not done yet)
- The code is on GitHub. Railway is next: follow `DEPLOY.md` (app, PostgreSQL, a volume for pictures, and optionally the Qwen service).

## Where 4.2 differs from the spec, and why

These are choices made during the build, not locks. After checking them, the team can move any of them closer to the spec, or somewhere else entirely. "If the team wants to switch" below says where each one lives in the code. Talk it over first, make the change on a branch, run the tests on both databases, and update this table so it stays true.

| Spec | 4.2 | Why |
|---|---|---|
| `agent_model.pkl` and `bkt_parameters.json`, 12 inputs | `struggle_model.json` and `bkt_params.json`, 8 inputs, refitted at the 10-skill level, plain Python, checked against `manifest.json` | The spec's BKT file has no limits on its guess and slip values. That clashes with the progress labels: a student with 0 of 6 right can still read as strong. 4.2 refits both files with limits (guess ≤ 0.3, slip ≤ 0.1, learn ≤ 0.3), so 0 of 6 right gives mastery of 0.03–0.34. The 4 attempt and time inputs shift between Junyi (unlimited attempts, hints any time) and PathGen (2 attempts, hint only after a wrong answer), so a model trained on them would misread PathGen students. Plain JSON also avoids loading a pickle, which runs code when it loads. All 12 inputs are still saved for every served question and exported in `agent_retrain.csv`, so a 12-input model can be trained on PathGen's own data later. |
| Admin writes the pretest and posttest | The locked 30-item test, read-only | Editing the test during the study would clash with the pre/post comparison, which needs the same approved instrument on both days. |
| Python 3.14.7 | Python 3.13 | Every test ran on 3.13; Django 5.2 supports both. |
| Google Fonts | System fonts | The approved 3.0 look uses system fonts, so adding a Google Font changes an approved design. It waits for approval. |
| Difficulty values Easy 0.15 / Medium 0.30 / Hard 0.50 | Bank questions: their Junyi template's real struggle rate. Editor questions: 0.15 / 0.30 / 0.50 | The model was trained on template struggle rates, so bank questions use the same scale. Teacher-written questions have no template, so they use the spec's provisional numbers. |
| Feedback from local Qwen | Built, off unless `LLM_BASE_URL` is set | Qwen needs about 1 GB of memory on Railway. The approved text is the feedback whenever Qwen is off or fails. |

### If the team wants to switch

- **To use the spec's pickle model (12 inputs):**
  1. Put `agent_model.pkl` and `bkt_parameters.json` in `model_artifacts/`, and add their SHA-256 values to `manifest.json`.
  2. Add the runtime pins from `docs/tech_stack.md` (scikit-learn, pandas, NumPy, SciPy, joblib) to `requirements.txt`.
  3. In `learning/agent.py`, load the pickle only after its checksum matches. Then call `predict_proba` on a pandas table built from `learning/features.snapshot()`, which already produces the 12 inputs in the spec's order.
  4. In `learning/bkt.py`, read `bkt_parameters.json` (`initial_mastery`, `learn`, `guess`, `slip`).
  5. Run `tests/test_phase5.py`. `test_zero_right_never_looks_strong` shows whether 0 of 6 right still reads as strong.

  A middle way: keep plain JSON but refit with all 12 inputs in `pathgen4.0-trainer`, using `agent_retrain.csv` from the study.
- **To let the admin edit the pretest and posttest:** only after the study. Either build an editor in the admin console's Assessments section, or edit `content/locked_test.json` and run `seed_assessments` on a database with no test attempts yet.
- **To use Python 3.14:**
  1. Change `FROM python:3.13-slim` in `Dockerfile` and the version in `.python-version`.
  2. Make a new virtual environment.
  3. Run the tests on SQLite and on PostgreSQL.
- **To add a Google Font:** once it is approved, add the font's `<link>` in `templates/layouts/base.html`, and put its name first in `--font-sans` at the top of `static/css/app.css`.
- **To use the spec's difficulty numbers everywhere:**
  - Editor questions already use `PROVISIONAL_DIFFICULTY` in `apps/practice/authoring.py`.
  - For bank questions, change `difficulty_value=templates[...]` in `apps/practice/importer.py` to `PROVISIONAL_DIFFICULTY[item["difficulty"]]`, then run `import_bank` again.
  - The model was trained on template rates, so compare the predictions before and after.
- **To turn Qwen on or change it:**
  - Set `LLM_BASE_URL` (no code change).
  - The wording request and the checks on Qwen's answer are in `learning/feedback/service.py`.
  - The timeout is `LLM_TIMEOUT_SECONDS`.

## Changes from PathGen 3.0 worth knowing
- **Lesson examples:** 3.0's lesson examples repeated two posttest items word for word (item 16's expression and item 18's temperature story). The 4.2 lessons use other numbers, and a test checks that no test item appears on a lesson page.
- **Pictures:** all of 3.0's practice pictures were blank 1×1 placeholders. Those 18 questions are text-only now (4 were reworded to put the numbers in the text).
- **New questions:** 13 were added so every skill has Easy, Medium and Hard questions.
- **Lesson 1:** it now has four separate skills (number line, opposites, absolute value, compare and order). Adding and subtracting are separate skills.

## Known limits (say these before someone else finds them)
- **"Doing well" can come early:** the fitted starting mastery is high for multiplication (0.90), absolute value (0.94), addition (0.86) and division (0.85). A student with 2 of 4 right on multiplication can read "Doing well" (0.76 against the spec's 0.75 line). It is a display label only.
- **The model can tie:** in 7 of the 10 skills every question shares one Junyi template, so the model gives them the same score. Inside those skills, the easier/harder rule does the adapting.
- **No opposites item in the test:** the spec's "covers all ten skills" check is relaxed and reported.
- **Guessed template matches:** for order of operations, the matches to Junyi templates T010–T012 follow difficulty order, because Junyi doesn't describe those three problem types.
- **Not yet checked by running:** the Docker images (no Docker on the build PC; the first Railway deploy is the test) and a real Qwen reply (the `check_llm` command is ready; see README).

## What's left to do
1. **Go online** with `DEPLOY.md`. Make one admin, the teacher and a demo class, and check `/health/` on mobile data and on Wi-Fi.
2. **Real Qwen check** on a laptop: start llama.cpp's server, then run `manage.py check_llm --example` and `--parallel 4`. Decide whether Qwen is on for the study: only if the 3-phone check passes with it on.
3. **Math teacher's check:** the 118 questions and the 10 feedback texts (the review sheet), and the six lesson pages in the app. Corrections go into the JSON files, then `import_bank` is run again.
4. **The 3-phone go/no-go** on the live site:
   - sign in, take the pretest, open all six lessons;
   - run each exercise to its count, with hints and retries;
   - see the results; take the posttest after the teacher opens it; see both scores.
   - No error pages, on mobile data as well as Wi-Fi.
5. **Before day 1:** a fresh study database (no demo accounts), the real class from `create_study_class`, the bank imported, and the login slips printed. Then freeze: only emergency fixes.
6. **After day 3:** run `export_study_data`, and the chapter 4 numbers come from `report.md`. `pseudonym_key.csv` stays private.

## What to check, by role
- **Everyone:** run the app (README, Docker or not), then sign in as a demo teacher and a demo student. Try:
  - the pretest;
  - a lesson;
  - one practice with a wrong first answer (hint, retry);
  - the results screen;
  - the teacher's class page;
  - creating and publishing a small exercise in the editor (one picture question, one video question).
- **The model groupmate:**
  - `model_artifacts/` (the fit's reports and checksums);
  - the template matches in `content/question_bank.json` (especially order of operations and the two addition templates);
  - the model rows in the "differs from the spec" table, against chapter 3;
  - `agent_retrain.csv` from a demo export, as the input for a later 12-input retrain.
- **The documentation groupmate:**
  - make chapter 3 match the "differs from the spec" table and the known limits above;
  - make chapter 4's analysis plan match `report.md` (paired t-test, Cohen's dz, normalized gain, scores by skill, Brier score and AUC).
- **The math teacher:** the review sheet (questions, hints, levels and the 10 feedback texts), and the lesson recaps in the app.

## Where things are

| Path | What |
|---|---|
| `docs/` | The 13-file spec |
| `PLAN.md` | The cram plan, dates and decisions as they were made |
| `apps/practice/` | Exercises, editor (`authoring.py`, `editor.py`), practice engine (`engine.py`), feedback |
| `learning/` | Pure logic: `bkt.py`, `agent.py`, `features.py`, `selection.py`, `stats.py`, `feedback/` |
| `content/` | Question bank, locked test, lesson knowledge (and the review sheet) |
| `model_artifacts/` | The fitted BKT and struggle model, with checksums and reports |
| `templates/lessons/` | The six lesson pages |
| `deploy/llm/`, `scripts/fetch_llm.py` | The Qwen service image and the model download |
| `tests/` | One file per phase, plus the editor, Qwen and spec-inventory tests |
