#!/usr/bin/env python3
"""Build and validate the agent-movement news corpus (stdlib only).

Usage:
  python3 tools/news_corpus.py merge RAW1.jsonl [RAW2.jsonl ...] [--target 100] [--manual screening.json]
      Validate raw theme files, remove duplicates, select a theme-balanced set,
      assign IDs and citation keys, and write docs/news-corpus/news.jsonl and
      docs/news-corpus/excluded.jsonl. Then runs `build`.
  python3 tools/news_corpus.py build
      Regenerate news.csv, news.bib, digest.md and stats.json from news.jsonl.
  python3 tools/news_corpus.py check
      Validate news.jsonl only (exit 1 on any error).
  python3 tools/news_corpus.py apply-audit AUDIT.jsonl
      Apply an independent audit's corrected_summary / corrected_fields to
      news.jsonl (IDs and cite keys are never changed), then `build`.

  Every command accepts --out DIR (default docs/news-corpus). Use a separate
  directory for a new collection round: `merge` reassigns IDs from AMN-001.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "news-corpus"

THEMES = {
    "T1": "Agent-to-agent protocols and multi-agent interoperability",
    "T2": "Model Context Protocol (MCP) ecosystem",
    "T3": "Security, identity, authorization and trust",
    "T4": "Durable execution, state, memory and context portability",
    "T5": "Agent runtimes, platforms, hosting and portability",
    "T6": "Standards, governance, regulation and observability",
    "T7": "Agent-to-user, agentic commerce and cross-organization action",
}
OPERATIONS = {
    "delegation", "portable-context", "runtime-relocation", "cross-framework-migration",
    "tool-access", "identity-trust", "observability", "governance",
}
SOURCE_TYPES = {
    "news-article", "press-release", "official-blog", "standards-announcement",
    "research-news", "analysis",
}
CLAIM_STATUS = {"fact", "vendor-claim", "analysis", "incident"}
RAW_KEYS = [
    "theme", "title", "publisher", "authors", "date_published", "url", "date_accessed",
    "source_type", "primary_source", "technologies", "movement_operations", "summary",
    "relevance", "claim_status", "verified_fetch", "search_query", "notes",
]
FINAL_KEYS = ["id", "citekey"] + RAW_KEYS
DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?$")
WINDOW = ("2024-01-01", "2026-10-15")
CSV_COLS = FINAL_KEYS


def norm_url(url: str) -> str:
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def validate(rec: dict, keys: list[str]) -> list[str]:
    errs = []
    missing = [k for k in keys if k not in rec]
    extra = [k for k in rec if k not in keys]
    if missing:
        errs.append(f"missing keys {missing}")
    if extra:
        errs.append(f"unexpected keys {extra}")
    if rec.get("theme") not in THEMES:
        errs.append(f"bad theme {rec.get('theme')!r}")
    d = str(rec.get("date_published", ""))
    if not DATE_RE.match(d):
        errs.append(f"bad date {d!r}")
    elif not (WINDOW[0][: len(d)] <= d <= WINDOW[1][: len(d)]):
        errs.append(f"date {d} outside window {WINDOW}")
    if not str(rec.get("url", "")).startswith(("http://", "https://")):
        errs.append("bad url")
    if rec.get("source_type") not in SOURCE_TYPES:
        errs.append(f"bad source_type {rec.get('source_type')!r}")
    if rec.get("claim_status") not in CLAIM_STATUS:
        errs.append(f"bad claim_status {rec.get('claim_status')!r}")
    ops = rec.get("movement_operations") or []
    if not ops or not set(ops) <= OPERATIONS:
        errs.append(f"bad movement_operations {ops}")
    for k in ("authors", "technologies"):
        if not isinstance(rec.get(k), list):
            errs.append(f"{k} must be a list")
    for k in ("primary_source", "verified_fetch"):
        if not isinstance(rec.get(k), bool):
            errs.append(f"{k} must be bool")
    for k in ("title", "publisher", "summary", "relevance"):
        if not str(rec.get(k, "")).strip():
            errs.append(f"empty {k}")
    return errs


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: invalid JSON: {e}")
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def rank_key(r: dict):
    # Within a theme: verified first, primary sources first, then most recent.
    return (not r["verified_fetch"], not r["primary_source"], _neg_date(r["date_published"]))


def _neg_date(d: str) -> str:
    return "".join(chr(ord("9") - ord(c) + ord("0")) if c.isdigit() else c for c in d)


def citekey(r: dict, used: set[str]) -> str:
    stop = {"the", "a", "an", "of", "and", "for", "to", "in", "on", "with", "is", "how", "why", "what"}
    pub = [w for w in norm_title(r["publisher"]).split() if w not in stop]
    pub = pub[0] if pub else "anon"
    words = [w for w in norm_title(r["title"]).split() if w not in stop]
    base = f"{pub}{r['date_published'][:4]}{words[0] if words else 'item'}"
    key, i = base, 0
    while key in used:
        i += 1
        key = base + "abcdefghijklmnopqrstuvwxyz"[i - 1]
    used.add(key)
    return key


def merge(raw_paths: list[Path], target: int, manual: Path | None = None) -> None:
    candidates, excluded, flow = [], [], Counter()
    # Curator's event-level screening decisions: [{"url": ..., "reason": ...}].
    manual_excl = {norm_url(m["url"]): m["reason"] for m in json.loads(manual.read_text())} if manual else {}
    for p in raw_paths:
        for r in load_jsonl(p):
            flow[f"identified:{r.get('theme')}"] += 1
            flow["identified"] += 1
            errs = validate(r, RAW_KEYS)
            if errs:
                excluded.append({**r, "exclusion_reason": "schema: " + "; ".join(errs)})
                flow["excluded_schema"] += 1
                continue
            if norm_url(r["url"]) in manual_excl:
                excluded.append({**r, "exclusion_reason": "manual screening: " + manual_excl[norm_url(r["url"])]})
                flow["excluded_manual_screening"] += 1
                continue
            candidates.append(r)

    # Deduplicate by normalized URL, then by near-identical title (ratio >= 0.9).
    kept: list[dict] = []
    for r in sorted(candidates, key=rank_key):
        u, t = norm_url(r["url"]), norm_title(r["title"])
        dup = next((k for k in kept if norm_url(k["url"]) == u
                    or SequenceMatcher(None, norm_title(k["title"]), t).ratio() >= 0.9), None)
        if dup:
            excluded.append({**r, "exclusion_reason": f"duplicate of {dup['url']}"})
            flow["excluded_duplicate"] += 1
        else:
            kept.append(r)

    verified = [r for r in kept if r["verified_fetch"]]
    unverified = [r for r in kept if not r["verified_fetch"]]
    pool = verified if len(verified) >= target else verified + unverified
    for r in unverified:
        if r not in pool:
            excluded.append({**r, "exclusion_reason": "not verified by fetch (enough verified items)"})
            flow["excluded_unverified"] += 1

    # Theme-balanced round-robin selection, deterministic.
    by_theme = defaultdict(list)
    for r in pool:
        by_theme[r["theme"]].append(r)
    for t in by_theme:
        by_theme[t].sort(key=rank_key)
    selected, idx = [], {t: 0 for t in by_theme}
    while len(selected) < target and any(idx[t] < len(by_theme[t]) for t in by_theme):
        for t in sorted(by_theme):
            if len(selected) < target and idx[t] < len(by_theme[t]):
                selected.append(by_theme[t][idx[t]])
                idx[t] += 1
    for t in by_theme:
        for r in by_theme[t][idx[t]:]:
            excluded.append({**r, "exclusion_reason": f"over target of {target} (theme-balanced selection)"})
            flow["excluded_over_target"] += 1

    selected.sort(key=lambda r: (r["date_published"], r["theme"], r["title"]))
    used: set[str] = set()
    final = []
    for i, r in enumerate(selected, 1):
        final.append({"id": f"AMN-{i:03d}", "citekey": citekey(r, used), **{k: r[k] for k in RAW_KEYS}})
    flow["included"] = len(final)

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "news.jsonl", final)
    write_jsonl(OUT / "excluded.jsonl", excluded)
    (OUT / "flow.json").write_text(json.dumps(dict(sorted(flow.items())), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(sorted(flow.items())), indent=2))
    build()


def bib_escape(s: str) -> str:
    s = s.replace("\\", r"\textbackslash{}")
    for c in "&%$#_{}":
        s = s.replace(c, "\\" + c)
    return s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")


def to_bib(r: dict) -> str:
    d = r["date_published"]
    fields = [("title", "{" + bib_escape(r["title"]) + "}")]
    if r["authors"]:
        fields.append(("author", " and ".join(bib_escape(a) for a in r["authors"])))
    else:
        fields.append(("author", "{" + bib_escape(r["publisher"]) + "}"))
    fields += [
        ("organization", bib_escape(r["publisher"])),
        ("date", d),
        ("year", d[:4]),
        ("url", r["url"]),
        ("urldate", r["date_accessed"]),
        ("note", bib_escape(f"{r['id']}; {r['source_type']}; theme {r['theme']}")),
    ]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    return f"@online{{{r['citekey']},\n{body}\n}}\n"


def build() -> None:
    rows = load_jsonl(OUT / "news.jsonl")
    errors = check(rows)
    if errors:
        sys.exit("\n".join(errors))

    with (OUT / "news.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: "; ".join(v) if isinstance(v, list) else v for k, v in r.items()})

    (OUT / "news.bib").write_text(
        "% Agent Movement news corpus — generated by tools/news_corpus.py; do not edit by hand.\n"
        "% biblatex @online entries; use with biber.\n\n" + "\n".join(to_bib(r) for r in rows),
        encoding="utf-8",
    )

    stats = {
        "n": len(rows),
        "by_theme": dict(sorted(Counter(r["theme"] for r in rows).items())),
        "by_year": dict(sorted(Counter(r["date_published"][:4] for r in rows).items())),
        "by_source_type": dict(Counter(r["source_type"] for r in rows).most_common()),
        "by_claim_status": dict(Counter(r["claim_status"] for r in rows).most_common()),
        "by_operation": dict(Counter(o for r in rows for o in r["movement_operations"]).most_common()),
        "primary_source": sum(r["primary_source"] for r in rows),
        "verified_fetch": sum(r["verified_fetch"] for r in rows),
        "top_technologies": dict(Counter(t for r in rows for t in r["technologies"]).most_common(20)),
        "date_range": [min(r["date_published"] for r in rows), max(r["date_published"] for r in rows)],
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    (OUT / "digest.md").write_text(render_digest(rows, stats), encoding="utf-8")
    print(f"built {len(rows)} records -> news.csv, news.bib, digest.md, stats.json")


def md_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def render_digest(rows: list[dict], stats: dict) -> str:
    L = [
        "# Agent Movement news digest",
        "",
        "<!-- Generated by tools/news_corpus.py from news.jsonl; do not edit by hand. -->",
        "",
        f"**{stats['n']} news items**, published {stats['date_range'][0]} to {stats['date_range'][1]}, "
        f"accessed 2026-10-15. Method, inclusion criteria and limitations: [README](README.md). "
        f"Machine-readable data: [news.jsonl](news.jsonl), [news.csv](news.csv); citations: [news.bib](news.bib).",
        "",
        "Summaries are paraphrased by the curator. Vendor statements are reported as claims, not verified facts.",
        "",
        "## Overview",
        "",
        "| Theme | Items |",
        "|---|---:|",
    ]
    for t, n in stats["by_theme"].items():
        L.append(f"| {t}: {THEMES[t]} | {n} |")
    L += ["", "| Year | Items |", "|---|---:|"]
    L += [f"| {y} | {n} |" for y, n in stats["by_year"].items()]
    L += ["", "| Movement operation (multi-label) | Items |", "|---|---:|"]
    L += [f"| {o} | {n} |" for o, n in stats["by_operation"].items()]
    L += [
        "",
        f"Primary sources: {stats['primary_source']}/{stats['n']}. "
        f"Verified by fetching the page: {stats['verified_fetch']}/{stats['n']}.",
        "",
        "## Chronological index",
        "",
        "| ID | Date | Theme | Title | Publisher |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(f"| [{r['id']}](#{r['id'].lower()}) | {r['date_published']} | {r['theme']} | "
                 f"{md_cell(r['title'])} | {md_cell(r['publisher'])} |")
    for t in THEMES:
        items = [r for r in rows if r["theme"] == t]
        if not items:
            continue
        L += ["", f"## {t}: {THEMES[t]}", ""]
        for r in items:
            authors = ", ".join(r["authors"]) if r["authors"] else r["publisher"]
            L += [
                f"### {r['id']}",
                "",
                f"**{r['title']}**. {authors}. *{r['publisher']}*, {r['date_published']}. "
                f"<{r['url']}> (accessed {r['date_accessed']}). Cite key: `{r['citekey']}`.",
                "",
                r["summary"],
                "",
                f"- **Relevance:** {r['relevance']}",
                f"- **Operations:** {', '.join(r['movement_operations'])}. "
                f"**Technologies:** {', '.join(r['technologies']) or 'n/a'}.",
                f"- **Source:** {r['source_type']}, {'primary' if r['primary_source'] else 'secondary'}; "
                f"claim status: {r['claim_status']}; "
                f"{'verified by fetch' if r['verified_fetch'] else 'NOT verified by fetch'}."
                + (f" Note: {r['notes']}" if r["notes"] else ""),
                "",
            ]
    return "\n".join(L).rstrip() + "\n"


def check(rows: list[dict] | None = None) -> list[str]:
    rows = rows if rows is not None else load_jsonl(OUT / "news.jsonl")
    errors = []
    for r in rows:
        for e in validate(r, FINAL_KEYS):
            errors.append(f"{r.get('id')}: {e}")
    for field in ("id", "citekey"):
        dupes = [v for v, n in Counter(r.get(field) for r in rows).items() if n > 1]
        if dupes:
            errors.append(f"duplicate {field}: {dupes}")
    dupes = [v for v, n in Counter(norm_url(r["url"]) for r in rows).items() if n > 1]
    if dupes:
        errors.append(f"duplicate url: {dupes}")
    return errors


def apply_audit(audit_path: Path) -> None:
    """Apply auditor corrections (corrected_summary / corrected_fields) to news.jsonl."""
    rows = load_jsonl(OUT / "news.jsonl")
    by_id = {r["id"]: r for r in rows}
    changed = 0
    for a in load_jsonl(audit_path):
        r = by_id.get(a["id"])
        if r is None:
            sys.exit(f"audit references unknown id {a['id']}")
        if a.get("corrected_summary"):
            r["summary"] = a["corrected_summary"]
            changed += 1
        for k, v in (a.get("corrected_fields") or {}).items():
            if k in ("id", "citekey") or k not in RAW_KEYS:
                sys.exit(f"{a['id']}: refusing to change field {k!r}")
            r[k] = v
            changed += 1
    errors = check(rows)
    if errors:
        sys.exit("\n".join(errors))
    write_jsonl(OUT / "news.jsonl", rows)
    print(f"applied {changed} corrections from {audit_path}")
    build()


def main(argv: list[str]) -> None:
    global OUT
    if not argv or argv[0] not in {"merge", "build", "check", "apply-audit"}:
        sys.exit(__doc__)
    if "--out" in argv:
        i = argv.index("--out")
        OUT = Path(argv[i + 1]).resolve()
        argv = argv[:i] + argv[i + 2:]
    if argv[0] == "merge":
        target = 100
        if "--target" in argv:
            i = argv.index("--target")
            target = int(argv[i + 1])
            argv = argv[:i] + argv[i + 2:]
        manual = None
        if "--manual" in argv:
            i = argv.index("--manual")
            manual = Path(argv[i + 1])
            argv = argv[:i] + argv[i + 2:]
        merge([Path(p) for p in argv[1:]], target, manual)
    elif argv[0] == "build":
        build()
    elif argv[0] == "apply-audit":
        apply_audit(Path(argv[1]))
    else:
        errs = check()
        print("\n".join(errs) or f"ok: {len(load_jsonl(OUT / 'news.jsonl'))} records valid")
        sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main(sys.argv[1:])
