# tau2-airline evaluation demo

This demo backfills recorded tau2 airline interactions into a local SQLite CLL,
publishes daily `evaluation-report/v1` Capsules, and reduces a calendar month into
an `evaluation-summary/v1`. It is demonstration material, not compiler input.

## Prerequisites

```sh
(cd ~/GitHub/capsule-cli && go build -o /tmp/capsulectl ./cmd/capsulectl)
```

Create the local `airlinedemo` profile and backfill a fresh small airline slice as
described in [backfill/README.md](backfill/README.md). The profile needs its normal
producer key and a checkpoint signing key.

## B5. Render the provenance graph

After publishing reports and the monthly summary, cut a checkpoint at the final tip.
`capsulectl view` requires a covering tip-aligned checkpoint before rendering.

```sh
capsulectl cll checkpoint create --profile airlinedemo
capsulectl view --profile airlinedemo --root "$MONTHLY_SUMMARY_CAPSULE_ID" \
  --closure-depth 3 --out "$HOME/Downloads/tau2-airline-month.html"
```

The generated file contains the disclosed bundle and boots
`renderEvidenceGraph(window.__BUNDLE__)`; depth 3 reaches cited acts and ratings.
`capsulectl bundle` writes a bundle JSON, `disclose` writes a disclosed bundle, and
`permalink` mints a disclosed URL fragment. Use `view` for this self-contained demo.

## B6. Temporal minimized run

Validate with two or three days, not a regenerated full month:

```sh
CAPSULECTL=/tmp/capsulectl AAC_PROFILE=airlinedemo \
  python3 demo/week-eval/assemble_week.py --month 2026-09 --days 2
CAPSULECTL=/tmp/capsulectl AAC_PROFILE=airlinedemo \
  python3 demo/week-eval/generate_synthetic_calibration.py --month 2026-09
capsulectl cll checkpoint create --profile airlinedemo
capsulectl view --profile airlinedemo --root "$MONTHLY_SUMMARY_CAPSULE_ID" \
  --closure-depth 3 --out "$HOME/Downloads/tau2-airline-month.html"
```

The assembler selects acts through committed `case.conversation_id` and `turn_idx`,
then freezes reports selected by each report payload's declared `date`. The calibration
generator appends labelled synthetic manifest/rating/summary Capsules; real blind human
ratings use [blind-expert/](blind-expert/), not synthetic output.
