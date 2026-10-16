# Development

This repository is documentation plus two machine-readable corpora:

- the news corpus in [`news-corpus/`](news-corpus/README.md), with IDs `AMN-NNN`;
- the scholarly paper corpus in [`paper-corpus/`](paper-corpus/README.md), with IDs `AMP-NNN`.

Both are built by stdlib-only Python scripts in `tools/`. The quality gates are in the `Makefile`, and CI (`.github/workflows/corpus.yml`) runs the same targets.

The repository also contains the experimental `agent_movement` Python package in `src/`. Its setup, tests, demos and CI are described in [The `agent_movement` package](#the-agent_movement-package) below, and its design in the [as-built architecture](architecture.md).

## Requirements

- Python 3 (CI uses the current stable CPython, 3.15). No third-party packages are needed to build or check the corpora.
- `make`.
- Optional: `biber` for `make bib` (`sudo apt-get install biber`), and `pytest` for `make test` (the `tests/` directory covers the corpus tools and the `agent_movement` package).

To use a different interpreter, override `PYTHON`, e.g. `make check PYTHON=python3.15`.

## Quality gates

| Target | What it does |
|---|---|
| `make check` | Validates `news.jsonl` and `papers.jsonl` (schema, vocabularies, IDs, cite keys, duplicates). Exits non-zero on any error. |
| `make verify-determinism` | Rebuilds both corpora from `raw/` + screening + audit files (papers: round 1, then `append` round 2 and its audit) into a temporary directory and requires all 7 generated files per corpus to be byte-identical to the committed ones. |
| `make test` | Runs `python -m pytest -q` if `tests/` exists; otherwise prints a skip message. This covers the corpus tools and the `agent_movement` package (pytest puts `tools/` and `src/` on the import path, so no install is needed); tests that need an optional extra skip. `tests/test_handoff_envelope_schema.py` validates every JSON block marked `<!-- envelope-example -->` in `docs/` against [`schemas/handoff-envelope.schema.json`](../schemas/handoff-envelope.schema.json) with the stdlib-only `tools/schema_subset.py` (see [the canonical handoff envelope](how-it-works.md#canonical-handoff-envelope-020-draft)). `tests/test_positioning.py` requires the positioning statement (between `<!-- positioning:start -->` and `<!-- positioning:end -->` in `README.md` and both agenda docs, and the first paragraph of the `CITATION.cff` abstract) to be byte-identical, so change all four together. The package's demos and extras run in `.github/workflows/python-smoke.yml`. |
| `make bib` | Runs `biber --tool --validate-datamodel` on `news.bib` and `papers.bib`. It fails on biber errors and prints warnings. Use `make bib BIB_STRICT=1` to make warnings fail too. It is skipped with a message if biber is not installed. |
| `make verify-analysis` | Regenerates `docs/corpus-analysis/timeline.md` and `coverage.md` into a temporary folder and requires them to match the committed files (`make analysis` regenerates them in place). |
| `make check-ids` | Runs `tools/check_ids.py` over `README.md` and `docs/` (not the generated corpora): fails on ambiguous bare `Q3`/`S2`/`[S7]` tokens outside code and URLs, and on prefixed question/study IDs (AM-, HQ-, SQ-, SH-, ST-, FM-, FS-) that are not defined in their source document. See the [question ID crosswalk](question-id-crosswalk.md). |
| `make build` | Rebuilds both corpora **in place**, exactly as documented in each README: `merge` from `raw/`, then `apply-audit`; for papers, then `append` each later round and apply its audit file. |
| `make` / `make all` | Runs `check`, `verify-determinism`, `verify-analysis`, `check-ids`, `test` and `bib`. |
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

## The `agent_movement` package

`src/agent_movement/` is a research-stage, **synthetic, local** testbed. It is not production software, it calls no model, and it uses only throw-away test keys. Its design is described in the [as-built architecture](architecture.md). The commands in this section were last run against commit `3bf98bd` on 2026-10-16 (Python 3.15.0rc2 without extras; Python 3.11.16 and 3.13.15 with all extras), and every exit code quoted below is what they returned.

### Requirements

- Python 3.11 or newer (`requires-python = ">=3.11"` in [`pyproject.toml`](../pyproject.toml)). CI tests the core on 3.11, 3.13 and 3.15, and the extras on 3.11 and 3.13.
- The core package has no third-party dependencies. `pytest>=9.1` is needed only to run `tests/`.
- `relocation_demo` and the relocation tests need `os.fork`, so they run only on Linux or macOS.

### Set up a virtual environment

Keep the environment outside the repository. With the standard library `venv` and `pip` (CI runs the same `pip install` commands in the runner's Python):

```bash
VENV="$HOME/.venvs/agent-movement"
python3 -m venv "$VENV"
# core only (the CI "core" job):
"$VENV/bin/python" -m pip install -e . "pytest>=9.1"
# or every optional extra (the CI "extras" job):
"$VENV/bin/python" -m pip install -e '.[a2a,ed25519,relocation,signing]' "pytest>=9.1"
```

With [uv](https://docs.astral.sh/uv/), the same environment is:

```bash
uv venv "$VENV" --python 3.13
uv pip install --python "$VENV/bin/python" -e '.[a2a,ed25519,relocation,signing]' "pytest>=9.1"
```

All the commands below are run from the repository root with that interpreter; write `python` for `"$VENV/bin/python"`. You can also run the tests without installing the package: `pyproject.toml` puts `src/` and `tools/` on the pytest import path, so an interpreter with only `pytest` installed is enough for the core tests.

### Optional extras

| Extra | Installs | Enables |
|---|---|---|
| `a2a` | `a2a-sdk[http-server]==1.2.2`, `uvicorn>=0.54` | `a2a_server`, `a2a_client`, `a2a_demo` and `tests/test_a2a_adapter.py` |
| `ed25519` | `cryptography>=50.0.2` | Ed25519 peer keys (`trust.Ed25519Key`) and `peer_demo --alg Ed25519` |
| `relocation` | `langgraph==1.2.15`, `langgraph-checkpoint==4.3.0`, `langgraph-checkpoint-sqlite==3.1.2` (exact pins) | `relocation`, `relocation_demo` and `tests/test_relocation.py` |
| `signing` | `cryptography>=50.0.2` | Ed25519 signature checks in `receipts` and fixture regeneration (`receipt_fixtures`) |

Without its extra, a feature fails closed instead of pretending to work. This is what the core CI job checks, and what the commands below returned in a core-only environment:

| Command without the extra | Exit code | Behaviour |
|---|---|---|
| `python -m agent_movement.a2a_demo` | 2 | Prints the install hint |
| `python -m agent_movement.peer_demo --alg Ed25519` | 1 | Prints the install hint |
| `python -m agent_movement.receipts verify tests/fixtures/movement-receipts/01-valid-delegation --now 2026-10-16T00:00:00Z` | 3 | Signatures are reported as `UNCHECKED` |
| `python -m agent_movement.relocation_demo` | 1 | `ImportError` with the install hint |

### Tests

`python -m pytest -q` runs all of `tests/`, which covers the corpus tools and the package. `make test PYTHON=python` runs the same command. Tests that need an extra are skipped, not failed, when it is missing. At `3bf98bd` the full run gave **338 passed, 76 skipped** without extras and **413 passed, 1 skipped** with all extras (the one skip is the test of the missing-extra path). Both exited 0.

Run one group with `python -m pytest -q <file>`:

| File | What it covers | Needs | Passed (no extras / all extras) |
|---|---|---|---|
| `tests/test_core.py` | Envelope contract, approvals, idempotency, `EffectGateway` fencing | core | 13 / 13 |
| `tests/test_http.py` | Loopback HTTP receiver: success, replay and denial, protocol errors, conflicts, loopback-only bind | core | 4 / 4 |
| `tests/test_peer.py` | Trust model, pre-disclosure handoff, attacks, revocation races | core; Ed25519 cases need `ed25519` | 39 (38 skipped) / 77 |
| `tests/test_a2a_profile.py` | Envelope to A2A mapping and receipt checks (no SDK) | core | 7 / 7 |
| `tests/test_a2a_adapter.py` | A2A server and client over the official SDK | `a2a` | 1 (11 skipped) / 11 (1 skipped) |
| `tests/test_relocation.py` | Checkpoint relocation and the fault matrix | `relocation`, `os.fork` | 0 (14 skipped) / 14 |
| `tests/test_movement_receipts.py` | Receipt schema, JCS, offline verifier, fixtures | `signing` for signature cases | 13 (13 skipped) / 26 |
| `tests/test_mobilitybench.py` | Smoke suite: fixture-declared verdicts, per-case isolation, order independence, byte-identical `--no-timing` output | core | 15 / 15 |
| `tests/test_mobilitybench_v01.py` | MobilityBench v0.1 fixtures, runner, report | core | 25 / 25 |
| `tests/test_review_regressions.py` | Regressions from the PR #6 and #14 review: JSON limits, lone surrogates, 400/500 answers, stalled bodies, SQLite start-up, pipe cleanup | core | 9 / 9 |
| `tests/test_handoff_envelope_schema.py` | Marked envelope examples in `docs/` against `schemas/handoff-envelope.schema.json`, and core compatibility with the schema | core | 47 / 47 |
| `tests/test_positioning.py` | The positioning statement is identical on every surface | core | 4 / 4 |
| `tests/test_news_corpus.py`, `tests/test_paper_corpus.py`, `tests/test_cli_determinism_integration.py` | Corpus tools (see above) | core | 161 / 161 |

Every group exited 0 in both environments.

### Demos

Each demo runs locally on `127.0.0.1` (or in-process), keeps its SQLite files in a temporary directory, prints a JSON or Markdown summary, and exits non-zero if one of its own checks fails. Only the files you name with `--json`, `--output` or `--out` are written elsewhere.

| Command | Needs | What it shows | Exit code |
|---|---|---|---|
| `python -m agent_movement.demo` | core | Two processes: a handoff, an exact replay, an unapproved request, and a stale-epoch effect that is fenced | 0 |
| `python -m agent_movement.peer_demo` | core | Authenticated pre-disclosure handoff (HS256): one honest run and nine attacks | 0 |
| `python -m agent_movement.peer_demo --alg Ed25519` | `ed25519` | The same with Ed25519 keys | 0 |
| `python -m agent_movement.a2a_demo` | `a2a` | A2A v1 delegation: server process plus five client processes | 0 |
| `python -m agent_movement.relocation_demo --json "$OUT/relocation-results.json"` | `relocation` | Headline relocation plus the 30-row fault matrix (`rows: 30, matching expectation: 30`) | 0 |
| `python -m agent_movement.mobilitybench --output "$OUT/mobilitybench-local.jsonl"` | core | Smoke suite `mobilitybench-local-smoke-v0.2`: 20 cases, 17 `pass`, 3 `known_gap`, 0 `gap_closed`, 0 `fail` | 0 |
| `python -m agent_movement.mobilitybench --no-timing --output "$OUT/smoke-1.jsonl"` (twice, then `cmp` the two files) | core | Timing-free output is byte-identical across runs | 0, and `cmp` exits 0 |

Here `OUT=$(mktemp -d)`, so no output lands in the working tree.

MobilityBench v0.1 (see [MobilityBench v0.1](mobilitybench-v0.1.md)):

```bash
python tools/mobilitybench_freeze.py --check                     # exit 0: ground truth and manifest match
python -m agent_movement.mobilitybench verify --suite v0.1        # exit 0: fixture digests match MANIFEST.json
python -m agent_movement.mobilitybench schedule --subset smoke    # exit 0: prints the seeded fault schedule
python -m agent_movement.mobilitybench run --suite v0.1 --subset smoke --out "$OUT/smoke.jsonl"   # exit 0
python -m agent_movement.mobilitybench report --in "$OUT/smoke.jsonl" --out "$OUT/smoke.md"       # exit 0
```

The smoke run gave 36 attempts (6 tasks, 1 seed, 6 modes) and 12 security cases (10 pass, 2 `known_gap`, 0 fail).

Movement receipts (needs `signing`; see [movement receipts](movement-receipts.md)):

```bash
python -m agent_movement.receipts verify tests/fixtures/movement-receipts/01-valid-delegation --now 2026-10-16T00:00:00Z     # exit 0
python -m agent_movement.receipts timeline tests/fixtures/movement-receipts/01-valid-delegation --now 2026-10-16T00:00:00Z   # exit 0
python -m agent_movement.receipts make-fixtures "$OUT/fixtures"   # exit 0; the output is identical to tests/fixtures/movement-receipts/
```

The nine fixture bundles return the exit codes that CI expects: 0 for `01`, `05`, `07` and `09`, and 1 for `02`, `03`, `04`, `06` and `08`.

### CI layout

| Workflow | Trigger | Jobs |
|---|---|---|
| [`corpus.yml`](../.github/workflows/corpus.yml) | push and pull request to `main` | `gates`: `make check verify-determinism verify-analysis`, then `make test` on Python 3.15. `bibliography`: `make bib BIB_STRICT=1`. |
| [`python-smoke.yml`](../.github/workflows/python-smoke.yml) | push or pull request touching `src/`, `tests/`, `tools/`, `pyproject.toml` or the workflow | `core` (Python 3.11, 3.13, 3.15; no extras): pytest, `demo`, `peer_demo`, the smoke suite (once with timing, then twice with `--no-timing`, compared with `cmp`), MobilityBench v0.1, and the fail-closed checks above. `extras` (Python 3.11, 3.13; all extras): pytest, every demo, and the nine receipt fixtures with their expected exit codes. Both upload their result files as artifacts for 7 days. |
| [`docs-links.yml`](../.github/workflows/docs-links.yml) | push to `main` and every pull request | `relative-links`: lychee in offline mode over all Markdown files |

### Adding a MobilityBench case

There are two suites, and they are extended differently.

**Smoke suite (`mobilitybench.py`, fixture-based).** A case has two parts, and both are needed:

1. A declaration: one JSON line in `src/agent_movement/fixtures/mobilitybench-local-smoke/cases.jsonl` with the fields `scenario`, `question_ids`, `baseline`, `expected`, `expectation` and `description` (checked by `mobilitybench.validate_case`). `expectation` is `pass`, `known_gap` or `gap_closed`. A `known_gap` case must also give `expected_fix` and a `closed_observation` that differs from `expected`; a `gap_closed` case gives `expected_fix` only; a `pass` case gives neither.
2. An evaluator: a function `case_<scenario>(workdir: Path) -> tuple[str, Evidence]` in `mobilitybench.py`, defined **above** the `EVALUATORS = {...}` line, because that dictionary is built from the module globals at import time. It must create everything it uses inside `workdir` and return `(observed, evidence)`; evidence values must be `str`, `int` or `bool`, and never task text.

If only one part exists, the CLI exits 2 with `case_fixture_invalid`: a declaration without an evaluator is reported as `no evaluator for scenario <name>`, and an evaluator without a declaration as `packaged declarations do not cover every evaluator`. In a rehearsal on a scratch copy of the package with one added `pass` case, the declaration alone and the evaluator alone each exited 2, and both together gave 21 cases (18 `pass`, 3 `known_gap`) with exit 0. `tests/test_mobilitybench.py` derives its counts from the declarations and passed, but `tests/test_mobilitybench_v01.py` (`test_run_smoke_report_verify_and_legacy_entrypoint`) still asserts that the smoke output has exactly 20 lines and failed, so update that number in the same change.

**MobilityBench v0.1 (`fixtures/mobilitybench-v0.1/`).** This release is frozen and must not be edited in place: a new task, rubric or ground truth needs a new suite version and a new fixture directory ([versioning rule](mobilitybench-v0.1.md#frozen-release)). At `b21da27` the harness knows one suite (`mobilitybench_v01.SUITES = {"v0.1": ...}`), and `verify_fixtures` requires the manifest's `suite_version` to equal `SUITE_VERSION`. A new release therefore also needs a change in `mobilitybench_v01.py` and in the `package-data` pattern in `pyproject.toml`. You can draft and test a case in a copy without touching the release:

```bash
DRAFT=$(mktemp -d)/mobilitybench-draft
cp -r src/agent_movement/fixtures/mobilitybench-v0.1 "$DRAFT"
# append one JSON object per line to "$DRAFT/tasks.jsonl" (the fields checked by mobilitybench_v01.validate_task)
python tools/mobilitybench_freeze.py --fixtures "$DRAFT"            # recomputes ground_truth.jsonl and MANIFEST.json
python tools/mobilitybench_freeze.py --fixtures "$DRAFT" --check    # exit 0
python -m agent_movement.mobilitybench verify --fixtures "$DRAFT"   # exit 0
python -m agent_movement.mobilitybench run --fixtures "$DRAFT" --seeds 1103 --repeats 1 --out "$DRAFT/../draft.jsonl"   # exit 0
```

Before the freeze step, `verify` exits 2 with `fixture digest mismatch: tasks.jsonl`. In a rehearsal with one added task (a copy of `doc-policy-digest` under a new `task_id`), every command above exited 0, and the new task appeared in 6 attempt records (one per mode). A negative case is a line in `negative.jsonl` whose `attack` names a handler in `mobilitybench_v01.SECURITY`. A new kind of attack needs a new handler in the code.
