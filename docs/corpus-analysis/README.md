# Corpus analysis: timeline and coverage

Two generated views over the curated evidence base of this repository:

- [`timeline.md`](timeline.md) lists every item of the [news corpus](../news-corpus/README.md) (`AMN-…`) and the [paper corpus](../paper-corpus/README.md) (`AMP-…`) in date order. Items are grouped by year, and by month for 2024–2026. Each line gives the date as stated by the source, the ID, a shortened title and the theme code.
- [`coverage.md`](coverage.md) holds descriptive tables:
  1. items per year × theme;
  2. news by source type, primary/secondary source, claim status and publisher;
  3. papers by publication type, peer-review status and contribution type;
  4. co-occurrence of the multi-label `movement_operations` codes, and those codes by theme;
  5. a keyword crosswalk to the four movement operations defined in the [project README](../../README.md): delegation/handoff, portable task context, runtime relocation and cross-framework migration;
  6. coverage gaps, written as hypotheses for the next search round.

Both files are generated. Do not edit them by hand; edit the canonical `news.jsonl` / `papers.jsonl` and regenerate.

## Regenerate

```bash
python3 tools/corpus_analysis.py
```

Optional arguments: `--news PATH`, `--papers PATH` and `--out DIR`. The defaults are `docs/news-corpus/news.jsonl`, `docs/paper-corpus/papers.jsonl` and this directory. The script uses only the Python standard library.

The output is deterministic. Rows are sorted, no wall-clock time is written, and the only date in the files ("data as of") is the latest `date_accessed` in the input records. Running the script twice on the same inputs gives byte-identical files. Nothing about corpus size is hard-coded, so records appended later (for example `AMP-076` onward) appear on the next run. Theme labels come from `tools/news_corpus.py` and `tools/paper_corpus.py`. A theme code without a label there is still counted, with the label "label not defined in tools".

## Limitations

- **The counts describe the samples, not the field.** Each corpus was built from a fixed set of themes, with a capped number of candidates per theme and a single search date. News was also restricted to a publication window, selected theme-balanced to a target size and ranked newest-first within each theme. Differences between years, themes or source types therefore reflect the protocol at least as much as real-world activity. No count here supports a causal or trend claim.
- **Themes are search strata.** Each record has exactly one `theme`: the search stream that found it. A theme is not an exhaustive topic label. A low count in a theme × operation cell can mean that the work exists but was found by another theme, or by none.
- **The crosswalk is a heuristic.** It matches a published list of keyword stems against title + summary. It has not been validated against human judgement. It misses paraphrases, and broad stems over-count. It is shown next to the curator-assigned `movement_operations` codes so the disagreement is visible. The coded labels are themselves a single curator's judgement.
- **Coverage gaps are hypotheses.** The gap list is mechanical: every cell at or below a fixed threshold. Each entry is a question for the next search round, not a finding that the topic is under-researched.
- **Dates come from the sources.** Some papers are dated only to a year or month. The timeline lists them after the fully dated items of the same period. Publication date is not the date an event happened.
