# Question and study ID crosswalk

**Created:** 2026-10-16 ([issue #34](https://github.com/MSKazemi/agent-movement/issues/34))  
**Status:** Naming convention for the research agenda documents, plus an editorial mapping of duplicated questions. The mapping is the author's **analysis**, not a measured result.  
**Checked by:** `make check-ids` ([`tools/check_ids.py`](../tools/check_ids.py)), which runs in `make all` and in CI.

Before this change, the agenda documents reused the same short labels for different things. `Q1`–`Q12` in the strategic agenda clashed with the numbered top-20 human-impact questions. `S0`–`S5` (stages), `S1`–`S4` (flagship studies) and `[S1]`–`[S8]` (source citations) clashed with each other. `H1`–`H3` (hypotheses) clashed with the host profiles `H0`–`H4`, and `E1`–`E3` in the human-impact lab clashed with the forensic evidence grades `E0`–`E3`. The [cross-agent prompt-injection study](cross-agent-prompt-injection.md) reused `E0`/`E1` and `H1`–`H4` in the same way, and the [research landscape](research-landscape.md) added a third `[S1]`–`[S12]` citation list. Every family now has its own prefix, and a crosswalk records which questions restate one another.

## 1. ID families

| Prefix | Meaning | Defined in | Range | Formerly |
| --- | --- | --- | --- | --- |
| **AM-** | Ranked open research questions | [open-questions.md](open-questions.md) | AM-01…AM-16 | unchanged (**frozen**: keys of [`data/evidence-map.csv`](../data/evidence-map.csv)) |
| **HQ-** | Human-impact questions, by rank | [top-20 human-impact questions](top-20-human-impact-questions-for-agentic-ai.md) | HQ-01…HQ-20 | headings `1.`–`20.`, cited as `Q1`–`Q20` |
| **SQ-** | Scientific questions of the strategic agenda | [strategic agenda §5](strategic-target-and-scientific-agenda.md) | SQ-01…SQ-12 | `Q1`–`Q12` |
| **SH-** | Hypotheses of the strategic agenda | [strategic agenda §5](strategic-target-and-scientific-agenda.md) | SH-1…SH-3 | `H1`–`H3` |
| **ST-** | Staged milestones | [strategic agenda §8](strategic-target-and-scientific-agenda.md) | ST-0…ST-5 | `S0`–`S5` |
| **FM-** | 2031 frontier questions | [2031 frontier agenda §2](2031-frontier-research-agenda.md) | FM-01…FM-20 | unchanged |
| **FS-** | 2031 flagship studies | [2031 frontier agenda §3](2031-frontier-research-agenda.md) | FS-1…FS-4 | `S1`–`S4` |
| **HX** | Priority experiments of the top-20 document | [top-20 human-impact questions](top-20-human-impact-questions-for-agentic-ai.md) | HX1…HX3 | `H1`–`H3` (renamed by [issue #45](https://github.com/MSKazemi/agent-movement/issues/45)) |
| **X** | Proposed experiments of the open questions | [open-questions.md](open-questions.md) | X1…X3 | `E1`–`E3` (renamed by issue #45) |
| **HL** | Next experiments of the human-impact lab | [human-impact research lab](human-impact-research-lab.md) | HL1…HL5 | `E1`–`E5` |
| **PI-** | Executors (PI-E0, PI-E1) and hypotheses (PI-H1…PI-H4) of the prompt-injection study | [cross-agent prompt injection §5](cross-agent-prompt-injection.md) | PI-E0, PI-E1; PI-H1…PI-H4 | `E0`, `E1`; `H1`–`H4` |
| **EV-** | Evaluation tasks (EV-A…EV-C) and their hypotheses (EV-A-H1, …) | [evaluation plan](evaluation-plan.md) (issue #26) | EV-A…EV-C | new |
| **[SRC-n]** | Source-citation label, local to one document | [open-questions.md](open-questions.md) (SRC-1…SRC-8); [top-20](top-20-human-impact-questions-for-agentic-ai.md) (SRC-1…SRC-11); [research landscape](research-landscape.md) (SRC-1…SRC-12) | — | `[S1]`–`[S8]`, `[S1]`–`[S11]`, `[S1]`–`[S12]` |

**Reserved elsewhere; do not reuse:** `E0`–`E3` for forensic evidence grades ([forensics](agent-forensics-and-fingerprints.md)) and `H0`–`H4` for host profiles ([device matrix](device-compatibility-and-capability-matrix.md)); both are serialized in code and data. `[R1]`–`[R11]` stay the strategic agenda's own citation labels.

**File-local labels left as they are:** carriers `C1`–`C7`, defense arms `D0`–`D8` and questions `Q-A`–`Q-C` in the [prompt-injection study](cross-agent-prompt-injection.md); `RQ1`–`RQ4` and `H1`–`H4` in the [MobilityBench protocol](mobilitybench-experiment-protocol.md), and `RQ1`–`RQ4` in the [paper](paper-corpus/README.md) and [news](news-corpus/README.md) corpus READMEs. Each is defined and used inside one document. Cite them with the document name (for example, "MobilityBench protocol `RQ2`").

**Legacy machine-readable values:** the MobilityBench fixtures store top-20 questions as `question_ids` strings `"Q1"`…`"Q19"`: `src/agent_movement/fixtures/mobilitybench-local-smoke/cases.jsonl` (read by `src/agent_movement/mobilitybench.py`, whose `outcome_digest` covers `question_ids`) and `src/agent_movement/fixtures/mobilitybench-v0.1/negative.jsonl` (read by `src/agent_movement/mobilitybench_v01.py`; its SHA-256 is pinned in that directory's `MANIFEST.json`). `"Qn"` there means HQ-*n* (`"Q19"` = HQ-19). They are not renamed, because changing a frozen fixture changes its digest; the checker scans only Markdown.

### Why these prefixes

- **AM- is frozen.** `data/evidence-map.csv` keys every row on an AM ID, and the [evidence map](evidence-map.md) verifies them against open-questions.md. All renaming happens in the other documents.
- **SQ-/SH- instead of RQ-.** `RQ1`–`RQ4` already name research questions in the MobilityBench protocol and in both corpus READMEs (corpus files are edited only through their pipelines). `RQ-03` next to `RQ3` would recreate the ambiguity this change removes. SQ- ("scientific question") follows the title of the agenda's §5, and SH- pairs the hypotheses with it.
- **ST- and FS- are separate families.** The agenda's stages and the 2031 agenda's flagship studies were both numbered from `S1`. One shared ST- prefix would keep the clash (ST-1 a stage and ST-1 a study). FS- also matches the FM- family of the same document.
- **HX and HL have no hyphen.** HX1–HX3 is exactly the form chosen in issue #45, so the two changes merge without a second rename; HL1–HL5 follows it.
- **PI- for the prompt-injection study.** Its executors `E0`/`E1` read as evidence grades and its hypotheses `H1`–`H4` as host profiles. The PI- prefix follows the EV-A-H1 pattern of the evaluation plan.
- **Citation labels become [SRC-n].** `[S7]` was cited from three other documents ([evidence map](evidence-map.md), [glossary](glossary.md), [sources](sources.md)), where a bare `S7` could also be read as a stage or study. `[SRC-n]` cannot collide with any ID family. A label stays local to its document, so a cross-document citation names the document: "[SRC-7] in open-questions.md".
- **Zero padding.** Families with ten or more members use two digits (AM-01, HQ-01, SQ-01, FM-01), so IDs sort correctly. Smaller families use one digit.

## 2. Crosswalk of duplicated questions

Relation codes: **duplicate** (asks the same question; cite the canonical ID), **refines** (a narrower or sharper test of an existing question; the ID stays, the canonical question is the parent), **related** (shares objects but asks something new), **new** (no counterpart). The canonical ID is the one to cite for the shared question. This is an editorial judgment from the question texts, not a measured overlap.

### 2.1 Strategic agenda (SQ-) to open questions (AM-)

| ID | Short question | Relation | Canonical |
| --- | --- | --- | --- |
| SQ-01 | Smallest sufficient portable unit | duplicate of AM-01 | AM-01 |
| SQ-02 | Semantic continuity across models/frameworks | duplicate of AM-07 + AM-08 | AM-07, AM-08 |
| SQ-03 | Ownership after failures, split brain | duplicate of AM-03 | AM-03 |
| SQ-04 | Side effects and safe retry | duplicate of AM-04 | AM-04 |
| SQ-05 | Authority without forwarding credentials | duplicate of AM-05 (revocation part: AM-10) | AM-05 |
| SQ-06 | Destination compatibility before disclosure | duplicate of AM-09 (negotiation part: AM-11) | AM-09 |
| SQ-07 | Safe context minimization | refines AM-01 (disclosure side: AM-06) | AM-01 |
| SQ-08 | Movement evidence under adversarial disagreement | related to AM-02, AM-13; no AM counterpart | SQ-08 |
| SQ-09 | When movement is worth cost and risk | duplicate of AM-14 | AM-14 |
| SQ-10 | Divergence and merge of copies/replicas | duplicate of AM-12 | AM-12 |
| SQ-11 | Partitions and offline edge | duplicate of the unnumbered P2 question "Offline and cross-cloud reconciliation" in open-questions.md | SQ-11 |
| SQ-12 | Evidence for independent certification/forensics | related to SQ-08, AM-13 | SQ-12 |

### 2.2 2031 frontier questions (FM-) to existing IDs

| ID | Short question | Relation | Canonical |
| --- | --- | --- | --- |
| FM-01 | Proof-carrying continuation | related to AM-11, AM-09 | FM-01 |
| FM-02 | Multi-hop intent drift | related to AM-08 (adds hop count) | FM-02 |
| FM-03 | Minimum sufficient move packet | **duplicate** of AM-01 (= SQ-01; see also SQ-07) | AM-01 |
| FM-04 | Move, delegate, restart or stay | **duplicate** of AM-14 (= SQ-09) | AM-14 |
| FM-05 | Conflicting twins (branch merge) | **duplicate** of AM-12 (= SQ-10) | AM-12 |
| FM-06 | Revocation horizon | **duplicate** of AM-10 | AM-10 |
| FM-07 | Derived-memory forgetting | refines AM-13 (deletion propagation) | AM-13 |
| FM-08 | Descendant inventory and non-proliferation | refines AM-12 (fork/fan-out lineage) | AM-12 |
| FM-09 | Authority conservation across graphs | related to AM-05 (graph rather than single hop) | FM-09 |
| FM-10 | Zero disclosure before trust | **duplicate** of AM-09 (= SQ-06) | AM-09 |
| FM-11 | Attestation versus behavior | related to AM-09 | FM-11 |
| FM-12 | Accountability without surveillance | related to AM-13 | FM-12 |
| FM-13 | Semantic rollback beyond a single tool | related to AM-04, AM-08 | FM-13 |
| FM-14 | Offline two-world problem | **duplicate** of SQ-11 | SQ-11 |
| FM-15 | Embodied/hardware deadline continuity | new (human-impact parent: HQ-15) | FM-15 |
| FM-16 | Forensics under missing evidence | **duplicate** of SQ-08 (see also SQ-12) | SQ-08 |
| FM-17 | Memory epidemiology | new (related to AM-12) | FM-17 |
| FM-18 | Collective governance failure | new (human-impact parent: HQ-18) | FM-18 |
| FM-19 | Fan-out conservation (combined budget) | refines AM-12 (its budget ceilings) | AM-12 |
| FM-20 | Movement and the real world (energy, carbon) | related to AM-14 and the P2 question "Economic scheduling"; human-impact parent: HQ-20 | FM-20 |

Seven FM questions are duplicates (five of AM questions, two of SQ questions) and three refine an AM question.

### 2.3 Human-impact questions (HQ-) to open questions (AM-)

HQ questions are broader than AM questions; an AM question is a technical sub-question of its HQ parent, never a duplicate. The links below are the "Agent Movement link" lines of the [top-20 document](top-20-human-impact-questions-for-agentic-ai.md); the *Top-20* column of the [evidence map](evidence-map.md) is the same mapping read from the AM side.

| HQ | AM sub-questions |
| --- | --- |
| HQ-01 Human control | AM-05, AM-10 |
| HQ-03 Identity and delegated authority | AM-02, AM-05, AM-09 |
| HQ-05 Memory ownership | AM-06, AM-13 |
| HQ-06 Accountability and redress | AM-02, AM-13 |
| HQ-18 Stable, bounded agent networks | AM-03, AM-04, AM-12 |
| HQ-19 Task movement without losing intent | AM-01, AM-07, AM-08, AM-11, AM-14, AM-15 |

### 2.4 Hypotheses

| Agenda | MobilityBench protocol | Relation |
| --- | --- | --- |
| SH-1 typed portability beats history replay | `H1` | duplicate; the protocol states the falsification condition |
| SH-2 fencing is necessary but not sufficient | `H2` | duplicate |
| SH-3 definition interoperability ≠ continuation interoperability | `H3` | duplicate |
| — | `H4` forensic receipts improve reconstruction | operationalizes SQ-08 / SQ-12 |

The MobilityBench protocol's `RQ1`, `RQ2`, `RQ3` and `RQ4` correspond to AM-01, AM-03, AM-14 and SQ-08 respectively.

## 3. Experiments, stages and studies

The same three-step research order (safe handoff, then same-runtime relocation, then cross-runtime continuation) appears in four documents.

| Step | Open questions | Top-20 | Strategic stages | Human-impact lab | 2031 studies | Issue |
| --- | --- | --- | --- | --- | --- | --- |
| Safe, authenticated handoff | X1 | HX1 | ST-1 | HL1, HL2 | — | [#7](https://github.com/MSKazemi/agent-movement/issues/7), [#8](https://github.com/MSKazemi/agent-movement/issues/8) |
| Crash-safe same-runtime relocation | X2 | HX2 | ST-2 | HL3 | — | [#9](https://github.com/MSKazemi/agent-movement/issues/9) |
| Benchmark and cross-runtime continuation | X3 | HX3 | ST-3, ST-4 | HL5 | FS-1 | [#10](https://github.com/MSKazemi/agent-movement/issues/10) |
| Independent forensic verification | — | — | ST-5 | HL4 | — | [#11](https://github.com/MSKazemi/agent-movement/issues/11) |
| Authority closure, memory, edge | — | — | ST-5 (edge) | — | FS-2, FS-3, FS-4 | — |

## 4. Rules for new text

1. Cite a question or study by its prefixed ID, never by a bare `Q3`, `S2` or `[S7]`. `make check-ids` fails on such tokens outside code spans, code blocks and URLs.
2. A new ID family gets a prefix that is not in §1 and a row in §1; add its defining pattern to `DEFINITIONS` in `tools/check_ids.py` if other documents will cite it, so unknown IDs fail the check.
3. A new question that restates an existing one gets a row in §2 pointing to the canonical ID.
4. Never renumber AM- IDs: the evidence map depends on them.
