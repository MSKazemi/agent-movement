# How to cite Agent Movement

The machine-readable citation metadata for this repository is in [`CITATION.cff`](../CITATION.cff) ([Citation File Format](https://citation-file-format.github.io/) 1.2.0). GitHub reads this file and shows a **"Cite this repository"** button in the repository sidebar.

The first tagged release is **v0.2.0** (2026-10-16; see the [CHANGELOG](../CHANGELOG.md)). There is no DOI. Cite the tag, or for any later state the exact **commit SHA** (see [Pin a version](#pin-a-version-by-commit-sha)).

## Cite the repository

### BibTeX

`cffconvert -f bibtex` (cffconvert 2.0.0) produces the following from `CITATION.cff`:

```bibtex
@misc{YourReferenceHere,
author = {Seyedkazemi Ardebili, Mohsen},
month = {10},
title = {Agent Movement: research notes and curated news and paper corpora on portable, interoperable AI-agent work},
url = {https://github.com/MSKazemi/agent-movement},
year = {2026}
}
```

The generated entry takes its year and month from `date-released` but omits the version (cffconvert's BibTeX output has no version field). For a reproducible reference, add the release tag or the commit you used, and give the entry a real key:

```bibtex
@misc{seyedkazemiardebili_agent_movement,
  author       = {Seyedkazemi Ardebili, Mohsen},
  title        = {Agent Movement: research notes and curated news and paper corpora on portable, interoperable AI-agent work},
  year         = {<year of the commit you used>},
  howpublished = {GitHub repository},
  url          = {https://github.com/MSKazemi/agent-movement},
  note         = {Commit <full 40-character SHA>, accessed <YYYY-MM-DD>}
}
```

### Plain text

> Seyedkazemi Ardebili, M. (*year*). *Agent Movement: research notes and curated news and paper corpora on portable, interoperable AI-agent work* [Data set]. GitHub. https://github.com/MSKazemi/agent-movement (commit *SHA*, accessed *YYYY-MM-DD*).

Replace the italic placeholders with the year, commit SHA and access date of the state you used.

## Cite a single corpus item

The two corpora are curated collections of **other people's work**. If you rely on what one item reports, **cite the original source**, not only this repository.

1. Find the item in [`docs/news-corpus/news.bib`](news-corpus/news.bib) (100 news items, ids `AMN-001` … `AMN-100`) or [`docs/paper-corpus/papers.bib`](paper-corpus/papers.bib) (75 papers, ids `AMP-001` … `AMP-075`). Each entry's `note` field carries its corpus id, for example `note = {AMP-008; theme P1}`.
2. Copy that entry into your bibliography and cite it by its key, for example `fuggetta1998understanding` (AMP-008) or `anthropic2024introducing` (AMN-001). Keys follow `<publisher><year><first-title-word>` for news items and `<first-author surname><year><first title word>` for papers.
3. The `.bib` files use **biblatex** fields (`@online`, `journaltitle`, `date`, `urldate`, `eprint`). Use them with `biblatex` + `biber`. For classic BibTeX, convert the fields (for example `journaltitle` to `journal`, `@online` to `@misc`).
4. For papers, prefer the DOI or arXiv identifier in the entry over the corpus URL.
5. If you also use the corpus itself (its selection, coding, summaries or statistics), cite this repository as well, and record the **corpus id** and the **commit SHA**. Ids are meant to be stable (new items get the next free id), but records can be corrected between commits, so the commit identifies the exact record you used. For example:

> Item AMP-008 of the Agent Movement paper corpus (Seyedkazemi Ardebili, commit *SHA*), citing Fuggetta, Picco and Vigna (1998), doi:10.1109/32.685258.

The canonical records are in [`news.jsonl`](news-corpus/news.jsonl) and [`papers.jsonl`](paper-corpus/papers.jsonl). The selection protocol for each corpus is described in its README ([news](news-corpus/README.md), [papers](paper-corpus/README.md)).

## Pin a version by commit SHA

The repository changes over time, and the corpora may be extended or corrected. To make a citation reproducible, cite one commit:

```bash
git clone https://github.com/MSKazemi/agent-movement.git
cd agent-movement
git rev-parse HEAD                      # full SHA of the state you used
git log -1 --format='%H %cd' --date=short   # SHA and commit date
```

A permanent link to that exact state has the form:

```text
https://github.com/MSKazemi/agent-movement/tree/<SHA>
https://github.com/MSKazemi/agent-movement/blob/<SHA>/docs/paper-corpus/papers.jsonl
```

To retrieve that state later:

```bash
git checkout <SHA>
```

Use the full 40-character SHA in publications. Short SHAs can become ambiguous as the history grows.
