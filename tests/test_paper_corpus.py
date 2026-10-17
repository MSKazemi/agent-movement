"""Unit tests for tools/paper_corpus.py: schema, check, dedupe, biblatex, apply-audit."""
from __future__ import annotations

import json

import pytest

import paper_corpus as pc
from conftest import paper_final, paper_raw, read_jsonl, run_tool, write_jsonl

PREPRINT = dict(publication_type="preprint", peer_reviewed=False, venue="arXiv", doi="",
                url="https://arxiv.org/abs/2505.01234", verification_source="arxiv")


# --------------------------------------------------------------------------- schema / validate


def test_valid_raw_and_final_records_pass():
    assert pc.validate(paper_raw(), pc.RAW_KEYS) == []
    assert pc.check([paper_final()]) == []


def test_missing_field_is_reported():
    r = paper_final()
    del r["venue"]
    errs = pc.check([r])
    assert any("missing keys ['venue']" in e for e in errs)


@pytest.mark.parametrize("year", [2027, 1899, "2025", None])
def test_bad_year_is_rejected(year):
    errs = pc.validate(paper_raw(year=year), pc.RAW_KEYS)
    assert any(e.startswith("bad year") for e in errs), errs


@pytest.mark.parametrize("date", ["2025-13", "2025-05-32", "2025/05", "2024-05", "05-2025", ""])
def test_bad_or_inconsistent_date_is_rejected(date):
    errs = pc.validate(paper_raw(date_published=date), pc.RAW_KEYS)
    assert any(e.startswith("bad date") for e in errs), errs


@pytest.mark.parametrize("date", ["2025", "2025-05", "2025-05-31"])
def test_year_month_day_precision_accepted(date):
    assert pc.validate(paper_raw(date_published=date), pc.RAW_KEYS) == []


@pytest.mark.parametrize("doi", ["doi:10.1145/1", "https://doi.org/10.1145/1", "10.12/x", "10.1145/"])
def test_bad_doi_is_rejected(doi):
    assert any(e.startswith("bad doi") for e in pc.validate(paper_raw(doi=doi), pc.RAW_KEYS))


@pytest.mark.parametrize("arxiv", ["arXiv:2505.01234", "2505.123", "2505.012345", "cs/01120"])
def test_bad_arxiv_id_is_rejected(arxiv):
    assert any(e.startswith("bad arxiv_id") for e in pc.validate(paper_raw(arxiv_id=arxiv), pc.RAW_KEYS))


@pytest.mark.parametrize("arxiv", ["2505.01234", "0704.0001", "cs/0112017", "math.GT/0309136"])
def test_new_and_old_style_arxiv_ids_accepted(arxiv):
    assert pc.validate(paper_raw(arxiv_id=arxiv), pc.RAW_KEYS) == []


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("theme", "T1", "bad theme"),
        ("publication_type", "blog", "bad publication_type"),
        ("contribution_type", "opinion", "bad contribution_type"),
        ("verification_source", "google", "bad verification_source"),
        ("authors", [], "empty authors"),
        ("authors", "Alice Smith", "authors must be a list"),
        ("peer_reviewed", "true", "peer_reviewed must be bool"),
        ("verified_metadata", None, "verified_metadata must be bool"),
        ("venue", " ", "empty venue"),
        ("movement_operations", ["swim"], "bad movement_operations"),
        ("url", "doi.org/10.1145/1", "bad url"),
    ],
)
def test_bad_field_values_are_rejected(field, value, fragment):
    errs = pc.validate(paper_raw(**{field: value}), pc.RAW_KEYS)
    assert any(fragment in e for e in errs), errs


def test_check_reports_duplicate_id_and_citekey():
    a = paper_final("AMP-001", "k")
    b = paper_final("AMP-001", "k", doi="10.1145/999", arxiv_id="", title="Something else entirely")
    errs = pc.check([a, b])
    assert "duplicate id: ['AMP-001']" in errs
    assert "duplicate citekey: ['k']" in errs


def test_check_reports_duplicate_doi_case_insensitively():
    a = paper_final("AMP-001", "k1", doi="10.1145/ABC.1", arxiv_id="")
    b = paper_final("AMP-002", "k2", doi="10.1145/abc.1", arxiv_id="", title="Other title")
    assert "duplicate identifier doi:10.1145/abc.1: AMP-001 and AMP-002" in pc.check([a, b])


def test_check_reports_duplicate_arxiv_id():
    a = paper_final("AMP-001", "k1", doi="")
    b = paper_final("AMP-002", "k2", doi="", title="Other title")
    assert "duplicate identifier arxiv:2505.01234: AMP-001 and AMP-002" in pc.check([a, b])


def test_check_allows_shared_url_without_shared_identifier():
    url = "https://proceedings.example.org/volume-7"
    a = paper_final("AMP-001", "k1", doi="10.1145/1", arxiv_id="", url=url)
    b = paper_final("AMP-002", "k2", doi="10.1145/2", arxiv_id="", url=url, title="Other title")
    assert pc.check([a, b]) == []


def test_check_reports_missing_doi_instead_of_crashing():
    r = paper_final()
    del r["doi"]
    errs = pc.check([r])
    assert any("missing keys ['doi']" in e for e in errs)


def test_check_cli_exits_1_on_bad_records(tmp_path):
    write_jsonl(tmp_path / "papers.jsonl", [paper_final(year=2027)])
    res = run_tool("paper_corpus.py", "check", "--out", str(tmp_path))
    assert res.returncode == 1
    assert "bad year 2027" in res.stdout


def test_check_cli_exits_0_on_good_records(tmp_path):
    write_jsonl(tmp_path / "papers.jsonl", [paper_final()])
    res = run_tool("paper_corpus.py", "check", "--out", str(tmp_path))
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip() == "ok: 1 records valid"


# --------------------------------------------------------------------------- merge: dedupe


def _merge(tmp_path, rows, manual=None):
    raw = write_jsonl(tmp_path / "raw" / "p.jsonl", rows)
    man = None
    if manual is not None:
        man = tmp_path / "screening.json"
        man.write_text(json.dumps(manual), encoding="utf-8")
    pc.merge([raw], man)
    out = pc.OUT
    return read_jsonl(out / "papers.jsonl"), read_jsonl(out / "excluded.jsonl"), json.loads((out / "flow.json").read_text())


def test_merge_dedupes_by_doi(paper_out, tmp_path):
    a = paper_raw(arxiv_id="", title="Agent Handoff Semantics", doi="10.1145/abc.42")
    b = paper_raw(arxiv_id="", title="Totally different wording of the record", url="https://e.org/b",
                  doi="10.1145/ABC.42")
    kept, excl, flow = _merge(tmp_path, [a, b])
    assert len(kept) == 1 and flow["excluded_duplicate"] == 1
    assert excl[0]["exclusion_reason"].startswith("duplicate of '")


def test_merge_dedupes_by_arxiv_id(paper_out, tmp_path):
    a = paper_raw(doi="10.1145/1", title="Agent Handoff Semantics")
    b = paper_raw(doi="10.1145/2", title="Unrelated looking title for the same eprint", url="https://e.org/b")
    kept, _, flow = _merge(tmp_path, [a, b])
    assert len(kept) == 1 and flow["excluded_duplicate"] == 1


def test_merge_dedupes_by_normalised_title(paper_out, tmp_path):
    a = paper_raw(doi="10.1145/1", arxiv_id="", url="https://e.org/a")
    b = paper_raw(doi="10.1145/2", arxiv_id="", url="https://e.org/b",
                  title="A protocol for agent-interoperability.", theme="P6")
    kept, excl, _ = _merge(tmp_path, [a, b])
    assert len(kept) == 1
    assert excl[0]["exclusion_reason"] == f"duplicate of '{kept[0]['title']}' ({kept[0]['theme']})"


def test_merge_keeps_distinct_papers(paper_out, tmp_path):
    a = paper_raw()
    b = paper_raw(doi="10.1145/2", arxiv_id="2506.00001", url="https://e.org/b",
                  title="Durable Execution for Long-Running LLM Agents")
    kept, excl, _ = _merge(tmp_path, [a, b])
    assert len(kept) == 2 and excl == []


@pytest.mark.parametrize("order", ["preprint-first", "published-first"])
def test_merge_prefers_published_peer_reviewed_version(paper_out, tmp_path, order):
    preprint = paper_raw(year=2025, date_published="2025-02", **PREPRINT)
    published = paper_raw(year=2026, date_published="2026-03", publication_type="conference",
                          peer_reviewed=True, doi="10.1145/3700000.1")
    rows = [preprint, published] if order == "preprint-first" else [published, preprint]
    kept, excl, _ = _merge(tmp_path, rows)
    assert len(kept) == 1
    assert kept[0]["peer_reviewed"] is True and kept[0]["doi"] == "10.1145/3700000.1"
    assert kept[0]["arxiv_id"] == "2505.01234"
    assert excl[0]["publication_type"] == "preprint"


def test_merge_retains_preprint_arxiv_id_on_published_version(paper_out, tmp_path):
    preprint = paper_raw(**PREPRINT)
    published = paper_raw(arxiv_id="", doi="10.1145/3700000.1")
    kept, _, _ = _merge(tmp_path, [preprint, published])
    assert kept[0]["doi"] == "10.1145/3700000.1"
    assert kept[0]["arxiv_id"] == "2505.01234"


def test_merge_excludes_unverified_metadata(paper_out, tmp_path):
    other = paper_raw(doi="10.1145/2", arxiv_id="", url="https://e.org/b", title="Durable Agent Execution")
    kept, excl, flow = _merge(tmp_path, [paper_raw(verified_metadata=False), other])
    assert [r["title"] for r in kept] == [other["title"]]
    assert excl[0]["exclusion_reason"] == "metadata not verified against an authoritative source"
    assert flow["excluded_unverified"] == 1


def test_merge_manual_screening_matches_normalised_title(paper_out, tmp_path):
    other = paper_raw(doi="10.1145/2", arxiv_id="", url="https://e.org/b", title="Durable Agent Execution")
    kept, excl, flow = _merge(tmp_path, [paper_raw(), other],
                              manual=[{"title": "A Protocol for Agent Interoperability!", "reason": "off-topic"}])
    assert [r["title"] for r in kept] == [other["title"]]
    assert excl[0]["exclusion_reason"] == "manual screening: off-topic"
    assert flow["excluded_manual_screening"] == 1


def test_merge_assigns_ids_chronologically_and_ascii_citekeys(paper_out, tmp_path):
    new = paper_raw(year=2025, date_published="2025-05", title="Towards Portable Agents")
    old = paper_raw(year=1998, date_published="1998", doi="10.1007/1", arxiv_id="", url="https://e.org/old",
                    title="Mobile Agents: An Overview", authors=["José Müller-Lüdenscheidt"],
                    publication_type="journal", venue="Journal of Agents")
    kept, _, _ = _merge(tmp_path, [new, old])
    assert [r["id"] for r in kept] == ["AMP-001", "AMP-002"]
    assert kept[0]["year"] == 1998
    assert kept[0]["citekey"] == "mullerludenscheidt1998mobile"
    assert kept[1]["citekey"] == "smith2025portable"  # "towards" is a stopword
    assert list(kept[0]) == pc.FINAL_KEYS


# --------------------------------------------------------------------------- biblatex


@pytest.mark.parametrize(
    "ptype,entry,venue_field",
    [
        ("journal", "article", "journaltitle"),
        ("conference", "inproceedings", "booktitle"),
        ("workshop", "inproceedings", "booktitle"),
        ("book-chapter", "incollection", "booktitle"),
        ("tech-report", "report", "institution"),
        ("whitepaper", "report", "institution"),
        ("preprint", "online", "organization"),
    ],
)
def test_to_bib_entry_type_mapping(ptype, entry, venue_field):
    bib = pc.to_bib(paper_final(publication_type=ptype, venue="R&D Lab"))
    assert bib.startswith(f"@{entry}{{smith2025protocol,\n")
    assert f"  {venue_field} = {{R\\&D Lab}}," in bib


@pytest.mark.parametrize("ptype,label", [("tech-report", "Technical report"), ("whitepaper", "White paper")])
def test_to_bib_report_type_label(ptype, label):
    assert f"  type = {{{label}}}," in pc.to_bib(paper_final(publication_type=ptype))


@pytest.mark.parametrize("venue", ["arXiv", "arxiv preprint"])
def test_to_bib_arxiv_preprint_has_no_organization(venue):
    bib = pc.to_bib(paper_final(**{**PREPRINT, "venue": venue}))
    assert bib.startswith("@online{")
    assert "organization" not in bib


def test_to_bib_eprint_and_doi_fields():
    bib = pc.to_bib(paper_final())
    assert "  doi = {10.1145/1234567.7654321}," in bib
    assert "  eprint = {2505.01234},\n  eprinttype = {arxiv}," in bib
    bare = pc.to_bib(paper_final(doi="", arxiv_id=""))
    assert "doi =" not in bare and "eprint" not in bare


def test_to_bib_escapes_and_marks_non_peer_reviewed():
    r = paper_final(title="Agents & Tools: 99% safe_ish #1 {really}", authors=["A. O_Brien", "B. Smith"],
                    **PREPRINT)
    bib = pc.to_bib(r)
    assert r"  author = {A. O\_Brien and B. Smith}," in bib
    assert r"  title = {{Agents \& Tools: 99\% safe\_ish \#1 \{really\}}}," in bib
    assert "  date = {2025-05},\n  year = {2025}," in bib
    assert "  note = {AMP-001; theme P2; not peer reviewed}\n}\n" in bib
    assert "not peer reviewed" not in pc.to_bib(paper_final())


def test_build_handles_empty_corpus(paper_out):
    write_jsonl(paper_out / "papers.jsonl", [])
    pc.build()
    assert json.loads((paper_out / "stats.json").read_text())["n"] == 0


def test_build_writes_all_outputs(paper_out):
    rows = [paper_final(), paper_final("AMP-002", "k2", doi="10.1145/2", arxiv_id="", url="https://e.org/2",
                                       title="Other paper", publication_type="journal", theme="P5")]
    write_jsonl(paper_out / "papers.jsonl", rows)
    pc.build()
    bib = (paper_out / "papers.bib").read_text(encoding="utf-8")
    assert bib.count("@inproceedings{") == 1 and bib.count("@article{") == 1
    stats = json.loads((paper_out / "stats.json").read_text())
    assert stats["n"] == 2 and stats["with_doi"] == 2 and stats["with_arxiv"] == 1
    assert "### AMP-002" in (paper_out / "digest.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- apply-audit


def _seed(paper_out):
    rows = [paper_final(), paper_final("AMP-002", "jones2025other", doi="10.1145/2", arxiv_id="",
                                       url="https://e.org/2", title="Other paper")]
    write_jsonl(paper_out / "papers.jsonl", rows)
    return (paper_out / "papers.jsonl").read_bytes()


def _audit(tmp_path, entries):
    return write_jsonl(tmp_path / "audit.jsonl", entries)


def test_apply_audit_applies_summary_and_fields(paper_out, tmp_path):
    _seed(paper_out)
    pc.apply_audit(_audit(tmp_path, [
        {"id": "AMP-001", "audit_pass": "independent-full", "corrected_summary": "Better.",
         "corrected_fields": {"peer_reviewed": False, "publication_type": "preprint"}},
    ]))
    r = read_jsonl(paper_out / "papers.jsonl")[0]
    assert r["summary"] == "Better." and r["peer_reviewed"] is False
    assert r["citekey"] == "smith2025protocol" and r["id"] == "AMP-001"
    assert "@online{smith2025protocol," in (paper_out / "papers.bib").read_text(encoding="utf-8")


def test_apply_audit_curator_prepublication_may_rekey_citekey(paper_out, tmp_path):
    _seed(paper_out)
    pc.apply_audit(_audit(tmp_path, [
        {"id": "AMP-001", "audit_pass": "curator-prepublication",
         "corrected_fields": {"year": 2026, "date_published": "2026-01", "citekey": "smith2026protocol"}},
    ]))
    r = read_jsonl(paper_out / "papers.jsonl")[0]
    assert r["citekey"] == "smith2026protocol" and r["id"] == "AMP-001"
    bib = (paper_out / "papers.bib").read_text(encoding="utf-8")
    assert "{smith2026protocol," in bib and "smith2025protocol" not in bib


@pytest.mark.parametrize("audit_pass", ["independent-full", "curator", "", None])
def test_apply_audit_refuses_rekey_without_curator_prepublication(paper_out, tmp_path, audit_pass):
    before = _seed(paper_out)
    entry = {"id": "AMP-001", "corrected_fields": {"citekey": "smith2026protocol"}}
    if audit_pass is not None:
        entry["audit_pass"] = audit_pass
    with pytest.raises(SystemExit) as exc:
        pc.apply_audit(_audit(tmp_path, [entry]))
    assert "refusing to change field 'citekey'" in str(exc.value.code)
    assert (paper_out / "papers.jsonl").read_bytes() == before


@pytest.mark.parametrize("field", ["id", "not_a_field"])
def test_apply_audit_curator_prepublication_cannot_change_id_or_unknown_field(paper_out, tmp_path, field):
    before = _seed(paper_out)
    with pytest.raises(SystemExit) as exc:
        pc.apply_audit(_audit(tmp_path, [{"id": "AMP-001", "audit_pass": "curator-prepublication",
                                          "corrected_fields": {field: "x"}}]))
    assert f"refusing to change field {field!r}" in str(exc.value.code)
    assert (paper_out / "papers.jsonl").read_bytes() == before


def test_apply_audit_rekey_collision_aborts_without_writing(paper_out, tmp_path):
    before = _seed(paper_out)
    with pytest.raises(SystemExit) as exc:
        pc.apply_audit(_audit(tmp_path, [{"id": "AMP-001", "audit_pass": "curator-prepublication",
                                          "corrected_fields": {"citekey": "jones2025other"}}]))
    assert "duplicate citekey" in str(exc.value.code)
    assert (paper_out / "papers.jsonl").read_bytes() == before


def test_apply_audit_unknown_id_aborts(paper_out, tmp_path):
    before = _seed(paper_out)
    with pytest.raises(SystemExit) as exc:
        pc.apply_audit(_audit(tmp_path, [{"id": "AMP-404", "corrected_summary": "x"}]))
    assert "unknown id AMP-404" in str(exc.value.code)
    assert (paper_out / "papers.jsonl").read_bytes() == before


def test_apply_audit_invalid_correction_aborts_without_writing(paper_out, tmp_path):
    before = _seed(paper_out)
    with pytest.raises(SystemExit) as exc:
        pc.apply_audit(_audit(tmp_path, [{"id": "AMP-001", "corrected_fields": {"year": 2026}}]))
    assert "bad date" in str(exc.value.code)  # date 2025-05 no longer matches year 2026
    assert (paper_out / "papers.jsonl").read_bytes() == before
