# Temporal airline demo: daily reports, monthly summary, calibration chain

`assemble_week.py` publishes one `evaluation-report/v1` per fixture day and then
one `evaluation-summary/v1`. The summary freezes every contributing report ID after
enumerating reports by their declared `payload.date` within `--month`; it does not
infer a calendar window from CLL sequence numbers.

For a small end-to-end validation, backfill a fresh two or three day slice, then run:

```sh
CAPSULECTL=/tmp/capsulectl AAC_PROFILE=airlinedemo \
  python3 demo/week-eval/assemble_week.py --month 2026-09 --days 2
CAPSULECTL=/tmp/capsulectl AAC_PROFILE=airlinedemo \
  python3 demo/week-eval/generate_synthetic_calibration.py --month 2026-09
capsulectl cll checkpoint create --profile airlinedemo
capsulectl view --profile airlinedemo --root "$MONTHLY_SUMMARY_CAPSULE_ID" \
  --closure-depth 3 --out "$HOME/Downloads/tau2-airline-month.html"
```

The calibration generator is labelled synthetic/illustrative. It publishes a
`sample-manifest/v1`, one chained `human-rating/v1` per sampled report, and a final
`calibration-summary/v1`; it is not a substitute for the blind human workflow in
[`../blind-expert/`](../blind-expert/). The checkpoint is deliberately cut after the
calibration summary: `view` requires a covering tip-aligned checkpoint. Its output is
a standalone HTML file that boots `renderEvidenceGraph(window.__BUNDLE__)`.
