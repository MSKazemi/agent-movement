#!/usr/bin/env python3
"""Timeline and coverage analysis of the news and paper corpora (stdlib only).

Usage:
  python3 tools/corpus_analysis.py [--news PATH] [--papers PATH] [--out DIR]

Defaults: docs/news-corpus/news.jsonl, docs/paper-corpus/papers.jsonl and
docs/corpus-analysis/. Writes timeline.md and coverage.md into DIR.

The output is deterministic: rows are sorted, no run-time clock is read, and the
only date stamped into the files ("data as of") is the latest `date_accessed`
found in the input records. Nothing is hard-coded about corpus size, so records
appended later (AMN-101+, AMP-076+) are picked up on the next run.

All numbers are descriptive statistics of the corpora as sampled. They reflect
the collection protocol (themes, per-theme candidate caps, the news date window,
the search date), not the true distribution of activity in the field.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # single source of truth for theme labels; fall back if the tools move
    from news_corpus import THEMES as NEWS_THEMES  # type: ignore
    from paper_corpus import THEMES as PAPER_THEMES  # type: ignore
except Exception:  # pragma: no cover - defensive only
    NEWS_THEMES, PAPER_THEMES = {}, {}

DEFAULT_NEWS = ROOT / "docs" / "news-corpus" / "news.jsonl"
DEFAULT_PAPERS = ROOT / "docs" / "paper-corpus" / "papers.jsonl"
DEFAULT_OUT = ROOT / "docs" / "corpus-analysis"

MONTHLY_YEARS = (2024, 2025, 2026)  # years broken down by month in the timeline
TITLE_MAX = 80
GAP_MAX = 1  # a cell with count <= GAP_MAX is reported as a coverage gap
RECENT_SPAN = 4  # "recent" = the last RECENT_SPAN years present in a corpus

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# The four movement operations of the project README, in README order.
CORE_OPS = [
    ("delegation", "Delegation / handoff"),
    ("portable-context", "Portable task context"),
    ("runtime-relocation", "Runtime relocation"),
    ("cross-framework-migration", "Cross-framework migration"),
]

# Keyword rule for the crosswalk. Keywords are the key terms of the README's
# definition of each operation plus common synonyms; they were fixed before the
# agreement figures were read and are not fitted to the coded labels. Each keyword is matched case-insensitively
# against title + " " + summary, anchored at a word start (regex `\b` + keyword)
# and open at the end, so a keyword acts as a stem ("delegat" matches
# "delegate", "delegation", "delegated"). An item "touches" an operation if any
# of that operation's keywords matches. This is a transparent heuristic, not a
# classifier; it is reported next to the curated `movement_operations` codes.
KEYWORDS: dict[str, list[str]] = {
    "delegation": [
        "delegat", "handoff", "hand-off", "hand off", "handover", "hand over",
        "agent-to-agent", "a2a", "subagent", "sub-agent", "contract net",
        "task assignment", "task allocation", "on behalf of",
    ],
    "portable-context": [
        "portable context", "task context", "context transfer", "context sharing",
        "shared context", "context management", "context engineering", "memory",
        "checkpoint", "session state", "agent state", "state transfer",
        "persistent state", "serializ", "snapshot", "artifact reference",
        "resumable",
    ],
    "runtime-relocation": [
        "relocat", "mobile agent", "agent mobility", "code mobility",
        "process migration", "live migration", "vm migration",
        "virtual machine migration", "durable", "idempoten", "safe boundary",
        "resum", "suspend", "failover", "crash recovery", "fault toleran",
    ],
    "cross-framework-migration": [
        "cross-framework", "framework-agnostic", "framework agnostic",
        "framework-independent", "framework-neutral", "interoperab", "adapter",
        "lock-in", "portabil", "agent spec", "agent specification",
        "agent definition", "declarative agent", "agent file",
        "portable representation", "across frameworks", "across runtimes",
        "cross-runtime", "different runtime",
    ],
}
_PATTERNS = {op: [re.compile(r"\b" + re.escape(k), re.IGNORECASE) for k in kws]
             for op, kws in KEYWORDS.items()}


# --------------------------------------------------------------------------- io

def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"{path}:{n}: invalid JSON: {exc}")
    return rows


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ---------------------------------------------------------------------- helpers

def cell(s: object) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def short(title: str, n: int = TITLE_MAX) -> str:
    t = " ".join(title.split())
    if len(t) <= n:
        return t
    cut = t[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return cut + "…"


def themes_of(r: dict) -> list[str]:
    t = r.get("theme", "")
    if isinstance(t, list):
        return sorted({str(x) for x in t if x}) or ["(none)"]
    return [str(t)] if t else ["(none)"]


def parse_date(r: dict) -> tuple[int, int, int, str]:
    """Return (year, month or 0, day or 0, date string as stated)."""
    raw = str(r.get("date_published") or "").strip()
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", raw)
    if m:
        return int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), raw
    y = r.get("year")
    if isinstance(y, int) or (isinstance(y, str) and y.isdigit()):
        return int(y), 0, 0, str(y)
    return 0, 0, 0, "undated"


def table(header: list[str], rows: list[list[object]], align: list[str] | None = None) -> list[str]:
    align = align or (["l"] + ["r"] * (len(header) - 1))
    sep = ["---:" if a == "r" else "---" for a in align]
    out = ["| " + " | ".join(cell(h) for h in header) + " |",
           "| " + " | ".join(sep) + " |"]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return out


def keyword_ops(r: dict) -> set[str]:
    text = f"{r.get('title', '')} {r.get('summary', '')}"
    return {op for op, pats in _PATTERNS.items() if any(p.search(text) for p in pats)}


def coded_ops(r: dict) -> set[str]:
    return {str(x) for x in r.get("movement_operations") or []}


def theme_label(code: str) -> str:
    return NEWS_THEMES.get(code) or PAPER_THEMES.get(code) or "label not defined in tools"


class Corpus:
    def __init__(self, name: str, rows: list[dict], kind: str, path: Path):
        self.name, self.rows, self.kind, self.path = name, rows, kind, path
        self.themes = sorted({t for r in rows for t in themes_of(r)})
        self.years = sorted({parse_date(r)[0] for r in rows})


def data_as_of(*corpora: Corpus) -> str:
    dates = sorted(str(r.get("date_accessed")) for c in corpora for r in c.rows
                   if r.get("date_accessed"))
    return dates[-1] if dates else "unknown"


def rel(path: Path, out: Path) -> str:
    """Link target of `path` relative to the output directory (POSIX form)."""
    return Path(os.path.relpath(path.resolve(), out.resolve())).as_posix()


# --------------------------------------------------------------------- timeline

def render_timeline(news: Corpus, papers: Corpus, out: Path, asof: str) -> str:
    items = []
    for c in (news, papers):
        for r in c.rows:
            y, m, d, raw = parse_date(r)
            items.append({
                "y": y, "m": m, "d": d, "date": raw, "id": str(r.get("id", "")),
                "title": short(str(r.get("title", ""))),
                "theme": "/".join(themes_of(r)), "kind": c.kind,
            })
    # undated precision sorts after dated items of the same year/month
    items.sort(key=lambda i: (i["y"], i["m"] or 13, i["d"] or 32, i["kind"], i["id"]))

    L = [
        "# Agent movement corpora: combined timeline",
        "",
        "<!-- Generated by tools/corpus_analysis.py; do not edit by hand. -->",
        "",
        f"**Data as of:** {asof} (latest `date_accessed` in the input records) · "
        f"**Items:** {len(news.rows)} news ([source]({rel(news.path, out)})) + "
        f"{len(papers.rows)} papers ([source]({rel(papers.path, out)}))",
        "",
        "Each line gives the publication date as stated by the source, the corpus ID "
        "(`AMN-` news, `AMP-` paper), a shortened title and the theme code. Papers dated "
        "only to a year or month are listed after the dated items of that period. Years "
        f"{MONTHLY_YEARS[0]}–{MONTHLY_YEARS[-1]} are broken down by month.",
        "",
        "> **Read with care.** The timeline shows what the two corpora sampled, not how "
        "activity in the field was distributed over time. The news corpus is restricted to a "
        "fixed publication window and capped per theme; the paper corpus took a fixed number "
        "of candidates per theme and deliberately included seminal older work. Density "
        "differences between periods are therefore partly or wholly artefacts of the "
        "sampling protocol (see the corpus READMEs).",
        "",
        "## Summary by year",
        "",
        "A Mermaid `timeline` block is not used: its rendering on GitHub could not be "
        "verified when this generator was written, so a plain table is given instead.",
        "",
    ]
    years = sorted({i["y"] for i in items})
    nc = Counter(i["y"] for i in items if i["kind"] == "news")
    pc = Counter(i["y"] for i in items if i["kind"] == "paper")
    L += table(["Year", "News", "Papers", "Total"],
               [[y or "undated", nc[y], pc[y], nc[y] + pc[y]] for y in years]
               + [["**Total**", sum(nc.values()), sum(pc.values()), len(items)]])
    L += ["", "Theme codes: " + "; ".join(
        f"{t} {theme_label(t)}" for t in news.themes + papers.themes) + ".", ""]

    for y in years:
        L += [f"## {y or 'Undated'}", ""]
        ys = [i for i in items if i["y"] == y]
        if y in MONTHLY_YEARS:
            for m in sorted({i["m"] for i in ys}, key=lambda m: m or 13):
                L += [f"### {MONTHS[m - 1] + ' ' + str(y) if m else str(y) + ', month not stated'}", ""]
                L += [_line(i) for i in ys if i["m"] == m] + [""]
        else:
            L += [_line(i) for i in ys] + [""]
    return "\n".join(L).rstrip() + "\n"


def _line(i: dict) -> str:
    return f"- `{i['date']}` · {i['id']} · {i['title']} · {i['theme']}"


# --------------------------------------------------------------------- coverage

def year_theme_table(c: Corpus) -> list[str]:
    cnt = Counter((parse_date(r)[0], t) for r in c.rows for t in themes_of(r))
    rows = []
    for y in c.years:
        vals = [cnt[(y, t)] for t in c.themes]
        rows.append([y or "undated", *vals, sum(vals)])
    totals = [sum(cnt[(y, t)] for y in c.years) for t in c.themes]
    rows.append(["**Total**", *totals, sum(totals)])
    return table(["Year", *c.themes, "Total"], rows)


def counter_table(label: str, cnt: Counter, total: int) -> list[str]:
    rows = [[k, v, f"{100 * v / total:.0f}%" if total else "–"]
            for k, v in sorted(cnt.items(), key=lambda kv: (-kv[1], str(kv[0])))]
    return table([label, "Items", "Share"], rows)


def cooccurrence(c: Corpus, key, labels: list[str]) -> list[str]:
    cnt = Counter()
    for r in c.rows:
        vals = sorted(key(r))
        for v in vals:
            cnt[(v, v)] += 1
        for a, b in combinations(vals, 2):
            cnt[(a, b)] += 1
            cnt[(b, a)] += 1
    return table(["", *labels], [[a, *[cnt[(a, b)] for b in labels]] for a in labels])


def theme_op_table(c: Corpus, ops: list[str], key) -> tuple[list[str], Counter]:
    cnt = Counter((t, o) for r in c.rows for t in themes_of(r) for o in key(r))
    n_theme = Counter(t for r in c.rows for t in themes_of(r))
    return table(["Theme", "Items", *ops],
                 [[t, n_theme[t], *[cnt[(t, o)] for o in ops]] for t in c.themes]), cnt


def crosswalk(c: Corpus) -> tuple[list[str], dict]:
    res = {}
    rows = []
    n = len(c.rows)
    for op, label in CORE_OPS:
        kw = {r.get("id") for r in c.rows if op in keyword_ops(r)}
        cd = {r.get("id") for r in c.rows if op in coded_ops(r)}
        res[op] = (len(kw), len(cd), len(kw & cd), len(kw | cd))
        rows.append([label, len(kw), f"{100 * len(kw) / n:.0f}%" if n else "–",
                     len(cd), len(kw & cd), len(kw - cd), len(cd - kw)])
    return table(["Operation", "Keyword hits", "Share", "Coded", "Both",
                  "Keyword only", "Coded only"], rows), res


def render_coverage(news: Corpus, papers: Corpus, out: Path, asof: str) -> str:
    core = [k for k, _ in CORE_OPS]
    # core operations first in README order, then the supporting codes alphabetically
    all_ops = sorted({o for c in (news, papers) for r in c.rows for o in coded_ops(r)},
                     key=lambda o: (core.index(o) if o in core else len(core), o))
    L = [
        "# Agent movement corpora: coverage analysis",
        "",
        "<!-- Generated by tools/corpus_analysis.py; do not edit by hand. -->",
        "",
        f"**Data as of:** {asof} (latest `date_accessed` in the input records) · "
        f"**Items:** {len(news.rows)} news ([source]({rel(news.path, out)})), "
        f"{len(papers.rows)} papers ([source]({rel(papers.path, out)}))",
        "",
        "> **Scope of these numbers.** Every table below is a descriptive count of the two "
        "curated corpora. The counts are shaped by the sampling protocol: a fixed set of "
        "search themes, a capped number of candidates per theme, theme-balanced selection "
        "for news, a fixed news publication window, and a single search date. They are not "
        "estimates of how activity or publication is distributed in the field, and no "
        "causal reading is intended. Percentages are shares of the corpus in question.",
        "",
        "## 1. Items per year × theme",
        "",
        "### News (themes T1–T7)" if news.themes == [f"T{i}" for i in range(1, 8)]
        else "### News",
        "",
        *year_theme_table(news),
        "",
        "### Papers (themes P1–P6)" if papers.themes == [f"P{i}" for i in range(1, 7)]
        else "### Papers",
        "",
        *year_theme_table(papers),
        "",
        "Theme codes: " + "; ".join(f"{t} {theme_label(t)}"
                                    for t in news.themes + papers.themes) + ".",
        "",
        "## 2. News by source and publisher type",
        "",
        "`source_type` is the coded publisher/source category; `primary_source` records "
        "whether the announcing organization published the item itself.",
        "",
    ]
    n = len(news.rows)
    L += counter_table("Source type", Counter(str(r.get("source_type", "(missing)"))
                                              for r in news.rows), n)
    L += [""]
    st = sorted({str(r.get("source_type", "(missing)")) for r in news.rows})
    ps = Counter((str(r.get("source_type", "(missing)")), bool(r.get("primary_source")))
                 for r in news.rows)
    L += table(["Source type", "Primary", "Secondary"],
               [[s, ps[(s, True)], ps[(s, False)]] for s in st]
               + [["**Total**", sum(v for (s, p), v in ps.items() if p),
                   sum(v for (s, p), v in ps.items() if not p)]])
    L += ["", "Claim status (how each summary's central statement was coded):", ""]
    L += counter_table("Claim status", Counter(str(r.get("claim_status", "(missing)"))
                                               for r in news.rows), n)
    pub = Counter(str(r.get("publisher", "(missing)")) for r in news.rows)
    multi = Counter({k: v for k, v in pub.items() if v >= 2})
    L += ["", f"Publishers with two or more items ({len(multi)} of {len(pub)} distinct "
          "publisher strings; strings are as recorded, so one organization can appear "
          "under several names):", ""]
    L += counter_table("Publisher", multi, n)

    m = len(papers.rows)
    L += ["", "## 3. Papers by venue type and peer-review status", ""]
    pt = sorted({str(r.get("publication_type", "(missing)")) for r in papers.rows})
    pr = Counter((str(r.get("publication_type", "(missing)")), bool(r.get("peer_reviewed")))
                 for r in papers.rows)
    L += table(["Publication type", "Peer reviewed", "Not peer reviewed", "Total"],
               [[t, pr[(t, True)], pr[(t, False)], pr[(t, True)] + pr[(t, False)]] for t in pt]
               + [["**Total**", sum(v for (t, p), v in pr.items() if p),
                   sum(v for (t, p), v in pr.items() if not p), m]])
    yp = Counter((parse_date(r)[0], bool(r.get("peer_reviewed"))) for r in papers.rows)
    L += ["", "Peer-review status by year:", ""]
    L += table(["Year", "Peer reviewed", "Not peer reviewed"],
               [[y or "undated", yp[(y, True)], yp[(y, False)]] for y in papers.years])
    L += ["", "Contribution type:", ""]
    L += counter_table("Contribution type", Counter(str(r.get("contribution_type", "(missing)"))
                                                    for r in papers.rows), m)

    L += ["", "## 4. Co-occurrence", ""]
    multi_theme = any(len(themes_of(r)) > 1 for c in (news, papers) for r in c.rows)
    if multi_theme:
        for c in (news, papers):
            L += [f"Theme co-occurrence, {c.name} (diagonal = items with that theme):", ""]
            L += cooccurrence(c, themes_of, c.themes) + [""]
    else:
        L += ["Every record carries exactly one `theme` code, so theme co-occurrence is "
              "empty by construction. The multi-label field is `movement_operations`; its "
              "co-occurrence is shown instead (diagonal = items carrying that code; "
              "off-diagonal = items carrying both codes).", ""]
    for c in (news, papers):
        L += [f"`movement_operations` co-occurrence, {c.name}:", ""]
        L += cooccurrence(c, coded_ops, all_ops) + [""]
    L += ["Coded `movement_operations` by theme (an item can carry several codes):", ""]
    theme_op = {}
    for c in (news, papers):
        tbl, cnt = theme_op_table(c, all_ops, coded_ops)
        theme_op[c.name] = cnt
        L += [f"{c.name.capitalize()}:", "", *tbl, ""]

    L += ["## 5. Crosswalk to the four movement operations", "",
          "The [project README](../../README.md) defines four operations: delegation / "
          "handoff, portable task context, runtime relocation and cross-framework "
          "migration. This crosswalk counts how many items *touch* each one under a "
          "keyword rule, and sets that beside the curated `movement_operations` codes.",
          "",
          "**Rule (heuristic).** Concatenate `title` and `summary`; an item touches an "
          "operation if any keyword below matches case-insensitively at the start of a "
          "word (regex `\\b` + keyword, open-ended, so keywords act as stems). An item can "
          "touch several operations. The rule is a transparent screen, not a validated "
          "classifier: it has not been checked against human judgement, it misses "
          "paraphrases, and broad stems (for example `memory`, `interoperab`, `resum`) "
          "will over-count. Treat agreement with the coded labels as a rough consistency "
          "check only.", ""]
    L += table(["Operation", "Keywords"],
               [[label, ", ".join(f"`{k}`" for k in KEYWORDS[op])] for op, label in CORE_OPS],
               ["l", "l"])
    L += ["", "Columns: *Keyword hits* = items matched by the rule; *Coded* = items whose "
          "`movement_operations` include the operation; *Both*, *Keyword only*, *Coded only* "
          "compare the two sets.", ""]
    cw = {}
    for c in (news, papers):
        tbl, res = crosswalk(c)
        cw[c.name] = res
        L += [f"{c.name.capitalize()} (n = {len(c.rows)}):", "", *tbl, ""]
    combined = Corpus("combined", news.rows + papers.rows, "all", news.path)
    tbl, _ = crosswalk(combined)
    L += [f"Both corpora combined (n = {len(combined.rows)}):", "", *tbl, ""]
    L += ["Keyword hits by theme (same rule):", ""]
    kw_theme = {}
    for c in (news, papers):
        tbl, cnt = theme_op_table(c, core, keyword_ops)
        kw_theme[c.name] = cnt
        L += [f"{c.name.capitalize()}:", "", *tbl, ""]

    L += render_gaps(news, papers, theme_op, kw_theme, cw)
    return "\n".join(L).rstrip() + "\n"


def render_gaps(news: Corpus, papers: Corpus, theme_op: dict, kw_theme: dict, cw: dict) -> list[str]:
    L = ["## 6. Coverage gaps (hypotheses for the next search round)", "",
         f"Rules: a cell is listed when its count is ≤ {GAP_MAX}. For year × theme, only the "
         f"last {RECENT_SPAN} years present in each corpus are checked, because older "
         "years are sparse by design. Every entry is a **hypothesis**: a low count may "
         "mean the topic is genuinely thin, or only that the search queries, the per-theme "
         "caps, the ranking tie-breaks or the single search date did not surface it. In "
         "particular, news selection ranked items newest-first within each theme before "
         "the per-theme cut, which by itself depresses counts for the earliest years of the "
         "news window. Each entry can be tested with targeted queries in the next round.", ""]
    h = 0

    def hyp(text: str) -> None:
        nonlocal h
        h += 1
        L.append(f"- **H{h}.** {text}")

    L += ["### Year × theme", ""]
    for c in (news, papers):
        recent = [y for y in c.years if y][-RECENT_SPAN:]
        cnt = Counter((parse_date(r)[0], t) for r in c.rows for t in themes_of(r))
        for y in recent:
            for t in c.themes:
                if cnt[(y, t)] <= GAP_MAX:
                    hyp(f"{c.name.capitalize()}, {t} ({theme_label(t)}), {y}: "
                        f"n = {cnt[(y, t)]}. Under-sampled or genuinely sparse for that year? "
                        f"Test with year-restricted {t} queries.")
    if L[-1] == "":
        L.append("- No year × theme cell at or below the threshold.")
    L += ["", "### Theme × core operation (curated codes)", ""]
    before = h
    for c in (news, papers):
        cnt = theme_op[c.name]
        for t in c.themes:
            for op, label in CORE_OPS:
                if cnt[(t, op)] <= GAP_MAX:
                    hyp(f"{c.name.capitalize()}, {t} × {label}: n = {cnt[(t, op)]} coded. "
                        f"Is {label.lower()} rare in the theme \u201c{theme_label(t)}\u201d, or "
                        "were such items outside this theme's queries?")
    if h == before:
        L.append("- No theme × core-operation cell at or below the threshold.")
    L += ["", "### Core operations overall", ""]
    for c in (news, papers):
        res = cw[c.name]
        ranked = sorted(CORE_OPS, key=lambda o: (res[o[0]][1], o[0]))
        op, label = ranked[0]
        kw_n, cd_n, both, union = res[op]
        hyp(f"{c.name.capitalize()}: the least-coded core operation is {label.lower()} "
            f"({cd_n} coded, {kw_n} keyword hits, of {len(c.rows)}). Hypothesis: it is "
            "under-represented relative to the other three operations in this corpus; a "
            "search round with queries aimed specifically at it would test whether that "
            "reflects the field or the theme definitions.")
        for op, label in CORE_OPS:
            kw_n, cd_n, both, union = res[op]
            if cd_n and kw_n < cd_n / 2:
                hyp(f"{c.name.capitalize()}, {label}: keyword hits ({kw_n}) are under half "
                    f"the coded count ({cd_n}). The keyword list may miss this operation's "
                    "vocabulary; refine the rule before using it for the next round.")
            elif kw_n > 2 * cd_n:
                hyp(f"{c.name.capitalize()}, {label}: keyword hits ({kw_n}) exceed twice "
                    f"the coded count ({cd_n}). Either the stems are too broad or the "
                    "curated codes under-label this operation; a manual re-check of the "
                    "keyword-only items would decide.")
    L.append("")
    return L


# ------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--news", type=Path, default=DEFAULT_NEWS, help="news JSONL (default: %(default)s)")
    ap.add_argument("--papers", type=Path, default=DEFAULT_PAPERS, help="papers JSONL (default: %(default)s)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default: %(default)s)")
    a = ap.parse_args(argv)
    news = Corpus("news", load_jsonl(a.news), "news", a.news)
    papers = Corpus("papers", load_jsonl(a.papers), "paper", a.papers)
    asof = data_as_of(news, papers)
    write(a.out / "timeline.md", render_timeline(news, papers, a.out, asof))
    write(a.out / "coverage.md", render_coverage(news, papers, a.out, asof))
    print(f"wrote {a.out / 'timeline.md'} and {a.out / 'coverage.md'} "
          f"({len(news.rows)} news, {len(papers.rows)} papers, data as of {asof})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
