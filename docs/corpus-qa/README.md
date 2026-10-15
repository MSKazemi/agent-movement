# Corpus QA: link health and archive availability

This directory holds dated link checks for the two source collections:

- [`docs/news-corpus/news.jsonl`](../news-corpus/news.jsonl): 100 news records (`AMN-001` to `AMN-100`)
- [`docs/paper-corpus/papers.jsonl`](../paper-corpus/papers.jsonl): 75 paper records (`AMP-001` to `AMP-075`), 44 of them with a DOI

## Purpose

A citation is only useful while a reader can open it. For each record the check answers three questions:

1. Does the cited URL still answer?
2. For papers with a DOI, is the DOI registered, and does its landing page answer?
3. Does the Wayback Machine hold a snapshot, so the source survives if the original disappears?

## Latest run: 2026-10-16

Summary: [`link-health-2026-10-16.md`](link-health-2026-10-16.md). Per-record data: [`link-health-2026-10-16.jsonl`](link-health-2026-10-16.jsonl), one line per ID, sorted by ID. The run took place from 22:20 to 22:30 UTC on 2026-10-15, which was 2026-10-16 local time (CEST); `checked_at` values are in UTC.

| Measure | Result |
|---|---|
| Record URLs that returned a usable 2xx response (126 direct, 19 after a redirect) | 145 / 175 |
| Bot-blocked or challenged (no 404 or 410, no network errors) | 30 / 175 |
| DOIs registered at doi.org | 44 / 44 |
| Record URL has a Wayback snapshot | 128 / 175 |
| Record URL has no snapshot, but the page it redirects to does | 31 |
| Neither the record URL nor its redirect target has a snapshot | 16 |

No cited URL returned 404 or 410. All 30 failures are refusals of automated clients: 1 Keysight blog (403), 18 ACM / Wiley / MDPI pages (403), 9 IEEE Xplore pages (AWS WAF `202` challenge) and 2 OpenReview pages (redirected to `/challenge`).

## Method

The script is [`tools/link_health.py`](../../tools/link_health.py). It uses only the Python standard library and runs these steps for each record:

1. **Record URL.** `GET` with redirects followed. It stores the final status and the final URL, and reads at most 64 KiB of the body. Outcomes:
   - `ok`: 2xx at the same URL.
   - `redirected`: 2xx at a different URL.
   - `blocked`: 401, 403, 429, 451 or 999; a `202` WAF challenge (`x-amzn-waf-action`); a `cf-mitigated` header; or a redirect to a `/challenge` page.
   - `not_found`: 404 or 410.
   - `other_http`: any other status.
   - `error`: network failure or timeout.

   A 429 gets one retry after 10 s.
2. **DOI** (papers only). A `HEAD` to `https://doi.org/<doi>` without following redirects. A 3xx with a `Location` header means the DOI is registered; a 404 means it is not. A second `HEAD` follows the redirect chain, with a `GET` fallback when `HEAD` fails or is refused. The final landing-page status and URL are stored.
3. **Wayback Machine.** Lookups use only the read-only availability API, `https://archive.org/wayback/available?url=…&timestamp=…`. In testing, this API sometimes returned an empty result for a URL without a timestamp but found a snapshot when given one. Each URL is therefore queried with the run date, then with no timestamp, then with `20200101`, stopping at the first snapshot found. If the record URL redirects (for example every `doi.org` link), the Wayback Machine stores it as a 3xx capture, which this API does not report. So the final landing URL is looked up the same way (`landing_wayback_*` fields), with Springer's `?error=cookies_not_supported` query removed.

Politeness and safety:
- A descriptive `User-Agent` that names the repository.
- A 20 s timeout per request.
- At most 4 records in flight.
- At least 1 s between requests to the same host (3 s for arxiv.org, 1.5 s for archive.org).
- IPv4 is tried before IPv6, because `urllib` has no Happy Eyeballs and the test network's IPv6 route timed out.
- The script never calls Save Page Now or any other endpoint that creates content.

## How to rerun

```bash
python3 tools/link_health.py                     # full check, dated today, about 10 minutes
python3 tools/link_health.py --date 2026-10-16   # set the date used in the file names and Wayback lookups
python3 tools/link_health.py --report-only --date 2026-10-16   # rebuild the .md from the .jsonl, no network
```

Each run writes `docs/corpus-qa/link-health-<date>.{jsonl,md}`. Older dated files stay in place, so results can be compared over time.

## Limitations

- **A 401, 403, 429 or WAF challenge is not proof that a link is dead.** Bot protection refuses scripted clients that a browser gets past. The earlier news-corpus QA confirmed the Visa, Keysight and Retail Insight Network pages by hand with a second fetcher (see [`../news-corpus/README.md`](../news-corpus/README.md)). In this run Visa (`AMN-042`) and Retail Insight Network (`AMN-089`) returned 200 to the descriptive user agent; Keysight (`AMN-072`) still returned 403. The ACM, IEEE, Wiley and MDPI papers behind blocked landing pages all have DOIs that doi.org confirms are registered.
- **A 200 does not prove the content is unchanged.** The script does not compare page text with the stored summary. Redirects that move a page to a new path or slug (`AMN-027`, `AMN-034`, `AMN-074`) are worth a manual look.
- **The availability API can miss snapshots.** "No snapshot" means three lookups came back empty. It is not a full index search: the CDX API was deliberately not used.
- **Results depend on time and network.** Bot rules, rate limits and the Wayback index all change. One run is one observation from one network on one day.

## Proposed next step (needs owner approval)

> **Not done. Waiting for the owner's decision.**
>
> Submit the 16 URLs that have no Wayback snapshot of either the record URL or its redirect target to the Internet Archive's Save Page Now service (`web.archive.org/save/…`), so that every cited source has an archived copy. The list is in the last table of [`link-health-2026-10-16.md`](link-health-2026-10-16.md):
> - news: `AMN-035`, `AMN-087`, `AMN-090`, `AMN-095`, `AMN-098`
> - papers: `AMP-004`, `AMP-014`, `AMP-043`, `AMP-055`, `AMP-056`, `AMP-057`, `AMP-062`, `AMP-068`, `AMP-072`, `AMP-073`, `AMP-075`
>
> Optionally, also submit the 31 `doi.org` record URLs whose landing pages are archived but whose DOI links are not.
>
> This creates public content on a third-party service, so it is an outward action. It should run only after explicit approval, with a slow rate (Save Page Now limits anonymous use), and the script would then be rerun to record the new snapshots.
