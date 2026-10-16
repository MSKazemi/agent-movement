## Summary

<!-- What changes and why. Link the issue: Refs #123 or Fixes #123. -->

## Gates

<!-- Tick what you ran locally and paste any notable output. See CONTRIBUTING.md#quality-gates. -->

- [ ] `make all` passes (check, verify-determinism, verify-analysis, test, bib)
- [ ] `make bib BIB_STRICT=1` passes, or this PR does not touch `docs/news-corpus/`, `docs/paper-corpus/` or `tools/`
- [ ] `python -m pytest -q` passes with the core only
- [ ] If `src/` or `tests/` changed: `python -m pytest -q` passes with all extras (`.[a2a,ed25519,relocation,signing]`), and the demos in CONTRIBUTING.md run
- [ ] Regenerated corpus or analysis files are committed with the change that caused them, and no generated file was hand-edited
- [ ] Relative Markdown links are valid

## Evidence and docs

- [ ] Facts, findings, hypotheses and proposals are labelled as such
- [ ] New claims cite primary sources with access dates, and new sources are added to `docs/sources.md` (or the document's own source list)
- [ ] Reported numbers state the command, date and environment that produced them
- [ ] Affected documentation (README, `docs/`) is updated

## Hygiene

- [ ] No real secrets, credentials, personal data or confidential payloads; fixtures are synthetic
- [ ] Conventional commit messages (`docs:`, `feat:`, `fix:`, `test:`, `ci:`, `build:`, `chore:`); commits carry the human author only, with no co-author trailers
