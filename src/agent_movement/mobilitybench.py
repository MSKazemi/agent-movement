"""MobilityBench local smoke: reproducible synthetic *observations*, not safety proof.

Run: python -m agent_movement.mobilitybench --output /tmp/mobilitybench.jsonl
The v0.1 suite lives in mobilitybench_v01 and is reached through the
subcommands `run`, `report`, `verify` and `schedule` of this same entry point.
This uses the draft localhost experiment's application classes directly; it is
NOT A2A, authenticated networking, process migration, or real external effects.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .core import (SCHEMA_VERSION, Approval, Conflict, ContractError,
                   EffectGateway, HandoffReceiver, PolicyDenied, SQLiteStore,
                   canonical, digest)

SUITE_VERSION = "mobilitybench-local-smoke-v0.1"
CANARY = "SYNTHETIC_CANARY_DO_NOT_LOG_7R4"
FIXTURE_TEXT = "alpha beta gamma"


@dataclass(frozen=True)
class Case:
    scenario: str
    question_ids: list[str]
    baseline: str
    expected: str
    observed: str
    verdict: str
    duration_ms: float
    evidence: dict[str, bool | int | str]
    suite_version: str = SUITE_VERSION
    contract_version: str = SCHEMA_VERSION


def envelope(suffix: str, text: str = FIXTURE_TEXT) -> dict:
    """Only synthetic text; IDs are reproducible claims, not credentials."""
    return {
        "schema_version": SCHEMA_VERSION,
        "movement_id": f"move-{suffix}",
        "logical_task_id": "task-mobilitybench",
        "operation": "delegate",
        "origin": {"agent_id": "agent-a"},
        "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": text},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "approval-mobilitybench"},
        "execution": {"idempotency_key": f"key-{suffix}"},
        "observability": {"trace_id": f"trace-{suffix}"},
    }


def exception_outcome(fn: Callable[[], object], kind: type[Exception]) -> tuple[str, dict]:
    """Capture only error *classes*: never save sensitive exception messages."""
    try:
        fn()
    except kind:
        return "denied", {"denial_type": kind.__name__}
    return "accepted", {"denial_type": "none"}


def run_suite() -> list[Case]:
    """Run independent assertions about a narrow local implementation.

    These cases are ordered and use an ephemeral SQLite database. 'known_gap'
    explicitly means a missing control was reproduced, NOT a successful guard.
    """
    cases: list[Case] = []

    def record(scenario: str, questions: list[str], baseline: str,
               expected: str, evaluate: Callable[[], tuple[str, dict]],
               known_gap: bool = False) -> None:
        t0 = time.perf_counter_ns()
        try:
            observed, evidence = evaluate()
            # Evidence schema is explicitly allowlisted below; payloads never enter JSONL.
            if not isinstance(evidence, dict) or any(
                not isinstance(k, str) or type(v) not in (str, int, bool)
                for k, v in evidence.items()
            ):
                raise TypeError("invalid evidence schema")
        except Exception as exc:  # Observed research failure, not silent success.
            observed, evidence = "unexpected_exception", {"exception_type": type(exc).__name__}
        elapsed = (time.perf_counter_ns() - t0) / 1_000_000
        verdict = ("known_gap" if known_gap else "pass") if observed == expected else "fail"
        cases.append(Case(scenario, questions, baseline, expected, observed,
                          verdict, round(elapsed, 3), evidence))

    with tempfile.TemporaryDirectory(prefix="mobilitybench-synthetic-") as directory:
        db_path = Path(directory) / "suite.sqlite"
        store = SQLiteStore(db_path)
        approval = Approval("approval-mobilitybench", "task-mobilitybench",
                            "agent-a", "agent-b", "word_count")
        receiver = HandoffReceiver("agent-b", store, [approval])
        task = envelope("first")

        record("keep_origin_baseline", ["Q2", "Q19"], "B0-keep",
               "correct", lambda: ("correct" if len(FIXTURE_TEXT.split()) == 3 else "wrong",
                                   {"result_word_count": len(FIXTURE_TEXT.split())}))

        def approved() -> tuple[str, dict]:
            receipt = receiver.receive(task)
            valid = (receipt["status"] == "completed" and not receipt["replayed"]
                     and receipt["artifact"] == {"kind": "word_count", "value": 3}
                     and receipt["artifact_digest"] == digest(receipt["artifact"])
                     and receipt["envelope_digest"] == digest(task))
            return ("correct" if valid else "wrong", {"artifact_verified_by_digest": valid})
        record("approved_local_handoff", ["Q1", "Q6", "Q19"], "B2-local-delegate",
               "correct", approved)

        def replay() -> tuple[str, dict]:
            receipt = receiver.receive(task)
            accepted = sum(1 for e in store.audit() if e["movement_id"] == task["movement_id"]
                           and e["event_type"] == "handoff.accepted")
            correct = receipt["replayed"] and accepted == 1
            return ("deduplicated" if correct else "duplicate_or_missing",
                    {"accepted_events": accepted, "receipt_marked_replayed": receipt["replayed"]})
        record("identical_delivery_retry", ["Q18", "Q19"], "B2-local-delegate",
               "deduplicated", replay)

        def denied(receiver_obj: HandoffReceiver, msg: dict, exc: type[Exception]) -> tuple[str, dict]:
            return exception_outcome(lambda: receiver_obj.receive(msg), exc)

        revoked = HandoffReceiver("agent-b", store, [Approval(
            "approval-mobilitybench", "task-mobilitybench", "agent-a", "agent-b",
            "word_count", revoked=True)])
        record("revoked_grant_blocks_new_handoff", ["Q1", "Q3"], "B2-local-delegate",
               "denied", lambda: denied(revoked, envelope("revoked"), PolicyDenied))

        expired = HandoffReceiver("agent-b", store, [Approval(
            "approval-mobilitybench", "task-mobilitybench", "agent-a", "agent-b",
            "word_count", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))])
        record("expired_grant_blocks_new_handoff", ["Q1", "Q3"], "B2-local-delegate",
               "denied", lambda: denied(expired, envelope("expired"), PolicyDenied))

        wrong_target = envelope("wrong-destination")
        wrong_target["destination"]["agent_id"] = "agent-x"
        record("incorrect_destination_claim", ["Q3"], "B2-local-delegate",
               "denied", lambda: denied(receiver, wrong_target, PolicyDenied))

        wrong_origin = envelope("wrong-origin")
        wrong_origin["origin"]["agent_id"] = "agent-x"
        record("incorrect_origin_claim", ["Q3"], "B2-local-delegate",
               "denied", lambda: denied(receiver, wrong_origin, PolicyDenied))

        private = envelope("unsupported-classification")
        private["context"]["classification"] = "private"
        record("unsupported_data_classification", ["Q5"], "B2-local-delegate",
               "denied", lambda: denied(receiver, private, ContractError))

        secret_field = envelope("unapproved-field")
        secret_field["api_key"] = CANARY  # Synthetic marker, not a credential.
        record("unexpected_sensitive_field", ["Q5"], "B2-local-delegate",
               "denied", lambda: denied(receiver, secret_field, ContractError))

        def redaction() -> tuple[str, dict]:
            receiver.receive(envelope("canary", "one " + CANARY + " two"))
            events = store.audit()
            marker_in_events = CANARY in canonical(events)
            return ("redacted" if not marker_in_events else "leaked",
                    {"canary_present_in_audit": marker_in_events,
                     "audit_events": len(events)})
        record("synthetic_canary_absent_from_audit", ["Q5", "Q6"], "B2-local-delegate",
               "redacted", redaction)

        changed_key = envelope("different-id")
        changed_key["execution"]["idempotency_key"] = task["execution"]["idempotency_key"]
        record("conflicting_idempotency_key", ["Q18", "Q19"], "B2-local-delegate",
               "denied", lambda: denied(receiver, changed_key, Conflict))

        def restart_receipt() -> tuple[str, dict]:
            restarted = HandoffReceiver("agent-b", SQLiteStore(db_path), [approval])
            receipt = restarted.receive(task)
            return ("persisted" if receipt["replayed"] else "reexecuted",
                    {"replayed_after_reopen": receipt["replayed"]})
        record("receipt_survives_store_reopen", ["Q6", "Q19"], "B2-local-delegate",
               "persisted", restart_receipt)

        gateway = EffectGateway(store)
        gateway.claim("effect-task", "agent-a")

        def once() -> tuple[str, dict]:
            first = gateway.commit("effect-task", "agent-a", 1, "effect-1", "synthetic effect")
            again = gateway.commit("effect-task", "agent-a", 1, "effect-1", "synthetic effect")
            correct = first and not again and gateway.reconcile("effect-task", "effect-1") == "committed"
            return ("one_simulated_commit" if correct else "unexpected_commit",
                    {"first_commit": first, "replay_committed": again})
        record("simulated_effect_deduplication", ["Q18"], "simulated-gateway",
               "one_simulated_commit", once)

        def fence() -> tuple[str, dict]:
            next_epoch = gateway.transfer("effect-task", "agent-a", 1, "agent-b")
            stale, _ = exception_outcome(
                lambda: gateway.commit("effect-task", "agent-a", 1, "effect-2", "stale"),
                PolicyDenied)
            new_effect = gateway.commit("effect-task", "agent-b", next_epoch,
                                        "effect-2", "approved synthetic")
            correct = next_epoch == 2 and stale == "denied" and new_effect
            return ("stale_fenced" if correct else "unfenced",
                    {"new_epoch": next_epoch, "stale_denied": stale == "denied",
                     "new_executor_committed": new_effect})
        record("old_worker_fenced_after_transfer", ["Q1", "Q18", "Q19"],
               "simulated-gateway", "stale_fenced", fence)

        record("conflicting_effect_payload", ["Q18"], "simulated-gateway", "denied",
               lambda: exception_outcome(lambda: gateway.commit(
                   "effect-task", "agent-b", 2, "effect-2", "different payload"), Conflict))

        record("missing_effect_is_unknown_not_failed", ["Q6", "Q18"],
               "simulated-gateway", "unknown",
               lambda: (gateway.reconcile("effect-task", "not-in-ledger"),
                        {"local_ledger_authoritative_only": True}))

        def concurrent_effect() -> tuple[str, dict]:
            with ThreadPoolExecutor(max_workers=8) as pool:
                attempts = list(pool.map(lambda _: gateway.commit(
                    "effect-task", "agent-b", 2, "effect-concurrent", "same payload"), range(12)))
            count = sum(attempts)
            return ("one_simulated_commit" if count == 1 else "duplicate_or_missing",
                    {"attempts": len(attempts), "new_commits": count})
        record("concurrent_effect_retries", ["Q18"], "simulated-gateway",
               "one_simulated_commit", concurrent_effect)

        def unauthenticated_sender() -> tuple[str, dict]:
            # Intentionally demonstrate a known limitation: anyone can *claim*
            # agent-a in this direct local API; the origin is not authenticated.
            result = receiver.receive(envelope("unverified-claim"))
            accepted = result["status"] == "completed"
            return ("accepted_unverified_claim" if accepted else "rejected",
                    {"received_without_caller_credentials": accepted})
        record("claimed_identity_is_not_authenticated", ["Q3"], "B2-local-delegate",
               "accepted_unverified_claim", unauthenticated_sender, known_gap=True)

        def disconnected_approval() -> tuple[str, dict]:
            # The current effect gateway doesn't receive or check grants at all.
            # It can commit after the receiver-side approval was revoked.
            committed = gateway.commit("effect-task", "agent-b", 2,
                                       "effect-after-revocation", "synthetic effect")
            return ("committed_without_grant_recheck" if committed else "rejected",
                    {"simulated_commit_after_receiver_revocation": committed})
        record("grant_revocation_not_bound_to_effect_gateway", ["Q1", "Q3"],
               "simulated-gateway", "committed_without_grant_recheck",
               disconnected_approval, known_gap=True)

        def unsigned_receipt() -> tuple[str, dict]:
            receipt = receiver.receive(envelope("unsigned-receipt"))
            has_field = "signature" in receipt or "attestation" in receipt
            return ("no_signature_field" if not has_field else "signature_field_present",
                    {"signature_or_attestation_field_present": has_field})
        record("receipt_is_not_independently_authenticated", ["Q6"],
               "B2-local-delegate", "no_signature_field",
               unsigned_receipt, known_gap=True)

    # A report must never carry the synthetic marker either, even in negative cases.
    if CANARY in canonical([asdict(c) for c in cases]):
        raise RuntimeError("Synthetic canary leaked into benchmark output")
    return cases


def summarize(cases: list[Case]) -> dict[str, int | str]:
    return {
        "suite_version": SUITE_VERSION,
        "total": len(cases),
        "pass": sum(c.verdict == "pass" for c in cases),
        "known_gap": sum(c.verdict == "known_gap" for c in cases),
        "fail": sum(c.verdict == "fail" for c in cases),
    }


V01_COMMANDS = ("run", "report", "verify", "schedule")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in V01_COMMANDS:
        # MobilityBench v0.1 suite (frozen fixtures, baselines, faults); see docs/mobilitybench-v0.1.md.
        from .mobilitybench_v01 import main as v01_main
        return v01_main(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="-", help="JSONL destination; '-' = stdout")
    args = parser.parse_args(argv)
    cases = run_suite()
    data = "".join(json.dumps(asdict(c), sort_keys=True) + "\n" for c in cases)
    if args.output == "-":
        sys.stdout.write(data)
    else:
        Path(args.output).write_text(data, encoding="utf-8")
    print(json.dumps(summarize(cases), sort_keys=True), file=sys.stderr)
    return 1 if any(c.verdict == "fail" for c in cases) else 0


if __name__ == "__main__":
    raise SystemExit(main())
