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
| `make test` | Runs `python -m pytest -q` if `tests/` exists; otherwise prints a skip message. This covers the corpus tools and the `agent_movement` package (pytest puts `tools/` and `src/` on the import path, so no install is needed); tests that need an optional extra skip. `tests/test_handoff_envelope_schema.py` validates every JSON block marked `<!-- envelope-example -->` in `docs/` against [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json) with the stdlib-only `tools/schema_subset.py` (see [the canonical handoff envelope](how-it-works.md#canonical-handoff-envelope-020-draft)). The package's demos and extras run in `.github/workflows/python-smoke.yml`. |
| `make bib` | Runs `biber --tool --validate-datamodel` on `news.bib` and `papers.bib`. It fails on biber errors and prints warnings. Use `make bib BIB_STRICT=1` to make warnings fail too. It is skipped with a message if biber is not installed. |
| `make verify-analysis` | Regenerates `docs/corpus-analysis/timeline.md` and `coverage.md` into a temporary folder and requires them to match the committed files (`make analysis` regenerates them in place). |
| `make build` | Rebuilds both corpora **in place**, exactly as documented in each README: `merge` from `raw/`, then `apply-audit`; for papers, then `append` each later round and apply its audit file. |
| `make` / `make all` | Runs `check`, `verify-determinism`, `test` and `bib`. |
| `make help` | Lists the targets. |

Run `make all` before every commit that touches `docs/news-corpus/`, `docs/paper-corpus/` or `tools/`. If `verify-determinism` fails, either the committed files were edited by hand or a tool change altered the output. Run `make build`, review `git diff`, and commit the regenerated files together with the change that caused them.

CI does no network link checking, so every gate is deterministic and runs offline.

## Editing records

Never hand-edit the generated files (`*.csv`, `*.bib`, `digest.md`, `stats.json`, `flow.json`, `excluded.jsonl`). They are overwritten by the tools.

- **Correcting an existing record:** add an entry to the corpus's `audit.jsonl` (round-1 records) or the round's own audit file such as `audit-round2.jsonl` (records added by `append`) with `corrected_summary` and/or `corrected_fields`, then run `make build` and `make all`. Routing corrections through `audit.jsonl` keeps the published dataset reproducible from `raw/`.
- **Adding a collection round:** follow the procedure in each README, then add the round's `append` and audit commands to `PAPER_APPEND`/`PAPER_AUDIT2` in the `Makefile` (or new variables after them) so `make build` and `verify-determinism` replay it:
  - news: [§11 "How to update the corpus"](news-corpus/README.md#11-how-to-update-the-corpus);
  - papers: [§11 "How to cite and update"](paper-corpus/README.md#11-how-to-cite-and-update).

  In short, save the new raw theme files and run `merge … --out <new-dir>`. Never point `merge` at the published directory, because `merge` numbers from `AMN-001` / `AMP-001`. Then append the screened records to the published `*.jsonl` with the next free IDs, run `build`, and record the date, queries and flow counts in a new snapshot section of the README. Update the `Makefile` reproduction commands if the round adds new raw inputs.

## Identifier stability

`AMN-` and `AMP-` IDs are **stable once published**. An ID is never renumbered, reused or reassigned to a different item, and new items always take the next free number. Other documents cite records by these IDs, so the IDs must not change.

Biblatex cite keys are frozen in the same way. Both tools' `apply-audit` refuse to change `id`. The news tool also refuses any `citekey` change. The paper tool allows one only through an explicit pre-publication curator entry (`audit_pass: curator-prepublication`), and that exception closed at first publication.
