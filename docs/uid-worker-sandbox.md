# Distinct-UID synthetic worker boundary (issues #98 and #50)

**Date:** 2026-10-17. **Research experiment only.** This is a **separately privileged Linux UID + syscall-deny experiment**, not an agent platform sandbox, production key vault, filesystem namespace, arbitrary-tool firewall, trusted execution environment or proof that all agents are containable. **No user data or real effects** are used.

## Precise security claim

Under an honest **container-root test supervisor** (UID 0 *inside an ephemeral CI container*, not elevated host root), a trusted package launcher and Linux/x86_64 kernel, an attacker-controlled Python worker with a different real/effective/saved UID/GID and no supplementary groups **cannot read the specifically tested root-only files or root-parent /proc metadata, inherit the specifically protected FD, create the specifically listed socket/spawn syscalls, or commit a protected synthetic effect except by asking a trusted allowlisted task-ID pipe broker**.

This conclusion only covers the enumerated test interfaces; it does not imply every writable file, all IPC, every file descriptor, pre-existing kernel APIs, hardware/device channels or remote target has been mediated. The parent trusted callback still uses the existing signed peer grant and operator-pinned [pre-disclosure sender gate](secure-sender-gate.md); it is not a new alternative authorization truth.

## What is new

The previous [seccomp experiment](isolated-egress-lab.md) blocked selected network/spawn syscalls in a child running under the **same UID** as the trusted process. That allowed filesystem and /proc access to same-UID operator secrets. The opt-in `run_guarded_agent(..., child_uid=65534, child_gid=65534)` profile now:

1. **Refuses to start** unless the supervising process is privileged UID 0 and the requested child UID/GID are explicit and non-root. There is no silent fallback to a same-UID worker.
2. Runs only the trusted launcher module before dropping privileges. In the child, calls `setgroups([])`, `setresgid(gid,gid,gid)`, `setresuid(uid,uid,uid)` and verifies *saved* IDs as well as real/effective IDs and group list. It then applies no-new-privileges + the existing seccomp-BPF deny rules **before running any attacker Python source**.
3. Uses `python -P`, an explicit trusted package source path, `PYTHONSAFEPATH` and no user site packages. The subprocess inherits only stdin/stdout/stderr plus two named broker pipes (`pass_fds`/`close_fds`); no operator policy, signing key, SQLite connection or receiver socket descriptor is passed.
4. Limits CPU time to ten seconds, file size to 64 KiB, address space to 1 GiB and core dumps to zero in the child; parent also enforces a wall-clock timeout and kills the uncooperative worker. These are *bounded test limits* rather than complete anti-denial-of-service resource accounting.
5. The broker keeps the same strict, single `{version:1, operation:delegate, task_id}` command. Only the **trusted parent** can map a task ID to a signed peer handoff; extra policy/grant fields from the worker are not accepted, and revoked or invalid grants still fail independently at the peer receiver and simulated effect ledger.
6. Checks the actually running **legacy HTTP handoff listener**. First, an unrestricted synthetic client sends a valid unauthenticated self-claimed-origin request and the legacy receiver records accepted/completed events (the red control). Then the UID-isolated worker tries that live listener and labeled A2A/peer/tool HTTP paths. Socket creation is denied by the kernel and the legacy receiver's independently read SQLite audit remains unchanged.

The UID worker additionally attempts to read a root-only synthetic canary and the trusted peer SQLite file (in a root-only test directory), inspect the trusted parent's `/proc/PID/environ` and specifically held private file descriptor, spawn a process, create AF_INET/UDP/AF_UNIX sockets and regain UID 0. Test results must be **blocked**, not merely unobserved. A valid authorized delegation through the trusted pipe broker still commits exactly one **synthetic peer effect**. A separate negative case proves a disallowed destination produces no peer network requests, task-text disclosure or committed effect.

## Reproduce without host-root permissions

CI runs the whole experiment inside the ephemeral `python:3.13-slim` job container under its container-root supervisor; **no `sudo` is invoked on the GitHub host**. The container is not started with `--privileged`; an additional `no-new-privileges` flag is passed. The root process executes only the trusted test harness, and the actual attacker-controlled code starts after `setresuid(65534)` and seccomp. The CI job **fails**, rather than using same-UID tests, if kernel/UID/permission conditions are unavailable.

```sh
# Safe, non-privileged source checks and refusal behavior on any ordinary dev host:
python -m pytest -q tests/test_uid_worker_boundary.py

# Full privilege-separation assertions need a disposable Linux x86_64 CI job
# container that explicitly provides root supervisor + an unprivileged worker.
# See .github/workflows/uid-worker-boundary.yml.
```

`AMV_UID_EVIDENCE_DIR` is an **operator-only test output** directory: when set, the tests write sorted, deterministic `allow.json`, `deny.json` and `timeout.json` reports. These include only tested route labels, blocked/allowed outcomes, UID, broker status and independently checked effect counts; they contain **no secrets, task text, root paths, process IDs, signed grants or private keys**. The CI uploads these synthetic JSON records for seven days. A test failure invalidates the results, and a missing kernel feature fails the dedicated job.

## Evidence and exclusions

| Measured test | Expected | Independent evidence | Limitation |
| --- | --- | --- | --- |
| Distinct UID/GID and no supplementary groups | All real/effective/saved IDs become 65534; groups empty | Child reported IDs plus kernel-protected file denial | Test uses *same host/container*, not a production tenant jail |
| Direct actual legacy listener | Unfenced control succeeds; isolated child socket blocked | Receiver-owned legacy SQLite audit unchanged for child | Does not authenticate or globally disable legacy handler |
| A2A JSON-RPC and REST, peer and tool URLs | Socket creation denied from this child | Kernel `EPERM` and no new legacy audit rows | Test does **not** start every adapter at once; real-A2A positive control is in [separate adapter experiment](real-adapter-egress.md) |
| Protected file, trusted peer DB, parent /proc and protected inherited FD | `EACCES`/`EPERM`; file FD not inherited | Independent root-only canary + protected DB inspection | Other readable/writable files and inherited pipes exist |
| Process creation and root reacquisition | `EPERM` | Child syscall/credential observations | No exhaustive syscall policy / user-namespace model |
| Trusted broker positive delegate | One admitted synthetic peer effect | Trusted receiver SQLite effect ledger and captured route trace | Trusted parent remains inside the same Python process as receiver for this test |
| Trusted broker refused destination | No pre-disclosure task bytes or effect | Trusted wire/receiver inspection and child output scan | Metadata disclosure on other independent paths is not proven absent |
| Uncooperative worker | Killed by parent wall timeout, no broker commit | Protected callback invocation count remains zero | Arbitrary external side effects/remote timeouts not addressed |

### Remaining threats that prevent closure of #50

- Independent **secure-test launcher** must inventory **all enabled runtime processes/listeners**, gate direct legacy/A2A/relocation/tools, and integrate authenticated peer movement with actual independent [tool-effect service](independent-tool-effect-service.md). A caller outside this specific UID-fenced worker is not covered.
- More comprehensive filesystem/IPC confinement (Landlock/mount namespace with measured policy, symlink/race attacks, writable storage, `/proc` peer disclosure, shared/mapped memory, inherited sockets), lifecycle suspension and key custody need a separate threat assessment. A compromised root supervisor, kernel, loaded package, trust issuer, clock or effect service invalidates the experiment.
- The trusted parent can still run arbitrary code with full privileges; the worker cannot prevent the parent or a separately launched unfenced program from invoking unmediated adapters. Secure channel confidentiality is a distinct question (HPKE remains opt-in on peer delivery).
- Receipt integrity proves signatures on recorded events only, not completeness of observation or global non-occurrence of unauthorized effects. External third-party APIs and credential-bearing tools remain **out of scope**.

The [16-route source inventory](secure-test-route-inventory.md) is an accompanying *planning artifact*, not deployment enforcement. Neither this isolated-UID experiment nor that inventory is an all-route safety guarantee.

**Next work:** issue [#99](https://github.com/MSKazemi/agent-movement/issues/99) to compose operator-owned secure-profile process admission and executable real-route negative tests; umbrella [#50](https://github.com/MSKazemi/agent-movement/issues/50) remains open until its enumerated safety acceptance criteria are met together.
