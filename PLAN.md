# PathGen 4.2: cram build plan

> For the current state, start with `HANDOFF.md`. This file is the cram plan as it was written and updated.

Written Sun 15 Nov 2026. We are going **all in on 4.2**: students use 4.2, and there is no prepared backup. The build follows the 13-file spec in `docs/` (`docs/build_order.md`), cut down to what the school study and the final check need.

## Status (Wed 18 Nov, night)

| Step | State |
|---|---|
| Phase 1 | Done Sun 15 |
| 10-skill model fit | Done Mon 16 morning. All 10 skills pass the BKT check; struggle model AUC 0.752 vs BKT alone 0.719 (validation students). Files in `model_artifacts/` |
| Phase 2 | Done Mon 16. Sign-in, roles, profile, admin console with the 3 create dialogs, classes, curriculum seed, 6 placeholder lesson pages, `create_study_class` with login slips |
| Phase 3 | Done Mon 16 (planned for Tue). Locked test as pretest and posttest, start/submit dialogs, autosave, server grading, pretest gate, the teacher's "Open posttest" |
| Phase 4 | Done Mon 16 (planned for Tue). Bank of 118 questions imported as one exercise per lesson; read-only pool view for teachers |
| Content | All 118 questions drafted at once, not in batches. Review sheet sent as a link; waiting for the math teacher |
| Phase 5 | Done Wed 18. Practice screen (start, question, hint after a wrong first answer, one retry, move on, results, one retake), one BKT update per first answer, the 5 selection rules with the 8-input struggle model, a decision log per served question, teacher-order fallback |
| Phase 6 | Done Wed 18. Six lesson pages: 2-minute recap first (key idea, worked example, one interactive), then a section per skill; 3.0's widgets ported; `content/lesson_knowledge.json` (10 draft texts) feeds the results screen; no Qwen |
| Phase 7 | Done Wed 18, except going online: teacher class page (practice finished, first-try score, skill gaps), student page (sessions, mastery), `export_study_data` with the pre/post analysis. Production settings checked locally. `DEPLOY.md` has the GitHub + Railway steps; they need the team's accounts |
| Spec alignment | Done Wed 18 night (see the next section): SQLite in development with PostgreSQL in production, Docker and Compose, the teacher exercise editor with picture and YouTube questions and dialogs 4–6, local Qwen feedback (switchable, with the approved text as fallback), all 12 model inputs logged, Chart.js summaries with tables, AnimateIcons |
| Tests | 123 pass, on PostgreSQL and on SQLite (`manage.py test`) |

Decided while building Phases 2–4:
- **Figure questions are text only.** 3.0's 18 exercise figures (like all 26 of its figures) are 1×1 blank placeholders. 4 prompts were reworded to put the numbers in the text.
- **13 new questions**, so every skill has Easy, Medium and Hard items: 3 number line (3.0 had no number-line reading items), 2 opposites, 2 absolute value, 4 addition, 2 subtraction.
- **Junyi templates:** context questions are matched by story type (temperature, depth, change). Addition uses T005 for "add a negative" and T006 for "negative plus positive". Order of operations uses T010/T011/T012 by difficulty order, because Junyi doesn't describe its 3 problem types. The model groupmate should confirm these.
- In 7 of the 10 skills every question shares one template, so inside those skills the model gives every candidate the same score and the Easy/Medium/Hard rule does the adapting. This is the "what the model decides" hurdle already in the team doc.
- **The admin console's create dialogs were built after all** (cut in the first plan); they were quick.
- ~~Still cut: the teacher exercise editor, the publish/unpublish/delete dialogs (4–6), uploaded figures and video.~~ Built Wed 18 night.

Decided while building Phases 5–7 (Wed 18):
- **3.0's lesson examples repeated two posttest items** (item 16's expression and item 18's temperature story). The 4.2 pages use different numbers, and a test checks that no locked item appears on a lesson page.
- **Struggle** (for the easier/harder rule and the logs) = wrong first answer, a retry, or the hint. The model's own target stays "wrong first answer or hint", as trained.
- **Score change** is computed from the raw counts, not from rounded percents.
- **Labels:** with the fitted priors, multiplication, division, addition and absolute value start high (0.85–0.94), so a student with 2 of 4 right on multiplication can read "Doing well" (0.76). The 0.75 line is the spec's; say so in chapter 4 if asked.
- **Going online without the Railway CLI:** each deploy runs the migrations and both seeds; accounts and imports run from the laptop against Railway's public database address (DEPLOY.md, step 3).

## Where 4.2 differs from the spec (Wed 18 Nov)

Everything in `docs/build_order.md` Phases 1–7 is built. These differences are deliberate:

| Spec | 4.2 | Why |
|---|---|---|
| `agent_model.pkl`, 12 inputs, loaded with scikit-learn | `struggle_model.json`, 8 inputs, plain Python, checked against `manifest.json` | A pickle runs code when it loads. The 8-input model was refitted at the 10-skill level with BKT limits (validation AUC 0.752 vs 0.719 for BKT alone). The 4 attempt and time inputs shift between Junyi (unlimited attempts, hints any time) and PathGen (2 attempts, hint only after a wrong answer). All 12 inputs are still saved for every served question and exported in `agent_retrain.csv`, so a 12-input retrain can use PathGen's own data. |
| Admin authors the pretest and posttest | The locked 30-item test, read-only in the admin console | It is the approved instrument; editing it during the study would break the pre/post comparison. It has no opposites item, so "covers all ten skills" is reported as a gap. |
| Python 3.14.7 | Python 3.13 | Every test ran on 3.13; Django 5.2 supports both. |
| Google Fonts | System fonts | The approved 3.0 look uses system fonts. Adding a Google Font changes the approved design, so it waits for the adviser. |
| Difficulty Easy 0.15 / Medium 0.30 / Hard 0.50 | Bank questions: their Junyi template's real struggle rate. Editor questions: 0.15 / 0.30 / 0.50 | The model was trained on template struggle rates, so bank questions use the same scale; teacher-written questions have no template and use the spec's provisional numbers. |
| Feedback from local Qwen | Built, off unless `LLM_BASE_URL` is set | Qwen needs about 1 GB on Railway. Turn it on for the study only if the Thu go/no-go passes with it on; otherwise the approved text is the feedback. |

Not yet verified on this PC: the Docker images (no Docker installed here) and a real Qwen reply (`manage.py check_llm` against llama.cpp b12464; see README). Both are checked on the first deploy.

## Dates

| When | What |
|---|---|
| Sun 15, tonight | Phase 1 starts |
| Sun 15 | Phase 1 done |
| Mon 16 | Claude fits the 10-skill model (trainer, about 6 minutes). Content drafts start and go to the math teacher as they're ready. Phase 2 |
| Tue 17 | ~~Phase 3. Phase 4~~ (done Mon). Phase 5 starts a day early; the teacher's corrections folded in when they arrive |
| Wed 18 | Phase 5, the practice engine. **Checkpoint at night** (Phases 5–7 done; only "online" waits for accounts) |
| Thu 19 | Phase 6, Phase 7, online. **Go/no-go at night** |
| Fri 20 | Groupmate check, then fixes |
| Sat 21 | Adviser and evaluator check |
| Sun 22 | Fixes, then freeze. Fresh study database and study accounts |
| Mon 23 | School day 1: pretest |
| Wed 25 | School day 2: students use 4.2 |
| Fri 27 | School day 3: posttest. Run the prepared analysis |
| Fri 27 – Sat 28 | Results go into chapter 4. Final check (pick 27 or 28 if you can choose) |

## Settled (don't reopen during the cram)

- **Pre/post test:** the locked 30 items, loaded from 3.0's `pretest_posttest.json` (it has the text choices for item 13). The test has no opposites item, so the spec's "covers all ten skills" check is relaxed and the gap is reported.
- **Stack:** SQLite first in development, PostgreSQL for the concurrency checks and production (the spec's order, and the team's). Docker for teammates and Railway. Python 3.13 and Django 5.2.
- **Model:**
  - BKT with limits (guess ≤ 0.3, slip ≤ 0.1, learn ≤ 0.3), plus the 8-input struggle model.
  - Claude fits both at the 10-skill level with `pathgen4.0-trainer` on Mon 16, without waiting.
  - If the groupmate's rerun (with limits) arrives later, it can replace them in the same slot, if it does better.
- **Attempts and timing** are recorded for the after-study retrain, but they are not model inputs.
- **Difficulty:** each question is tagged with its closest Junyi template, and its difficulty is that template's real struggle rate. Easy/Medium/Hard stays, for the "easier or harder next" rule.
- **Questions:**
  - 3.0's 105 questions, re-tagged into the 10 skills, plus a few new ones where a skill is thin (opposites has 4).
  - The 84 missing hints are drafted from each question's own explanation.
  - Everything stays a draft until a math teacher checks it.
- **Day 2 is 1 hour of system use.** The team arrives early to set up, so sign-in problems don't eat the hour.
  - **Questions per exercise:** 4 per lesson, and 5 for Integer Foundations (it has 4 skills). That's 25 in total.
  - **Lesson pages** open with a short recap: the key idea, one worked example and one interactive, about 2–3 minutes. 3.0's full content sits below it for anyone who wants more.
  - **Time budget:** about 5 minutes to sign in, then 6 lessons × (recap 2–3 min + exercise 4–6 min) ≈ 45–50 minutes, with about 10 minutes spare.
  - A student who doesn't finish all 6 lessons is reported as such in chapter 4 (lessons finished per student).

## Phases

### Phase 1: project setup (Sun night to Mon morning)
- **Build:** the project in the spec's layout: 6 apps, the custom user, split settings, the base page, the shared CSS with the 6 breakpoints, a health page, README and AGENTS.md.
- **Cut:** Docker, Compose and SQLite.
- **Done when:** `manage.py check` and the migrations pass on PostgreSQL, `/health/` answers, and the base page loads on a phone.

### Phase 2: accounts, classes, curriculum (Mon)
- **Build:**
  - sign-in, sign-out, role landing pages and the profile page;
  - classrooms and student profiles;
  - the seed of the 6 lessons, 10 skills and prerequisites;
  - 6 placeholder lesson pages;
  - a command that creates a whole study class from a list and prints a login sheet (one slip per student) for the school days.
- **Cut:** the admin's custom create dialogs. Django's own admin covers them during the cram.
- **Done when:**
  - each role signs in and lands on its page;
  - a teacher can't open another teacher's class;
  - reseeding leaves 6 lessons and 10 skills.

### Phase 3: pre/post test and journey (Tue morning)
- **Build:**
  - the assessment tables and the locked test seed;
  - the assessment page with its start and submit dialogs, saved drafts and server grading;
  - the journey gate (pretest first, then all 6 lessons);
  - the teacher's "open posttest" button.
- **Cut:** the assessment editor (the test is locked anyway).
- **Done when:**
  - lessons stay locked until the pretest is submitted;
  - the posttest appears only after the teacher opens it;
  - scores are stable on repeat requests.

### Phase 4: exercises from 3.0's bank (Tue)
- **Build:**
  - the exercise, revision, question, choice and assignment tables;
  - an import command that loads the bank as one published exercise per lesson, assigned to a class.
- **Content (Claude, at the same time):** for every question, the 10-skill tag, the difficulty, the Junyi template and the hint, plus the new questions.
- **Cut:** the teacher exercise editor. It's built after the school days.
- **Done when:**
  - every imported question has 4 choices, 1 correct answer, 1 skill, a difficulty, a hint and a template;
  - the import refuses a pool that can't cover its skills.

### Phase 5: BKT, model, adaptive practice, decision log (Tue night to Wed)
- **Build:**
  - `learning/bkt.py`, `features.py`, `agent.py` (reusing the 4.0 app's `struggle.py`), `selection.py` (the spec's rules 1–5) and `progress.py` (the labels);
  - the session, served question, attempt, mastery, mastery event, decision and feedback tables;
  - the practice screen: start, resume, answer, hint, one retry, next, results, and one retake.
- **Done when:**
  - answers change the next question while coverage and length still hold;
  - exactly one BKT update happens per first answer;
  - the retry and retake follow the spec's rules;
  - picking falls back to teacher order when the model can't run;
  - every pick is logged with its inputs, candidates and prediction;
  - the spec's acceptance cases pass.
- **Checkpoint, Wed night:** if a student can't finish an exercise end to end by now, say so then, not on Thursday.

### Phase 6: lesson pages and feedback (Thu morning)
- **Build:**
  - 3.0's 7 lesson parts moved into the 6 lesson pages, with their interactive activities and the spec's skill anchors (`skill-int-…`);
  - `content/lesson_knowledge.json` (10 entries);
  - results that show the first-try score, the number corrected on retry, one focus skill, a review link, and feedback text taken from the knowledge file.
- ~~Cut: Qwen and llama.cpp.~~ Built Wed 18 night and off unless `LLM_BASE_URL` is set; the approved text shows either way.
- **Done when:** all 6 pages show their content on a phone, and the results screen works with and without the knowledge file.

### Phase 7: teacher results, phone tests, export, online (Thu)
- **Build:**
  - the teacher's class and student pages: practice results, labels and test scores, as tables;
  - the analysis export (pre/post per student plus the practice logs);
  - the deployment, set up the same way as 3.0's (Django plus PostgreSQL on Railway).
- **Cut:** charts, the admin overview extras, and the Qwen service. They're built after the school days.
- **Done when:** the go/no-go list below passes online.

## Go/no-go, Thu 19 night

Go only if all of these hold:
- [ ] On 3 phones at once, a student can: sign in, take the pretest, open all 6 lessons, run each exercise to its count (adaptive picks, hint and retry), see the results, then take the posttest once the teacher opens it and see both scores.
- [ ] Every answer has its mastery update and decision log saved.
- [ ] The export produces the analysis file.
- [ ] No error pages appear on a full run, on mobile data as well as Wi-Fi.

**If it's a no**, decide that night:
- fix on Fri and squeeze both checks into Sat–Sun (only if the gap is small); or
- finish 3.0 plus the 4.0 model on Fri (half a day) and send that to the checks; or
- accept March.

## While the study runs

- **Freeze from Sun 22 to Fri 27.** Only emergency fixes go online.
- On Wed 25 – Fri 27, the teacher editor, charts and Qwen are built separately and go online only after the posttest, in time for the final check.
- The analysis script is written and tested before Mon 23.

## Who does what (proposal, change as needed)

- **Claude, with you:** Phases 1–7, the content drafts, the model fit and the analysis script. You test on your phone after each step and answer questions quickly.
- **Model groupmate:** the model sections of chapters 3 and 4 (Claude supplies the numbers from Monday's fit). A rerun with limits is welcome, but nothing waits for it.
- **Other groupmate:**
  - chapters 3–5;
  - each evening, running the "done when" checks of the day's phase, which keeps Friday's check short;
  - the consent letters (hand them out Mon 16 or Wed 18) and the school schedule.
- **A math teacher:** checks the drafted tags, hints, new questions and lesson recaps as each batch arrives, Mon to Thu.

## Built after the school days, or future work

The optional dialogs, the assessment editor, and the contextual bandit. (The editor, charts, Qwen, Docker, SQLite and video questions were built on Wed 18.)

## Risks to watch

- **Phase 5 is the core.** If it isn't working by Wed night, Thursday will probably be a no.
- **Content checking takes people time.** Start it on Tue.
- **School network:** test on mobile data, not only Wi-Fi.
- **Day 2's length** decides the questions per exercise.

## Open items

1. ~~How long is day 2?~~ 1 hour, plus setup time beforehand (answered 15 Nov).
2. ~~The groupmate's rerun.~~ Claude fits the model on Mon 16 instead of waiting.
3. A shared GitHub repo: none yet. Claude builds locally until the team says otherwise.
4. ~~Who checks the drafts?~~ The user gets each batch checked as soon as it's ready.
