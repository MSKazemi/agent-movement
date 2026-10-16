# Changelog

All notable changes to this repository are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the `agent_movement`
package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html) while it is
pre-1.0 (minor versions may change behaviour).

**Scope of every release:** a research prototype. All code is synthetic, localhost-only and
LLM-free; it is **not production software**, not a new agent protocol and not a rival to
A2A or MCP. Benchmark results come from small frozen synthetic suites and carry no
statistical claims.

## [Unreleased]

## [0.2.0] - 2026-10-16

First tagged release. It integrates the localhost prototype stack, five movement
prototypes, MobilityBench v0.1 and v0.2, and the research and corpus work into one
gated tree.

### Added — prototype (`src/agent_movement`)

- **Localhost handoff with durable receipts and fenced synthetic effects** (PR #6), with
  review fixes: malformed input answers 400/500 instead of dropping the connection, stalled
  bodies time out, and the SQLite WAL switch honours the busy timeout.
- **Optional A2A v1 adapter** on the official `a2a-sdk` (extra `a2a`): two processes, the
  JSON-RPC and HTTP+JSON bindings, a strict agent-movement profile, and audit correlation.
  It proves delegation, not migration (#7).
  - A resolvable profile-extension spec, with a server-generated `contextId` by default
    (#18, PR #60).
  - A2A TCK conformance run and a JavaScript `@a2a-js/sdk` interop client, with the
    remaining failures documented as deviations D1–D5 (#28, PR #69).
- **Peer authentication before disclosure** (extra `ed25519`): signed agent cards from a
  test CA, scoped grants, a metadata-only preflight and a commit-time grant recheck (#8).
  - HPKE-sealed delivery to the receiver's signed card key (extra `hpke`), so an on-path
    relay sees only ciphertext (#19, PR #62).
  - Per-sender idempotency keys, with an in-place store migration, and counted
    single-use grants (`max_uses`) (#29, PR #72).
- **Same-runtime checkpoint relocation** on pinned LangGraph (extra `relocation`), with a
  30-row crash, duplicate and version fault matrix (#9).
  - A two-store mode that copies the checkpoint as a digest-verified bundle, with an
    11-row copy fault matrix (#20, PR #66).
  - Operator reconciliation for parked effects whose outcome is unknown
    (`confirmed_done` or `confirmed_absent`), fenced by the ownership epoch and audited
    (#30, PR #74).
- **Signed movement receipts and an offline forensic verifier** (extra `signing`): JCS-subset
  canonicalization, per-issuer replay detection and evidence grades (#11).
  - Out-of-band trust anchors are required, every fixture's exit code is asserted, and
    test canaries are seed-derived (#21, PR #61).
  - Opt-in signed receipts from the live HTTP path (`demo --receipts`), and verification
    of signed revocation notices (#32, PR #70).
- **Runtime revocation API** for the localhost receiver: `POST /v0/revocations`, effective
  at admission and rechecked at effect commit (#38, PR #77).
- **Data retention:** keyed (HMAC) store commitments in place of unsalted content digests,
  store layout v2, and an audited `agent-movement purge --older-than`, with a written policy
  (#39, PR #75).
- **Unified `agent-movement` CLI** (`demo`, `a2a-demo`, `peer-demo`, `relocate`, `bench`,
  `receipts`, `purge`, `version`), with a CLI reference checked against the live `--help`
  output (#41, PR #64).

### Added — MobilityBench

- **v0.1:** 18 frozen synthetic tasks with ground truth, a SHA-256 release manifest,
  negative fixtures and a CLI (#10).
  - Five scored modes: keep, restart, local delegate, A2A delegate and checkpoint relocate.
    The last two are gated on optional extras, and unavailable modes are recorded
    explicitly (#31, PR #68).
- **v0.2:** a new frozen release with mid-step crash and partition faults, and a
  `restart_stable_ids` baseline. v0.1 stays byte-identical (#40, PR #78).
- **20-case human-impact smoke:** fixture-declared expectations, isolated cases and
  byte-identical timing-free output (#22, PR #58).

### Added — research and documentation

- **Positioning and agendas:**
  - scientific agenda and MobilityBench protocol (PR #4);
  - 2031 frontier agenda (PR #13);
  - language and SDK strategy proposal (PR #3);
  - a single positioning statement used across README, both agendas and CITATION.cff
    (#44, PR #55).
- **Protocols and standards:**
  - protocols and networks guide (PR #5);
  - Agent Skills, AGENTS.md and browser/computer-use comparison (#24, PR #48);
  - standards and protocol version tracker;
  - one canonical handoff envelope (0.2.0-draft), with a JSON Schema and tests of the doc
    examples (#33, PR #59).
- **Security:**
  - threat model for unnoticed movement (PR #12);
  - agent communication policy (PR #15);
  - OWASP Agentic Top 10 (ASI01–ASI10) mapping (#23, PR #52);
  - cross-agent prompt-injection synthesis (#35, PR #51);
  - claim-level corrections (#25, PR #54).
- **Evaluation:** evaluation plan for tasks EV-A/B/C, including a non-agent baseline (#26,
  PR #56), and an economic-value methodology (#36, PR #49).
- **Reference and design:**
  - glossary, with the 13 cross-document terminology inconsistencies resolved (#45, PR #53);
  - question and study ID scheme with a crosswalk (#34, PR #65);
  - as-built architecture and developer guide (#46, PR #79);
  - agent lifecycle and liveness notes;
  - device compatibility matrix;
  - agent forensics research.
- **Doc syncs after the code landed:** a SECURITY.md note that private reporting is enabled (PR #63),
  per-sender idempotency keys and counted grants (PR #73), the five MobilityBench modes and
  operator reconciliation (PR #76), and runtime revocation, keyed retention and MobilityBench v0.2
  across the security, architecture, development and evaluation docs (PR #81).
- **Community and citation:** SECURITY.md (private vulnerability reporting is enabled),
  CONTRIBUTING.md, issue and PR templates (#27, PR #57, PR #63), and CITATION.cff with a
  how-to-cite guide.

### Added — corpora

- **News corpus:** 100 dated, fetch-verified news items, with a protocol, an independent
  audit and BibTeX.
- **Paper corpus:** 83 metadata-verified scholarly papers (rounds 1 and 2, AMP-001…083),
  with an independent audit, stable IDs and BibTeX.
- **Analysis:** a corpus timeline and coverage analysis, an evidence map of open questions
  against the corpora, and link-health and Wayback availability QA.

### Added — quality gates and CI

- **Make targets:** `make all` runs the corpus checks, byte-identical corpus rebuilds and
  analysis regeneration, pytest, strict biber, and:
  - `check-ids` (#34);
  - `check-tests-registry`, backed by a test registry (#43, PR #67);
  - `sources`, which requires every external URL to be indexed with access dates
    (#37, PR #71);
  - `lint` (ruff) and `typecheck` (mypy `--strict`) (#42, PR #80).
- **CI workflows:**
  - corpus gates;
  - `agent_movement` core (Python 3.11/3.13/3.15) and extras (Python 3.11/3.13) jobs;
  - docs link check;
  - optional A2A interop;
  - static checks;
  - a pinned gitleaks scan, with an allowlist for known false positives.

### Changed

- **Python version:** `requires-python` is now `>=3.11`, since 3.10 reached end of life.
- **Tests:** they run under pytest; README and docs report real test counts and commands.
- **README:** status line is now "research-stage; experimental synthetic local prototypes,
  not production".
- **Issue #1:** the research snapshot was fact-checked and refreshed. For example, MCP's
  current revision is 2026-07-28, and "excessive agency" is an OWASP LLM Top 10 item, not
  an Agentic one.

### Security

- **Closed gaps:**
  - peer delivery confidentiality (#19);
  - out-of-band receipt trust anchors (#21);
  - grant recheck at effect commit on the peer path (#8) and on the core path (#38);
  - unsalted content digests at rest (#39).
- **Known limits** (documented in the respective docs):
  - the core receiver does not authenticate senders;
  - there is no TLS or channel binding;
  - there is no forward secrecy for HPKE delivery;
  - coordinator and relocation fencing assume a single host.

[Unreleased]: https://github.com/MSKazemi/agent-movement/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MSKazemi/agent-movement/releases/tag/v0.2.0
