# Agent Movement paper corpus: protocol and dataset

**Snapshot:** 2026-10-16 · **Papers:** 83 (1980–2026; 75 from round 1, 8 from round 2) · **Status:** curated, metadata-verified and independently audited reading list for the research documents in this repository. It is not an exhaustive systematic review.

This corpus collects scholarly work on *agent movement*: how AI-agent work moves between agents, frameworks, models, machines and organizations without losing context, accountability or safety controls (see the [project README](../../README.md)). It complements the [news corpus](../news-corpus/README.md). The news corpus records what industry and standards bodies *announced*; this corpus records what research has *proposed, built, measured or formalized*, including the mobile-agent and process-migration literature of the 1990s and 2000s that the current wave of agent protocols tends to overlook.

| File | Purpose |
|---|---|
| [`digest.md`](digest.md) | Human-readable summaries grouped by theme, with an index |
| [`papers.jsonl`](papers.jsonl) | **Canonical dataset**, one JSON record per paper. Edit this file, not the generated ones |
| [`papers.csv`](papers.csv) | Spreadsheet view (generated) |
| [`papers.bib`](papers.bib) | biblatex entries (`@article`, `@inproceedings`, `@online` with `eprint`, `@report`) with `doi`, `url`, `urldate` (generated) |
| [`stats.json`](stats.json) | Counts by theme, decade, publication type, contribution type and operation (generated) |
| [`flow.json`](flow.json), [`excluded.jsonl`](excluded.jsonl) | Selection-flow counts and every excluded candidate, with its reason |
| [`raw/`](raw/) | Raw candidate records exactly as collected: 78 from round 1, one file per theme (`P1.jsonl`–`P6.jsonl`), and 8 from round 2 (`round2.jsonl`) |
| [`audit.jsonl`](audit.jsonl) | The independent audit verdict for each of the 75 round-1 papers, with corrections applied, plus curator entries |
| [`audit-round2.jsonl`](audit-round2.jsonl) | The independent audit verdict for each of the 8 round-2 papers (applied after `append`) |
| [`../../tools/paper_corpus.py`](../../tools/paper_corpus.py) | Validator and generator (Python standard library only) |

## 1. Research questions

- **RQ1.** What earlier research on code mobility, mobile agents and process/VM migration bears directly on moving LLM-agent work, and which of its results (taxonomies, security results, performance trade-offs) carry over?
- **RQ2.** What does current research propose for agent-to-agent communication, delegation, identity and authorization, and what has it measured?
- **RQ3.** What evidence exists on the security failure modes of agent tool use and multi-agent handoffs?
- **RQ4.** What mechanisms exist for agent memory, state, checkpointing and durable execution that a portable task context or runtime relocation could build on?

## 2. Themes

| Code | Theme |
|---|---|
| P1 | Mobile agents and agent/process migration (classic and modern) |
| P2 | Agent communication protocols and interoperability (KQML/FIPA to MCP/A2A/ANP) |
| P3 | Security of LLM agents, tool use and multi-agent handoffs |
| P4 | Agent identity, delegated authorization, accountability and governance |
| P5 | Agent memory, state, context management and durable execution |
| P6 | Multi-agent orchestration, delegation and portable agent specifications |

## 3. Eligibility criteria

**Inclusion**

1. The paper is directly relevant to at least one coded movement operation (§5) and to its theme.
2. It is a scholarly or technical publication: a journal article, conference or workshop paper, book chapter, technical report, standards-body white paper or arXiv preprint.
3. Its metadata (title, full author list in order, year, venue and DOI or arXiv ID) can be confirmed against an authoritative source: Crossref, the arXiv API, OpenReview, or the publisher's or proceedings page.

Seminal papers of any year were allowed. Preprints were allowed where clearly relevant, because much of the agent-protocol literature is from 2025–2026 and not yet published. Every record is flagged `peer_reviewed: true/false` so readers can filter.

**Exclusion**

Unverifiable metadata, schema violations, and duplicates (the same DOI or arXiv ID, or a near-identical title). Where a preprint and a published version both existed, the **published version was kept** and its arXiv ID retained.

## 4. Procedure

1. **Identification.** On 2026-10-15, six collector agents (one per theme, running in parallel) searched the web and scholarly APIs, and each returned 13 candidates. Each record stores the query that found it (`search_query`).
2. **Metadata verification.** Collectors had to take every bibliographic field from Crossref, the arXiv API, OpenReview or the publisher, and to drop any paper they could not confirm. Where a field could not be obtained (e.g. an abstract), they had to say so in `notes`. `verification_source` records which authority was used.
3. **Summaries.** Each summary is 2–4 sentences in the collector's own words, based on the abstract or paper.
4. **Screening and deduplication** (`tools/paper_corpus.py merge`). This ran schema validation, the unverified-metadata filter and deduplication by DOI, arXiv ID or title similarity (difflib ratio ≥ 0.9). On a duplicate, the peer-reviewed version was kept. There was no numeric target and no quota, so every eligible unique paper was included.
5. **Identifiers.** Round-1 papers were sorted by year and assigned `AMP-001` … `AMP-075`. Each also gets a biblatex citation key (`<first-author surname><year><first title word>`). Published IDs and cite keys are frozen: later rounds are added with `paper_corpus.py append`, which deduplicates against the existing corpus and numbers only the new papers, from the next free ID, in year order (round 2: `AMP-076` … `AMP-083`).
6. **Independent audit.** Separate auditor agents re-checked every record against the authorities (§7). Corrections were logged in `audit.jsonl` and applied by script.
7. **Round 2 (2026-10-16).** The eight candidates that round-1 collectors had verified or flagged but left out because of the per-theme cap (formerly listed in §10) were collected in `raw/round2.jsonl` and screened with `append` (§6, §7).

To reproduce the published dataset (into a fresh directory, add `--out <dir>` to each command; `make build` runs the same sequence):

```sh
python3 tools/paper_corpus.py merge docs/paper-corpus/raw/P[1-6].jsonl
python3 tools/paper_corpus.py apply-audit docs/paper-corpus/audit.jsonl
python3 tools/paper_corpus.py append docs/paper-corpus/raw/round2.jsonl --round round2
python3 tools/paper_corpus.py apply-audit docs/paper-corpus/audit-round2.jsonl
```

## 5. Data schema

| Field | Meaning |
|---|---|
| `id`, `citekey` | Stable corpus ID (`AMP-NNN`) and biblatex key |
| `theme` | `P1`…`P6` (§2) |
| `title`, `authors`, `year`, `date_published` | As given by the authority. `date_published` is `YYYY`, `YYYY-MM` or `YYYY-MM-DD` |
| `venue`, `publication_type` | Full venue name; one of `journal`, `conference`, `workshop`, `book-chapter`, `tech-report`, `whitepaper`, `preprint` |
| `peer_reviewed` | Whether the version cited went through peer review |
| `doi`, `arxiv_id`, `url` | Persistent identifiers and canonical landing page |
| `technologies` | Free-text tags |
| `movement_operations` | Multi-label, same vocabulary as the news corpus: `delegation`, `portable-context`, `runtime-relocation`, `cross-framework-migration`, `tool-access`, `identity-trust`, `observability`, `governance` |
| `contribution_type` | `system`, `empirical`, `survey`, `position`, `formal`, `benchmark`, `taxonomy` |
| `summary`, `relevance` | Paraphrased summary; why the paper matters for agent movement |
| `verified_metadata`, `verification_source` | Verification flag and authority used |
| `search_query`, `date_accessed`, `notes` | Provenance and caveats |

## 6. Selection flow

```text
Identified (6 themes × 13)                       n = 78
  ├─ excluded: schema-invalid                    n = 0
  ├─ excluded: metadata not verified             n = 0
  └─ excluded: duplicate (DOI / arXiv / title)   n = 3   (preprint and published version found in two themes)
Included                                         n = 75

Round 2 (2026-10-16): §10 candidates               n = 8   (P1 2, P3 2, P4 2, P5 1, P6 1)
  ├─ excluded: schema-invalid                    n = 0
  ├─ excluded: metadata not verified             n = 0
  └─ excluded: duplicate of corpus or round      n = 0
Included                                         n = 8   (AMP-076 … AMP-083)

Corpus total                                     n = 83
```

The 3 round-1 duplicates were Internet of Agents (P2/P6), MCP: Landscape, Security Threats… (P2/P3) and Building a Secure Agentic AI Application Leveraging A2A (P2/P3). See [`excluded.jsonl`](excluded.jsonl). In [`flow.json`](flow.json), the unprefixed keys are round-1 counts, `round2:*` keys are round-2 counts, and `included` is the corpus total.

## 7. Quality assurance

Round-1 checks were run on 2026-10-15. Every round-1 verdict and correction is in [`audit.jsonl`](audit.jsonl).

| Check | Method | Result |
|---|---|---|
| Schema and identifiers | `paper_corpus.py check`: required keys, vocabularies, DOI and arXiv syntax, year–date consistency, unique IDs, cite keys and identifiers | 75/75 valid, exit code 0 |
| Metadata | Independent auditor agents (6, in parallel) re-checked all 75 records against Crossref, the arXiv API, OpenReview, OpenAlex and publisher or proceedings pages | **10/75** needed a correction, mostly because a peer-reviewed version had appeared after the preprint: 5 newly published versions, 3 NeurIPS proceedings DOIs added, 2 dates or venues fixed |
| Peer-review status | Same audit: a search for published versions of every preprint, and a venue check for every "peer reviewed" claim | **7/75** failed. 6 flags changed: 5 preprints turned out to be published, and 1 edited-volume chapter was changed to not peer reviewed. In 1 more case (AMP-044) the flag was correct but a peer-reviewed successor had been missed |
| Summary fidelity | Same audit. A summary fails if any problem statement, method, number or named result is not supported by the abstract or paper | **7/75** failed. 4 overstated or described a different version (e.g. Mem0's accuracy relative to full-context prompting; arXiv wording kept for a published paper). 3 pre-2000 papers had no reachable abstract or full text and were marked UNVERIFIABLE. All 7 were rewritten to cautious, supported text |
| Curator re-check | Every DOI an auditor added was resolved again by the curator via the Crossref API | 7/7 matched title, venue, date and first author |
| Bibliography | `pdflatex` + `biber` with `\nocite{*}` | 75/75 entries resolved, no biber warnings, LaTeX exit code 0 |
| Reproducibility | `merge` raw → `apply-audit` into a fresh directory, then compare byte for byte | All 7 output files identical |

Six curator entries in `audit.jsonl` (`audit_pass: curator-prepublication`) do two things. They align two `technologies` lists with the published versions. They also re-key four citation keys whose year changed from 2025 to 2026 when the published version replaced the preprint. Re-keying is allowed only before first publication; after that, keys are frozen.

**Round 2 audit (2026-10-16).** A separate auditor independently re-checked the eight round-2 records (AMP-076 … AMP-083) against Crossref, arXiv, OpenAlex, PMLR, the ICLR and TMLR sites and the SIGOPS policy page. Metadata: 8/8 correct. Peer-review flag: 8/8 justified (AMP-077 is not refereed: the SIGOPS *Operating Systems Review* policy page states the newsletter's technical material is not refereed, and `notes` now cites it). Summaries: 2/8 corrected: AMP-078 overstated who usually audits deployed systems, and AMP-081 said "36 high-stakes tools" where the published ICLR version reports 36 toolkits with 311 tools. Verdicts and corrections are in [`audit-round2.jsonl`](audit-round2.jsonl). The curator re-checked the ToolEmu figure against the arXiv abstract. OpenReview, DBLP and Semantic Scholar blocked automated access, so the exact TMLR acceptance day of AMP-082 was not re-checked.

**Curator entry (2026-10-16).** AMP-007 lacked the volume editor, so its `@incollection` entry failed biber's datamodel check. The record now carries an optional `editors` field, set to Giovanni Vigna from Crossref's record for the volume (10.1007/3-540-68671-1).

| Check | Method | Result |
|---|---|---|
| Metadata | Every field taken from the primary authority: Crossref API for the four DOIs (10.1109/4434.708256, 10.1145/311124.311130, 10.1145/3351095.3372873, 10.1145/3593013.3594033); the arXiv API for all six arXiv IDs; OpenReview API for the ICLR 2024 and TMLR versions; PMLR v235 page citation tags for the ICML 2024 paper. Full author names missing from Crossref were taken from OpenAlex and the author's or a bibliography index page (cited in `notes`) | 8/8 confirmed. The published version was preferred in every case where one exists (7/8). TaskWeaver has no peer-reviewed version in Crossref, OpenAlex or OpenReview and is kept as a preprint. DBLP and Semantic Scholar refused automated requests (bot check, HTTP 429) and were not used |
| Peer-review status | Venue check for each record | 6 peer reviewed; 2 not: TaskWeaver (preprint) and Kotz & Gray (ACM SIGOPS *Operating Systems Review*, peer review not established, so flagged `false` conservatively) |
| Summary fidelity | Summaries written only from the abstract (arXiv API, OpenAlex, publisher or author page). Numbers (68.8%, 36 tools, 144 cases, 23.9%; one million agents) copied from the abstracts. No full text read | Karnik & Tripathi rests on the abstract exposed by OpenAlex; the IEEE full text was not read (noted in the record) |
| Identifiers | `append` assigns `AMP-076`+ without renumbering. The `id → title` map of AMP-001 … AMP-075 was diffed before and after, and the first 75 records of `papers.jsonl` compared byte for byte | No change |
| Schema, bibliography, reproducibility | `check`; `biber --tool --validate-datamodel`; `pdflatex` + `biber` with `\nocite{*}`; the three-step pipeline (§4) run twice into fresh directories and compared with the committed files | `ok: 83 records valid`, exit 0. biber tool mode: exit 0 with 1 warning (`sander1998protecting` has no `editor`), which is pre-existing in round 1. LaTeX: 83 entries, biber 0 warnings, exit 0. All 7 output files byte-identical |

**Tool fix found in round 2.** `merge`'s URL identity dropped the query string, so any two `openreview.net/forum?id=…` landing pages counted as the same paper. A first round-2 run wrongly excluded ToolEmu and CoALA as duplicates of Internet of Agents. The URL identity now keeps the query. Round 1 was re-run with the fix and still reproduces the committed files byte for byte.

**Interpretation.** Agent-collected bibliographic metadata was reliable: no paper was invented, and no DOI or arXiv ID pointed to the wrong work. The main metadata risk is *staleness*: 2025 preprints that have since been published. Summaries failed less often than in the news corpus (7/75 here, against 27/100 there), because abstracts are a tighter source than news pages. **Open decision:** AMP-044 (South et al., *Authenticated Delegation and Authorized AI Agents*, arXiv) has a peer-reviewed successor with a different title and author list, *Position: AI Agents Need Authenticated Delegation* (ICML 2025 position track). The preprint is kept, and the successor is recorded in `notes`.

## 8. What the literature says about agent movement (preliminary synthesis)

These are observations about **this corpus only**, with IDs referring to [`digest.md`](digest.md). They are offered as inputs to the project's [open questions](../open-questions.md), not as settled conclusions.

1. **Relocating execution is old and well studied at the lower layers.**
   - **Mobile agents:** a mobile agent was defined in the 1990s as a program that suspends on one host, transfers itself and resumes on another (AMP-012). Mobile-agent systems were built and measured (AMP-009, AMP-014).
   - **Process migration:** surveys of process migration analysed why it saw little adoption despite clear benefits (AMP-013).
   - **Live migration of state:**
     - VM live migration reported downtimes as low as 60 ms (AMP-015).
     - GPU state can be checkpointed transparently (AMP-048).
     - LLM serving live-migrates requests together with their in-memory state (AMP-035).
     - Edge systems migrate LLM agents by moving only the essential state (AMP-056).

   This suggests that the hard part of agent movement is not moving bytes within a homogeneous substrate. It is what the bytes *mean* across heterogeneous runtimes, and what happens to external effects and authority.
2. **Restoring an agent is unsafe without side-effect discipline.** ACRFence (AMP-070) shows that an agent restored from a checkpoint re-generates slightly different tool requests, which servers treat as new. The authors name two attack classes, *action replay* and *authority resurrection*. Their proposed mitigation records irreversible effects and enforces replay-or-fork semantics. Exactly-once logging for stateful serverless (AMP-023) and transactional OS state (AMP-019) are the systems foundations. Together they turn the repository's "replay-safe resumption" gap into concrete design inputs.
3. **The destination is a potential adversary, and movement is a propagation channel.**
   - **Classic results:** mobile-agent research treated the host as a threat to the agent and proposed protections (AMP-007, AMP-012).
   - **Modern multi-agent failures:**
     - Adversarial content can hijack the control flow of multi-agent frameworks into executing arbitrary code, in 58–90% of trials with GPT-4o (AMP-049).
     - Injected prompts self-replicate from agent to agent (AMP-072).
     - Injected prompts spread across RAG-connected applications like a worm (AMP-062).
     - In simulations of up to one million multimodal agents chatting in random pairs, one adversarial image placed in a single agent's memory was enough to jailbreak (almost) all of them, exponentially fast (AMP-083).

   A task envelope therefore needs integrity, provenance and untrusted-input handling at *every* hop, not just at the origin.
4. **Delegation has formal and practical foundations that agent protocols can reuse.**
   - **Formal and cryptographic foundations:**
     - Lampson et al.'s "speaks for" calculus covers delegated authority and revocation (AMP-002).
     - Macaroons give attenuable, decentralized delegation through contextual caveats (AMP-016).
   - **Agent-specific proposals:**
     - OAuth 2.0 and OpenID Connect extended with agent credentials (AMP-044, AMP-061).
     - A provider-mediated system with formally grounded access-control tokens (AMP-066).
     - PKI-backed agent discovery (AMP-052).

   Attenuation at each hop matches the repository's principle that privileges are "scoped independently at the destination".
5. **Portable representations exist for definitions, not for running state.**
   - **Precedent:** KQML separated message performatives from the content language and used facilitator agents for routing (AMP-004), much as A2A separates task messaging from payloads.
   - **Definitions across runtimes:** Agent Spec runs one declarative agent definition on four runtimes (LangGraph, CrewAI, AutoGen, WayFlow) with a shared evaluation harness (AMP-059). This is the strongest evidence in the corpus for cross-framework migration, but it moves *definitions*. DSPy makes pipelines declarative and compilable (AMP-030).
   - **Running state:** no paper in this corpus proposes *and evaluates* the transfer of a running agent's checkpoint between unrelated frameworks.
6. **Handoffs fail in measurable ways.** MAST (AMP-042) catalogs 14 failure modes of multi-agent LLM systems in three categories, including inter-agent misalignment and task verification. This offers a ready-made coding scheme for evaluating whether a moved task arrives intact.

## 9. Limitations

- **Not exhaustive.** Thirteen candidates per theme, plus the eight round-2 additions, is a reading list, not a census.
- **Round 2 audit scope.** Round 2 had one independent auditor, like round 1, but some sources (OpenReview, DBLP, Semantic Scholar) were not reachable by automated access (§7).
- **Agent-assisted collection and audit.** Collectors and auditors were AI agents working under fixed rules. Metadata comes from authoritative APIs, but summaries can still mis-state a paper. Read the paper before citing a specific result.
- **Abstract availability.** For several pre-2000 papers, publishers do not expose abstracts to APIs. Those summaries were checked against whatever text was reachable and kept deliberately general (see `notes` and `audit.jsonl`).
- **Preprint volatility.** 2025–2026 preprints may change between versions. The record cites the version current on 2026-10-15; check arXiv for later versions.
- **Coding subjectivity.** `movement_operations` and `contribution_type` were assigned by collectors, not double-coded. Treat counts as indicative.

## 10. Candidates noted but not included

All eight candidates listed here after round 1 were added in round 2 (AMP-076 … AMP-083). Open items for a next round:
- South et al., *Position: AI Agents Need Authenticated Delegation* (ICML 2025 position track): the peer-reviewed successor of AMP-044 (open decision, §7).
- Round 2 found no further eligible candidates. It saw only earlier versions of papers it added, which are not separate candidates: Kotz & Gray's *Mobile Code: The Future of the Internet* (the version AMP-077 revises, per the author's page) and the NeurIPS 2023 FMDM workshop version of ToolEmu (AMP-081).

## 11. How to cite and update

- Cite the **paper** via its entry in [`papers.bib`](papers.bib) (biblatex + biber). Entries carry the DOI and/or arXiv `eprint`, and a `note` marks papers that are not peer reviewed.
- To add papers, put the new raw records in a new file under `raw/` and run `python3 tools/paper_corpus.py append raw/<file>.jsonl --round <name>`. It screens and deduplicates them against the corpus, numbers them from the next free `AMP-NNN`, records the round in `flow.json`, and rebuilds. Existing IDs and cite keys never change. Then run `check`. Never re-run `merge` on the published directory: it renumbers from `AMP-001`.
