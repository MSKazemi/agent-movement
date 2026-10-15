# Local mobility proof of concept (2026-10-15)

**Status:** Tested experimental software. **Not A2A-compatible; not cross-framework migration; not production-secure.** This first executable slice implements only a small, synthetic, local, out-of-process delegation and a separate simulated fenced-effect experiment.

## Why start here?

The existing docs describe movement, replication, state transfer, security and device requirements, but do not contain a runnable reference. The first falsifiable claim is intentionally narrow: *an origin process can request a preapproved pure task from a receiver process on loopback, obtain a reproducible artifact receipt, reject unapproved requests, and replay the same delivery without executing the task again*. A separate test checks that a durable SQLite fencing epoch protects **a cooperative, simulated effect gateway** from stale executors.

This is an experimental application profile. It is NOT a substitute for [A2A v1.0](https://a2a-protocol.org/v1.0.0/specification/) and deliberately does not advertise A2A Agent Cards or protocol compatibility. The [official Python SDK](https://github.com/a2aproject/a2a-python) is the recommended follow-on integration.

## Run locally

Requires Python 3.10+ and no runtime dependencies. From the repository root:

~~~sh
python -m pip install -e .
python -m agent_movement.demo
python -m unittest discover -s tests -v
~~~

The demo starts an ephemeral localhost-only HTTP receiver as a **separate operating-system process** (`agent-b`), sends from `agent-a`, repeats the same request, tries a denied approval, and tests a stale-worker fenced commit. All task data are synthetic; SQLite is stored in a temporary directory and removed afterward. Output includes a completed word count, replay detection, HTTP 403 denial, and a successful new-epoch simulated commit. The process exiting cleans up only the demo's own child process and temp data.

For manual testing in another terminal, run `python -m agent_movement.http --db /tmp/agent-movement-demo.sqlite --port 0`. It prints the actual loopback port on stdout. **Do not run behind a public proxy or forward this port.** The receiver allows exactly one sample task reference (`demo-task`), one origin claim (`agent-a`), and one task type by default. Its policy entry expires after ten minutes.

## Contract, failure handling and evidence

- `src/agent_movement/core.py`: strict `0.1.0-draft` typed JSON envelope, allowlisted task kinds (`word_count`, `sha256`), UTF-8 size bounds and unsupported/extra-field denial. This is not a normative standard.
- `HandoffReceiver`: validates the destination claim and a receiver-local scoped `Approval` before performing an **allowlisted, pure** text calculation. Agent IDs are **claims, not authenticated workload principals**.
- `SQLiteStore`: transactional deduplication by operation idempotency key and movement ID, atomic result/receipt persistence, and audit events containing only IDs and digests (no raw task text). Concurrent exact retries are answered with `replayed: true`.
- `EffectGateway`: separate simulated ownership table with monotonically increasing epochs; an old worker cannot commit after a transfer because the gateway checks the epoch in the same SQLite transaction as its effect record. This is **not** an exactly-once guarantee for third-party tools, nor an actual runtime checkpoint.
- `HTTP` boundary: loopback-only, intentionally simple HTTP+JSON, with input validation and bounded sizes. It does **not** provide TLS, sender authentication, signature verification or user identity proof. Do not expose across trust domains.
- `demo.py`: end-to-end out-of-process experiment; no model API keys, third-party accounts, browser sessions or physical devices involved.

A receipt includes transfer identifiers, a content digest, a deterministic result artifact/digest, and a caller-supplied trace correlation ID. This receipt itself is unsigned, so it must not be described as cryptographic proof of an agent's identity or behavior. Its digests are unsalted and cover the task text. A separate experiment, [signed movement receipts](movement-receipts.md), adds Ed25519-signed receipts over salted commitments, independent tool-side records and an offline verifier with synthetic fixtures. A signature still does not make a statement true.

## What the tests establish

The committed unit/integration tests cover: structural contract validation, duplicate JSON keys, rejected task kinds/classifications, wrong/expired/revoked approvals, serial and concurrent replay safety, receipt persistence after re-opening a DB, conflicting reuse of operation/movement identifiers, local HTTP status codes, epoch fencing after ownership transfer, and concurrent duplicate simulated effects.

**Scope limit:** There is no injected coordinator crash matrix, real cross-machine run, A2A interoperability check, model continuation measurement, tool authorization boundary outside the simulated gateway, or verified production-security claim.

## Next engineering and scientific issues (ordered)

1. **Real A2A v1 integration:** build an opt-in official-SDK adapter and independent sender/receiver, pin supported SDK and spec versions, test against the A2A inspector and a second implementation. Keep the transfer application profile separate from A2A message framing.
2. **Pre-disclosure authorization:** authenticate peer identity, verify recipient and authority *before transmitting task content*, negotiate capabilities, issue expiring audience-bound approvals, and enforce revocation at the action boundary. Local untrusted agent_id strings are insufficient.
3. **True same-runtime checkpoint relocation:** integrate one pinned durable agent runtime (e.g. LangGraph), specify safe checkpoint boundaries, transfer task ownership and continue on a second worker; persist and reconcile out-of-band effects.
4. **Fault injection:** kill origin, receiver and coordinator at every state transition; add delayed acknowledgements, lost replies, forged recipients, partitions, cancellation and external effect states marked `unknown/reconcile` rather than assuming failure.
5. **MobilityBench:** publish versioned synthetic datasets, the keep/restart/delegate/relocate baselines, per-run quality/cost/safety measures, reproducible seed manifests and negative findings; align with the companion [research strategy PR](https://github.com/MSKazemi/agent-movement/pull/4).
6. **Independent forensics and evidence:** signed/verified transfer receipts, an audited event-store design, independent tool-side attestations and redaction/retention tests before claiming provenance assurance.

## Source, licensing and contribution notes

No open-source license has been selected for the repository. Adding Python package metadata does not grant rights to third parties. No secrets or user-specific private information should be committed; only synthetic/public experiments belong here. Research descriptions and current implementation support are intentionally distinguished.

References: [A2A specification](https://a2a-protocol.org/v1.0.0/specification/), [A2A Python SDK](https://github.com/a2aproject/a2a-python), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [SQLite atomic transactions](https://www.sqlite.org/lang_transaction.html).
