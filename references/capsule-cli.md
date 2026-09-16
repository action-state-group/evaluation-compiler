# Capsule CLI contract

`capsulectl` is a host prerequisite. Use a configured profile; keep credentials out
of bundles and requests. Successful commands write JSON, but always check exit status.

```sh
capsulectl profile list
capsulectl profile show NAME
capsulectl cll list --profile NAME --after AFTER --through THROUGH --limit 1000
capsulectl get --profile NAME --capsule-id ID
capsulectl get --profile NAME --capsule-id ID --raw --output record.json
capsulectl verify --profile NAME --capsule record.json
capsulectl publish --profile NAME --request request.json
```

`get` exposes unordered artifacts; select them by name. Use a raw record for
verification. Requests use PascalCase capsule fields. A `Chain` has a single parent
and is store-checked on publish; `References` is the fan-in citation mechanism.

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
evidence-graph HTML. `view` requires a covering tip-aligned checkpoint, so create it
after the final append and before rendering. A view root summary must disclose agent
input; use suppression only for intentional withholding.
