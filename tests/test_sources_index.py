"""Tests for tools/sources_index.py (the URL index in docs/sources.md).

The committed repository is only read. Every test that writes works on a copy of
README.md and docs/ in tmp_path and passes it to the tool with --root.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import sources_index as si
from conftest import DOCS, REPO, run_tool

SOURCES = Path("docs/sources.md")


@pytest.fixture
def repo_copy(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy2(REPO / "README.md", root / "README.md")
    shutil.copytree(DOCS, root / "docs")
    return root


def check(root: Path):
    return run_tool("sources_index.py", "--root", str(root), "check")


def generate(root: Path, *extra: str):
    return run_tool("sources_index.py", "--root", str(root), "generate", *extra)


def write_doc(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def rows_of(root: Path) -> dict[tuple[str, str], si.Row]:
    _, section, _ = si.split_sources((root / SOURCES).read_text(encoding="utf-8"))
    rows, problems = si.parse_section(section)
    assert problems == []
    return rows


# ------------------------------------------------------------- the committed repo

def test_check_passes_on_repo():
    r = check(REPO)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sources: ok" in r.stdout


def test_generate_on_repo_copy_is_a_no_op(repo_copy):
    before = (repo_copy / SOURCES).read_bytes()
    r = generate(repo_copy)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (repo_copy / SOURCES).read_bytes() == before


def test_corpus_and_generated_files_are_not_scanned():
    rels = si.doc_files(REPO)
    assert "README.md" in rels and "docs/sources.md" in rels
    for rel in rels:
        assert not rel.startswith(("docs/news-corpus/", "docs/paper-corpus/", "docs/corpus-analysis/"))
        assert not rel.startswith("docs/corpus-qa/link-health-")
        assert rel != "docs/evidence-map.md"


# --------------------------------------------------------------- check failures

def test_new_unindexed_url_fails_check(repo_copy):
    write_doc(repo_copy, "docs/new-topic.md",
              "# New topic\n\n**Reviewed:** 2026-10-16.\n\nSee [the spec](https://new-standard.org/spec/v2).\n")
    r = check(repo_copy)
    assert r.returncode == 1
    assert "UNINDEXED  docs/new-topic.md:5  https://new-standard.org/spec/v2" in r.stdout
    assert "1 unindexed" in r.stdout


def test_new_url_in_existing_doc_fails_check(repo_copy):
    p = repo_copy / "docs/glossary.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nAlso see https://w3c.github.io/new-draft/.\n",
                 encoding="utf-8")
    r = check(repo_copy)
    assert r.returncode == 1
    assert "https://w3c.github.io/new-draft/" in r.stdout


def test_known_url_cited_by_a_new_doc_fails_check(repo_copy):
    # The URL is indexed already, but not for this document.
    write_doc(repo_copy, "docs/new-topic.md", "# T\n\n<https://www.rfc-editor.org/rfc/rfc8693>\n")
    r = check(repo_copy)
    assert r.returncode == 1
    assert "UNINDEXED  docs/new-topic.md:3  https://www.rfc-editor.org/rfc/rfc8693" in r.stdout


def test_removed_citation_is_reported_stale(repo_copy):
    (repo_copy / "docs/how-to-cite.md").unlink()
    r = check(repo_copy)
    assert r.returncode == 1
    assert "STALE" in r.stdout and "https://citation-file-format.github.io/" in r.stdout


def test_missing_section_fails_check(repo_copy):
    p = repo_copy / SOURCES
    before, _, after = si.split_sources(p.read_text(encoding="utf-8"))
    p.write_text(before + after, encoding="utf-8")
    r = check(repo_copy)
    assert r.returncode == 1
    assert "NO-SECTION" in r.stdout


def test_row_without_access_date_fails_check(repo_copy):
    p = repo_copy / SOURCES
    text = p.read_text(encoding="utf-8")
    old = "| <https://citation-file-format.github.io/> | how-to-cite | "
    i = text.index(old) + len(old)
    j = text.index(" |", i)
    p.write_text(text[:i] + "n/a" + text[j:], encoding="utf-8")
    r = check(repo_copy)
    assert r.returncode == 1
    assert "NO-DATE" in r.stdout


# ------------------------------------------------------------------- generation

def test_generate_then_check_round_trips(repo_copy):
    top = (repo_copy / SOURCES).read_text(encoding="utf-8").split(si.SECTION_START)[0]
    write_doc(repo_copy, "docs/sub/new-topic.md",
              "# New topic\n\n**Reviewed:** 2026-10-16.\n\n- [A](https://a.org/x).\n"
              "- https://b.org/y?q=1#section-2\n")
    assert check(repo_copy).returncode == 1
    r = generate(repo_copy)
    assert r.returncode == 0, r.stdout + r.stderr
    r = check(repo_copy)
    assert r.returncode == 0, r.stdout
    text = (repo_copy / SOURCES).read_text(encoding="utf-8")
    assert text.startswith(top)  # hand-written top kept byte for byte
    assert "### [sub/new-topic](sub/new-topic.md)" in text
    assert "| <https://b.org/y?q=1> | sub/new-topic | 2026-10-16 | document |" in text
    # Deterministic: a second run changes nothing.
    once = (repo_copy / SOURCES).read_bytes()
    assert generate(repo_copy).returncode == 0
    assert (repo_copy / SOURCES).read_bytes() == once


def test_generate_appends_section_when_markers_are_missing(repo_copy):
    p = repo_copy / SOURCES
    before, _, after = si.split_sources(p.read_text(encoding="utf-8"))
    p.write_text(before + after, encoding="utf-8")
    assert generate(repo_copy).returncode == 0
    assert check(repo_copy).returncode == 0
    assert p.read_text(encoding="utf-8").rstrip().endswith(si.SECTION_END)


def test_manual_dates_survive_regeneration(repo_copy):
    p = repo_copy / SOURCES
    url = "https://citation-file-format.github.io/"
    row = rows_of(repo_copy)[("how-to-cite", url)]
    assert row.basis == "default"
    text = p.read_text(encoding="utf-8")
    old = f"| <{url}> | {row.cited_in} | {row.accessed} | {row.basis} |"
    p.write_text(text.replace(old, f"| <{url}> | {row.cited_in} | 2025-01-02 | manual |"), encoding="utf-8")
    # An unrelated change forces a real rewrite of the section.
    write_doc(repo_copy, "docs/new-topic.md", "# T\n\nhttps://c.org/z\n")
    for extra in ((), ("--refresh-dates",)):
        assert generate(repo_copy, *extra).returncode == 0
        kept = rows_of(repo_copy)[("how-to-cite", url)]
        assert (kept.accessed, kept.basis) == ("2025-01-02", "manual")
    assert check(repo_copy).returncode == 0


def test_stored_automatic_dates_are_kept_unless_refreshed(repo_copy):
    write_doc(repo_copy, "docs/new-topic.md", "# T\n\n**Reviewed:** 2026-10-01.\n\nhttps://c.org/z\n")
    assert generate(repo_copy).returncode == 0
    assert rows_of(repo_copy)[("new-topic", "https://c.org/z")].accessed == "2026-10-01"
    write_doc(repo_copy, "docs/new-topic.md", "# T\n\n**Reviewed:** 2026-10-09.\n\nhttps://c.org/z\n")
    assert generate(repo_copy).returncode == 0
    assert rows_of(repo_copy)[("new-topic", "https://c.org/z")].accessed == "2026-10-01"
    assert check(repo_copy).returncode == 0
    assert generate(repo_copy, "--refresh-dates").returncode == 0
    assert rows_of(repo_copy)[("new-topic", "https://c.org/z")].accessed == "2026-10-09"


# ---------------------------------------------------------- extraction rules

@pytest.mark.parametrize("raw, want", [
    ("https://a.org/b).", "https://a.org/b"),
    ("https://a.org/b));", "https://a.org/b"),
    ("https://a.org/wiki/X_(y)", "https://a.org/wiki/X_(y)"),
    ("https://a.org/b**", "https://a.org/b"),
    ("https://a.org/b/:", "https://a.org/b/"),
])
def test_clean_url_strips_markdown_residue(raw, want):
    assert si.clean_url(raw) == want


@pytest.mark.parametrize("url, want", [
    ("HTTPS://Spec.Standards.ORG/Path/#413-taskstate", "https://spec.standards.org/Path/"),
    ("https://app.org/#/route/a", "https://app.org/#/route/a"),
    ("https://a.org/x?hub=1", "https://a.org/x?hub=1"),
    ("http://127.0.0.1:8080/x", None),
    ("http://localhost/x", None),
    ("https://example.com/x", None),
    ("https://github.com/MSKazemi/agent-movement/issues/7", None),
    ("https://GitHub.com/MSKazemi/agent-movement-other", "https://github.com/MSKazemi/agent-movement-other"),
])
def test_normalize(url, want):
    assert si.normalize(url) == want


def test_scan_skips_code_templates_and_dates_citations(tmp_path):
    write_doc(tmp_path, "docs/t.md", "\n".join([
        "# Title",
        "",
        "**Last reviewed:** 2026-10-03. Sources accessed on 2026-10-04.",
        "",
        "Inline `https://in.code.org/x` and a template https://w3.org/TR/<shortname>/ here.",
        "```bash",
        "curl https://fenced.org/api",
        "```",
        "A [link](https://doc.org/a) and (checked 2026-10-09) https://cite.org/b.",
        "",
        "## Sources (accessed 2026-10-07)",
        "",
        "- https://section.org/c",
        "- https://cite.org/b",
    ]) + "\n")
    doc = si.scan_doc(tmp_path, "docs/t.md", own_section=False)
    assert sorted(doc.citations) == ["https://cite.org/b", "https://doc.org/a", "https://section.org/c"]
    assert doc.header_date == "2026-10-04"  # "accessed" wins over "Last reviewed"
    dates = {u: si.derived_date(doc, c) for u, c in doc.citations.items()}
    assert dates["https://doc.org/a"] == ("2026-10-04", "document")
    assert dates["https://cite.org/b"] == ("2026-10-09", "citation")
    assert dates["https://section.org/c"] == ("2026-10-07", "section")


def test_default_date_when_document_has_none(tmp_path):
    write_doc(tmp_path, "docs/t.md", "# Title\n\nSee https://x.org/.\n")
    doc = si.scan_doc(tmp_path, "docs/t.md", own_section=False)
    assert si.derived_date(doc, doc.citations["https://x.org/"]) == (si.DEFAULT_ACCESS_DATE, "default")


def test_generated_markdown_is_skipped(tmp_path):
    write_doc(tmp_path, "docs/t.md", "# T\n\n<!-- Generated by tools/x.py; do not edit by hand. -->\n\nhttps://x.org/\n")
    assert si.scan_doc(tmp_path, "docs/t.md", own_section=False) is None
