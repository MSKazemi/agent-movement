# Contributing to Agent Movement

Thank you for helping. This repository is a research project: documentation, two curated corpora (news `AMN-NNN`, papers `AMP-NNN`) and an experimental Python package of synthetic, local prototypes. Contributions that are especially welcome:

- corrections to research claims, with a primary source;
- protocol compatibility experiments and concrete failure modes;
- reproducible benchmarks and tests;
- fixes to the corpus tools and the `agent_movement` package.

For anything larger than a small fix, open an issue first with one of the [issue forms](https://github.com/MSKazemi/agent-movement/issues/new/choose) (bug, research claim correction, feature or experiment). Security problems go through [SECURITY.md](SECURITY.md), never a public issue.

Contributions are plain pull requests: no CLA and no DCO sign-off. The repository has **no license yet** (see the [README](README.md)); do not add one in a pull request.

## Repository layout

| Path | Contents |
|---|---|
| `docs/` | Research documents, plus the [news corpus](docs/news-corpus/README.md) and [paper corpus](docs/paper-corpus/README.md) |
| `data/` | Machine-readable CSV tables used by the documents |
| `tools/` | Stdlib-only corpus, analysis and MobilityBench fixture tools |
| `src/agent_movement/` | Experimental package (stdlib-only core, optional extras) |
| `tests/` | pytest suite for the package and the corpus tools |

## Development setup

You need Python 3.11 or newer, `make` and `git`. Optional: [`uv`](https://docs.astral.sh/uv/), and `biber` for the bibliography gate (`sudo apt-get install biber`).

Create the virtual environment **outside** the working tree, so it is never committed:

```sh
git clone https://github.com/MSKazemi/agent-movement.git
cd agent-movement
export VENV="$HOME/.venvs/agent-movement"   # any directory outside the working tree
```

With `venv` and `pip` (what CI uses):

```sh
python3 -m venv "$VENV"
. "$VENV/bin/activate"
python -m pip install -e . "pytest>=9.1"
```

Or with `uv`:

```sh
uv venv --python 3.13 "$VENV"
. "$VENV/bin/activate"
uv pip install -e . "pytest>=9.1"
```

The core package and the corpus tools use only the standard library. Each optional extra adds one experiment:

| Extra | Adds | Used by |
|---|---|---|
| `a2a` | `a2a-sdk[http-server]`, `uvicorn` | A2A v1 adapter (`agent_movement.a2a_demo`) |
| `ed25519` | `cryptography` | Ed25519 peer keys (`peer_demo --alg Ed25519`) |
| `relocation` | pinned `langgraph` and SQLite checkpointer | checkpoint relocation (`agent_movement.relocation_demo`) |
| `signing` | `cryptography` | signed movement receipts (`agent_movement.receipts`) |

Install all of them (CI tests the extras on CPython 3.11 and 3.13):

```sh
python -m pip install -e '.[a2a,ed25519,relocation,signing]'
```

With `uv`, use `uv pip install -e '.[a2a,ed25519,relocation,signing]'` instead.

## Quality gates

Run these from the repository root with the environment active. They are the same checks CI runs ([`corpus.yml`](.github/workflows/corpus.yml), [`python-smoke.yml`](.github/workflows/python-smoke.yml)).

```sh
make all                  # check, verify-determinism, verify-analysis, test, bib
make bib BIB_STRICT=1     # CI also fails on biber warnings
python -m pytest -q       # all tests: agent_movement + corpus tooling
```

`make bib` is skipped with a message if `biber` is not installed; CI always runs it. `make help` lists every target, and [docs/development.md](docs/development.md) explains each one.

Tests that need an optional extra are **skipped, not failed**, when the extra is missing. If you change `src/` or `tests/`, run the suite both with and without the extras, and run the demos and benchmark checks:

```sh
python -m agent_movement.demo
python -m agent_movement.peer_demo
python tools/mobilitybench_freeze.py --check
python -m agent_movement.mobilitybench verify --suite v0.1
```

With all extras installed, also run:

```sh
python -m agent_movement.a2a_demo
python -m agent_movement.peer_demo --alg Ed25519
python -m agent_movement.relocation_demo
python -m agent_movement.receipts verify tests/fixtures/movement-receipts/01-valid-delegation --now 2026-10-16T00:00:00Z
```

CI also checks relative Markdown links offline ([`docs-links.yml`](.github/workflows/docs-links.yml)), so keep links between files in this repository valid.

### Corpus rules

- Never hand-edit generated corpus files (`*.csv`, `*.bib`, `digest.md`, `stats.json`, `flow.json`, `excluded.jsonl`). Correct a record through the corpus's audit file, then run `make build` and `make all`. See [Editing records](docs/development.md#editing-records).
- `AMN-` and `AMP-` IDs and cite keys are **stable once published**: never renumber, reuse or reassign them.
- Commit regenerated files together with the change that caused them.

## Evidence and citation standards

The documents are research notes, so every claim must be traceable.

- **Separate fact from proposal.** Label verified protocol or product behaviour, research findings, project hypotheses and project design proposals as such. Do not present a hypothesis or a proposal as fact, and do not generalize from synthetic, local results.
- **Cite primary sources:** the specification, standard, paper (DOI or arXiv ID) or official documentation, not a secondary summary. Link the exact version of a versioned specification.
- **Record access dates.** Claims about upstream projects change, so give the date you checked them (`checked YYYY-MM-DD`). Add every new external source to [docs/sources.md](docs/sources.md), or to the document's own dated source list for the documents that keep one (listed at the top of `docs/sources.md`).
- **Cite corpus items by ID** (`AMN-NNN`, `AMP-NNN`) and, for reproducibility, the commit SHA. See [docs/how-to-cite.md](docs/how-to-cite.md).
- **Report how numbers were produced.** Test totals, benchmark results and counts state the command, the date and the environment (Python version, extras).
- **State uncertainty** where the evidence is incomplete or contested.

## Data hygiene

Never commit real credentials, tokens, private keys, personal data, private conversations or confidential task payloads. Tests and fixtures use synthetic data and keys generated only for the test.

## Commits and pull requests

- Branch from `main` and open the pull request against `main`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) prefixes, as in the existing history: `docs:`, `feat:`, `fix:`, `test:`, `ci:`, `build:`, `chore:`. Write a short imperative summary, for example `docs: correct the A2A version in the standards tracker`.
- Keep one logical change per commit, and reference the issue in the body (`Refs #123` or `Fixes #123`).
- Commits carry the human author only; no co-author trailers.
- Fill in the pull request checklist and make sure CI is green.
