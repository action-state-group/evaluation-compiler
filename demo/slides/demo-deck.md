# tau2-airline evaluation demo

## Pipeline

Recorded airline interactions are backfilled into a local CLL. The evaluator emits
daily `evaluation-report/v1` Capsules; a monthly reducer selects reports by their
declared `date`, freezes the selected IDs, and publishes `evaluation-summary/v1`.

## Calibration and render

The demo may append labelled synthetic calibration Capsules to illustrate the chain;
real calibration is blind human work. After the final append, checkpoint and render:

```sh
capsulectl cll checkpoint create --profile airlinedemo
capsulectl view --profile airlinedemo --root "$MONTHLY_SUMMARY_CAPSULE_ID" \
  --closure-depth 3 --out tau2-airline-month.html
```

The HTML contains `window.__BUNDLE__` and boots `renderEvidenceGraph`.
