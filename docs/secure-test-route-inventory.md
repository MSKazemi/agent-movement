# Secure-test route inventory — preliminary, **not** a launcher

**Date:** 2026-10-17 · **Parent [#99](https://github.com/MSKazemi/agent-movement/issues/99), [#50](https://github.com/MSKazemi/agent-movement/issues/50).**

**Status: source-linked inventory and fail-closed planning checks only.** No single supervisor yet disables all forbidden listeners or instruments every permitted one. The fact that a route appears as `gated_candidate` is **not proof** it is protected in the same run as another candidate. **All-path policy remains unproven.**

## Audited list and terminology

The [machine-readable inventory](../data/secure-route-inventory.csv) enumerates **16 entry points or sink categories** with a concrete implementation/source anchor (for present routes), transport/protection semantics, proposed secure-test policy, known vulnerability/boundary, existing related test and tracking issue.

- `must_disable`: currently unmediated, non-authenticated, or incompatible with the proposed secure-test profile. A future **operator-owned supervisor** must demonstrate this route is NOT listening/callable for the protected task, with an explicit test against the actual endpoint. A Python `if` or imported module list does not disable another OS process.
- `gated_candidate`: this route has some existing signing/SQLite/kernel boundary for a **specific opt-in test path**, but must pass separate admission, enablement and independently observed effect checks before the proposed secure-profile launcher may allow it.
- `out_of_scope`: arbitrary independent tools or an independent optional service, **not** counted as denied, contained or safe. If enabled by a test deployment later, inventory and reclassify before admitting a protected task.

The test [`test_secure_route_inventory.py`](../tests/test_secure_route_inventory.py) fails on removed/duplicated rows, nonexistent sources/tests, changed source anchors or an attempt to silently promote the known direct legacy HTTP, A2A, low-level effect gateway, relocation or unified CLI routes into the protected profile. This is a **static registry mutation red control**, not the runtime gate-removal control required to close #99.

## Which boundaries remain actually absent

| Exposure | What is observed in source/tests | Not proven |
| --- | --- | --- |
| Legacy `POST /v0/handoffs` | Loopback syntactic handoff; sender ID claim under preconfigured approval; real listener positive control in [PR #100 research](real-adapter-egress.md) | Authenticated sender or protected-profile suppression for all processes |
| A2A JSON-RPC and REST bindings | Official SDK paths allow pure delegation but do not authenticate agent ID; separate listeners available | Signed identity or secure-launcher disabling of both routes |
| Peer preflight/delivery | Signed origin descriptor/grant, continuity checks on opt-in receiver; sender `OutboundGate` is independent opt-in | A globally enforced egress/no-disclosure gate across all clients or late-side channels |
| Peer effect ledger | A guarded-enrolled task refuses bare peer effect path under same SQLite lock | Same enforcement for unenrolled tasks and all third-party effect sinks |
| Core + Guarded SQLite effect gates | Correct *local* epoch/policy subsets when explicitly enrolled | All operation categories or arbitrary DB writers; independently privileged host process |
| Relocation | Separate pinned checkpoint runtime, own coordinator and tool ledger | Safe integration into every guard policy; generic cross-host atomicity |
| Linux seccomp child | Narrow syscall/socket/spawn fence on a particular Linux/x86_64 process | Distinct UID, filesystem/FD/`/proc` isolation, network namespace, covert channels |
| Independent synthetic tool service | Merged [PR #106](https://github.com/MSKazemi/agent-movement/pull/106) added a separate loopback signed effect sink and dedicated SQLite ledger | Integrated enablement/egress restrictions for every protected task; distinct UID and filesystem isolation; guaranteed delivery of revocation to tool |

A **pre-disclosure denial**, **metadata-disclosed rejection**, **task-content-disclosed but effect refused**, and **committed protected effect** are distinct observables. Future tests must record those independently and never turn a zero-effect audit into a claim that task bytes did not leave the process.

## Concrete next phase for #99

1. Build one **operator-owned, explicit, versioned launcher configuration** naming enabled process/route identities, pinned issuers/grants/policy, allowed destination/capability and trusted source/sink DBs. It must reject unknown route names.
2. Start only the verified peer/guarded/tool-side subset and **prove other real endpoints are unreachable** while the launcher owns the test profile, not just stubbed at Python import.
3. Run actual direct requests against legacy `/v0/handoffs` and official A2A JSON-RPC + REST bindings in a **red** control with no isolation and a **green** bounded control with independently enforced route disabling. Include an arbitrary custom HTTP binding probe.
4. Attempt misuse from an attacker-controlled separate unprivileged process with [#98](https://github.com/MSKazemi/agent-movement/issues/98) host isolation and [#102](https://github.com/MSKazemi/agent-movement/issues/102) independent effect service, including stale/revoked/expired grants and pre-disclosure canary absence. Classify `blocked`, `observed-allowed`, `attempted-but-unobserved`, and `unsupported` separately.
5. Exercise **runtime gate mutation**: deliberate re-enablement of an unmediated listener MUST cause the acceptance suite to fail by an independently observed illegal accepted handoff/effect, not just a CSV change.
6. Keep #99 open until all specified conditions hold and the accepted secure-profile scope is published. Keep #50 open until its broader independent OS and effect-path dependencies hold.

## Reproduce this preliminary artifact

```sh
python -m pytest -q tests/test_secure_route_inventory.py
python -m pytest -q tests/test_real_adapter_egress.py
```

The second suite has optional A2A/OS dependencies; an unavailable A2A test is `UNSUPPORTED`, never evidence that the adapter is secure or disabled. The new inventory has no credentials, payload content, real actions, network calls or model inference. The static test only reads local repository sources.
