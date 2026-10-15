#!/usr/bin/env python3
"""Build and validate the agent-movement scholarly paper corpus (stdlib only).

Usage:
  python3 tools/paper_corpus.py merge RAW1.jsonl [...] [--manual screening.json] [--out DIR]
      Validate raw theme files, apply manual screening, remove duplicates
      (DOI, arXiv ID, near-identical title), assign IDs (AMP-NNN) and cite keys,
      write papers.jsonl and excluded.jsonl, then run `build`.
  python3 tools/paper_corpus.py build [--out DIR]
      Regenerate papers.csv, papers.bib, digest.md and stats.json.
  python3 tools/paper_corpus.py check [--out DIR]
      Validate papers.jsonl only (exit 1 on any error).
  python3 tools/paper_corpus.py apply-audit AUDIT.jsonl [--out DIR]
      Apply an independent audit's corrected_summary / corrected_fields, then `build`.

Default DIR is docs/paper-corpus. `merge` numbers from AMP-001, so run it on a
fresh directory for a new collection round and append the results by hand.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from news_corpus import OPERATIONS, bib_escape, load_jsonl, md_cell, norm_title, norm_url, write_jsonl

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "paper-corpus"

THEMES = {
    "P1": "Mobile agents and agent/process migration",
    "P2": "Agent communication protocols and interoperability",
    "P3": "Security of LLM agents, tool use and multi-agent handoffs",
    "P4": "Agent identity, delegated authorization, accountability and governance",
    "P5": "Agent memory, state, context and durable execution",
    "P6": "Multi-agent orchestration, delegation and portable agent specifications",
}
PUB_TYPES = {"journal", "conference", "workshop", "preprint", "book-chapter", "tech-report", "whitepaper"}
CONTRIB = {"system", "empirical", "survey", "position", "formal", "benchmark", "taxonomy"}
VERIF = {"crossref", "arxiv", "dblp", "semantic-scholar", "publisher"}
RAW_KEYS = [
    "theme", "title", "authors", "year", "date_published", "venue", "publication_type",
    "peer_reviewed", "doi", "arxiv_id", "url", "date_accessed", "technologies",
    "movement_operations", "contribution_type", "summary", "relevance", "verified_metadata",
    "verification_source", "search_query", "notes",
]
FINAL_KEYS = ["id", "citekey"] + RAW_KEYS
DATE_RE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
ARXIV_RE = re.compile(r"^(\d{4}\.\d{4,5}|[a-z\-]+(\.[A-Z]{2})?/\d{7})$")


def validate(r: dict, keys: list[str]) -> list[str]:
    errs = []
    if missing := [k for k in keys if k not in r]:
        errs.append(f"missing keys {missing}")
    if extra := [k for k in r if k not in keys]:
        errs.append(f"unexpected keys {extra}")
    if r.get("theme") not in THEMES:
        errs.append(f"bad theme {r.get('theme')!r}")
    if not isinstance(r.get("year"), int) or not 1900 <= r["year"] <= 2026:
        errs.append(f"bad year {r.get('year')!r}")
    d = str(r.get("date_published", ""))
    if not DATE_RE.match(d) or (isinstance(r.get("year"), int) and not d.startswith(str(r["year"]))):
        errs.append(f"bad date {d!r} for year {r.get('year')}")
    if r.get("publication_type") not in PUB_TYPES:
        errs.append(f"bad publication_type {r.get('publication_type')!r}")
    if r.get("contribution_type") not in CONTRIB:
        errs.append(f"bad contribution_type {r.get('contribution_type')!r}")
    if r.get("verification_source") not in VERIF:
        errs.append(f"bad verification_source {r.get('verification_source')!r}")
    if r.get("doi") and not DOI_RE.match(r["doi"]):
        errs.append(f"bad doi {r['doi']!r}")
    if r.get("arxiv_id") and not ARXIV_RE.match(r["arxiv_id"]):
        errs.append(f"bad arxiv_id {r['arxiv_id']!r}")
    if not (r.get("doi") or r.get("arxiv_id") or r.get("url")):
        errs.append("no persistent identifier or url")
    if not str(r.get("url", "")).startswith(("http://", "https://")):
        errs.append("bad url")
    ops = r.get("movement_operations") or []
    if not ops or not set(ops) <= OPERATIONS:
        errs.append(f"bad movement_operations {ops}")
    for k in ("authors", "technologies"):
        if not isinstance(r.get(k), list):
            errs.append(f"{k} must be a list")
    if not r.get("authors"):
        errs.append("empty authors")
    for k in ("peer_reviewed", "verified_metadata"):
        if not isinstance(r.get(k), bool):
            errs.append(f"{k} must be bool")
    for k in ("title", "venue", "summary", "relevance"):
        if not str(r.get(k, "")).strip():
            errs.append(f"empty {k}")
    return errs


def ident(r: dict) -> set[str]:
    ids = set()
    if r["doi"]:
        ids.add("doi:" + r["doi"].lower())
    if r["arxiv_id"]:
        ids.add("arxiv:" + r["arxiv_id"].lower())
    ids.add("url:" + norm_url(r["url"]))
    return ids


def rank_key(r: dict):
    return (not r["verified_metadata"], not r["peer_reviewed"], r["year"], r["title"].lower())


def ascii_word(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def citekey(r: dict, used: set[str]) -> str:
    last = ascii_word(r["authors"][0].split()[-1]) or "anon"
    stop = {"the", "a", "an", "of", "and", "for", "to", "in", "on", "with", "is", "how", "why", "what", "towards", "toward"}
    words = [w for w in norm_title(r["title"]).split() if w not in stop]
    base = f"{last}{r['year']}{ascii_word(words[0]) if words else 'paper'}"
    key, i = base, 0
    while key in used:
        i += 1
        key = base + "abcdefghijklmnopqrstuvwxyz"[i - 1]
    used.add(key)
    return key


def merge(raw_paths: list[Path], manual: Path | None) -> None:
    manual_excl = {norm_title(m["title"]): m["reason"] for m in json.loads(manual.read_text())} if manual else {}
    candidates, excluded, flow = [], [], Counter()
    for p in raw_paths:
        for r in load_jsonl(p):
            flow["identified"] += 1
            flow[f"identified:{r.get('theme')}"] += 1
            if errs := validate(r, RAW_KEYS):
                excluded.append({**r, "exclusion_reason": "schema: " + "; ".join(errs)})
                flow["excluded_schema"] += 1
            elif not r["verified_metadata"]:
                excluded.append({**r, "exclusion_reason": "metadata not verified against an authoritative source"})
                flow["excluded_unverified"] += 1
            elif norm_title(r["title"]) in manual_excl:
                excluded.append({**r, "exclusion_reason": "manual screening: " + manual_excl[norm_title(r["title"])]})
                flow["excluded_manual_screening"] += 1
            else:
                candidates.append(r)

    kept: list[dict] = []
    for r in sorted(candidates, key=rank_key):
        t = norm_title(r["title"])
        dup = next((k for k in kept if ident(k) & ident(r)
                    or SequenceMatcher(None, norm_title(k["title"]), t).ratio() >= 0.9), None)
        if dup:
            excluded.append({**r, "exclusion_reason": f"duplicate of '{dup['title']}' ({dup['theme']})"})
            flow["excluded_duplicate"] += 1
        else:
            kept.append(r)

    kept.sort(key=lambda r: (r["year"], r["date_published"], r["title"].lower()))
    used: set[str] = set()
    final = [{"id": f"AMP-{i:03d}", "citekey": citekey(r, used), **{k: r[k] for k in RAW_KEYS}}
             for i, r in enumerate(kept, 1)]
    flow["included"] = len(final)
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "papers.jsonl", final)
    write_jsonl(OUT / "excluded.jsonl", excluded)
    (OUT / "flow.json").write_text(json.dumps(dict(sorted(flow.items())), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(sorted(flow.items())), indent=2))
    build()


def to_bib(r: dict) -> str:
    t = r["publication_type"]
    entry = {"journal": "article", "conference": "inproceedings", "workshop": "inproceedings",
             "book-chapter": "incollection", "tech-report": "report", "whitepaper": "report",
             "preprint": "online"}[t]
    f = [("author", " and ".join(bib_escape(a) for a in r["authors"])),
         ("title", "{" + bib_escape(r["title"]) + "}")]
    if entry == "article":
        f.append(("journaltitle", bib_escape(r["venue"])))
    elif entry in ("inproceedings", "incollection"):
        f.append(("booktitle", bib_escape(r["venue"])))
    elif entry == "report":
        f += [("institution", bib_escape(r["venue"])), ("type", "Technical report" if t == "tech-report" else "White paper")]
    elif entry == "online" and r["venue"].lower() not in ("arxiv", "arxiv preprint"):
        f.append(("organization", bib_escape(r["venue"])))
    f += [("date", r["date_published"]), ("year", str(r["year"]))]
    if r["doi"]:
        f.append(("doi", r["doi"]))
    if r["arxiv_id"]:
        f += [("eprint", r["arxiv_id"]), ("eprinttype", "arxiv")]
    f += [("url", r["url"]), ("urldate", r["date_accessed"]),
          ("note", bib_escape(f"{r['id']}; theme {r['theme']}" + ("" if r["peer_reviewed"] else "; not peer reviewed")))]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in f)
    return f"@{entry}{{{r['citekey']},\n{body}\n}}\n"


def link(r: dict) -> str:
    if r["doi"]:
        return f"[doi:{r['doi']}](https://doi.org/{r['doi']})"
    if r["arxiv_id"]:
        return f"[arXiv:{r['arxiv_id']}](https://arxiv.org/abs/{r['arxiv_id']})"
    return f"<{r['url']}>"


def authors_short(a: list[str]) -> str:
    return a[0] if len(a) == 1 else f"{a[0]} and {a[1]}" if len(a) == 2 else f"{a[0]} et al."


def build() -> None:
    rows = load_jsonl(OUT / "papers.jsonl")
    if errors := check(rows):
        sys.exit("\n".join(errors))
    with (OUT / "papers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FINAL_KEYS)
        w.writeheader()
        for r in rows:
            w.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in r.items()})
    (OUT / "papers.bib").write_text(
        "% Agent Movement paper corpus — generated by tools/paper_corpus.py; do not edit by hand.\n"
        "% biblatex entries; use with biber.\n\n" + "\n".join(to_bib(r) for r in rows), encoding="utf-8")
    stats = {
        "n": len(rows),
        "by_theme": dict(sorted(Counter(r["theme"] for r in rows).items())),
        "by_decade": dict(sorted(Counter(f"{r['year'] // 10 * 10}s" for r in rows).items())),
        "by_year_2020s": dict(sorted(Counter(r["year"] for r in rows if r["year"] >= 2020).items())),
        "by_publication_type": dict(Counter(r["publication_type"] for r in rows).most_common()),
        "by_contribution_type": dict(Counter(r["contribution_type"] for r in rows).most_common()),
        "by_operation": dict(Counter(o for r in rows for o in r["movement_operations"]).most_common()),
        "peer_reviewed": sum(r["peer_reviewed"] for r in rows),
        "with_doi": sum(bool(r["doi"]) for r in rows),
        "with_arxiv": sum(bool(r["arxiv_id"]) for r in rows),
        "verification_source": dict(Counter(r["verification_source"] for r in rows).most_common()),
        "year_range": [min(r["year"] for r in rows), max(r["year"] for r in rows)],
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    (OUT / "digest.md").write_text(render_digest(rows, stats), encoding="utf-8")
    print(f"built {len(rows)} records -> papers.csv, papers.bib, digest.md, stats.json")


def render_digest(rows: list[dict], s: dict) -> str:
    L = ["# Agent Movement paper digest", "",
         "<!-- Generated by tools/paper_corpus.py from papers.jsonl; do not edit by hand. -->", "",
         f"**{s['n']} papers**, {s['year_range'][0]}–{s['year_range'][1]}. "
         f"{s['peer_reviewed']} peer reviewed, {s['n'] - s['peer_reviewed']} preprints, white papers or reports. "
         "Method and limitations: [README](README.md). Data: [papers.jsonl](papers.jsonl), "
         "[papers.csv](papers.csv). Citations: [papers.bib](papers.bib).", "",
         "Summaries are paraphrased from abstracts and papers. Cite the paper, not the summary.", "",
         "## Overview", "", "| Theme | Papers |", "|---|---:|"]
    L += [f"| {t}: {THEMES[t]} | {n} |" for t, n in s["by_theme"].items()]
    L += ["", "| Movement operation (multi-label) | Papers |", "|---|---:|"]
    L += [f"| {o} | {n} |" for o, n in s["by_operation"].items()]
    L += ["", "## Index", "", "| ID | Year | Theme | Paper | Venue | Peer reviewed |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| [{r['id']}](#{r['id'].lower()}) | {r['year']} | {r['theme']} | "
                 f"{md_cell(authors_short(r['authors']))}: {md_cell(r['title'])} | {md_cell(r['venue'])} | "
                 f"{'yes' if r['peer_reviewed'] else 'no'} |")
    for t in THEMES:
        items = [r for r in rows if r["theme"] == t]
        if not items:
            continue
        L += ["", f"## {t}: {THEMES[t]}", ""]
        for r in items:
            L += [f"### {r['id']}", "",
                  f"{', '.join(r['authors'])} ({r['year']}). **{r['title']}**. *{r['venue']}*. {link(r)}. "
                  f"Cite key: `{r['citekey']}`.", "",
                  r["summary"], "",
                  f"- **Relevance:** {r['relevance']}",
                  f"- **Operations:** {', '.join(r['movement_operations'])}. "
                  f"**Contribution:** {r['contribution_type']}. "
                  f"**Type:** {r['publication_type']}{'' if r['peer_reviewed'] else ' (not peer reviewed)'}.",
                  f"- **Metadata verified via:** {r['verification_source']}." + (f" Note: {r['notes']}" if r["notes"] else ""),
                  ""]
    return "\n".join(L).rstrip() + "\n"


def check(rows: list[dict] | None = None) -> list[str]:
    rows = rows if rows is not None else load_jsonl(OUT / "papers.jsonl")
    errors = [f"{r.get('id')}: {e}" for r in rows for e in validate(r, FINAL_KEYS)]
    for field in ("id", "citekey"):
        if dupes := [v for v, n in Counter(r.get(field) for r in rows).items() if n > 1]:
            errors.append(f"duplicate {field}: {dupes}")
    seen: dict[str, str] = {}
    for r in rows:
        for i in ident(r):
            if i in seen and not i.startswith("url:"):
                errors.append(f"duplicate identifier {i}: {seen[i]} and {r['id']}")
            seen[i] = r["id"]
    return errors


def apply_audit(audit_path: Path) -> None:
    rows = load_jsonl(OUT / "papers.jsonl")
    by_id = {r["id"]: r for r in rows}
    changed = 0
    for a in load_jsonl(audit_path):
        r = by_id.get(a["id"]) or sys.exit(f"audit references unknown id {a['id']}")
        if a.get("corrected_summary"):
            r["summary"] = a["corrected_summary"]
            changed += 1
        for k, v in (a.get("corrected_fields") or {}).items():
            # Cite keys may be rekeyed only by an explicit pre-publication curator entry;
            # once a corpus is published its keys are frozen.
            rekey = k == "citekey" and a.get("audit_pass") == "curator-prepublication"
            if k == "id" or (k not in RAW_KEYS and not rekey):
                sys.exit(f"{a['id']}: refusing to change field {k!r}")
            r[k] = v
            changed += 1
    if errors := check(rows):
        sys.exit("\n".join(errors))
    write_jsonl(OUT / "papers.jsonl", rows)
    print(f"applied {changed} corrections from {audit_path}")
    build()


def pop_opt(argv: list[str], name: str) -> tuple[list[str], str | None]:
    if name in argv:
        i = argv.index(name)
        return argv[:i] + argv[i + 2:], argv[i + 1]
    return argv, None


def main(argv: list[str]) -> None:
    global OUT
    if not argv or argv[0] not in {"merge", "build", "check", "apply-audit"}:
        sys.exit(__doc__)
    argv, out = pop_opt(argv, "--out")
    if out:
        OUT = Path(out).resolve()
    argv, manual = pop_opt(argv, "--manual")
    if argv[0] == "merge":
        merge([Path(p) for p in argv[1:]], Path(manual) if manual else None)
    elif argv[0] == "build":
        build()
    elif argv[0] == "apply-audit":
        apply_audit(Path(argv[1]))
    else:
        errs = check()
        print("\n".join(errs) or f"ok: {len(load_jsonl(OUT / 'papers.jsonl'))} records valid")
        sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
