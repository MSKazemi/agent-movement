"""Operator CLI for parked effects whose outcome is unknown (issue #30).

    python -m pip install -e '.[relocation]'
    python -m agent_movement.relocation_reconcile example --dir DIR [--crash after|before] [--two-store]
    python -m agent_movement.relocation_reconcile list --authority DIR/coordinator.sqlite [--task T]
    python -m agent_movement.relocation_reconcile decide --authority F --task T --effect E \\
        --decision confirmed_done|confirmed_absent --operator ID --reason TEXT --epoch N
    python -m agent_movement.relocation_reconcile resume --authority F --task T --worker W \\
        --incarnation N --epoch N [--store W.sqlite]
    python -m agent_movement.relocation_reconcile log --authority F [--task T]

The same commands run as ``agent-movement relocate reconcile ...`` and
``python -m agent_movement.relocation_demo reconcile ...``.
``--authority`` is the coordinator file (in single-store mode also the checkpoint store);
``--store`` is the resuming worker's own store in two-store mode.

``decide`` records the operator's claim; it does not check it. The coordinator fences it
by the ownership epoch the operator inspected and appends it to an audit log, but it
trusts the operator's out-of-band check of the external system: a wrong decision loses
(false ``confirmed_done``) or duplicates (false ``confirmed_absent``) the effect.

Exit codes: 0 done, or an idempotent replay of the same decision; 1 denied (stale epoch,
already resolved differently, not parked, retry budget exhausted, not the owner);
2 usage error, invalid input or missing optional extra.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from .core import Conflict, ContractError, PolicyDenied

PROG = "python -m agent_movement.relocation_reconcile"
CRASH_POINTS = {"after": "effect_commit.after", "before": "effect_commit.before"}


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def build_parser(prog: str = PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog, description="Resolve parked effects whose outcome is unknown (operator reconciliation). "
                               "The decision is fenced by the ownership epoch and audited, not verified.")
    commands = parser.add_subparsers(dest="command", required=True)

    def authority(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--authority", required=True, type=Path,
                         help="coordinator SQLite file (owners, epochs, reconciliation records)")

    listing = commands.add_parser("list", help="list parked effects and their decisions (JSON)")
    authority(listing)
    listing.add_argument("--task", help="only this logical task ID")

    decide = commands.add_parser("decide", help="record confirmed_done or confirmed_absent for a parked effect")
    authority(decide)
    decide.add_argument("--task", required=True, help="logical task ID")
    decide.add_argument("--effect", required=True, help="parked effect ID")
    decide.add_argument("--decision", required=True, choices=("confirmed_done", "confirmed_absent"),
                        help="confirmed_done: continue without re-execution; confirmed_absent: retry once "
                             "under a new effect ID")
    decide.add_argument("--operator", required=True, help="operator identity recorded in the audit log")
    decide.add_argument("--reason", required=True, help="why (evidence of the out-of-band check), <= 512 bytes")
    decide.add_argument("--epoch", required=True, type=int,
                        help="ownership epoch the operator inspected; denied if the task has moved on")

    resume = commands.add_parser("resume", help="the owning worker continues the task after a decision")
    authority(resume)
    resume.add_argument("--task", required=True, help="logical task ID")
    resume.add_argument("--worker", required=True, help="worker ID of the current owner, e.g. worker-b")
    resume.add_argument("--incarnation", required=True, type=int, help="incarnation of the current owner")
    resume.add_argument("--epoch", required=True, type=int, help="current ownership epoch")
    resume.add_argument("--store", type=Path, help="the worker's own store (two-store mode only)")

    log = commands.add_parser("log", help="print the append-only reconciliation audit log (JSON)")
    authority(log)
    log.add_argument("--task", help="only this logical task ID")

    example = commands.add_parser("example", help="create a synthetic parked task to try the commands on")
    example.add_argument("--dir", required=True, type=Path, help="new or empty directory for the SQLite files")
    example.add_argument("--crash", choices=sorted(CRASH_POINTS), default="after",
                         help="crash the receiver after (row C14, default) or before (row C13) the opaque call")
    example.add_argument("--two-store", action="store_true", help="one store per worker (bundle copy)")
    return parser


def _example(options: argparse.Namespace) -> dict[str, Any]:
    """Replay row C13/C14 into ``--dir`` (forked actors) and print the follow-up commands."""
    if not hasattr(os, "fork"):
        raise ContractError("example needs os.fork (Linux/macOS)")
    root = options.dir
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ContractError(f"--dir must be a new or empty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    from . import relocation_demo_reconcile as rec
    from .relocation_demo import EFFECT_ID, TASK, Run
    from .relocation_demo_two_store import TwoStoreRun
    run = (TwoStoreRun if options.two_store else Run)(str(root), "example", "opaque")
    obs = rec.park(run, CRASH_POINTS[options.crash])
    owner = obs["owner"]
    worker, incarnation = owner["execution_id"].rsplit(".", 1)
    authority, q = shlex.quote(run.path), shlex.quote
    store = f" --store {q(run.stores[worker])}" if isinstance(run, TwoStoreRun) else ""
    truth = rec.out_of_band_check(obs, EFFECT_ID)
    decision = "confirmed_done" if truth == "done" else "confirmed_absent"
    return {
        "authority": run.path, "task": TASK, "effect": EFFECT_ID, "owner": owner,
        "status": obs["values"]["status"], "stores": getattr(run, "stores", None), "steps": run.steps,
        "simulated_out_of_band_check": {"opaque_calls": obs["opaque_calls_by_effect"].get(EFFECT_ID, 0),
                                        "true_decision": decision},
        "next": [
            f"{PROG} list --authority {authority}",
            (f"{PROG} decide --authority {authority} --task {TASK} --effect {EFFECT_ID} --decision {decision} "
             f"--operator ops-alice --reason 'checked the external system' --epoch {owner['epoch']}"),
            (f"{PROG} resume --authority {authority} --task {TASK} --worker {worker} "
             f"--incarnation {incarnation} --epoch {owner['epoch']}{store}"),
            f"{PROG} log --authority {authority}",
        ],
    }


def run_command(options: argparse.Namespace) -> Any:
    from . import relocation
    if options.command == "example":
        return _example(options)
    if not options.authority.is_file():
        raise ContractError(f"no coordinator file at {options.authority}")
    coordinator = relocation.Coordinator(options.authority)
    if options.command == "list":
        return coordinator.parked_effects(options.task)
    if options.command == "log":
        return coordinator.reconciliation_events(options.task)
    if options.command == "decide":
        return coordinator.reconcile(options.task, options.effect, options.decision, operator=options.operator,
                                     reason=options.reason, epoch=options.epoch)
    worker = relocation.Worker(options.authority, options.worker, options.incarnation, store=options.store)
    return worker.attach(options.task, options.epoch).resume_reconciled()


def main(argv: list[str] | None = None, prog: str = PROG) -> int:
    options = build_parser(prog).parse_args(argv)
    try:
        from . import relocation  # noqa: F401 - only to report a missing optional extra cleanly
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        result = run_command(options)
    except (PolicyDenied, Conflict) as exc:
        print(f"denied ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
