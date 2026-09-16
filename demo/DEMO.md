# tau2-airline evaluation demo

This demo backfills recorded tau2 airline interactions into a local SQLite CLL,
publishes daily `evaluation-report/v1` Capsules, and reduces a calendar month into
an `evaluation-summary/v1`. It is demonstration material, not compiler input.

## Prerequisites

```sh
(cd ~/GitHub/capsule-cli && go build -o /tmp/capsulectl ./cmd/capsulectl)
```

Create the local `airlinedemo` profile before following
[backfill/README.md](backfill/README.md). Use a dedicated local store and two
separate Ed25519 seeds: one to publish Capsules and one to sign checkpoints.
Keep both seed files outside this repository. Obtain each public key with
`capsulectl key show-public`; the profile must trust each corresponding signer.

```sh
DEMO_STORE="$HOME/.local/share/evaluation-runs/tau2-airline-eval/store"
mkdir -p "$DEMO_STORE"
capsulectl key generate --output "$DEMO_STORE/producer-seed.hex"
capsulectl key generate --output "$DEMO_STORE/checkpoint-seed.hex"
PRODUCER_PUBLIC_KEY=$(capsulectl key show-public "$DEMO_STORE/producer-seed.hex")
CHECKPOINT_PUBLIC_KEY=$(capsulectl key show-public "$DEMO_STORE/checkpoint-seed.hex")
capsulectl profile create --name airlinedemo --type sqlite \
  --sqlite-path "$DEMO_STORE/airlinedemo.sqlite" --namespace airlinedemo \
  --log-id tau2-airline-20260914 \
  --signing-key-file "$DEMO_STORE/producer-seed.hex" --trusted-key "$PRODUCER_PUBLIC_KEY" \
  --checkpoint-signing-key-file "$DEMO_STORE/checkpoint-seed.hex" \
  --checkpoint-trusted-key "$CHECKPOINT_PUBLIC_KEY"
capsulectl store init --profile airlinedemo
```

The checkpoint signer is required by `capsulectl cll checkpoint create`, which
must run after the final append and before `view`.

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
