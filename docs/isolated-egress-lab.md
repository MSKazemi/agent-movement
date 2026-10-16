# Independent-process agent egress experiment: v0.1

**Date:** 2026-10-16. **Status:** Synthetic Linux/x86_64 bypass experiment. This is an explicitly bounded **OS-enforced network and spawn syscall restriction**, not production containment, arbitrary agent confinement, or assurance for third-party runtimes. Work toward issue #50, not a closure claim.

## Research question

Can an attacker-controlled, separate Python process bypass the existing authorization gateway by using raw sockets, alternate HTTP routes or subprocess creation? What happens if the process can instead request one narrow delegated synthetic task from a separately controlled, trusted parent?

The prior receiver already verifies signed user grants and, in opted-in mode, independent principal approvals at preflight, delivery and inside the SQLite transaction for a simulated effect. Those checks do not prevent an untrusted **separate** process with generic network access from calling an unrelated service. This experiment exercises that missing process/network boundary.

## Architecture and explicit security boundary

- **Trusted supervisor (parent process):** owns the synthetic user/agent signing keys, SQLite store, `PeerClient` and `PeerReceiver`. It receives one bounded JSON command per attacker process via dedicated inherited anonymous pipe descriptors; it does **not** expose a generic HTTP proxy, network forwarder, arbitrary tool name, supplied grant, or task text to the child. Only the exact schema `{version: 1, operation: "delegate", task_id: "task-1"}` (with an independently provisioned mapping of allowed task IDs to trusted callbacks) may dispatch a task. Every other operation, unknown task, extra field, duplicate key or malformed message is refused. Real peer authority checks still run in the parent.
- **Untrusted attacker (different OS process):** the trusted bootstrap calls `prctl(PR_SET_NO_NEW_PRIVS)` and installs an **irreversible kernel seccomp-BPF filter before running attacker code**. The filter rejects x86_64 networking/socket syscalls (including direct raw `socket(2)`), `fork`/`clone`/`exec*`, `io_uring` and several cross-process access syscalls with `EPERM`. An unexpected architecture or x32 ABI is killed rather than silently accepted. The child receives no parent agent keys or SQLite path through the broker interface, only a small allowlisted environment and two pipe FDs.
- **Independent loopback observer:** a separate trusted TCP listener records whether any attacker-generated connection reaches it. A deliberately **unfenced baseline** connects successfully first; the isolated attacker then exercises TCP, UDP, IPv6, Unix sockets, direct syscall invocation and HTTP patterns labeled `legacy_http` and `a2a_http`. The latter labels indicate attempted generic HTTP egress, **not** an invocation of actual A2A/legacy adapters. The listener reports zero additional accepted connections for the fenced child.

The parent callback is either a deliberately synthetic stub (for deterministic JSON reporting) or, in the integration tests, a real `Rig.handoff()` through the previously authenticated `PeerClient` and continuity-enforced `PeerReceiver`. Test code asserts that actual SQLite simulated effects are committed only after a valid delegated movement and are absent for missing or revoked consent. Tests distinguish pre-disclosure denial from revocation after delivery: **after-delivery denial does not undo already transmitted task bytes**.

## Run (audited platform only)

~~~sh
python -m pytest -q tests/test_isolated_egress.py
python -m agent_movement.egress_experiment --output /tmp/isolated-egress.json
cmp /tmp/isolated-egress.json docs/isolated-egress-results.json
~~~

The report is deterministic: 16 cases consisting of **nine prohibited network/process mechanisms**, one admitted broker delegation, three denied broker requests, one deliberately unfenced control, one independent listener-count check and one effect-count check. The version-pinned expected report is [isolated-egress-results.json](isolated-egress-results.json). CI requires two runs to be byte-identical and equal to the committed report, while a separate full pytest run exercises the real peer and revocation path.

**Important:** If Linux/x86_64 seccomp support or installation is unavailable, this demonstration **fails**, rather than disabling the filter and returning success. Other platforms are not in its evidence scope and their generic test jobs may skip the isolation-specific tests.

## What these experiments DO and DO NOT establish

**Evidence supported:** With this specific kernel filter installed before attacker source runs, the measured socket/spawn syscall attempts return `EPERM`, no additional loopback connection reaches the external observer, and a limited broker can run or refuse named synthetic delegations by invoking existing authenticated checks in the trusted parent. A red/green unfenced control verifies the observer would notice a reachable route without the policy.

**Outside the claim:**

- **Filesystem and device access are not confined.** The filter is a **denylist**, not a complete seccomp allowlist, mount namespace, Landlock or capability-drop mechanism. The child inherits the test runner's Unix UID and read permissions. Same-UID `/proc` inspection, preexisting file handles, filesystem writes, inherited privileged FDs, device IO and new unmodeled syscall families are not proven blocked.
- **Stdout/stderr are writable pipes to the test runner.** The test runner must not relay arbitrary attacker output to external tools or logs containing secrets. No real secrets or user data may be passed to this experiment.
- **No side-channel, covert channel, denial-of-service or privileged-host protection.** A compromised host/kernel, same-UID access to parent resources, malicious native code, hostile runtime, arbitrary code with broader OS privileges or an authority issuer compromise can break the assumptions.
- **No effect-side enforcement beyond the tested broker and existing simulated SQLite gateway.** Legacy `http.py`, A2A, relocation, external effect providers and unrelated processes are **not** disabled globally. The proposed worker-side OS profile cannot guarantee what another service reachable from the host will do.
- **Broker grants are test fixtures, not credentials.** The attacker cannot supply its own private agent key, sign a new user grant, or force an arbitrary task through the pipe; the trusted callback chooses the synthetic operation.
- **No production isolation guarantee or global agent erasure.** Real deployment requires a differently privileged supervisor, separate user/UID and filesystem namespace, readonly root, robust allowed-FD audit, full syscall policy, network namespace/firewall evidence, authenticated provisioning, resource limits, multi-host testing and independently verified external tool-side authorization.

## Research follow-ups

1. Implement an **independently configured and differently privileged** supervisor, readonly filesystem/mount namespace and ephemeral task directory, with explicit allowed FDs, identity/secret isolation and resource quotas. Verify unsupported kernel features fail closed.
2. In a network namespace, deny arbitrary destinations through a host-owned firewall, and allow only a separately authenticated broker endpoint; test direct legacy/A2A server access from the attack process as real targets, not merely path labels.
3. Validate authorized handoff through an unprivileged child and separate real process receiver, and preserve receipt evidence when the worker crashes or disappears mid-commit.
4. Add adaptive attack cases, coverage of non-socket exfiltration/storage/IPC, deny-versus-unobserved distinction, and formally documented attacker capabilities. An absent observation is not evidence of no attempted action.
5. Only after those controls and independent effect-side tests exist should issue #50 be considered for closure. Never generalize a synthetic result to production safety.
