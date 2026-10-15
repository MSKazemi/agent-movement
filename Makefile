# Quality gates for the agent-movement corpora (news: AMN-, papers: AMP-).
# The corpus tools are stdlib-only Python; see docs/development.md.

PYTHON ?= python3
BIBER  ?= biber
# BIB_STRICT=1 makes biber datamodel warnings fail `make bib` (errors always fail).
BIB_STRICT ?= 0
# Keep the tree clean: paper_corpus.py imports news_corpus.py.
export PYTHONDONTWRITEBYTECODE := 1

NEWS_DIR   := docs/news-corpus
PAPER_DIR  := docs/paper-corpus
NEWS_RAW   := $(NEWS_DIR)/raw/T[1-7].jsonl
PAPER_RAW  := $(PAPER_DIR)/raw/P[1-6].jsonl
NEWS_GEN   := news.jsonl excluded.jsonl flow.json news.csv news.bib digest.md stats.json
PAPER_GEN  := papers.jsonl excluded.jsonl flow.json papers.csv papers.bib digest.md stats.json
NEWS_MERGE  = $(PYTHON) tools/news_corpus.py merge $(NEWS_RAW) --target 100 --manual $(NEWS_DIR)/screening.json
PAPER_MERGE = $(PYTHON) tools/paper_corpus.py merge $(PAPER_RAW)
# Later rounds are appended in order so published AMP- IDs stay pinned (see paper README §6).
PAPER_APPEND = $(PYTHON) tools/paper_corpus.py append $(PAPER_DIR)/raw/round2.jsonl --round round2
PAPER_AUDIT2 = $(PYTHON) tools/paper_corpus.py apply-audit $(PAPER_DIR)/audit-round2.jsonl

.DEFAULT_GOAL := all
.PHONY: all help check build analysis verify-analysis verify-determinism sources sources-index test bib

all: check verify-determinism verify-analysis sources test bib ## Run every gate

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

check: ## Validate news.jsonl and papers.jsonl (schema, IDs, cite keys)
	$(PYTHON) tools/news_corpus.py check
	$(PYTHON) tools/paper_corpus.py check

build: ## Rebuild both corpora in place from raw/ + screening + audit (as documented)
	$(NEWS_MERGE)
	$(PYTHON) tools/news_corpus.py apply-audit $(NEWS_DIR)/audit.jsonl
	$(PAPER_MERGE)
	$(PYTHON) tools/paper_corpus.py apply-audit $(PAPER_DIR)/audit.jsonl
	$(PAPER_APPEND)
	$(PAPER_AUDIT2)

verify-determinism: ## Rebuild both corpora into a temp dir and require byte-identical output
	@set -e; tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	mkdir -p "$$tmp/news" "$$tmp/papers"; \
	$(NEWS_MERGE) --out "$$tmp/news" >/dev/null; \
	$(PYTHON) tools/news_corpus.py apply-audit $(NEWS_DIR)/audit.jsonl --out "$$tmp/news" >/dev/null; \
	$(PAPER_MERGE) --out "$$tmp/papers" >/dev/null; \
	$(PYTHON) tools/paper_corpus.py apply-audit $(PAPER_DIR)/audit.jsonl --out "$$tmp/papers" >/dev/null; \
	$(PAPER_APPEND) --out "$$tmp/papers" >/dev/null; \
	$(PAPER_AUDIT2) --out "$$tmp/papers" >/dev/null; \
	fail=0; \
	for f in $(NEWS_GEN); do \
	  if cmp -s "$$tmp/news/$$f" "$(NEWS_DIR)/$$f"; then echo "identical  $(NEWS_DIR)/$$f"; \
	  else echo "DIFFERS    $(NEWS_DIR)/$$f"; diff -u "$(NEWS_DIR)/$$f" "$$tmp/news/$$f" | head -40; fail=1; fi; \
	done; \
	for f in $(PAPER_GEN); do \
	  if cmp -s "$$tmp/papers/$$f" "$(PAPER_DIR)/$$f"; then echo "identical  $(PAPER_DIR)/$$f"; \
	  else echo "DIFFERS    $(PAPER_DIR)/$$f"; diff -u "$(PAPER_DIR)/$$f" "$$tmp/papers/$$f" | head -40; fail=1; fi; \
	done; \
	if [ $$fail -ne 0 ]; then echo "verify-determinism: committed corpus does not match a fresh rebuild (run 'make build')"; exit 1; fi; \
	echo "verify-determinism: ok (both corpora reproduce byte for byte)"

analysis: ## Regenerate docs/corpus-analysis/ from both corpora
	$(PYTHON) tools/corpus_analysis.py

verify-analysis: ## Require docs/corpus-analysis/ to match a fresh regeneration
	@set -e; tmp=$$(mktemp -d docs/.verify-analysis.XXXXXX); trap 'rm -rf "$$tmp"' EXIT; \
	$(PYTHON) tools/corpus_analysis.py --out "$$tmp" >/dev/null; \
	fail=0; for f in timeline.md coverage.md; do \
	  cmp -s "$$tmp/$$f" "docs/corpus-analysis/$$f" || { diff -u "docs/corpus-analysis/$$f" "$$tmp/$$f" | head -40; fail=1; }; \
	done; \
	if [ $$fail -ne 0 ]; then echo "verify-analysis: docs/corpus-analysis is stale (run 'make analysis')"; exit 1; fi; \
	echo "verify-analysis: ok (timeline.md, coverage.md current)"

sources: ## Require every external URL in README.md and docs/ to be indexed in docs/sources.md
	$(PYTHON) tools/sources_index.py check

sources-index: ## Regenerate the URL index section of docs/sources.md (keeps hand-edited dates)
	$(PYTHON) tools/sources_index.py generate

test: ## Run pytest if tests/ exists
	@if [ -d tests ]; then $(PYTHON) -m pytest -q; \
	else echo "test: skipped (no tests/ directory)"; fi

bib: ## Validate news.bib and papers.bib with biber --tool (skipped if biber is absent)
	@if ! command -v $(BIBER) >/dev/null 2>&1; then echo "bib: skipped (biber not installed)"; exit 0; fi; \
	set -e; tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; status=0; \
	for b in $(NEWS_DIR)/news.bib $(PAPER_DIR)/papers.bib; do \
	  if ! $(BIBER) --tool --validate-datamodel --output-directory "$$tmp" "$$b" >"$$tmp/log" 2>&1; then \
	    cat "$$tmp/log"; echo "bib: biber failed on $$b"; status=1; continue; fi; \
	  w=$$(grep -cE '^(WARN|ERROR) ' "$$tmp/log" || true); \
	  grep -E '^(WARN|ERROR) ' "$$tmp/log" || true; \
	  echo "bib: $$b parsed by biber, $$w warning(s)"; \
	  if [ "$(BIB_STRICT)" = 1 ] && [ "$$w" -gt 0 ]; then status=1; fi; \
	done; \
	exit $$status
