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

## The `agent_movement` package

`src/agent_movement/` is a research-stage, **synthetic, local** testbed. It is not production software, it calls no model, and it uses only throw-away test keys. Its design is described in the [as-built architecture](architecture.md), and every command, flag and exit code is listed in the [CLI reference](cli.md). The commands in this section were last run against commit `4809bdf` on 2026-10-16 (Python 3.15.0rc2 without extras; Python 3.11.16 and 3.13.15 with all extras), and every exit code quoted below is what they returned.

### Requirements

- Python 3.11 or newer (`requires-python = ">=3.11"` in [`pyproject.toml`](../pyproject.toml)). CI tests the core on 3.11, 3.13 and 3.15, and the extras on 3.11 and 3.13.
- The core package has no third-party dependencies. `pytest>=9.1` is needed only to run `tests/`.
- Both relocation demos and their tests need `os.fork`, so they run only on Linux or macOS.

### Set up a virtual environment

Keep the environment outside the repository. With the standard library `venv` and `pip` (CI runs the same `pip install` commands in the runner's Python):

```bash
VENV="$HOME/.venvs/agent-movement"
python3 -m venv "$VENV"
# core only (the CI "core" job):
"$VENV/bin/python" -m pip install -e . "pytest>=9.1"
# or every optional extra (the CI "extras" job):
"$VENV/bin/python" -m pip install -e '.[a2a,ed25519,hpke,relocation,signing]' "pytest>=9.1"
```

With [uv](https://docs.astral.sh/uv/), the same environment is:

```bash
uv venv "$VENV" --python 3.13
uv pip install --python "$VENV/bin/python" -e '.[a2a,ed25519,hpke,relocation,signing]' "pytest>=9.1"
```

The install puts the `agent-movement` console script in `"$VENV/bin"`. All commands below run from the repository root with that environment active (`python` is `"$VENV/bin/python"`). `agent-movement version` prints which extras are installed. You can also run the tests without installing the package: `pyproject.toml` puts `src/` and `tools/` on the pytest import path, so an interpreter with only `pytest` is enough for the core tests.

### Optional extras

| Extra | Installs | Enables |
|---|---|---|
| `a2a` | `a2a-sdk[http-server]==1.2.2`, `uvicorn>=0.54` | `a2a_server`, `a2a_client`, `agent-movement a2a-demo` and `tests/test_a2a_adapter.py` |
| `ed25519` | `cryptography>=50.0.2` | Ed25519 peer keys (`trust.Ed25519Key`) and `peer-demo --alg Ed25519` |
| `hpke` | `cryptography>=50.0.2` | HPKE-sealed peer delivery (`trust.HpkeKey`) and `peer-demo --delivery hpke` |
| `relocation` | `langgraph==1.2.15`, `langgraph-checkpoint==4.3.0`, `langgraph-checkpoint-sqlite==3.1.2` (exact pins) | `relocation`, `relocation_bundle`, `agent-movement relocate [--two-store]` and the relocation tests |
| `signing` | `cryptography>=50.0.2` | Ed25519 signature checks in `agent-movement receipts` and fixture regeneration |

Without its extra, a command fails closed instead of pretending to work. Through the CLI every such case prints an install hint and exits 2; the module entry points keep their own codes. In a core-only environment:

| Command without the extra | CLI exit | `python -m` exit |
|---|---|---|
| `agent-movement a2a-demo` / `python -m agent_movement.a2a_demo` | 2 | 2 |
| `agent-movement peer-demo --alg Ed25519` / `python -m agent_movement.peer_demo --alg Ed25519` | 2 | 1 |
| `agent-movement peer-demo --delivery hpke` / `python -m agent_movement.peer_demo --delivery hpke` | 2 | 1 |
| `agent-movement relocate` / `python -m agent_movement.relocation_demo` | 2 | 1 (`ImportError` with the hint) |
| `agent-movement receipts verify tests/fixtures/movement-receipts/01-valid-delegation --trust tests/fixtures/movement-receipts/trust.json` | 2 | 3 with `python -m agent_movement.receipts` (signatures reported as `UNCHECKED`) |

### Tests

`python -m pytest -q` runs all of `tests/`, which covers the corpus tools, the docs checks and the package. `make test PYTHON=python` runs the same command. Tests that need an extra are skipped, not failed, when it is missing. At `4809bdf` the full run gave **426 passed, 173 skipped** without extras and **596 passed, 3 skipped** with all extras; with the `gitleaks` binary on `PATH` or in `$GITLEAKS` (as in the CI extras job), one more test runs (427/172 and 597/2). All exited 0. With all extras and `gitleaks`, the two remaining skips are tests of the missing-extra path.

Run one group with `python -m pytest -q <file>` (counts below were measured with `$GITLEAKS` set):

| File | What it covers | Needs | Passed (no extras / all extras) |
|---|---|---|---|
| `tests/test_core.py` | Envelope contract, approvals, idempotency, `EffectGateway` fencing | core | 13 / 13 |
| `tests/test_http.py` | Loopback HTTP receiver: success, replay and denial, protocol errors, conflicts, loopback-only bind | core | 4 / 4 |
| `tests/test_peer.py` | Trust model, pre-disclosure handoff, attacks, revocation races, HPKE delivery | core; see the classes below | 39 (101 skipped) / 140 |
| `tests/test_a2a_profile.py` | Envelope to A2A mapping, contextId policy, receipt checks (no SDK) | core | 13 / 13 |
| `tests/test_a2a_adapter.py` | A2A server and client over the official SDK | `a2a` | 1 (21 skipped) / 21 (1 skipped) |
| `tests/test_relocation.py` | Single-store relocation and the 30-row fault matrix | `relocation`, `os.fork` | 0 (14 skipped) / 14 |
| `tests/test_relocation_two_store.py` | Two-store relocation, bundle checks and the 11-row copy fault matrix | `relocation`, `os.fork` | 0 (16 skipped) / 16 |
| `tests/test_movement_receipts.py` | Receipt schema, JCS, offline verifier, out-of-band anchors, CLI exit codes, fixtures | `signing` for signature cases | 15 (16 skipped) / 31 |
| `tests/test_movement_receipts_secret_scan.py` | Receipt files against a gitleaks v8.30.1 rule subset, and the real `gitleaks` binary if present | core; `gitleaks` binary for one test | 5 / 5 |
| `tests/test_cli.py` | `agent-movement` dispatch, argument forwarding, extra hints, `docs/cli.md` up to date | core; end-to-end cases need extras | 50 (4 skipped) / 53 (1 skipped) |
| `tests/test_mobilitybench.py` | Smoke suite: declared verdicts, per-case isolation, order independence, byte-identical `--no-timing` output | core | 15 / 15 |
| `tests/test_mobilitybench_v01.py` | MobilityBench v0.1 fixtures, runner, report | core | 25 / 25 |
| `tests/test_review_regressions.py` | Regressions from the PR #6 and #14 review | core | 9 / 9 |
| `tests/test_handoff_envelope_schema.py` | Marked envelope examples in `docs/` against the envelope schema, and core compatibility | core | 47 / 47 |
| `tests/test_check_test_registry.py` | `tools/check_test_registry.py` | core | 20 / 20 |
| `tests/test_check_ids.py`, `tests/test_positioning.py` | Question/study IDs and the positioning statement in the docs | core | 6 + 4 / 6 + 4 |
| `tests/test_news_corpus.py`, `tests/test_paper_corpus.py`, `tests/test_cli_determinism_integration.py` | Corpus tools (see above) | core | 161 / 161 |

The peer tests are split by class (`python -m pytest -q tests/test_peer.py::<Class>`): `PeerAuthTests` (HS256, plaintext delivery; 37 / 37), `PeerAuthHpkeTests` (HS256 with HPKE delivery, needs `hpke`; 0 / 48), `PeerAuthEd25519Tests` (needs `ed25519` and `hpke`; 0 / 49), `PeerHttpTests` (2 / 2), `PeerHttpHpkeTests` (0 / 2) and `Rfc9180KnownAnswerTests` (the RFC 9180 Appendix A.2.1 vector, needs `hpke`; 0 / 2). The relay test `test_on_path_relay_sees_only_ciphertext_with_hpke` runs in every `PeerAuth*` class: with HPKE it asserts that the relay sees only ciphertext, and in plaintext mode that it does see the task text.

Every group and class exited 0 in both environments.

**Registering a test.** A new security or conformance test needs its node ID in a row of [`data/test-registry.csv`](../data/test-registry.csv) (see [Test registry](#test-registry)); `make check-tests-registry` checks the file, and `--strict` turns unregistered tests in registered files into errors.

### Demos

Each demo runs locally on `127.0.0.1` (or in-process), keeps its SQLite files in a temporary directory, prints a JSON or Markdown summary, and exits non-zero if one of its own checks fails. Only the files you name with `--json`, `--output` or `--out` are written elsewhere; below, `OUT=$(mktemp -d)`. Each `agent-movement` subcommand has an equivalent `python -m agent_movement.<module>` form (see the [CLI reference](cli.md)).

| Command | Needs | What it shows | Exit code |
|---|---|---|---|
| `agent-movement demo` | core | Two processes: a handoff, an exact replay, an unapproved request, and a stale-epoch effect that is fenced | 0 |
| `agent-movement peer-demo` | core | Authenticated pre-disclosure handoff (HS256): one honest run and nine attacks; plaintext delivery, reported as `no confidentiality` | 0 |
| `agent-movement peer-demo --alg Ed25519` | `ed25519`, `hpke` | The same with Ed25519 keys; delivery defaults to HPKE | 0 |
| `agent-movement peer-demo --delivery hpke` | `hpke` | HS256 signatures with HPKE-sealed delivery; the task canary must not appear in any captured bytes | 0 |
| `agent-movement a2a-demo` | `a2a` | A2A v1 delegation: a server process and seven client processes, including the legacy URN alias and a refused client contextId | 0 |
| `agent-movement relocate --json "$OUT/relocation.json"` | `relocation` | Single store: headline relocation plus the 30-row fault matrix (`rows: 30, matching expectation: 30`) | 0 |
| `agent-movement relocate --two-store --json "$OUT/relocation-two-store.json"` | `relocation` | Two stores: the checkpoint is copied as a digest-verified bundle; 11-row copy fault matrix (`rows: 11, matching expectation: 11`) | 0 |
| `agent-movement bench smoke --output "$OUT/smoke.jsonl"` | core | Smoke suite `mobilitybench-local-smoke-v0.2`: 20 cases, 17 `pass`, 3 `known_gap`, 0 `fail` | 0 |
| `agent-movement bench smoke --no-timing --output "$OUT/s1.jsonl"` (twice, then `cmp` the files) | core | Timing-free output is byte-identical across runs | 0, and `cmp` exits 0 |

MobilityBench v0.1 (see [MobilityBench v0.1](mobilitybench-v0.1.md)):

```bash
python tools/mobilitybench_freeze.py --check                     # exit 0: ground truth and manifest match
agent-movement bench verify --suite v0.1                         # exit 0: fixture digests match MANIFEST.json
agent-movement bench schedule --subset smoke                     # exit 0: prints the seeded fault schedule
agent-movement bench run --suite v0.1 --subset smoke --out "$OUT/v01.jsonl"   # exit 0
agent-movement bench report --in "$OUT/v01.jsonl" --out "$OUT/v01.md"         # exit 0
```

The smoke run gave 36 attempts (6 tasks, 1 seed, 6 modes) and 12 security cases (10 pass, 2 `known_gap`, 0 fail).

Movement receipts (needs `signing`; see [movement receipts](movement-receipts.md)). Trust anchors are never taken from the evidence implicitly, so `--trust` is required:

```bash
R=tests/fixtures/movement-receipts
agent-movement receipts verify $R/01-valid-delegation --now 2026-10-16T00:00:00Z                       # exit 2: no trust anchors
agent-movement receipts verify $R/01-valid-delegation --trust $R/trust.json --now 2026-10-16T00:00:00Z  # exit 0
agent-movement receipts timeline $R/01-valid-delegation --trust $R/trust.json --now 2026-10-16T00:00:00Z  # exit 0
agent-movement receipts make-fixtures "$OUT/fixtures"   # exit 0; identical to tests/fixtures/movement-receipts/
```

With `--trust $R/trust.json`, the nine fixture bundles return 0 for `01`, `05`, `07` and `09`, and 1 for `02`, `03`, `04`, `06` and `08`. Without the `signing` extra (`python -m agent_movement.receipts`), they return 3 for `01`, `05`, `06`, `07` and `09`, and 1 for `02`, `03`, `04` and `08`. `--fixture-trust` instead of `--trust` reads the fixtures' own `trust.json` with a warning; it is for the synthetic fixtures only.

### CLI reference

[`docs/cli.md`](cli.md) is generated from the live `--help` output. After changing a subcommand, its flags or its help text, run `make cli-docs` (needs every optional extra) and commit the result; `python tools/cli_reference.py --check` (exit 0 at `4809bdf`) fails when the file is stale, and CI runs it in the extras job.

### CI layout

| Workflow | Trigger | Jobs |
|---|---|---|
| [`corpus.yml`](../.github/workflows/corpus.yml) | push and pull request to `main` | `gates`: `make check verify-determinism verify-analysis`, `make check-ids`, `make check-tests-registry`, then `make test` on Python 3.15. `bibliography`: `make bib BIB_STRICT=1`. |
| [`python-smoke.yml`](../.github/workflows/python-smoke.yml) | push or pull request touching `src/`, `tests/`, `tools/`, `pyproject.toml` or the workflow | `core` (Python 3.11, 3.13, 3.15; no extras): pytest, `demo`, `peer_demo`, the smoke suite (once with timing, then twice with `--no-timing`, compared with `cmp`), MobilityBench v0.1, the fail-closed checks above (including the receipt exit codes without `signing`) and the `agent-movement` CLI with its exit-2 hints. `extras` (Python 3.11, 3.13; all extras plus a pinned, checksum-verified `gitleaks`): pytest, every demo including `peer_demo --delivery hpke` and `relocation_demo --two-store`, the nine receipt fixtures with `--trust`, every CLI subcommand, and `tools/cli_reference.py --check`. Both upload their result files as artifacts for 7 days. |
| [`docs-links.yml`](../.github/workflows/docs-links.yml) | push to `main` and every pull request | `relative-links`: lychee in offline mode over all Markdown files |

### Adding a MobilityBench case

There are two suites, and they are extended differently.

**Smoke suite (`mobilitybench.py`, fixture-based).** A case has two parts, and both are needed:

1. A declaration: one JSON line in `src/agent_movement/fixtures/mobilitybench-local-smoke/cases.jsonl` with the fields `scenario`, `question_ids`, `baseline`, `expected`, `expectation` and `description` (checked by `mobilitybench.validate_case`). `expectation` is `pass`, `known_gap` or `gap_closed`. A `known_gap` case must also give `expected_fix` and a `closed_observation` that differs from `expected`; a `gap_closed` case gives `expected_fix` only; a `pass` case gives neither.
2. An evaluator: a function `case_<scenario>(workdir: Path) -> tuple[str, Evidence]` in `mobilitybench.py`, defined **above** the `EVALUATORS = {...}` line, because that dictionary is built from the module globals at import time. It must create everything it uses inside `workdir` and return `(observed, evidence)`; evidence values must be `str`, `int` or `bool`, and never task text.

If only one part exists, the CLI exits 2 with `case_fixture_invalid`: a declaration without an evaluator is reported as `no evaluator for scenario <name>`, and an evaluator without a declaration as `packaged declarations do not cover every evaluator`. In a rehearsal on a scratch copy of the package with one added `pass` case, the declaration alone and the evaluator alone each exited 2, and both together gave 21 cases (18 `pass`, 3 `known_gap`) with exit 0. `tests/test_mobilitybench.py` derives its counts from the declarations and passed, but `tests/test_mobilitybench_v01.py` (`test_run_smoke_report_verify_and_legacy_entrypoint`) still asserts that the smoke output has exactly 20 lines and failed, so update that number in the same change.

**MobilityBench v0.1 (`fixtures/mobilitybench-v0.1/`).** This release is frozen and must not be edited in place: a new task, rubric or ground truth needs a new suite version and a new fixture directory ([versioning rule](mobilitybench-v0.1.md#frozen-release)). At `4809bdf` the harness knows one suite (`mobilitybench_v01.SUITES = {"v0.1": ...}`), and `verify_fixtures` requires the manifest's `suite_version` to equal `SUITE_VERSION`. A new release therefore also needs a change in `mobilitybench_v01.py` and in the `package-data` pattern in `pyproject.toml`. You can draft and test a case in a copy without touching the release:

```bash
DRAFT=$(mktemp -d)/mobilitybench-draft
cp -r src/agent_movement/fixtures/mobilitybench-v0.1 "$DRAFT"
# append one JSON object per line to "$DRAFT/tasks.jsonl" (the fields checked by mobilitybench_v01.validate_task)
python tools/mobilitybench_freeze.py --fixtures "$DRAFT"            # recomputes ground_truth.jsonl and MANIFEST.json
python tools/mobilitybench_freeze.py --fixtures "$DRAFT" --check    # exit 0
agent-movement bench verify --fixtures "$DRAFT"                   # exit 0
agent-movement bench run --fixtures "$DRAFT" --seeds 1103 --repeats 1 --out "$DRAFT/../draft.jsonl"   # exit 0
```

Before the freeze step, `verify` exits 2 with `fixture digest mismatch: tasks.jsonl`. In a rehearsal with one added task (a copy of `doc-policy-digest` under a new `task_id`), every command above exited 0, and the new task appeared in 6 attempt records (one per mode). A negative case is a line in `negative.jsonl` whose `attack` names a handler in `mobilitybench_v01.SECURITY`. A new kind of attack needs a new handler in the code.
