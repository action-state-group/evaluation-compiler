# Capsule CLI contract

`capsulectl` is a host prerequisite. Use a configured profile and keep credentials
out of bundles and requests. Successful commands write JSON; always check exit status.

```sh
capsulectl profile list
capsulectl profile show NAME
capsulectl cll list --profile NAME --after AFTER --through THROUGH --limit 1000
capsulectl get --profile NAME --capsule-id ID
capsulectl get --profile NAME --capsule-id ID --raw --output record.json
capsulectl verify --profile NAME --capsule record.json
capsulectl publish --profile NAME --request request.json
```

`get` exposes unordered artifacts, so select them by name. Use raw record
verification. Requests use PascalCase capsule fields. A `Chain` single parent is
store-checked on publish; `References` are the fan-in citation mechanism.

## Publication request

`capsulectl publish --request` accepts a complete `capsule-seal-request/v1`
JSON object. The capsule envelope has the required identity fields below; the
application payload is placed in `payload`.

```json
{
  "spec_version": "capsule-seal-request/v1",
  "capsule": {
    "ActionID": "urn:example:daily-report:2026-09-14",
    "ActionType": "fyi",
    "Operator": "example-operator",
    "Developer": "example-producer@v1",
    "Timestamp": "2026-09-14T18:00:00Z",
    "References": [{
      "Type": "agent-action-capsule",
      "DigestAlg": "SHA-256",
      "Digest": "CAPSULE_ID",
      "CitationPurpose": "acted_on"
    }]
  },
  "payload": {"spec_version": "example/v1"}
}
```

Use one `References` entry for each cited Capsule. `CitationPurpose` states why
it is cited. `LogCoordinates` is optional; if present, it must include `log_id`, `leaf_index`, and `inclusion_proof`.
A request
may instead use `capsule.Chain` for one store-checked parent relation; do not use
it to replace a multi-Capsule citation set.

## Evidence output

```sh
capsulectl bundle --profile NAME --root ID --closure-depth 3 --out bundle.json
capsulectl disclose --profile NAME --root ID --closure-depth 3 --out disclosed.json
capsulectl permalink --profile NAME --root ID --closure-depth 3
capsulectl cll checkpoint create --profile NAME
capsulectl view --profile NAME --root ID --closure-depth 3 --out evidence.html
```

`bundle` assembles the citation closure, `disclose` includes committed member
originals, `permalink` emits a disclosed viewer URL, and `view` writes standalone
evidence-graph HTML. `view` requires a covering tip-aligned checkpoint, created
after the final append. Its root should be the summary; disclose agent input only
when it is intended to be visible.
