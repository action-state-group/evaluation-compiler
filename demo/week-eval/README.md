# Temporal minimized demo — daily reports + end-of-week aggregate

A minimized, time-structured run of the tau2-airline evaluation: **9 conversations**
(tasks 0,1,10,11,12,13,14,15,16), grouped **3 per day over 3 days**. Each day the
evaluator judges that day's 3 conversations into ONE `evaluation-report/v1` daily
report; at end of week one `evaluation-summary/v1` aggregates the 3 daily reports.

## Pipeline

1. **B1/B2** (see `../DEMO.md`): create the `airlinedemo` SQLite CLL under a fresh
   `log_id`, backfill 9 conversations (`backfill.py --conversations 9`, 158 acts,
   published seq 1-158).
2. **Judge** (agentic, evidence-derived, isolated per the compiler's execution.md):
   each day's 3 conversations are judged on the three axes
   (`policy_compliance`, `task_resolution`, `grounded_communication`) against the
   declared `evaluation_criteria` in tau2 `tasks.json` (transcript-blind), the
   transcript, `policy.md`, and `db.json`. The verdicts are recorded in
   `verdicts.json`.
3. **`assemble_week.py`**: publishes the 3 daily reports + the weekly aggregate as
   real format-4 Capsules (each report `references[] acted_on` its day's act
   capsules; the aggregate fans in to the 3 reports), then assembles two Evidence
   Bundle v2 outputs and writes `PERMALINK.txt`.
4. **`build_offline_html.py`**: wraps the all-capsule bundle in a self-contained
   offline viewer HTML using the browser build of `agent-action-capsule/ts`
   (`browser_entry.mjs` -> esbuild IIFE), so it opens and verifies with no network.

## Two-version output rule (permanent)

A bundle that **includes the interaction (act) capsules** with both members
disclosed exceeds a browser's ~2 MB URL limit, so it is emitted only as an
**offline viewer HTML**. A second bundle that **excludes the interaction capsules**
(the daily reports + weekly aggregate only, the acts declared missing) stays small
and is emitted as a clickable **URL permalink**.

- `tau2-airline-week1-full.html` — all 162 capsules, both agent_input+output
  disclosed; ~5 MB; open the file directly.
- `PERMALINK.txt` — reports + aggregate only (4 records, 158 acts declared missing);
  ~87 KB URL; open against the scitt-cose viewer.

## Note

`assemble_week.py` rebuilds the MMR from `cll_entries` because `capsulectl publish`
appends leaves without materializing the checkpoint/MMR — cutting a checkpoint
(`capsulectl cll checkpoint create`) is a separate lifecycle step. See the plan's
step-7 CLL lifecycle note.
