#!/usr/bin/env python3
"""Link-health and archive-availability check for both corpora (stdlib only).

Read-only: issues plain GET/HEAD requests and queries the Wayback Machine
*availability* API (https://archive.org/wayback/available). It never calls
Save Page Now or any other endpoint that creates content.

Usage:
  python3 tools/link_health.py [--date YYYY-MM-DD] [--workers 4] [--out DIR]
      Check every record in docs/news-corpus/news.jsonl and
      docs/paper-corpus/papers.jsonl, then write
      DIR/link-health-<date>.jsonl and DIR/link-health-<date>.md
      (DIR defaults to docs/corpus-qa).
  python3 tools/link_health.py --report-only [--date YYYY-MM-DD] [--out DIR]
      Rebuild the Markdown summary from an existing JSONL without network access.

For every record:
  (a) GET the record URL, following redirects; record the final HTTP status and URL.
  (b) Papers with a DOI: request https://doi.org/<doi> without following redirects
      (is the DOI registered?), then follow it with HEAD, falling back to GET when
      HEAD fails or is refused, and record the final status and URL.
  (c) Query the Wayback availability API for the record URL; record whether a
      snapshot exists, its timestamp and its URL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPORA = [
    ("news", ROOT / "docs" / "news-corpus" / "news.jsonl"),
    ("paper", ROOT / "docs" / "paper-corpus" / "papers.jsonl"),
]
DEFAULT_OUT = ROOT / "docs" / "corpus-qa"
USER_AGENT = (
    "agent-movement-link-health/1.0 "
    "(+https://github.com/MSKazemi/agent-movement; read-only citation link QA)"
)
TIMEOUT = 20
MAX_BODY = 64 * 1024  # bytes read from each GET body; enough to confirm a response
WAYBACK_API = "https://archive.org/wayback/available"
BOT_BLOCK = {401, 403, 429, 451, 999}  # 999: LinkedIn-style bot refusal
GONE = {404, 410}
# Minimum seconds between two requests to the same host (politeness).
HOST_INTERVAL = {"arxiv.org": 3.0, "export.arxiv.org": 3.0, "archive.org": 1.5}
DEFAULT_INTERVAL = 1.0

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_first(*args, **kwargs):
    """Try IPv4 addresses before IPv6. urllib has no Happy Eyeballs, so on a network
    with broken IPv6 every dual-stack host would otherwise cost one full timeout per
    IPv6 address before IPv4 is tried. IPv6-only hosts still work."""
    res = _orig_getaddrinfo(*args, **kwargs)
    return sorted(res, key=lambda a: a[0] != socket.AF_INET)


socket.getaddrinfo = _ipv4_first

RUN_DATE = dt.date.today().isoformat()  # overwritten by --date
_host_locks: dict[str, threading.Lock] = {}
_host_last: dict[str, float] = {}
_registry_lock = threading.Lock()


def _pace(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    with _registry_lock:
        lock = _host_locks.setdefault(host, threading.Lock())
    interval = HOST_INTERVAL.get(host, DEFAULT_INTERVAL)
    with lock:
        wait = _host_last.get(host, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.monotonic()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_follow = urllib.request.build_opener()
_nofollow = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, method: str = "GET", follow: bool = True) -> dict:
    """One request. Returns status, final_url, location (no-follow), error."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en",
    }
    req = urllib.request.Request(url, headers=headers, method=method)
    opener = _follow if follow else _nofollow
    _pace(url)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            if method == "GET":
                resp.read(MAX_BODY)
            return {"status": resp.status, "final_url": resp.geturl(), "location": None,
                    "challenge": _challenge(resp.headers), "error": None}
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.headers else None
        return {"status": e.code, "final_url": e.geturl() or url, "location": loc,
                "challenge": _challenge(e.headers), "error": None}
    except Exception as e:  # URLError, timeout, SSL, connection reset, ...
        reason = getattr(e, "reason", e)
        return {"status": None, "final_url": None, "location": None, "challenge": None,
                "error": f"{type(e).__name__}: {reason}"[:300]}


def _challenge(headers) -> str | None:
    """Name the bot-mitigation signal in a response, if any (AWS WAF, Cloudflare)."""
    if headers is None:
        return None
    for name in ("x-amzn-waf-action", "cf-mitigated"):
        if headers.get(name):
            return f"{name}: {headers.get(name)}"
    return None


def classify(status: int | None, url: str, final_url: str | None,
             challenge: str | None = None) -> str:
    if status is None:
        return "error"
    if challenge or status == 202:  # 202 + empty body = WAF JavaScript challenge
        return "blocked"
    if final_url and "/challenge" in urllib.parse.urlsplit(final_url).path:
        return "blocked"  # redirected to a bot-challenge page (e.g. OpenReview)
    if 200 <= status < 300:
        return "ok" if _same(url, final_url) else "redirected"
    if status in BOT_BLOCK:
        return "blocked"
    if status in GONE:
        return "not_found"
    return "other_http"


def _same(a: str, b: str | None) -> bool:
    if b is None:
        return True
    norm = lambda u: u.rstrip("/").replace("http://", "https://", 1)  # noqa: E731
    return norm(a) == norm(b)


def check_url(url: str) -> dict:
    r = fetch(url, "GET")
    if r["status"] == 429:  # one polite retry for rate limiting
        time.sleep(10)
        r = fetch(url, "GET")
    return {"url_status": r["status"], "url_final": r["final_url"], "url_error": r["error"],
            "url_challenge": r["challenge"],
            "url_class": classify(r["status"], url, r["final_url"], r["challenge"])}


def check_doi(doi: str) -> dict:
    doi_url = "https://doi.org/" + urllib.parse.quote(doi, safe="/:;()._-")
    first = fetch(doi_url, "HEAD", follow=False)
    registered = None
    if first["status"] is not None:
        registered = 300 <= first["status"] < 400 and bool(first["location"])
        if first["status"] == 404:
            registered = False
    r = fetch(doi_url, "HEAD")
    method = "HEAD"
    if r["status"] is None or r["status"] >= 400 or r["status"] == 202:
        g = fetch(doi_url, "GET")
        if g["status"] is not None or r["status"] is None:
            r, method = g, "GET"
    return {"doi_url": doi_url, "doi_registered": registered,
            "doi_resolver_status": first["status"], "doi_resolver_location": first["location"],
            "doi_status": r["status"], "doi_final": r["final_url"], "doi_method": method,
            "doi_error": r["error"] or first["error"], "doi_challenge": r["challenge"],
            "doi_class": _doi_class(r)}


def _doi_class(r: dict) -> str:
    """Landing-page outcome; a redirect from doi.org is expected, so 2xx is 'ok'."""
    cls = classify(r["status"], "", None, r["challenge"])
    return "ok" if cls in ("ok", "redirected") else cls


def _wayback_query(url: str, timestamp: str | None) -> tuple[dict | None, str | None]:
    """One availability lookup -> (closest snapshot or None, error or None)."""
    params = {"url": url}
    if timestamp:
        params["timestamp"] = timestamp
    q = WAYBACK_API + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(3):
        _pace(q)
        try:
            req = urllib.request.Request(q, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            snap = (data.get("archived_snapshots") or {}).get("closest") or {}
            return (snap if snap.get("available") else None), None
        except urllib.error.HTTPError as e:
            last_err = f"HTTPError: {e.code}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {getattr(e, 'reason', e)}"[:300]
        time.sleep(5 * (attempt + 1))
    return None, last_err


def check_wayback(url: str, run_date: str, prefix: str = "wayback") -> dict:
    """The availability API gives false negatives: the same URL can come back empty
    without a timestamp yet resolve with one. Try the run date, no timestamp, and
    2020-01-01, and stop at the first snapshot. 'Not archived' means all three were
    empty; 'lookup failed' means at least one lookup errored and none found a snapshot."""
    errors = []
    for ts in (run_date.replace("-", ""), None, "20200101"):
        snap, err = _wayback_query(url, ts)
        if snap:
            return {f"{prefix}_archived": True, f"{prefix}_timestamp": snap.get("timestamp"),
                    f"{prefix}_url": snap.get("url"), f"{prefix}_status": snap.get("status"),
                    f"{prefix}_query_timestamp": ts, f"{prefix}_error": None}
        if err:
            errors.append(err)
    return {f"{prefix}_archived": None if errors else False, f"{prefix}_timestamp": None,
            f"{prefix}_url": None, f"{prefix}_status": None, f"{prefix}_query_timestamp": None,
            f"{prefix}_error": "; ".join(errors) or None}


def _landing_url(final: str | None) -> str | None:
    """Final URL without Springer-style cookie-check query noise."""
    if not final:
        return None
    parts = urllib.parse.urlsplit(final)
    if "cookies_not_supported" in parts.query:
        parts = parts._replace(query="")
    return urllib.parse.urlunsplit(parts)


def load_records() -> list[dict]:
    out = []
    for corpus, path in CORPORA:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out.append({"id": rec["id"], "corpus": corpus, "title": rec.get("title", ""),
                            "url": rec["url"], "doi": rec.get("doi") or ""})
    return sorted(out, key=lambda r: r["id"])


def check_record(rec: dict) -> dict:
    row = dict(rec)
    row["checked_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row.update(check_url(rec["url"]))
    if rec["doi"]:
        row.update(check_doi(rec["doi"]))
    row.update(check_wayback(rec["url"], RUN_DATE))
    # doi.org and other redirecting URLs are stored by the Wayback Machine as 3xx
    # captures, which the availability API does not report. Also look up the page the
    # redirect lands on, so a DOI's publisher page counts when it is archived.
    landing = _landing_url(row.get("url_final"))
    if landing and not _same(rec["url"], landing):
        row["landing_url"] = landing
        row.update(check_wayback(landing, RUN_DATE, prefix="landing_wayback"))
    print(f"{row['id']}: {row['url_class']} {row['url_status']} "
          f"doi={row.get('doi_status', '-')} archived={row['wayback_archived']}",
          file=sys.stderr, flush=True)
    return row


CLASS_LABEL = {
    "ok": "OK (2xx, same URL)",
    "redirected": "Redirected (2xx after redirect)",
    "blocked": "Bot-blocked or challenged (202 WAF challenge, 401/403/429/451/999)",
    "not_found": "Not found (404/410)",
    "other_http": "Other HTTP status",
    "error": "Network error / timeout",
}


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def render_md(rows: list[dict], date: str) -> str:
    def count(pred, corpus=None):
        return sum(1 for r in rows if (corpus is None or r["corpus"] == corpus) and pred(r))

    L = [f"# Link health and archive availability — {date}", "",
         f"Generated by `tools/link_health.py` on {date} over {len(rows)} records "
         f"({count(lambda r: True, 'news')} news, {count(lambda r: True, 'paper')} papers). "
         "Raw per-record results: "
         f"[`link-health-{date}.jsonl`](link-health-{date}.jsonl). Method and limitations: "
         "[README](README.md).", "",
         "> A 401/403/429 answer usually means bot protection refused an automated client. "
         "It is **not** proof that the link is dead. The earlier news-corpus QA confirmed the "
         "Visa, Keysight and Retail Insight Network pages manually with a second fetcher "
         "(see `docs/news-corpus/README.md`).", "",
         "## Record URL (GET, redirects followed)", "",
         "| Outcome | News | Papers | Total |", "|---|---:|---:|---:|"]
    for cls, label in CLASS_LABEL.items():
        p = lambda r, c=cls: r["url_class"] == c  # noqa: E731
        L.append(f"| {label} | {count(p, 'news')} | {count(p, 'paper')} | {count(p)} |")
    tot = lambda r: True  # noqa: E731
    L.append(f"| **Total** | {count(tot, 'news')} | {count(tot, 'paper')} | {len(rows)} |")
    reach = lambda r: r["url_class"] in ("ok", "redirected")  # noqa: E731
    L += ["", f"Reachable with a 2xx response: **{count(reach)} / {len(rows)}**.", ""]

    dois = [r for r in rows if r.get("doi")]
    if dois:
        L += ["## DOI resolution (papers with a DOI)", "",
              "| Check | Count |", "|---|---:|",
              f"| Papers with a DOI | {len(dois)} |",
              f"| DOI registered (doi.org answered with a redirect) | "
              f"{sum(1 for r in dois if r.get('doi_registered'))} |",
              f"| DOI not registered (doi.org 404) | "
              f"{sum(1 for r in dois if r.get('doi_registered') is False)} |",
              f"| Landing page 2xx after redirects | "
              f"{sum(1 for r in dois if r.get('doi_class') == 'ok')} |",
              f"| Landing page bot-blocked or challenged | "
              f"{sum(1 for r in dois if r.get('doi_class') == 'blocked')} |",
              f"| Landing page other non-2xx or error | "
              f"{sum(1 for r in dois if r.get('doi_class') not in ('ok', 'blocked'))} |",
              "", "A registered DOI resolves through doi.org even when the publisher's landing "
              "page then refuses the automated client.", ""]

    L += ["## Wayback Machine availability (record URL)", "",
          "| Status | News | Papers | Total |", "|---|---:|---:|---:|"]
    for label, pred in (("Archived (snapshot exists)", lambda r: r["wayback_archived"] is True),
                        ("Not archived", lambda r: r["wayback_archived"] is False),
                        ("Lookup failed", lambda r: r["wayback_archived"] is None),
                        ("Record URL not archived, but its redirect target is",
                         lambda r: r["wayback_archived"] is not True
                         and r.get("landing_wayback_archived") is True),
                        ("**No snapshot of the record URL or its redirect target**",
                         lambda r: r["wayback_archived"] is not True
                         and r.get("landing_wayback_archived") is not True)):
        L.append(f"| {label} | {count(pred, 'news')} | {count(pred, 'paper')} | {count(pred)} |")
    L += ["", "Lookups use the availability API only, at three timestamps (run date, none, "
          "2020-01-01); see the README for why. A `doi.org` URL is stored by the Wayback "
          "Machine as a redirect capture, which this API does not report, so the publisher "
          "page it lands on is looked up as well.", ""]

    non200 = [r for r in rows
              if r["url_status"] != 200 or r["url_class"] not in ("ok", "redirected")]
    L += [f"## Every record URL without a usable final HTTP 200 ({len(non200)})", "",
          "Non-200 final status, or a 200 that is a bot-challenge page.", ""]
    if non200:
        L += ["| ID | Status | Outcome | URL | Final URL / error | DOI status |",
              "|---|---:|---|---|---|---:|"]
        for r in non200:
            L.append(f"| {r['id']} | {r['url_status'] if r['url_status'] is not None else '—'} | "
                     f"{r['url_class']} | {_md_escape(r['url'])} | "
                     f"{_md_escape(r['url_error'] or (r['url_final'] if r['url_final'] != r['url'] else ''))} | "
                     f"{r.get('doi_status') if r.get('doi') else '—'} |")
    else:
        L.append("None.")
    L.append("")

    redir = [r for r in rows if r["url_class"] == "redirected"]
    L += [f"## Redirected record URLs ({len(redir)})", "",
          "Final status 2xx, but the server moved the request to another URL. "
          "Shown for maintenance; most are canonicalisation (DOI → publisher, trailing paths, "
          "renamed blogs).", ""]
    if redir:
        L += ["| ID | URL | Final URL |", "|---|---|---|"]
        for r in redir:
            L.append(f"| {r['id']} | {_md_escape(r['url'])} | {_md_escape(r['url_final'])} |")
    else:
        L.append("None.")
    L.append("")

    bad_doi = [r for r in dois if r.get("doi_class") != "ok"]
    if bad_doi:
        L += [f"## DOIs whose landing page did not return 2xx ({len(bad_doi)})", "",
              "| ID | DOI | Registered | Landing status | Method | Final URL / error |",
              "|---|---|---|---:|---|---|"]
        for r in bad_doi:
            L.append(f"| {r['id']} | {r['doi']} | {r.get('doi_registered')} | "
                     f"{r.get('doi_status') if r.get('doi_status') is not None else '—'} | "
                     f"{r.get('doi_method')} | {_md_escape(r.get('doi_error') or r.get('doi_final') or '')} |")
        L.append("")

    unarch = [r for r in rows if r["wayback_archived"] is not True]
    L += [f"## Every URL without a Wayback snapshot ({len(unarch)})", ""]
    if unarch:
        L += ["| ID | Corpus | URL | Lookup | Redirect target archived? |",
              "|---|---|---|---|---|"]
        for r in unarch:
            if r.get("landing_url"):
                la = r.get("landing_wayback_archived")
                tgt = (f"yes, {r.get('landing_wayback_timestamp')}" if la is True
                       else "lookup failed" if la is None else "no") + \
                    f" ({_md_escape(r['landing_url'])})"
            else:
                tgt = "— (no redirect)"
            L.append(f"| {r['id']} | {r['corpus']} | {_md_escape(r['url'])} | "
                     f"{'failed: ' + _md_escape(r['wayback_error']) if r['wayback_archived'] is None else 'no snapshot'} | {tgt} |")
    else:
        L.append("None.")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--workers", type=int, default=4, help="concurrent records (max 4)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()
    global RUN_DATE
    RUN_DATE = args.date
    args.out.mkdir(parents=True, exist_ok=True)
    jl = args.out / f"link-health-{args.date}.jsonl"
    md = args.out / f"link-health-{args.date}.md"
    if args.report_only:
        rows = [json.loads(x) for x in jl.read_text(encoding="utf-8").splitlines() if x.strip()]
    else:
        records = load_records()
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as ex:
            rows = list(ex.map(check_record, records))
        rows.sort(key=lambda r: r["id"])
        jl.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    md.write_text(render_md(rows, args.date), encoding="utf-8")
    rel = lambda p: p.relative_to(ROOT) if p.is_relative_to(ROOT) else p  # noqa: E731
    wrote = f"{rel(md)}" if args.report_only else f"{rel(jl)} and {rel(md)}"
    print(f"wrote {wrote} ({len(rows)} records)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
