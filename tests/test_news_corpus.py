"""Unit tests for tools/news_corpus.py: schema, check, dedupe, selection, biblatex, apply-audit."""
from __future__ import annotations

import json

import pytest

import news_corpus as nc
from conftest import news_final, news_raw, read_jsonl, run_tool, write_jsonl


# --------------------------------------------------------------------------- schema / validate


def test_valid_raw_and_final_records_pass():
    assert nc.validate(news_raw(), nc.RAW_KEYS) == []
    assert nc.check([news_final()]) == []


def test_missing_field_is_reported():
    r = news_final()
    del r["summary"]
    errs = nc.check([r])
    assert any("missing keys ['summary']" in e for e in errs)
    assert errs[0].startswith("AMN-001: ")


def test_unexpected_field_is_reported():
    errs = nc.validate(news_raw(extra="x"), nc.RAW_KEYS)
    assert "unexpected keys ['extra']" in errs


@pytest.mark.parametrize("date", ["2025-13-01", "2025-02-32", "2025/03/14", "25-03-14", "", "2025-3-4"])
def test_malformed_date_is_rejected(date):
    errs = nc.validate(news_raw(date_published=date), nc.RAW_KEYS)
    assert any(e.startswith("bad date") for e in errs), errs


@pytest.mark.parametrize("date", ["2023-12-31", "2026-10-16", "2026-11", "2027-01-01"])
def test_date_outside_collection_window_is_rejected(date):
    errs = nc.validate(news_raw(date_published=date), nc.RAW_KEYS)
    assert any("outside window" in e for e in errs), errs


@pytest.mark.parametrize("date", ["2024-01-01", "2026-10-15", "2026-10", "2025-02"])
def test_dates_inside_window_and_month_precision_accepted(date):
    assert nc.validate(news_raw(date_published=date), nc.RAW_KEYS) == []


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("theme", "T9", "bad theme"),
        ("source_type", "tweet", "bad source_type"),
        ("claim_status", "rumour", "bad claim_status"),
        ("movement_operations", [], "bad movement_operations"),
        ("movement_operations", ["teleport"], "bad movement_operations"),
        ("url", "ftp://example.com/x", "bad url"),
        ("authors", "Jane Doe", "authors must be a list"),
        ("technologies", "A2A", "technologies must be a list"),
        ("primary_source", "yes", "primary_source must be bool"),
        ("verified_fetch", 1, "verified_fetch must be bool"),
        ("title", "   ", "empty title"),
        ("publisher", "", "empty publisher"),
    ],
)
def test_bad_field_values_are_rejected(field, value, fragment):
    errs = nc.validate(news_raw(**{field: value}), nc.RAW_KEYS)
    assert any(fragment in e for e in errs), errs


def test_check_reports_duplicate_id():
    errs = nc.check([news_final("AMN-001", "k1"), news_final("AMN-001", "k2", url="https://example.com/other")])
    assert "duplicate id: ['AMN-001']" in errs


def test_check_reports_duplicate_citekey():
    errs = nc.check([news_final("AMN-001", "same"), news_final("AMN-002", "same", url="https://example.com/other")])
    assert "duplicate citekey: ['same']" in errs


def test_check_reports_duplicate_url_after_normalisation():
    a = news_final("AMN-001", "k1", url="https://www.example.com/a/")
    b = news_final("AMN-002", "k2", url="http://example.com/a?utm_source=x#frag")
    errs = nc.check([a, b])
    assert any(e.startswith("duplicate url") for e in errs), errs


def test_check_reports_missing_url_instead_of_crashing():
    r = news_final()
    del r["url"]
    errs = nc.check([r])
    assert any("missing keys ['url']" in e for e in errs)


def test_check_cli_exits_1_on_bad_records(tmp_path):
    bad = news_final(date_published="2025-13-01")
    write_jsonl(tmp_path / "news.jsonl", [bad, news_final("AMN-001", "k2", url="https://example.com/b")])
    res = run_tool("news_corpus.py", "check", "--out", str(tmp_path))
    assert res.returncode == 1
    assert "bad date" in res.stdout
    assert "duplicate id" in res.stdout


def test_check_cli_exits_0_on_good_records(tmp_path):
    write_jsonl(tmp_path / "news.jsonl", [news_final()])
    res = run_tool("news_corpus.py", "check", "--out", str(tmp_path))
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip() == "ok: 1 records valid"


def test_build_refuses_invalid_records(news_out):
    write_jsonl(news_out / "news.jsonl", [news_final(theme="T9")])
    with pytest.raises(SystemExit) as exc:
        nc.build()
    assert "bad theme" in str(exc.value.code)
    assert not (news_out / "news.bib").exists()


# --------------------------------------------------------------------------- normalisation


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a",
        "http://example.com/a",
        "https://www.example.com/a/",
        "https://EXAMPLE.com/a?utm_source=feed",
        "  https://example.com/a#section ",
    ],
)
def test_norm_url_collapses_variants(url):
    assert nc.norm_url(url) == "https://example.com/a"


def test_norm_title_ignores_case_and_punctuation():
    assert nc.norm_title("MCP: The “USB-C” of AI!").split() == ["mcp", "the", "usb", "c", "of", "ai"]


# --------------------------------------------------------------------------- merge: dedupe and selection


def _merge(tmp_path, rows, target=100, manual=None):
    raw = write_jsonl(tmp_path / "raw" / "t.jsonl", rows)
    man = None
    if manual is not None:
        man = tmp_path / "screening.json"
        man.write_text(json.dumps(manual), encoding="utf-8")
    nc.merge([raw], target, man)
    out = nc.OUT
    return read_jsonl(out / "news.jsonl"), read_jsonl(out / "excluded.jsonl"), json.loads((out / "flow.json").read_text())


def test_merge_dedupes_same_url_variants_keeping_primary_source(news_out, tmp_path):
    secondary = news_raw(url="http://www.example.com/news/acme-protocol/", primary_source=False,
                         title="Acme launches protocol (coverage)")
    primary = news_raw()
    kept, excl, flow = _merge(tmp_path, [secondary, primary])
    assert [r["url"] for r in kept] == [primary["url"]]
    assert kept[0]["primary_source"] is True
    assert len(excl) == 1 and excl[0]["exclusion_reason"] == f"duplicate of {primary['url']}"
    assert flow["excluded_duplicate"] == 1 and flow["included"] == 1


def test_merge_dedupes_same_event_by_near_identical_headline(news_out, tmp_path):
    a = news_raw(url="https://vendor.example/blog/launch", title="Acme launches open agent handoff protocol")
    b = news_raw(url="https://press.example/acme", title="Acme Launches Open Agent Handoff Protocol!",
                 primary_source=False, source_type="news-article", publisher="Tech Press")
    kept, excl, _ = _merge(tmp_path, [b, a])
    assert [r["url"] for r in kept] == [a["url"]]
    assert excl[0]["url"] == b["url"] and excl[0]["exclusion_reason"].startswith("duplicate of")


def test_merge_keeps_distinct_headlines(news_out, tmp_path):
    a = news_raw(url="https://example.com/a", title="Acme launches open agent handoff protocol")
    b = news_raw(url="https://example.com/b", title="Regulator publishes guidance on agent identity")
    kept, excl, _ = _merge(tmp_path, [a, b])
    assert len(kept) == 2 and excl == []


def test_merge_prefers_verified_then_primary_then_recent(news_out, tmp_path):
    base = dict(title="Same headline about agent movement standards")
    unverified = news_raw(url="https://e.com/1", verified_fetch=False, **base)
    secondary = news_raw(url="https://e.com/2", primary_source=False, **base)
    older = news_raw(url="https://e.com/3", date_published="2024-06-01", **base)
    newer = news_raw(url="https://e.com/4", date_published="2025-06-01", **base)
    kept, excl, _ = _merge(tmp_path, [unverified, secondary, older, newer])
    assert [r["url"] for r in kept] == ["https://e.com/4"]
    assert len(excl) == 3


def test_merge_manual_screening_excludes_same_event_from_different_url(news_out, tmp_path):
    a = news_raw(url="https://foundation.example/press/joins", title="A2A joins the foundation")
    b = news_raw(url="https://vendor.example/blog/a-new-chapter/", title="A new chapter for our protocol")
    kept, excl, flow = _merge(tmp_path, [a, b], manual=[{"url": "https://www.vendor.example/blog/a-new-chapter",
                                                          "reason": "same event as foundation release"}])
    assert [r["url"] for r in kept] == [a["url"]]
    assert excl[0]["exclusion_reason"] == "manual screening: same event as foundation release"
    assert flow["excluded_manual_screening"] == 1


def test_merge_excludes_schema_failures_with_reason(news_out, tmp_path):
    good = news_raw()
    bad = news_raw(url="https://example.com/bad", title="Other", date_published="2019-01-01")
    kept, excl, flow = _merge(tmp_path, [good, bad])
    assert len(kept) == 1
    assert excl[0]["exclusion_reason"].startswith("schema: ") and "outside window" in excl[0]["exclusion_reason"]
    assert flow["excluded_schema"] == 1 and flow["identified"] == 2


def test_merge_theme_balanced_selection_and_target(news_out, tmp_path):
    titles = ["Alpha framework adds memory export", "Bravo runtime supports live migration",
              "Charlie SDK gains durable state"]
    rows = [news_raw(theme="T1", url=f"https://e.com/t1/{i}", title=t, date_published=f"2025-0{i + 1}-01")
            for i, t in enumerate(titles)]
    rows.append(news_raw(theme="T2", url="https://e.com/t2", title="MCP registry goes live"))
    kept, excl, flow = _merge(tmp_path, rows, target=2)
    assert sorted(r["theme"] for r in kept) == ["T1", "T2"]
    # Within T1 the most recent item wins the single slot.
    assert next(r for r in kept if r["theme"] == "T1")["date_published"] == "2025-03-01"
    assert flow["excluded_over_target"] == 2
    assert all("over target of 2" in e["exclusion_reason"] for e in excl)


def test_merge_drops_unverified_when_enough_verified(news_out, tmp_path):
    v = news_raw(url="https://e.com/v", title="Verified story about protocols")
    u = news_raw(url="https://e.com/u", title="Unverified story about identity", verified_fetch=False)
    kept, excl, flow = _merge(tmp_path, [v, u], target=1)
    assert [r["url"] for r in kept] == [v["url"]]
    assert excl[0]["exclusion_reason"] == "not verified by fetch (enough verified items)"
    assert flow["excluded_unverified"] == 1


def test_merge_assigns_ids_in_date_order_and_unique_citekeys(news_out, tmp_path):
    late = news_raw(url="https://e.com/late", title="Acme ships version two", date_published="2025-09-01")
    early = news_raw(url="https://e.com/early", title="Acme ships first release", date_published="2025-01-01")
    kept, _, _ = _merge(tmp_path, [late, early])
    assert [(r["id"], r["url"]) for r in kept] == [("AMN-001", early["url"]), ("AMN-002", late["url"])]
    # publisher "Acme Corp" -> "acme"; first non-stopword of title -> "acme"; collision gets suffix "a".
    assert [r["citekey"] for r in kept] == ["acme2025acme", "acme2025acmea"]
    assert list(kept[0]) == nc.FINAL_KEYS
    assert nc.check(kept) == []


def test_citekey_skips_stopwords_and_handles_empty_publisher_words():
    used: set[str] = set()
    r = news_raw(publisher="The Linux Foundation", title="The Agentic AI Foundation is formed")
    assert nc.citekey(r, used) == "linux2025agentic"
    assert nc.citekey(r, used) == "linux2025agentica"


# --------------------------------------------------------------------------- biblatex


def test_bib_escape_special_characters():
    assert nc.bib_escape("R&D 50% $5 #1 a_b {x}") == r"R\&D 50\% \$5 \#1 a\_b \{x\}"
    assert nc.bib_escape("a~b^c") == r"a\textasciitilde{}b\textasciicircum{}c"


def test_bib_escape_backslash():
    assert nc.bib_escape("C:\\path") == r"C:\textbackslash{}path"


def test_to_bib_online_entry_fields_and_escaping():
    r = news_final(title="Q&A: 100% of #agents use_snake {case}", publisher="R&D Weekly",
                   authors=["Jane Doe", "John O_Neil"])
    bib = nc.to_bib(r)
    assert bib.startswith("@online{acme2025launches,\n")
    assert bib.endswith("\n}\n")
    assert r"  title = {{Q\&A: 100\% of \#agents use\_snake \{case\}}}," in bib
    assert r"  author = {Jane Doe and John O\_Neil}," in bib
    assert r"  organization = {R\&D Weekly}," in bib
    assert "  date = {2025-03-14},\n  year = {2025}," in bib
    assert "  url = {https://example.com/news/acme-protocol},\n  urldate = {2026-10-15}," in bib
    assert "  note = {AMN-001; press-release; theme T1}" in bib


def test_to_bib_without_authors_uses_braced_corporate_author():
    bib = nc.to_bib(news_final(authors=[], publisher="Smith & Sons"))
    assert r"  author = {{Smith \& Sons}}," in bib


def test_build_handles_empty_corpus(news_out):
    write_jsonl(news_out / "news.jsonl", [])
    nc.build()
    assert json.loads((news_out / "stats.json").read_text())["n"] == 0


def test_build_writes_all_outputs(news_out):
    rows = [news_final(), news_final("AMN-002", "k2", url="https://e.com/2", theme="T3", title="Other")]
    write_jsonl(news_out / "news.jsonl", rows)
    nc.build()
    bib = (news_out / "news.bib").read_text(encoding="utf-8")
    assert bib.count("@online{") == 2
    stats = json.loads((news_out / "stats.json").read_text())
    assert stats["n"] == 2 and stats["by_theme"] == {"T1": 1, "T3": 1}
    csv_lines = (news_out / "news.csv").read_text(encoding="utf-8").splitlines()
    assert csv_lines[0] == ",".join(nc.CSV_COLS) and len(csv_lines) == 3
    assert "### AMN-002" in (news_out / "digest.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- apply-audit


def _seed(news_out):
    rows = [news_final(), news_final("AMN-002", "k2", url="https://e.com/2", title="Other")]
    write_jsonl(news_out / "news.jsonl", rows)
    return (news_out / "news.jsonl").read_bytes()


def _audit(tmp_path, entries):
    return write_jsonl(tmp_path / "audit.jsonl", entries)


def test_apply_audit_applies_summary_and_fields_and_rebuilds(news_out, tmp_path):
    _seed(news_out)
    audit = _audit(tmp_path, [
        {"id": "AMN-001", "audit_pass": "1-sample", "corrected_summary": "Corrected.", "corrected_fields": {}},
        {"id": "AMN-002", "audit_pass": "1-sample", "corrected_summary": "",
         "corrected_fields": {"claim_status": "fact", "date_published": "2025-04"}},
    ])
    nc.apply_audit(audit)
    rows = read_jsonl(news_out / "news.jsonl")
    assert rows[0]["summary"] == "Corrected."
    assert rows[1]["claim_status"] == "fact" and rows[1]["date_published"] == "2025-04"
    assert [r["id"] for r in rows] == ["AMN-001", "AMN-002"]
    assert [r["citekey"] for r in rows] == ["acme2025launches", "k2"]
    assert "date = {2025-04}" in (news_out / "news.bib").read_text(encoding="utf-8")


def test_apply_audit_empty_summary_is_not_a_correction(news_out, tmp_path):
    _seed(news_out)
    nc.apply_audit(_audit(tmp_path, [{"id": "AMN-001", "corrected_summary": "", "corrected_fields": {}}]))
    assert read_jsonl(news_out / "news.jsonl")[0]["summary"] == news_raw()["summary"]


@pytest.mark.parametrize("field", ["id", "citekey", "not_a_field"])
@pytest.mark.parametrize("audit_pass", ["1-sample", "curator-prepublication"])
def test_apply_audit_refuses_protected_or_unknown_fields(news_out, tmp_path, field, audit_pass):
    before = _seed(news_out)
    audit = _audit(tmp_path, [{"id": "AMN-001", "audit_pass": audit_pass, "corrected_fields": {field: "x"}}])
    with pytest.raises(SystemExit) as exc:
        nc.apply_audit(audit)
    assert f"refusing to change field {field!r}" in str(exc.value.code)
    assert (news_out / "news.jsonl").read_bytes() == before


def test_apply_audit_unknown_id_aborts(news_out, tmp_path):
    before = _seed(news_out)
    with pytest.raises(SystemExit) as exc:
        nc.apply_audit(_audit(tmp_path, [{"id": "AMN-999", "corrected_summary": "x"}]))
    assert "unknown id AMN-999" in str(exc.value.code)
    assert (news_out / "news.jsonl").read_bytes() == before


def test_apply_audit_invalid_correction_aborts_without_writing(news_out, tmp_path):
    before = _seed(news_out)
    with pytest.raises(SystemExit) as exc:
        nc.apply_audit(_audit(tmp_path, [{"id": "AMN-001", "corrected_fields": {"date_published": "2025-13"}}]))
    assert "bad date" in str(exc.value.code)
    assert (news_out / "news.jsonl").read_bytes() == before
