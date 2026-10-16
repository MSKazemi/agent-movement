"""Deterministic, local-only, *synthetic* envelope migration demonstration.

No network operations, keys, approvals or private user data.  The draft is a
proposal only; this does not turn the local runtime into a 0.2 receiver.
"""
from __future__ import annotations

import argparse
import json

from agent_movement.contract_compat import (
    DRAFT_VERSION, negotiate_wire_version, project_draft_to_runtime,
    project_runtime_to_draft, runtime_capabilities,
)
from agent_movement.core import SCHEMA_VERSION, digest, validate_envelope


def demo() -> dict[str, object]:
    original = validate_envelope({
        "schema_version": SCHEMA_VERSION,
        "movement_id": "demo-movement-1",
        "logical_task_id": "demo-task-1",
        "operation": "delegate",
        "origin": {"agent_id": "synthetic-origin"},
        "destination": {"agent_id": "synthetic-destination"},
        "task": {"kind": "word_count", "text": "synthetic sample only"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "synthetic-approval"},
        "execution": {"idempotency_key": "synthetic-key"},
        "observability": {"trace_id": "synthetic-trace"},
    })
    proposal = project_runtime_to_draft(original)
    recovered = project_draft_to_runtime(proposal, allow_projection=True)
    assert recovered == original
    return {
        "executed_version": negotiate_wire_version([SCHEMA_VERSION, DRAFT_VERSION]),
        "draft_version": proposal["schema_version"],
        "identical_runtime_roundtrip": recovered == original,
        "original_fingerprint": digest(original),
        "roundtrip_fingerprint": digest(recovered),
        "runtime_capabilities": runtime_capabilities(),
        "unimplemented": ["relocate", "automatic_downgrade", "draft_ingress", "draft_auth_verification"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="render deterministic compact JSON")
    args = parser.parse_args()
    outcome = demo()
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":") if args.json else None,
                     indent=None if args.json else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
