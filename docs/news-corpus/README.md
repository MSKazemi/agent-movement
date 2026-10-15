# Agent Movement news corpus: protocol and dataset

**Snapshot:** 2026-10-15 · **Items:** 100 · **Status:** curated evidence base for the research documents in this repository. It is not a systematic review of the scholarly literature.

This corpus records dated, publicly reported **events** (releases, announcements, incidents, standards actions, regulatory steps and press analysis) relevant to *agent movement*: how AI-agent work moves between agents, frameworks, models, machines and organizations without losing context, accountability or safety controls (see the [project README](../../README.md)). Each item has a structured record, a paraphrased summary, coded attributes and a citable reference.

| File | Purpose |
|---|---|
| [`digest.md`](digest.md) | Human-readable summaries, grouped by theme, with a chronological index |
| [`news.jsonl`](news.jsonl) | **Canonical dataset**, one JSON record per item. Edit this file, not the generated ones |
| [`news.csv`](news.csv) | Spreadsheet view (generated) |
| [`news.bib`](news.bib) | biblatex `@online` references with `urldate` (generated) |
| [`stats.json`](stats.json) | Descriptive counts by theme, year, source type, operation and technology (generated) |
| [`flow.json`](flow.json) | Selection-flow counts: identified, excluded and included |
| [`excluded.jsonl`](excluded.jsonl) | Every screened-out candidate, with its exclusion reason |
| [`raw/`](raw/) | The 126 raw candidate records exactly as collected, one file per theme (input to `merge`) |
| [`screening.json`](screening.json) | The curator's event-level duplicate decisions, with reasons |
| [`audit.jsonl`](audit.jsonl) | The independent audit verdict for each of the 100 records, with corrections applied |
| [`../../tools/news_corpus.py`](../../tools/news_corpus.py) | Validator and generator (Python standard library only) |

## 1. Research questions

- **RQ1.** Which protocols, platforms and standards relevant to agent delegation, context portability, relocation and cross-framework migration were publicly launched or changed between January 2024 and October 2026?
- **RQ2.** Which security, identity and governance developments constrain how agent work may cross runtime and organizational boundaries?
- **RQ3.** Which of the four movement operations in this repository (delegation, portable context, runtime relocation, cross-framework migration) do industry and standards activity actually address, and which remain unaddressed?

## 2. Scope and themes

The search was split into seven themes so it could run in parallel. Each theme maps to a layer in [the research landscape](../research-landscape.md):

| Code | Theme |
|---|---|
| T1 | Agent-to-agent protocols and multi-agent interoperability (A2A, ACP, ANP, AGNTCY, agent discovery) |
| T2 | Model Context Protocol (MCP) ecosystem: specification releases, adoption, registry, governance, security incidents |
| T3 | Security, identity, authorization and trust for agents and delegated agent actions |
| T4 | Durable execution, checkpointing, state, memory and context portability |
| T5 | Agent runtimes, platforms, hosting and cross-framework portability |
| T6 | Standards bodies, governance, regulation and observability (incl. OpenTelemetry GenAI) |
| T7 | Agent-to-user and agentic-commerce protocols, and cross-organization delegated actions |

## 3. Eligibility criteria

**Inclusion**

1. Publication date between **2024-01-01 and 2026-10-15**. Items from 2025–2026 were prioritized.
2. The item reports a **datable event, release, finding or incident**. Examples: a news article, a press release, an official project or vendor blog post announcing a release, a standards-body announcement, research news, or dated analysis in the technology press.
3. The item is substantively relevant to at least one coded movement operation (§5).
4. The URL resolves to the item, and its title, publisher and date can be confirmed.

**Exclusion**

1. Undated or evergreen material: specification pages, product documentation, tutorials, marketing landing pages.
2. Duplicate coverage of the same event. The primary source is kept; secondary coverage is kept only when it adds independent information.
3. Records that fail schema validation (§5).
4. Unverified records, when enough verified records exist to reach the target.

## 4. Search and verification procedure

1. **Identification.** Seven independent search agents (one per theme, run in parallel on 2026-10-15) ran multiple web-search queries and returned up to 18 candidates each. Every record stores the query that found it in `search_query`, so the search can be audited and repeated.
2. **Verification.** Each candidate URL was fetched to confirm that the page exists and to check its headline, publisher, author and publication date. `verified_fetch` records the outcome. When a page blocked automated fetching but search results confirmed the item, the record is kept with `verified_fetch: false` and an explanatory `notes` entry.
3. **Summarization.** Summaries are paraphrased (2–4 sentences) rather than quoted. Statements from vendors about their own products are written as claims ("X says …") and coded `claim_status: vendor-claim`.
4. **Screening and selection** (`tools/news_corpus.py merge`). The script runs these steps in order:
   1. Schema validation.
   2. Deduplication by normalized URL and by near-identical headline (difflib ratio ≥ 0.9). The higher-ranked record is kept, by the order in the next step.
   3. Ranking within each theme: verified before unverified, primary before secondary, then newest first.
   4. **Theme-balanced round-robin selection** up to the target (100), so that no single theme dominates.

   The selection is deterministic: the same inputs always produce the same corpus. Audit corrections (step 6) are applied afterwards, so to reproduce the published `news.jsonl`, run `merge` and then `apply-audit docs/news-corpus/audit.jsonl`.
5. **Identifiers.** Included items are sorted by date and assigned stable IDs `AMN-001` … `AMN-100`. Each also gets a biblatex citation key (`<publisher><year><first-title-word>`).
6. **Independent audit.** Separate auditor agents re-fetched every included record and checked its headline, publisher, date, summary claims and claim status against the source. Corrections were logged and applied by script (§7).

## 5. Data schema and coding vocabulary

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable corpus ID, `AMN-NNN` |
| `citekey` | string | biblatex key in `news.bib` |
| `theme` | `T1`…`T7` | Search theme (§2) |
| `title` | string | Headline as published |
| `publisher` | string | Outlet or organization |
| `authors` | list | Bylined authors; empty if none is listed |
| `date_published` | `YYYY-MM-DD` or `YYYY-MM` | Publication date as stated by the source |
| `url` | URL | Canonical address |
| `date_accessed` | date | Date the record was retrieved |
| `source_type` | enum | `news-article`, `press-release`, `official-blog`, `standards-announcement`, `research-news`, `analysis` |
| `primary_source` | bool | Whether the organization that made the announcement published it |
| `technologies` | list | Free-text technology tags (A2A, MCP, …) |
| `movement_operations` | list (enum) | `delegation`, `portable-context`, `runtime-relocation`, `cross-framework-migration`, `tool-access`, `identity-trust`, `observability`, `governance` |
| `summary` | string | Paraphrased factual summary |
| `relevance` | string | Why the item matters to agent-movement research |
| `claim_status` | enum | `fact` (independently reported or self-evident event), `vendor-claim`, `analysis`, `incident` |
| `verified_fetch` | bool | Whether the page was fetched and its metadata confirmed |
| `search_query` | string | Query that surfaced the item |
| `notes` | string | Caveats: verification gaps, paywalls, date ambiguities |

The first four `movement_operations` codes correspond to the four operations in the project README. The other four code the supporting layers: tools, trust, observability and governance.

## 6. Selection flow

Snapshot 2026-10-15. Reproduce with:
`python3 tools/news_corpus.py merge docs/news-corpus/raw/T[1-7].jsonl --target 100 --manual docs/news-corpus/screening.json`

```text
Identified via web search (7 themes × 18)            n = 126
  ├─ excluded: schema-invalid                        n = 0
  ├─ excluded: manual event-level screening          n = 2   (screening.json)
  ├─ excluded: duplicate URL / near-identical title  n = 11
Eligible unique events                               n = 113
  ├─ excluded: unverified                            n = 0   (all 113 verified by fetch)
  └─ excluded: over target (reserve set)             n = 13
Included                                             n = 100
```

The fetch-verified raw records are kept in [`raw/`](raw/) exactly as the search agents returned them. All 26 exclusions are listed with reasons in [`excluded.jsonl`](excluded.jsonl).

**Manual screening.** Two pairs reported the same event from different URLs, which the automatic deduplication cannot detect. In each pair the curator kept one record, giving the reason in [`screening.json`](screening.json): A2A joining the AAIF, and the formation of the AAIF.

**Reserve set.** Thirteen eligible items fell below the per-theme cut. Ten of them are secondary sources, which the ranking places after primary sources. They are fully coded and can be promoted. Note that the ranking's recency tie-break pushed out some landmark secondary reports, such as TechCrunch on OpenAI adopting MCP (2025-03-26) and the EchoLeak coverage (2025-06-11). The reserve set is:

| Theme | Date | Item |
|---|---|---|
| T1 | 2025-05-07 | ServiceNow Launches AI Control Tower and AI Agent Fabric (destinationCRM) |
| T1 | 2025-06-07 | Introducing ANS: DNS-Inspired Secure Discovery for AI Agents (InfoQ) |
| T2 | 2025-03-26 | OpenAI adopts rival Anthropic's standard for connecting AI models to data (TechCrunch) |
| T2 | 2025-06-18 | Asana's AI feature data-leakage incident (The Register) |
| T3 | 2025-04-21 | Agent In the Middle: abusing A2A agent cards (LevelBlue SpiderLabs) |
| T3 | 2025-05-19 | Microsoft extends Zero Trust to secure the agentic workforce: Entra Agent ID (Microsoft) |
| T3 | 2025-06-11 | Critical flaw in Microsoft Copilot could have allowed zero-click attack: EchoLeak (Cybersecurity Dive) |
| T4 | 2025-04-10 | ChatGPT memory upgrade references full chat history (Decrypt) |
| T4 | 2025-10-28 | Mem0 raises $24M (TechCrunch) |
| T4 | 2026-02-17 | Temporal raises $300M (SiliconANGLE) |
| T5 | 2025-03-12 | OpenAI reveals Responses API, Agents SDK (SD Times) |
| T5 | 2025-03-17 | Meet Kagent, open-source framework for AI agents in Kubernetes (The New Stack) |
| T7 | 2025-10-07 | OpenAI expands ChatGPT with embedded apps and developer SDK (National CIO Review) |

## 7. Quality assurance

All checks were run on 2026-10-15. Every audit verdict and correction is recorded in [`audit.jsonl`](audit.jsonl) and applied with `tools/news_corpus.py apply-audit`, so each change to a collected record can be traced.

| Check | Method | Result |
|---|---|---|
| Schema and vocabulary | `news_corpus.py check` (required keys, controlled vocabularies, date format and window, unique IDs, cite keys and URLs) | 100/100 valid, exit code 0 |
| Link resolution | `curl -L` with a browser user agent, all 100 URLs | 97 returned HTTP 200. Three (Visa, Keysight, Retail Insight Network) block automated clients; all three resolved with a second fetcher (see next row) |
| Metadata accuracy | Independent re-fetch by auditor agents that did not collect the records. Pass 1: a random sample of 12 (seed 20261015) plus the 3 link failures. Pass 2: the remaining 85 | Title, publisher and date correct in **100/100** records |
| Summary fidelity | Same audit. A summary fails if *any* number, name, version, venue, product status or mechanism is not supported by the source page | **27/100** summaries contained at least one unsupported detail. All 27 were rewritten to keep only supported claims |
| Other field corrections | Same audit | 8 URLs canonicalized after redirects, 5 author lists completed, 8 `notes` corrected, 1 `claim_status` changed to `vendor-claim` |
| Bibliography | `pdflatex` + `biber` with `\nocite{*}` on `news.bib` | 100/100 entries resolved, no biber warnings, LaTeX exit code 0 |

**Interpretation.** Collector errors were overstatements, not fabrications: no record had a non-existent source or a wrong headline, publisher or date. The errors were details such as an announcement "at re:Invent" that the page did not mention, a stated aim reported as an achieved result, a missing "preview" qualifier, or an added sentence ("X disputed the findings") that was not in the source. A 27% rate of detail errors before audit is the main reason to cite the **original source**, not the summary. The audit was also carried out by AI agents, although independent ones. Have a human check a record against its source before relying on a specific number or quotation from it.

## 8. Preliminary observations

These are descriptive observations about **this corpus only**, offered as hypotheses for the project's [open questions](../open-questions.md). They are not claims about the whole field. IDs refer to [`digest.md`](digest.md). Coded counts are multi-label: one item can carry several operations.

1. **Delegation and tool-access protocols consolidated under one governance home.**
   - MCP was launched (AMN-001) and A2A was announced (AMN-005).
   - A2A moved to the Linux Foundation (AMN-014), absorbed IBM's ACP (AMN-028) and reached v1.0 (AMN-071).
   - The Agentic AI Foundation was formed (AMN-056) and A2A then joined it (AMN-091).

   This supports the repository's framing of A2A as the **delegation** layer and MCP as the **tool-access** layer, now with neutral governance.
2. **Runtime relocation ships as durable execution *within* a single platform.** Of the 25 items coded `runtime-relocation`, those describing a concrete mechanism all describe checkpoint/resume inside one runtime:
   - LangGraph (AMN-011, AMN-045) and Temporal (AMN-022)
   - Lambda durable functions (AMN-055) and DBOS (AMN-077)
   - Cloudflare Durable Objects (AMN-080) and Vercel Workflow (AMN-046)
   - AgentCore harness (AMN-086) and Kubernetes Agent Sandbox (AMN-073)

   No item in the corpus reports a cross-vendor checkpoint interchange format. The closest candidates portably serialize agent *definitions* or agent *state*:
   - Letta's Agent File (AMN-004)
   - Oracle Agent Spec with AG-UI (AMN-060)
   - Agents distributed through OCI registries by cagent (AMN-031)

   This is consistent with the repository's claim that relocation across unrelated frameworks remains unsolved.
3. **Long-running task semantics are moving into the protocols.**
   - MCP added experimental Tasks (AMN-053), put them on its roadmap (AMN-069, AMN-092) and made the 2026-07-28 revision stateless per request (AMN-088).
   - A2A v1.0 provides polling, streaming and webhook delivery (AMN-071).
   - At IETF 126 the agentproto BoF supported working on interoperability. Participants rejected the initial scope by 38–124 and proposed reframing it around **context propagation across trust boundaries** (AMN-087), which is close to this project's "portable task envelope".
4. **Consumer context portability is user-mediated.** The memory-import tools for Claude and Gemini (AMN-068, AMN-075) rely on the user copying a generated text prompt or summary between assistants, or uploading an export archive. They are not a machine-readable interchange protocol. For Claude, the corpus has only secondary reporting of how the import works.
5. **Trust is the most frequently coded concern** (`identity-trust` on 57 of 100 items).
   - **Attacks on discovery and handoff:** reported attacks target exactly the surfaces movement depends on: agent session smuggling (AMN-047), cross-agent prompt injection via discovery (AMN-052) and agent-card poisoning (AMN-072).
   - **Standards and products:** NIST (AMN-062, AMN-065, AMN-066), OWASP (AMN-057), the OpenID Foundation (AMN-040) and CoSAI's delegation work (AMN-093) are converging on agent identity and delegated authority. Identity products have reached general availability (AMN-025, AMN-051, AMN-098).
6. **Cross-organization agent action is contested in practice.** Examples are the Amazon v. Perplexity litigation (AMN-048, AMN-070, AMN-089) and the dispute over undeclared crawlers (AMN-024). Commerce protocols encode verifiable user authorization and agent identity explicitly:

- Signed user mandates in AP2 (AMN-030)
- Scoped payment tokens in the Agentic Commerce Protocol (AMN-036)
- HTTP-message-signature agent identity in Visa TAP (AMN-042)
- Well-known capability manifests in UCP (AMN-061)

This suggests that a verifiable agent identity and user mandate are becoming preconditions for agents acting across organizational boundaries.

## 9. Limitations and threats to validity

- **Search-engine and recency bias.** Web search ranks recent and popular sources higher. Coverage of non-English sources, academic venues and small projects is therefore weak.
- **Vendor-source bias.** Much primary information about agent protocols is published by vendors themselves. These records are coded `vendor-claim`; none of their performance, adoption or security claims were independently tested.
- **Theme quotas.** Balancing across themes shapes the corpus. Counts by theme reflect the design, not the relative volume of news.
- **Agent-assisted collection.** Records were collected by AI search agents under a fixed protocol, validated by script and audited by independent AI agents. Automated extraction can still mis-state a detail. Cite the original source, not the summary, in any publication.
- **Link rot.** Web pages change or disappear. `date_accessed` records the snapshot date. Archive important URLs (for example in the Wayback Machine) before citing them in a paper.
- **Not a systematic review.** This corpus follows PRISMA-style transparency (stated criteria, logged exclusions, flow counts) but does not claim exhaustive coverage.

## 10. How to cite and reuse

- Cite the **original item**, using its entry in [`news.bib`](news.bib), e.g. `\cite{<citekey>}` with biblatex + biber. Every entry includes `url` and `urldate`.
- To refer to the corpus itself: *Seyedkazemi Ardebili, M. (2026). Agent Movement news corpus, snapshot 2026-10-15. https://github.com/MSKazemi/agent-movement/tree/main/docs/news-corpus*.

## 11. How to update the corpus

1. Add or correct records in `news.jsonl`, keeping the schema. New items take the next free `AMN-NNN` ID. Existing IDs are never renumbered.
2. Run `python3 tools/news_corpus.py check` (validation; exits non-zero on error), then `python3 tools/news_corpus.py build` (regenerates the CSV, BibTeX, digest and stats).
3. For a new collection round, save raw theme files and run `merge … --out <new-dir>`. `merge` assigns IDs from `AMN-001`, so never point it at this directory. Append the screened new records to `news.jsonl` with the next free IDs, then `build`. Record the date, queries and flow counts in a new snapshot section of this README.
