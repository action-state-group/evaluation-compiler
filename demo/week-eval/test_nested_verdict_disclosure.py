# SPDX-License-Identifier: BSD-3-Clause
"""Regression guard: a nested verdict discloses as `disclosure_match`.

The crux of the eval-compiler demo is that a report/aggregate capsule commits
`json_digest(verdict)` over a *nested* structure (a `per_axis` object of objects
plus an `outcomes` list of objects), and the disclosed value must recompute to
that exact committed digest under DE-3. A canonicalization that mishandled nested
members would silently turn `disclosure_match` into `disclosure_mismatch`. This
pins the Python DE-3 path (`agent_action_capsule`); the browser viewer's own
nested-canonicalization guard lives in scitt-cose's `test_bundle_page.py`.

This repo has no CI, so this is a manual/local gate: run
`pytest demo/week-eval/test_nested_verdict_disclosure.py` with
`agent_action_capsule` importable.
"""
from __future__ import annotations

import pytest

pytest.importorskip("agent_action_capsule")

from agent_action_capsule.bundle import verify_bundle
from agent_action_capsule.canonical import compute_capsule_id, json_digest

# A representative nested verdict, matching the report/aggregate disclosure shape.
NESTED_VERDICT = {
    "per_axis": {
        "policy_compliance": {"pass": True, "rationale": "no disallowed action", "evidence_ids": ["e1", "e2"]},
        "task_resolution": {"pass": False, "rationale": "refund not issued", "evidence_ids": ["e3"]},
        "grounded_communication": {"pass": True, "rationale": "cited policy §3.1"},
    },
    "outcomes": [
        {"case": "task-1", "policy_compliant_resolution": False, "reward_basis": "all_required"},
        {"case": "task-2", "policy_compliant_resolution": True, "reward_basis": "all_required"},
    ],
    "aggregate": {"policy_compliance": "1/2", "task_resolution": "1/2", "grounded_communication": "2/2"},
}


def _report_capsule(verdict: dict) -> dict:
    capsule = {
        "spec_version": "draft-mih-scitt-agent-action-capsule-04", "format_version": "4",
        "canonicalization_id": "jcs", "action_id": "week-eval-report", "action_type": "decide",
        "operator": "ACME-CO", "developer": "eval-compiler@v1", "timestamp": "2026-09-14T00:00:00Z",
        "assurance": {"effect_mode": "not_applicable", "attestation_mode": "self_attested", "ledger_mode": "standalone"},
        "disposition": {"verdict_class": "blocked", "decision": "reject", "approver": "policy", "human_disposed": False},
        "model_attestation": {"compute_attestation": {"agent_output_digest": json_digest(verdict)}},
    }
    capsule["capsule_id"] = compute_capsule_id(capsule)
    return capsule


def test_nested_verdict_discloses_as_match():
    capsule = _report_capsule(NESTED_VERDICT)
    bundle = {
        "bundle_version": "2", "bundle_kind": "evidence-bundle/v2",
        "root": capsule["capsule_id"], "records": [capsule],
        "disclosures": {capsule["capsule_id"]: {"agent_output": NESTED_VERDICT}},
    }
    result = verify_bundle(bundle)
    statuses = [(d.member, d.status) for d in result.disclosures]
    assert ("agent_output", "disclosure_match") in statuses, statuses


def test_altered_nested_leaf_is_a_mismatch():
    # A single changed nested leaf must break the match — proves the check binds
    # the whole nested structure, not just its top-level keys.
    capsule = _report_capsule(NESTED_VERDICT)
    tampered = {**NESTED_VERDICT, "per_axis": {**NESTED_VERDICT["per_axis"],
                "task_resolution": {"pass": True, "rationale": "refund not issued", "evidence_ids": ["e3"]}}}
    bundle = {
        "bundle_version": "2", "bundle_kind": "evidence-bundle/v2",
        "root": capsule["capsule_id"], "records": [capsule],
        "disclosures": {capsule["capsule_id"]: {"agent_output": tampered}},
    }
    result = verify_bundle(bundle)
    statuses = [(d.member, d.status) for d in result.disclosures]
    assert ("agent_output", "disclosure_mismatch") in statuses, statuses
