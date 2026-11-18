# Instructions for anyone working on PathGen 4.2 (people and AI coding agents)

**Read `HANDOFF.md` first, before anything else.** It says what is built, where 4.2 differs from the spec and why, what is still open, and what to check. Don't change code until you have read it.

Then:

1. Read `docs/system.md` and `docs/build_order.md`. The 13 files in `docs/` are the spec.
2. Read `PLAN.md` for the dates and the decisions as they were made. The differences listed in `HANDOFF.md` ("Where 4.2 differs from the spec") are the team's current choices, not locks. Change one only after the team agrees; `HANDOFF.md` ("If the team wants to switch") says where each lives in the code. Update that table when you do.
3. Work one phase at a time, and run its "Done when" checks before calling it done.
4. Develop on SQLite first. Run the tests on PostgreSQL as well before deploying (README, "Check it"). `manage.py test` uses `config.settings.test`.
5. Never commit `.env`, real student data, uploaded media, `db.sqlite3`, or model binaries (the Qwen GGUF).
6. When you finish a piece of work, update `HANDOFF.md` (what's done, what's left) so the next person starts from the truth.
