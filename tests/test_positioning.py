"""The one positioning statement is byte-identical on every surface (issue #44).

Markdown surfaces mark it with ``<!-- positioning:start -->`` / ``<!-- positioning:end -->``.
In CITATION.cff it is the first paragraph of the folded (``>-``) abstract, written on one line.
Stdlib only: the CFF abstract is read line by line, not with a YAML parser.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MARKDOWN_SURFACES = (
    "README.md",
    "docs/strategic-target-and-scientific-agenda.md",
    "docs/2031-frontier-research-agenda.md",
)
MARKED = re.compile(r"<!-- positioning:start -->\n(.*?)\n<!-- positioning:end -->", re.S)
PREFIX = "Agent Movement is a research prototype: "


def markdown_statement(rel: str) -> str:
    blocks = MARKED.findall((REPO / rel).read_text(encoding="utf-8"))
    assert len(blocks) == 1, f"{rel}: expected exactly one positioning block, found {len(blocks)}"
    return blocks[0]


def cff_statement() -> str:
    lines = (REPO / "CITATION.cff").read_text(encoding="utf-8").split("\n")
    start = lines.index("abstract: >-") + 1
    paragraph = []
    for line in lines[start:]:
        if not line.strip():
            break
        assert line.startswith("  "), f"CITATION.cff: abstract line is not indented: {line!r}"
        paragraph.append(line[2:])
    # A folded scalar joins the lines of one paragraph with single spaces.
    return " ".join(paragraph)


def test_readme_statement_is_well_formed():
    stmt = markdown_statement("README.md")
    assert stmt.startswith(PREFIX)
    assert "\n" not in stmt and stmt == stmt.strip()


@pytest.mark.parametrize("rel", MARKDOWN_SURFACES[1:])
def test_markdown_surface_matches_readme(rel):
    assert markdown_statement(rel).encode("utf-8") == markdown_statement("README.md").encode("utf-8")


def test_citation_abstract_matches_readme():
    assert cff_statement().encode("utf-8") == markdown_statement("README.md").encode("utf-8")
