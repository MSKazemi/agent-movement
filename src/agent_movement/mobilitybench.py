"""MobilityBench local smoke: reproducible synthetic *observations*, not safety proof.

Run: python -m agent_movement.mobilitybench --output /tmp/mobilitybench.jsonl
     python -m agent_movement.mobilitybench --no-timing --output a.jsonl  # byte-identical reruns
The v0.1 suite lives in mobilitybench_v01 and is reached through the
subcommands `run`, `report`, `verify` and `schedule` of this same entry point.
This uses the draft localhost experiment's application classes directly; it is
NOT A2A, authenticated networking, process migration, or real external effects.

Every case declares its expectation in a packaged fixture
(fixtures/mobilitybench-local-smoke/cases.jsonl): `pass`, `known_gap` (with the
expected fix and the observation that would show it closed), or `gap_closed`.
Each case runs in its own temporary directory and SQLite database, so the
results do not depend on case order.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .core import (
    ID,
    SCHEMA_VERSION,
    Approval,
    Conflict,
    ContractError,
    EffectGateway,
    HandoffReceiver,
    PolicyDenied,
    SQLiteStore,
    canonical,
    digest,
    parse_json,
)
from .trust import HmacKey, issue_revocation

# v0.2: per-case isolation, fixture-declared expectations, attack-exercising gap cases.
SUITE_VERSION = "mobilitybench-local-smoke-v0.2"
CANARY = "SYNTHETIC_CANARY_DO_NOT_LOG_7R4"
FIXTURE_TEXT = "alpha beta gamma"
CASES_PATH = Path(__file__).resolve().parent / "fixtures" / "mobilitybench-local-smoke" / "cases.jsonl"
EXPECTATIONS = ("pass", "known_gap", "gap_closed")
VERDICTS = ("pass", "known_gap", "gap_closed", "fail")
_REQUIRED = {"scenario", "question_ids", "baseline", "expected", "expectation", "description"}
_OPTIONAL = {"closed_observation", "expected_fix"}

Evidence = dict[str, bool | int | str]
Evaluator = Callable[[Path], tuple[str, Evidence]]


class CaseFixtureError(ValueError):
    """The smoke's case declarations are missing, malformed or do not match the harness."""


@dataclass(frozen=True)
class Case:
    scenario: str
    question_ids: list[str]
    baseline: str
    expected: str
    observed: str
    verdict: str
    duration_ms: float | None  # None with --no-timing; never part of the outcome digest
    evidence: Evidence
    expectation: str = "pass"
    expected_fix: str | None = None
    suite_version: str = SUITE_VERSION
    contract_version: str = SCHEMA_VERSION


def envelope(suffix: str, text: str = FIXTURE_TEXT) -> dict[str, Any]:
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


def exception_outcome(fn: Callable[[], object],
                      kind: type[Exception] | tuple[type[Exception], ...]) -> tuple[str, dict[str, Any]]:
    """Capture only error *classes*: never save sensitive exception messages."""
    try:
        fn()
    except kind as exc:
        return "denied", {"denial_type": type(exc).__name__}
    return "accepted", {"denial_type": "none"}


# --------------------------------------------------------------------------- case declarations

def validate_case(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict) or not _REQUIRED <= set(case) <= _REQUIRED | _OPTIONAL:
        raise CaseFixtureError("invalid case fields")
    if not isinstance(case["scenario"], str) or not ID.fullmatch(case["scenario"]):
        raise CaseFixtureError("invalid scenario")
    name = case["scenario"]
    if (not isinstance(case["question_ids"], list) or not case["question_ids"]
            or not all(isinstance(q, str) for q in case["question_ids"])):
        raise CaseFixtureError(f"invalid question_ids in {name}")
    for key in ("baseline", "expected", "description"):
        if not isinstance(case[key], str) or not case[key]:
            raise CaseFixtureError(f"invalid {key} in {name}")
    if case["expectation"] not in EXPECTATIONS:
        raise CaseFixtureError(f"unknown expectation in {name}")
    if case["expectation"] == "pass" and set(case) & _OPTIONAL:
        raise CaseFixtureError(f"a pass case declares no fix or closed observation: {name}")
    if case["expectation"] != "pass" and not isinstance(case.get("expected_fix"), str):
        raise CaseFixtureError(f"{case['expectation']} case {name} must name its fix")
    if case["expectation"] == "known_gap" and (
            not isinstance(case.get("closed_observation"), str)
            or case["closed_observation"] == case["expected"]):
        raise CaseFixtureError(f"known_gap case {name} needs a distinct closed_observation")
    if case["expectation"] == "gap_closed" and "closed_observation" in case:
        raise CaseFixtureError(f"gap_closed case {name}: its closed observation is `expected`")
    if name not in EVALUATORS:
        raise CaseFixtureError(f"no evaluator for scenario {name}")
    return case


def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read and validate the declarations; the packaged file must cover every evaluator."""
    source = Path(path) if path is not None else CASES_PATH
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
        cases = [validate_case(parse_json(line.encode("utf-8"))) for line in lines if line.strip()]
    except (OSError, ContractError) as exc:
        raise CaseFixtureError(f"unreadable case fixture {source.name}") from exc
    names = [c["scenario"] for c in cases]
    if len(names) != len(set(names)):
        raise CaseFixtureError("duplicate scenario")
    if path is None and set(names) != set(EVALUATORS):
        raise CaseFixtureError("packaged declarations do not cover every evaluator")
    return cases


def verdict_for(case: dict[str, Any], observed: str) -> str:
    """Observed vs declared. A known gap that now shows its closed observation is
    `gap_closed`: reported separately, not a failure, and the case must be rewritten."""
    if observed == case["expected"]:
        expectation: str = case["expectation"]
        return expectation
    if case["expectation"] == "known_gap" and observed == case["closed_observation"]:
        return "gap_closed"
    return "fail"


# --------------------------------------------------------------------------- isolated evaluators
# Each evaluator receives a fresh, empty directory and builds every receiver, store and
# gateway it uses inside it. No evaluator reads state written by another case.

APPROVAL = Approval("approval-mobilitybench", "task-mobilitybench", "agent-a", "agent-b", "word_count")
REVOKED_AT = 1_792_000_000  # fixed claimed revocation time; never part of the output


def _store(workdir: Path) -> SQLiteStore:
    return SQLiteStore(workdir / "case.sqlite")


def _receiver(workdir: Path, approval: Approval = APPROVAL) -> HandoffReceiver:
    return HandoffReceiver("agent-b", _store(workdir), [approval])


def _denied(receiver: HandoffReceiver, message: dict[str, Any],
            kind: type[Exception]) -> tuple[str, dict[str, Any]]:
    return exception_outcome(lambda: receiver.receive(message), kind)


def _gateway(workdir: Path) -> tuple[EffectGateway, int]:
    gateway = EffectGateway(_store(workdir))
    return gateway, gateway.claim("effect-task", "agent-a")


def case_keep_origin_baseline(workdir: Path) -> tuple[str, Evidence]:
    count = len(FIXTURE_TEXT.split())
    return ("correct" if count == 3 else "wrong"), {"result_word_count": count}


def case_approved_local_handoff(workdir: Path) -> tuple[str, Evidence]:
    task = envelope("first")
    receipt = _receiver(workdir).receive(task)
    valid = (receipt["status"] == "completed" and not receipt["replayed"]
             and receipt["artifact"] == {"kind": "word_count", "value": 3}
             and receipt["artifact_digest"] == digest(receipt["artifact"])
             and receipt["envelope_digest"] == digest(task))
    return ("correct" if valid else "wrong"), {"artifact_verified_by_digest": valid}


def case_identical_delivery_retry(workdir: Path) -> tuple[str, Evidence]:
    receiver, task = _receiver(workdir), envelope("first")
    receiver.receive(task)
    receipt = receiver.receive(task)
    accepted = sum(1 for e in receiver.store.audit() if e["movement_id"] == task["movement_id"]
                   and e["event_type"] == "handoff.accepted")
    correct = receipt["replayed"] and accepted == 1
    return ("deduplicated" if correct else "duplicate_or_missing"), {
        "accepted_events": accepted, "receipt_marked_replayed": receipt["replayed"]}


def case_revoked_grant_blocks_new_handoff(workdir: Path) -> tuple[str, Evidence]:
    revoked = replace(APPROVAL, revoked=True)  # the same grant with its static revoked flag set
    return _denied(_receiver(workdir, revoked), envelope("revoked"), PolicyDenied)


def case_expired_grant_blocks_new_handoff(workdir: Path) -> tuple[str, Evidence]:
    expired = replace(APPROVAL, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    return _denied(_receiver(workdir, expired), envelope("expired"), PolicyDenied)


def case_incorrect_destination_claim(workdir: Path) -> tuple[str, Evidence]:
    message = envelope("wrong-destination")
    message["destination"]["agent_id"] = "agent-x"
    return _denied(_receiver(workdir), message, PolicyDenied)


def case_incorrect_origin_claim(workdir: Path) -> tuple[str, Evidence]:
    message = envelope("wrong-origin")
    message["origin"]["agent_id"] = "agent-x"
    return _denied(_receiver(workdir), message, PolicyDenied)


def case_unsupported_data_classification(workdir: Path) -> tuple[str, Evidence]:
    message = envelope("unsupported-classification")
    message["context"]["classification"] = "private"
    return _denied(_receiver(workdir), message, ContractError)


def case_unexpected_sensitive_field(workdir: Path) -> tuple[str, Evidence]:
    message = envelope("unapproved-field")
    message["api_key"] = CANARY  # Synthetic marker, not a credential.
    return _denied(_receiver(workdir), message, ContractError)


def case_synthetic_canary_absent_from_audit(workdir: Path) -> tuple[str, Evidence]:
    receiver = _receiver(workdir)
    receiver.receive(envelope("canary", "one " + CANARY + " two"))
    events = receiver.store.audit()
    leaked = CANARY in canonical(events)
    return ("redacted" if not leaked else "leaked"), {
        "canary_present_in_audit": leaked, "audit_events": len(events)}


def case_conflicting_idempotency_key(workdir: Path) -> tuple[str, Evidence]:
    receiver, task = _receiver(workdir), envelope("first")
    receiver.receive(task)
    changed = envelope("different-id")
    changed["execution"]["idempotency_key"] = task["execution"]["idempotency_key"]
    return _denied(receiver, changed, Conflict)


def case_receipt_survives_store_reopen(workdir: Path) -> tuple[str, Evidence]:
    task = envelope("first")
    _receiver(workdir).receive(task)
    restarted = HandoffReceiver("agent-b", SQLiteStore(workdir / "case.sqlite"), [APPROVAL])
    receipt = restarted.receive(task)
    return ("persisted" if receipt["replayed"] else "reexecuted"), {
        "replayed_after_reopen": receipt["replayed"]}


def case_simulated_effect_deduplication(workdir: Path) -> tuple[str, Evidence]:
    gateway, epoch = _gateway(workdir)
    first = gateway.commit("effect-task", "agent-a", epoch, "effect-1", "synthetic effect")
    again = gateway.commit("effect-task", "agent-a", epoch, "effect-1", "synthetic effect")
    correct = first and not again and gateway.reconcile("effect-task", "effect-1") == "committed"
    return ("one_simulated_commit" if correct else "unexpected_commit"), {
        "first_commit": first, "replay_committed": again}


def case_old_worker_fenced_after_transfer(workdir: Path) -> tuple[str, Evidence]:
    gateway, epoch = _gateway(workdir)
    next_epoch = gateway.transfer("effect-task", "agent-a", epoch, "agent-b")
    stale, _ = exception_outcome(
        lambda: gateway.commit("effect-task", "agent-a", epoch, "effect-2", "stale"), PolicyDenied)
    new_effect = gateway.commit("effect-task", "agent-b", next_epoch, "effect-2", "approved synthetic")
    correct = next_epoch == 2 and stale == "denied" and new_effect
    return ("stale_fenced" if correct else "unfenced"), {
        "new_epoch": next_epoch, "stale_denied": stale == "denied", "new_executor_committed": new_effect}


def case_conflicting_effect_payload(workdir: Path) -> tuple[str, Evidence]:
    gateway, epoch = _gateway(workdir)
    gateway.commit("effect-task", "agent-a", epoch, "effect-1", "synthetic effect")
    return exception_outcome(lambda: gateway.commit(
        "effect-task", "agent-a", epoch, "effect-1", "different payload"), Conflict)


def case_missing_effect_is_unknown_not_failed(workdir: Path) -> tuple[str, Evidence]:
    gateway, epoch = _gateway(workdir)
    gateway.commit("effect-task", "agent-a", epoch, "effect-1", "synthetic effect")
    return gateway.reconcile("effect-task", "not-in-ledger"), {
        "committed_effect_reconciles": gateway.reconcile("effect-task", "effect-1"),
        "local_ledger_authoritative_only": True}


def case_concurrent_effect_retries(workdir: Path) -> tuple[str, Evidence]:
    gateway, epoch = _gateway(workdir)
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(lambda _: gateway.commit(
            "effect-task", "agent-a", epoch, "effect-concurrent", "same payload"), range(12)))
    count = sum(attempts)
    return ("one_simulated_commit" if count == 1 else "duplicate_or_missing"), {
        "attempts": len(attempts), "new_commits": count}


def case_claimed_identity_is_not_authenticated(workdir: Path) -> tuple[str, Evidence]:
    """Known gap, exercised: impersonation of agent-a by a party holding no secret.

    The forger (agent-x in this script) knows only non-secret identifiers: the task
    ID, the approval reference and the two agent names. It claims origin agent-a and
    submits its own text. The core API has no caller credential to check, so this
    call is indistinguishable from agent-a's; that inability IS the gap.
    """
    receiver = _receiver(workdir)
    forged = envelope("forged-origin", "attacker chosen synthetic text")
    forged["origin"]["agent_id"] = "agent-a"  # the claim; the actual caller is agent-x
    try:
        receipt = receiver.receive(forged)
    except (PolicyDenied, ContractError) as exc:  # what a caller-authenticating receiver would do
        return "denied", {"denial_type": type(exc).__name__}
    executed = receipt["status"] == "completed" and receipt["artifact"]["value"] == 4
    attributed = receipt["origin_agent_id"] == "agent-a"
    return ("accepted_forged_origin_claim" if executed and attributed else "rejected"), {
        "credential_presented": False, "forged_task_executed": executed,
        "receipt_attributes_to_claimed_origin": attributed}


def case_grant_revocation_blocks_effect_commit(workdir: Path) -> tuple[str, Evidence]:
    """Revoke the grant mid-task at runtime, then let the executor commit its next effect.

    Rewritten after issue #38 closed the former known gap
    `grant_revocation_not_bound_to_effect_gateway` on the core path. The synthetic user
    authority revokes with a signed notice (issue #8 format) through the receiver's
    runtime API; a forged notice must be refused first.
    """
    authority = HmacKey.generate("authority-mobilitybench")  # synthetic, fresh per run
    receiver = HandoffReceiver("agent-b", _store(workdir), [APPROVAL], revocation_authorities=[authority])
    receiver.receive(envelope("before-revocation"))  # approved work starts on agent-b
    gateway = EffectGateway(receiver.store)
    epoch = gateway.claim("task-mobilitybench", "agent-b")
    impostor = HmacKey.generate(authority.kid)  # knows the authority's name, not its key
    forged, _ = exception_outcome(lambda: receiver.revoke(
        issue_revocation(impostor, APPROVAL.ref, REVOKED_AT)), PolicyDenied)
    receiver.revoke(issue_revocation(authority, APPROVAL.ref, REVOKED_AT))
    new_handoff, _ = exception_outcome(lambda: receiver.receive(envelope("after-revocation")), PolicyDenied)
    if forged != "denied" or new_handoff != "denied":
        return "revocation_not_enforced_at_receiver", {
            "forged_revocation_rejected": forged == "denied", "new_handoff_denied": new_handoff == "denied"}
    try:  # Attack: the executor keeps going and commits its next simulated effect anyway.
        committed = gateway.commit("task-mobilitybench", "agent-b", epoch,
                                   "effect-after-revocation", "synthetic effect")
    except (PolicyDenied, Conflict):
        committed = False
    return ("committed_without_grant_recheck" if committed else "rejected"), {
        "forged_revocation_rejected": True, "new_handoff_denied": True,
        "simulated_commit_after_revocation": committed}


def case_receipt_is_not_independently_authenticated(workdir: Path) -> tuple[str, Evidence]:
    """Known gap, exercised: forge a receipt and run the only offline check available."""
    receipt = _receiver(workdir).receive(envelope("unsigned-receipt"))
    if "signature" in receipt or "attestation" in receipt:
        return "signature_field_present", {"signature_or_attestation_field_present": True}
    forged = {**receipt, "artifact": {"kind": "word_count", "value": 300}}
    forged["artifact_digest"] = digest(forged["artifact"])  # unkeyed: anyone can recompute it
    passes = forged["artifact_digest"] == digest(forged["artifact"]) and forged != receipt
    return ("forged_receipt_passes_offline_check" if passes else "forgery_detected"), {
        "forged_receipt_self_consistent": passes, "signature_or_attestation_field_present": False}


EVALUATORS: dict[str, Evaluator] = {
    name[len("case_"):]: fn for name, fn in sorted(globals().items())
    if name.startswith("case_") and callable(fn)
}


# --------------------------------------------------------------------------- runner

def _run_case(case: dict[str, Any], timing: bool) -> Case:
    with tempfile.TemporaryDirectory(prefix="mobilitybench-smoke-") as directory:
        t0 = time.perf_counter_ns()
        try:
            observed, evidence = EVALUATORS[case["scenario"]](Path(directory))
            # Evidence schema is explicitly allowlisted below; payloads never enter JSONL.
            if not isinstance(evidence, dict) or any(
                not isinstance(k, str) or type(v) not in (str, int, bool)
                for k, v in evidence.items()
            ):
                raise TypeError("invalid evidence schema")
        except Exception as exc:  # noqa: BLE001 - observed research failure, not silent success
            observed, evidence = "unexpected_exception", {"exception_type": type(exc).__name__}
        elapsed = round((time.perf_counter_ns() - t0) / 1_000_000, 3) if timing else None
    return Case(case["scenario"], list(case["question_ids"]), case["baseline"], case["expected"],
                observed, verdict_for(case, observed), elapsed, evidence,
                case["expectation"], case.get("expected_fix"))


def run_suite(timing: bool = True, cases: Sequence[dict[str, Any]] | None = None,
              order: Iterable[str] | None = None) -> list[Case]:
    """Run each declared case in isolation; return results in declaration order.

    `order` (scenario names) changes only the execution order, to test that
    results do not depend on it. timing=False sets every duration_ms to None so
    that two runs serialize byte-identically. 'known_gap' means a missing control
    was reproduced by an attack, NOT a successful guard.
    """
    declared = [validate_case(c) for c in cases] if cases is not None else load_cases()
    by_name = {c["scenario"]: c for c in declared}
    if len(by_name) != len(declared):
        raise CaseFixtureError("duplicate scenario")
    sequence = list(order) if order is not None else list(by_name)
    if sorted(sequence) != sorted(by_name):
        raise ValueError("order must name every declared scenario exactly once")
    results = {name: _run_case(by_name[name], timing) for name in sequence}
    ordered = [results[c["scenario"]] for c in declared]
    # A report must never carry the synthetic marker either, even in negative cases.
    if CANARY in canonical([asdict(c) for c in ordered]):
        raise RuntimeError("Synthetic canary leaked into benchmark output")
    return ordered


def outcome_digest(cases: Iterable[Case]) -> str:
    """SHA-256 over the timing-free records: equal across runs whose outcomes match."""
    return digest([{k: v for k, v in asdict(c).items() if k != "duration_ms"} for c in cases])


def summarize(cases: list[Case]) -> dict[str, int | str]:
    return {
        "suite_version": SUITE_VERSION,
        "total": len(cases),
        **{verdict: sum(c.verdict == verdict for c in cases) for verdict in VERDICTS},
        "outcome_digest": outcome_digest(cases),
    }


def to_jsonl(cases: Iterable[Case]) -> str:
    return "".join(json.dumps(asdict(c), sort_keys=True) + "\n" for c in cases)


V01_COMMANDS = ("run", "report", "verify", "schedule")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in V01_COMMANDS:
        # MobilityBench v0.1 suite (frozen fixtures, baselines, faults); see docs/mobilitybench-v0.1.md.
        from .mobilitybench_v01 import main as v01_main
        return v01_main(argv)
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="-", help="JSONL destination; '-' = stdout")
    parser.add_argument("--no-timing", action="store_true",
                        help="write duration_ms as null so that two runs are byte-identical")
    args = parser.parse_args(argv)
    try:
        cases = run_suite(timing=not args.no_timing)
    except CaseFixtureError as exc:
        print(json.dumps({"error": "case_fixture_invalid", "detail": str(exc)}), file=sys.stderr)
        return 2
    data = to_jsonl(cases)
    if args.output == "-":
        sys.stdout.write(data)
    else:
        Path(args.output).write_text(data, encoding="utf-8")
    print(json.dumps(summarize(cases), sort_keys=True), file=sys.stderr)
    return 1 if any(c.verdict == "fail" for c in cases) else 0


if __name__ == "__main__":
    raise SystemExit(main())
