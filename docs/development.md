# Development

This repository is documentation plus two machine-readable corpora:

- the news corpus in [`news-corpus/`](news-corpus/README.md), with IDs `AMN-NNN`;
- the scholarly paper corpus in [`paper-corpus/`](paper-corpus/README.md), with IDs `AMP-NNN`.

Both are built by stdlib-only Python scripts in `tools/`. The quality gates are in the `Makefile`, and CI (`.github/workflows/corpus.yml`) runs the same targets.

## Requirements

- Python 3 (CI uses the current stable CPython, 3.15). No third-party packages are needed to build or check the corpora.
- `make`.
- Optional: `biber` for `make bib` (`sudo apt-get install biber`), and `pytest` for `make test` once a `tests/` directory exists.

To use a different interpreter, override `PYTHON`, e.g. `make check PYTHON=python3.15`.

## Quality gates

| Target | What it does |
|---|---|
| `make check` | Validates `news.jsonl` and `papers.jsonl` (schema, vocabularies, IDs, cite keys, duplicates). Exits non-zero on any error. |
| `make verify-determinism` | Rebuilds both corpora from `raw/` + screening + audit files (papers: round 1, then `append` round 2 and its audit) into a temporary directory and requires all 7 generated files per corpus to be byte-identical to the committed ones. |
| `make test` | Runs `python -m pytest -q` if `tests/` exists; otherwise prints a skip message. This covers the corpus tools and the `agent_movement` package (pytest puts `tools/` and `src/` on the import path, so no install is needed); tests that need an optional extra skip. `tests/test_handoff_envelope_schema.py` validates every JSON block marked `<!-- envelope-example -->` in `docs/` against [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json) with the stdlib-only `tools/schema_subset.py` (see [the canonical handoff envelope](how-it-works.md#canonical-handoff-envelope-020-draft)). `tests/test_positioning.py` requires the positioning statement (between `<!-- positioning:start -->` and `<!-- positioning:end -->` in `README.md` and both agenda docs, and the first paragraph of the `CITATION.cff` abstract) to be byte-identical, so change all four together. The package's demos and extras run in `.github/workflows/python-smoke.yml`. |
| `make check-tests-registry` | Runs the stdlib-only `tools/check_test_registry.py` on [`data/test-registry.csv`](../data/test-registry.csv) (see [Test registry](#test-registry)). It parses the test files with `ast` and never imports them, so it needs no optional extra. It fails when an `implemented` or `partial` row names a test node ID that does not exist, on duplicate IDs, unknown status values or missing source documents, and when a document cites a registry-style ID that is neither a registry ID nor an alias. It warns (or, with `--strict`, fails) when a test in a registered test file is not named by any row. `--stats` also prints rows per test file. |
| `make bib` | Runs `biber --tool --validate-datamodel` on `news.bib` and `papers.bib`. It fails on biber errors and prints warnings. Use `make bib BIB_STRICT=1` to make warnings fail too. It is skipped with a message if biber is not installed. |
| `make verify-analysis` | Regenerates `docs/corpus-analysis/timeline.md` and `coverage.md` into a temporary folder and requires them to match the committed files (`make analysis` regenerates them in place). |
| `make check-ids` | Runs `tools/check_ids.py` over `README.md` and `docs/` (not the generated corpora): fails on ambiguous bare `Q3`/`S2`/`[S7]` tokens outside code and URLs, and on prefixed question/study IDs (AM-, HQ-, SQ-, SH-, ST-, FM-, FS-) that are not defined in their source document. See the [question ID crosswalk](question-id-crosswalk.md). |
| `make sources` | Runs `tools/sources_index.py check`. It extracts every external URL from `README.md` and `docs/**/*.md` and requires each one to be listed in the generated *URL index by document* section of [`sources.md`](sources.md), with its document key(s) and an access date. It fails on unindexed URLs, on index rows that no document cites any more, and on rows without a valid date. Corpus files, generated files, code spans, templates, loopback/example hosts and links to this repository are not indexed (see the module docstring and `EXCLUDE_GLOBS`). |
| `make sources-index` | Runs `tools/sources_index.py generate`. It rewrites only the section between `<!-- sources-index:start -->` and `<!-- sources-index:end -->` in `sources.md`; the hand-written text above it is kept. Access dates already in the index (including hand-edited ones) are kept. `generate --refresh-dates` recomputes the automatic dates and still keeps rows whose *Date basis* is not automatic (e.g. `manual`). |
| `make build` | Rebuilds both corpora **in place**, exactly as documented in each README: `merge` from `raw/`, then `apply-audit`; for papers, then `append` each later round and apply its audit file. |
| `make` / `make all` | Runs `check`, `verify-determinism`, `verify-analysis`, `check-ids`, `check-tests-registry`, `sources`, `test` and `bib`. |
| `make help` | Lists the targets. |

Run `make all` before every commit that touches `docs/news-corpus/`, `docs/paper-corpus/` or `tools/`. When a document gains or loses an external link, run `make sources-index`, check the access dates of the new rows in `sources.md` (edit a cell and set its *Date basis* to `manual` if the derived date is wrong), and commit `sources.md` with the document. If `verify-determinism` fails, either the committed files were edited by hand or a tool change altered the output. Run `make build`, review `git diff`, and commit the regenerated files together with the change that caused them.

CI does no network link checking, so every gate is deterministic and runs offline.

## Editing records

Never hand-edit the generated files (`*.csv`, `*.bib`, `digest.md`, `stats.json`, `flow.json`, `excluded.jsonl`). They are overwritten by the tools.

- **Correcting an existing record:** add an entry to the corpus's `audit.jsonl` (round-1 records) or the round's own audit file such as `audit-round2.jsonl` (records added by `append`) with `corrected_summary` and/or `corrected_fields`, then run `make build` and `make all`. Routing corrections through `audit.jsonl` keeps the published dataset reproducible from `raw/`.
- **Adding a collection round:** follow the procedure in each README, then add the round's `append` and audit commands to `PAPER_APPEND`/`PAPER_AUDIT2` in the `Makefile` (or new variables after them) so `make build` and `verify-determinism` replay it:
  - news: [§11 "How to update the corpus"](news-corpus/README.md#11-how-to-update-the-corpus);
  - papers: [§11 "How to cite and update"](paper-corpus/README.md#11-how-to-cite-and-update).

  In short, save the new raw theme files and run `merge … --out <new-dir>`. Never point `merge` at the published directory, because `merge` numbers from `AMN-001` / `AMP-001`. Then append the screened records to the published `*.jsonl` with the next free IDs, run `build`, and record the date, queries and flow counts in a new snapshot section of the README. Update the `Makefile` reproduction commands if the round adds new raw inputs.

## Test registry

[`data/test-registry.csv`](../data/test-registry.csv) is the single list of documented test cases and the tests that implement them. It replaces four overlapping lists: the protocol guide's T01–T18, the threat model's E01–E15, the communication policy's COM-T001–COM-T028 and the recommended assurance tests of `docs/security-and-trust.md` (now SEC-01–SEC-11). Those documents keep a crosswalk from their IDs to registry rows, and the two older CSVs (`data/agent-communication-conformance-cases.csv`, `data/unnoticed-agent-movement-defense-tests.csv`) keep the case specifications (expected decision, boundary, evidence, severity) with a `registry_id` column. Status is kept only in the registry.

| Column | Content |
|---|---|
| `id` | `T01`–`T18`, `E01`–`E15`, `COM-T001`–`COM-T028`, `SEC-01`–`SEC-11`, or `REG-nnn` for a registered test that no document describes. IDs are never renumbered or reused. |
| `title` | The scenario and its expected result. |
| `source_docs` | `;`-separated repository paths that define or describe the case; each must exist. |
| `threat_asi` | `;`-separated OWASP Agentic Top 10 IDs (`ASI01`–`ASI10`), from the [mapping table](security-and-trust.md#owasp-top-10-for-agentic-applications-2026-mapping); may be empty. |
| `status` | `implemented` (a test exercises the whole case), `partial` (tests cover part of it; `notes` says which part is missing) or `planned` (no test). Decide from the test body, not its name. |
| `implementing_tests` | `;`-separated pytest node IDs, `tests/<file>.py::<Class>::<test>` (or `tests/<file>.py::<test>`). Required for `implemented` and `partial`, empty for `planned`. |
| `aliases` | Old IDs of duplicate cases folded into this row. An alias may sit on several rows when one old case was split (for example T04). |
| `notes` | Scope, limits and what a `partial` row lacks. |

**Adding a row.** When you add a test, add its node ID to the row of the case it exercises, or add a new `REG-nnn` row with the next free number. Once one test of a file is registered, the check reports every other test defined in that file that no row names. It prints these as warnings, so a new test in a parallel PR does not turn CI red before its row exists; `python3 tools/check_test_registry.py --strict` turns them into errors. A test that several classes inherit from a base or mixin class of the same file counts as registered when any one class's node ID is listed (for example `tests/test_peer.py::PeerAuthHpkeTests::test_hpke_client_never_downgrades` for a mixin test); list more classes when they assert different things, as the plaintext and HPKE runs of one test do. Raise a row from `planned` to `partial` or `implemented` only after reading what the test asserts. Renaming or deleting a test means updating its node ID here in the same commit. Then run `make check-tests-registry`.

## Identifier stability

`AMN-` and `AMP-` IDs are **stable once published**. An ID is never renumbered, reused or reassigned to a different item, and new items always take the next free number. Other documents cite records by these IDs, so the IDs must not change.

Biblatex cite keys are frozen in the same way. Both tools' `apply-audit` refuse to change `id`. The news tool also refuses any `citekey` change. The paper tool allows one only through an explicit pre-publication curator entry (`audit_pass: curator-prepublication`), and that exception closed at first publication.
