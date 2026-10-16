# Actual alternative-adapter reachability test (bounded)

**Date:** 2026-10-16. **Status:** local synthetic negative experiment for [issue #50](https://github.com/MSKazemi/agent-movement/issues/50). This is **not** an all-path policy-enforcement feature, security certification, remote authorization or production containment guarantee.

## Why this separate test exists

The [Linux egress experiment](isolated-egress-lab.md) has synthetic HTTP labels but uses one simple observer, **not the actual legacy or A2A listeners**. The current opt-in [sender gate](secure-sender-gate.md) protects only the official authenticated peer-client method. The legacy HTTP and A2A implementations run independently, without that sender gate, and have intentionally limited identity semantics.

This experiment closes only that **test-target realism** gap:

1. Start a real `http.make_server` legacy handoff listener on loopback with a synthetic approval. Show an **unfenced positive control**: a matching *self-declared* origin envelope yields a completed pure word-count handoff. This is a **demonstration of an unmediated alternative handler**, not proof of authorization.
2. On a supported Linux/x86_64 host, run the existing **separate attacker process** with seccomp restrictions and one trusted pipe-only broker. A new synthetic probe sends requests to the **real path names** `/v0/handoffs`, `/a2a/jsonrpc` and `/v0/preflight`, using the actual listener's port. Assert each socket attempt returns `EPERM`, and that an **independent read of the listener's durable audit** is unchanged.
3. If optional A2A dependencies are installed, start the **actual A2A SDK server** in its own process, complete a separate synthetic A2A delegation as a positive control, then aim the same fenced attacker process at the real A2A server port and assert no new completed movement in its SQLite audit. Skip this additional variant when the extra/ABI is unavailable; a skip is **not** evidence of enforcement.

The sample request bodies contain **only synthetic/public data** and no real tools, tokens or external host names. The client cannot select a new network destination through the pipe broker; the trusted parent owns the runnable task mapping.

## Reproduce

```sh
python -m pytest -q tests/test_real_adapter_egress.py
# For the real A2A listener, install the optional extra:
python -m pip install -e '.[a2a]'
python -m pytest -q tests/test_real_adapter_egress.py
```

The extra A2A test runs only where the tested Linux seccomp ABI exists and the adapter is installed. The legacy positive control is valid on all normal Python platforms.

## Claim boundary

- **Observed:** The real legacy receiver accepts a narrowly shaped unauthenticated handoff under its existing local approval; a separate kernel-fenced child cannot establish new connections to tested live listeners; independent SQLite audits record no extra completed handoffs.
- **Not established:** That a third party cannot invoke legacy/A2A outside the fenced child, that all processes/ports are mediated, that a different-UID/mount/file/IPC escape is prevented, that an A2A policy can safely authorize arbitrary agents, or that real third-party side effects are blocked.
- **Important:** An `EPERM` proves socket-creation denial for this process and kernel ABI, **not that an adapter has an authentication rule**. Legacy/A2A are still reachable by unfenced code running outside the experimental process boundary.
- **Egress, disclosure and effect are distinct:** A `blocked` socket attempt means no network request reached this tested destination *through that call*. A request denied **after** payload delivery may still disclose task text; a zero-effect result is not a no-disclosure result.

**Remaining P0 work:** an operator-owned secure-profile supervisor that inventories/mediates **every enabled** ingress and egress route; real adapter requests with independent trust checks (or explicit disabling); process isolation beyond the tested denylist; and an independently controlled *effect service* with its own policy check and failure oracle. See [issue #50](https://github.com/MSKazemi/agent-movement/issues/50) and [the roadmap](roadmap.md).
