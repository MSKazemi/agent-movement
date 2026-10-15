# Open questions and research agenda (2026-10-15)

These are **unresolved**. Priorities reflect a proposed research strategy.

| Priority | Question | Why it matters | Minimum test |
|---|---|---|---|
| P0 | Is the product about task delegation, checkpoint relocation, or both? | Defines the promise and protocol boundary | Write concrete acceptance tests for each |
| P0 | What is an agent's *identity* across copy, handoff and relocation? | Audit, authentication and duplicate prevention | Assign and trace agent/run/task identities |
| P0 | Who owns a task after delegation? | Revocation, authorization and responsibility | Simulate cancellation and contested ownership |
| P0 | What context is safe and lawful to transfer? | Privacy, IP, prompt injection | Data-classification and redaction tests |
| P0 | What is the smallest portable state? | Avoid nonportable runtime internals | Resume using explicit app checkpoint only |
| P0 | How are tool permissions re-issued? | Prevent privilege escalation | Use audience-bound expiring grants, deny fallback |
| P0 | How to handle ambiguous timeouts and duplicates? | Prevent repeated external effects | Crash between side effect and acknowledgement |
| P0 | How is recipient trust established? | Agent-card spoofing / supply chain | Verify allowlist, endpoint identity, signing policy |
| P1 | What must compatibility negotiation contain? | Honest cross-framework guarantees | Deliberately incompatible adapter test |
| P1 | How are artifacts addressed and retained? | Reliability and data governance | Expiring, integrity-checked artifact retrieval |
| P1 | How are costs and budgets enforced? | Production feasibility | Measure token, tool, network and runtime cost |
| P1 | What do users see and approve? | User control | Show a permission/transfer diff before dispatch |
| P1 | How do traces cross trust domains? | Debugging without leakage | Redacted end-to-end correlation |
| P1 | Can movement happen offline or cross-cloud? | Deployment scope | Reconcile queued and delayed handoffs |
| P1 | What happens after credential revocation? | Containment | Revoke mid-run and assert no new tool action |
| P2 | When should an agent be replicated vs moved? | Efficient parallelism | Compare worker fanout with a single relocated task |
| P2 | Does multi-agent coordination improve success? | Real value vs overhead | Matched workload baseline |
| P2 | Should there be a marketplace/registry? | Discovery / governance | Threat-model registry poisoning first |
| P2 | What is a meaningful standardization claim? | Scope and adoption | Publish minimal versioned spec plus conformance suite |

## Definitional distinctions worth formalizing

- **Copy:** create a new instance from agent definition, not necessarily same logical identity.
- **Replication:** run equivalent instances for redundancy; state consistency is not automatic.
- **Multiplication:** scale out many agents for parallel tasks; requires coordinator and budget.
- **Movement:** transfer work and optionally compatible checkpoint between execution locations.
- **Delegation:** origin retains oversight while recipient performs work.
- **Full migration:** usually infeasible to promise across unrelated model providers/runtime architectures.

## Empirical research questions

1. Does A2A delegation increase cross-framework completion compared with bespoke integration?
2. What fraction of state can be reconstructed portably on two chosen frameworks?
3. What failure-injection scenarios cause duplicate irreversible operations?
4. What sensitive data crosses boundaries under default vs strict policy?
5. What is the overhead of traces, envelopes, policy checks and checkpoint storage?

Report methodology, dataset provenance, versions, raw measurements and failures—not just success demos.
