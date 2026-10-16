"""Tests for tools/check_ids.py: bare Q#/S# detection and unknown prefixed IDs (issue #34)."""
from __future__ import annotations

from pathlib import Path

import check_ids as ci

REPO = Path(__file__).resolve().parent.parent


def tokens(text: str) -> list[str]:
    return [token for _, _, token in ci.bare_ids(text)]


def test_bare_ids_are_found_with_line_and_column():
    text = "intro\nSee Q19 and stage S2, cited [S7] and [S1, S2].\n"
    assert ci.bare_ids(text)[0] == (2, 5, "Q19")
    assert tokens(text) == ["Q19", "S2", "S7", "S1", "S2"]


def test_prefixed_ids_and_other_words_are_not_bare():
    text = "HQ-19, SQ-03, ST-0, FS-1, SH-2, [SRC-7], HX1, RQ1, Q&A, S3x, AQ1, SQL and E2.\n"
    assert tokens(text) == []


def test_code_urls_comments_and_ignore_marker_are_skipped():
    text = "\n".join([
        "Inline `Q1` code and ``S2 `x` `` spans.",
        "[link](https://example.org/S1/Q2) and <https://example.org/Q3> and https://e.org/pii/S1042",
        "<!-- old label S4 -->",
        "Calendar Q3 2025 <!-- check-ids: ignore -->",
        "```",
        "Q5 inside a fenced block",
        "~~~ still inside: a different fence character does not close it",
        "```",
        "~~~~",
        "S6 inside a tilde fence",
        "~~~~",
        "but Q7 after the fences counts",
    ])
    assert ci.bare_ids(text) == [(12, 5, "Q7")]


def test_unknown_prefixed_ids_are_reported():
    defined = {"HQ": {"HQ-01", "HQ-19"}, "ST": {"ST-0"}}
    text = "HQ-19 and HQ-21; ST-0 and ST-9; AM-99 is not checked without its definitions.\n"
    assert ci.undefined_ids(text, defined) == [(1, 11, "HQ-21"), (1, 27, "ST-9")]


def test_main_on_a_small_tree(tmp_path, capsys):
    docs = tmp_path / "docs"
    (docs / "news-corpus").mkdir(parents=True)
    (docs / "open-questions.md").write_text("| AM-01 | P0 | x |\n| AM-02 | P0 | y |\n")
    (docs / "news-corpus" / "digest.md").write_text("Revenue in Q3 2025.\n")  # excluded
    (tmp_path / "README.md").write_text("Answers AM-01 and AM-02.\n")
    assert ci.main(["--root", str(tmp_path)]) == 0
    assert "check-ids: ok (2 Markdown files" in capsys.readouterr().out

    (docs / "agenda.md").write_text("Stage S1 tests AM-03.\n")
    assert ci.main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "docs/agenda.md:1:7: ambiguous bare ID 'S1'" in out
    assert "docs/agenda.md:1:16: unknown ID 'AM-03': not defined in docs/open-questions.md" in out


def test_repository_docs_pass():
    defined = ci.defined_ids(REPO)
    assert {k: len(v) for k, v in defined.items()} == {
        "AM": 16, "HQ": 20, "SQ": 12, "SH": 3, "ST": 6, "FM": 20, "FS": 4}
    assert ci.main([]) == 0
