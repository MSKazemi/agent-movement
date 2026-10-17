"""Operator-provisioned broker-only secure *test* profile (issue #99).

This is an explicit launcher for one fenced worker and an allowlisted trusted
pipe broker. It does NOT start or authenticate independent peer/legacy/A2A
listeners, contain arbitrary processes, or constitute a global tool gateway.
No production credentials, real tools or private content may be used.
"""

from __future__ import annotations

import csv
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import ContractError
from .egress_lab import SandboxResult, run_guarded_agent

_PROFILE_VERSION = "amv-broker-only-secure-test-v1"
_REQUIRED_ROUTES = frozenset({
    "legacy_handoff_http", "legacy_revocation_http", "peer_card",
    "peer_preflight", "peer_delivery", "peer_revocation",
    "peer_simulated_effect", "legacy_effect_gateway",
    "guarded_effect_gateway", "a2a_jsonrpc", "a2a_rest",
    "relocation_coordinator", "unified_cli", "egress_child",
    "generic_unmediated_tools", "independent_tool_pilot",
})
# Enabled means only *the trusted parent* may call these peer operations
# through its one-task pipe broker. The child cannot create sockets.
# This is not evidence that a receiver is safe if run by another process.
_BROKER_ROUTES = frozenset({"egress_child", "peer_card", "peer_preflight", "peer_delivery"})
_MUST_DISABLE = frozenset({
    "legacy_handoff_http", "legacy_revocation_http", "legacy_effect_gateway",
    "a2a_jsonrpc", "a2a_rest", "relocation_coordinator", "unified_cli",
})
_OUT_OF_SCOPE = frozenset({"generic_unmediated_tools"})
_IDENT = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_FIELDS = frozenset({"schema", "worker_uid", "worker_gid", "allowed_task_ids", "enabled_routes"})
_ROOT = Path(__file__).resolve().parents[2]


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    if len(pairs) != len({k for k, _ in pairs}):
        raise ContractError("duplicated operator profile key")
    return dict(pairs)


def _source_route_inventory(path: Path) -> None:
    """Fail closed if the reviewed entrypoint inventory or its classification changed."""
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            records = list(csv.DictReader(stream))
    except (OSError, UnicodeError) as exc:
        raise ContractError("source-linked route inventory unavailable") from exc
    ids = [row.get("route_id") for row in records]
    if len(ids) != len(_REQUIRED_ROUTES) or set(ids) != _REQUIRED_ROUTES:
        raise ContractError("unknown/duplicated/missing protected route inventory")
    classification = {row["route_id"]: row["proposed_secure_test_policy"] for row in records}
    # A planning-registry edit must never silently promote a known unmediated
    # listener or external plugin into a reachable operator profile.
    for route in _REQUIRED_ROUTES:
        expected = ("must_disable" if route in _MUST_DISABLE
                    else "out_of_scope" if route in _OUT_OF_SCOPE
                    else "gated_candidate")
        if classification[route] != expected:
            raise ContractError("operator route profile changed without review")


@dataclass(frozen=True)
class BrokerOnlyProfile:
    """Trusted operator's immutable selection of one real worker identity and broker tasks."""

    worker_uid: int
    worker_gid: int
    task_ids: frozenset[str]
    enabled_routes: frozenset[str]

    def __post_init__(self) -> None:
        # Even construction outside the owner-only loader cannot expand the
        # allowed routes or silently remove the non-root worker requirement.
        if (type(self.worker_uid) is not int or type(self.worker_gid) is not int
                or not 1 <= self.worker_uid <= 65534
                or not 1 <= self.worker_gid <= 65534
                or type(self.task_ids) is not frozenset or not self.task_ids
                or any(not isinstance(t, str) or not _IDENT.fullmatch(t) for t in self.task_ids)
                or type(self.enabled_routes) is not frozenset
                or self.enabled_routes != _BROKER_ROUTES):
            raise ContractError("unreviewed broker-only profile construction")

    def run(
        self, script: Path, trusted_handlers: Mapping[str, Callable[[], str]], *,
        probe_port: int, operation: str = "delegate", task_id: str = "task-1",
        timeout: float = 15.0,
    ) -> SandboxResult:
        """Run only the enumerated, strict single-task synthetic broker/UID worker.

        The parent must separately bind handlers to signed peer + consent
        policy; the untrusted child never chooses them, grants or destinations.
        The UID/secure-syscall fence fails closed if Linux root authority is
        unavailable; no fallback to a weaker local Python client is offered.
        """
        _source_route_inventory(_ROOT / "data" / "secure-route-inventory.csv")
        if set(trusted_handlers) != self.task_ids or not all(callable(f) for f in trusted_handlers.values()):
            raise ContractError("trusted broker tasks must exactly match operator allowlist")
        if type(probe_port) is not int or not 1 <= probe_port < 65536:
            raise ContractError("invalid loopback probe port")
        if type(timeout) not in (int, float) or not 0 < timeout <= 30:
            raise ContractError("invalid synthetic worker timeout")
        return run_guarded_agent(
            script, trusted_handlers, operation=operation, task_id=task_id,
            probe_port=probe_port, timeout=float(timeout),
            child_uid=self.worker_uid, child_gid=self.worker_gid,
        )


def load_operator_profile(path: Path) -> BrokerOnlyProfile:
    """Owner-only, non-symlink, bounded operator manifest; never from agent HTTP.

    The launcher runs as container root. A principal that can write the
    manifest or invoke callbacks with root privileges is an explicit trust
    assumption, not an adversarial worker.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ContractError("operator-owned profile missing or unsafe") from exc
    try:
        meta = os.fstat(fd)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                or meta.st_mode & 0o077 or not 0 < meta.st_size <= 8192):
            raise ContractError("operator profile must be owner-only regular file")
        raw = os.read(fd, 8193)
        if len(raw) != meta.st_size:
            raise ContractError("operator profile changed while loading")
    finally:
        os.close(fd)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ContractError("invalid operator profile JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _FIELDS or payload["schema"] != _PROFILE_VERSION:
        raise ContractError("unsupported operator profile schema")
    uid, gid = payload["worker_uid"], payload["worker_gid"]
    if (type(uid) is not int or type(gid) is not int
            or not 1 <= uid <= 65534 or not 1 <= gid <= 65534):
        raise ContractError("worker identity must be non-root UID/GID")
    tasks, routes = payload["allowed_task_ids"], payload["enabled_routes"]
    if (not isinstance(tasks, list) or not tasks
            or any(not isinstance(t, str) or not _IDENT.fullmatch(t) for t in tasks)
            or len(set(tasks)) != len(tasks)):
        raise ContractError("invalid or duplicate operator task ID")
    if (not isinstance(routes, list) or any(not isinstance(r, str) for r in routes)
            or len(routes) != len(set(routes)) or frozenset(routes) != _BROKER_ROUTES):
        raise ContractError("profile must allow only reviewed broker+peer route subset")
    _source_route_inventory(_ROOT / "data" / "secure-route-inventory.csv")
    return BrokerOnlyProfile(uid, gid, frozenset(tasks), frozenset(routes))
