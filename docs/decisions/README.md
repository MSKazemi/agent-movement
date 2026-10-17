# Architecture decisions and review status

This directory describes a lightweight **proposed** architecture-decision-record (ADR) convention. **No architecture decision is accepted merely because a file is created here.** The repository's existing README/code remain authoritative until a maintainer explicitly adopts a decision and updates relevant docs/tests.

For each independently reviewable decision, create `NNNN-short-topic.md`, with:

- **Status:** `proposed`, `accepted`, `rejected`, or `superseded`; only maintainers may mark an ADR accepted through review.
- **Date and reviewers:** date of decision and the approving review/PR link (when there is one).
- **Context and evidence:** observed implementation/test coverage, alternatives, security assumptions, source references, failure modes.
- **Decision:** one precise contract and what is in/out of scope.
- **Consequences:** migration/backward-compatibility plan, reproducibility and security impact, tests and falsification criteria.
- **Follow-up:** PR/issue, explicitly measurable exit criteria, and superseding ADR if later reversed.

## Recommended first ADRs (not yet accepted)

1. **Record the adopted north-star research mission:** [project charter](../project-charter.md) (merged PR #88) already distinguishes delegation from strict task-ownership relocation. A future ADR may document architectural implications without reopening the adopted research scope.
2. **Canonical envelope version and upgrade/downgrade semantics:** runtime `0.1.0-draft` versus proposed `0.2.0-draft` schema; no silent compatibility claims.
3. **Secure-test complete-mediation scope:** Issue #50 remains open. Use the [16-route inventory](../secure-test-route-inventory.md) and [broker-only operator profile](../secure-broker-only-profile.md) as partial inputs; neither currently proves global mediation of other processes or external tools.
4. **Benchmark evaluation protocol and identity:** deterministic tests versus preregistered held-out model-backed trials; avoid confusion with independently named MobilityBench projects.

When replacing a past decision, keep the earlier ADR for provenance and add `superseded by ADR-NNNN` rather than deleting its rationale. Do not adopt broad runtime changes through a documentation-only proposal.
