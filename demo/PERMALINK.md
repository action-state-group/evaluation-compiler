# Permalinks: selective disclosure and the aggregate-rooted bundle

Two share surfaces close the demo. Both are produced by existing tools already on
the host — do not build new tooling.

- `capsule-emit` (console script `capsule-emit`) mints verify-surface permalinks,
  including selective disclosure of a single interaction Capsule.
- `capsule-engine` (console script `capsule-engine`) builds a self-contained,
  independently verifiable bundle plus its permalink, walking the provenance graph.

Both are separate from `capsulectl`, the evaluation CLI the generated skill drives.
The fragment after `#` is never sent to a server: only browser-side JS reads it.

## (a) Selective-disclosure permalink for one interaction Capsule

Only `agent_input` and `agent_output` are disclosable (`_REVEALABLE_FIELDS` in
`capsule-emit`). Every other field — effects, evidence, model attestation —
stays a committed digest and is never revealed.

1. Fetch the interaction Capsule as an exact SDK record:

   ```sh
   capsulectl get --profile "$PROFILE" --capsule-id "$INTERACTION_ID" \
     --raw --output interaction.json
   ```

2. Place the exact committed `agent_input` / `agent_output` payloads in their own
   JSON files (`agent_input.json`, `agent_output.json`). They must be the exact
   values the Capsule committed: `capsule-emit` recomputes each disclosed field's
   digest and refuses to emit the URL if it does not match the committed
   `{field}_digest`.

3. Mint the disclosed permalink:

   ```sh
   capsule-emit permalink interaction.json \
     --reveal agent_input=agent_input.json \
     --reveal agent_output=agent_output.json \
     --check
   ```

   `--reveal FIELD=payload.json` wraps the single Capsule in the Disclosure
   Envelope shape the viewer reads; fields with no `--reveal` stay withheld as
   digests. `--check` runs local `verify()` first and refuses to emit if the
   Capsule fails. Output is a one-line summary and the URL
   `https://verify.agentactioncapsule.org/v/<capsule_id>#<fragment>` (override the
   base with `--base-url`).

   For more than one Capsule the reveal selector is prefixed
   (`--reveal SELECTOR:FIELD=payload.json`, SELECTOR = 1-based record number or an
   >=8-char capsule_id prefix); a single interaction needs no selector.

## (b) Aggregate-rooted bundle permalink

`capsule-engine bundle` selects records from the ledger and transitively pulls in
everything they cite — each record's `chain.parent_capsule_id` and every
`references[]` edge — so the slice verifies standalone. Rooting the selection at
the `evaluation-summary/v1` Capsule therefore pulls in every contributing
`evaluation-report/v1` (the summary's `acted_on` references) and, through each
report's own `acted_on` references, the interaction acts they evaluated.

A single-capsule `--capsule-id`/`--root` selector is being added to `bundle` (it would
root the walk directly at the aggregate). Until it lands, `bundle` has no capsule-id
selector; select the summary with the scan filters
(`--agent`, `--since`/`--until`, `--counterparty`, `--verdict`, `--action-type`,
`--limit`) — e.g. a tight append-time window around the summary, or the aggregator
identity — and the walker resolves the rest:

```sh
capsule-engine bundle \
  --ledger "$CAPSULE_LEDGER" \
  --since "$SUMMARY_APPEND_START" --until "$SUMMARY_APPEND_END" \
  --out aggregate-bundle.json \
  --with-viewer
```

This writes `aggregate-bundle.json` (records, MMR completeness certificate, and a
per-record verification report run with the store restricted to the bundle's own
ids), prints the permalink
`https://verify.agentactioncapsule.org/bundle#<fragment>` (override with
`--verify-base-url` / `$CAPSULE_VERIFY_BASE_URL`), and — with `--with-viewer` —
writes `aggregate-bundle.html`, a self-contained offline viewer that verifies with
no network. A cited id genuinely absent from the ledger surfaces as an honest
finding on the citing record, never hidden.
