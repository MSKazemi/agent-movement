"""Shared fixtures for the corpus-tool tests.

`tools/` is put on sys.path by `pythonpath` in pyproject.toml, so the tools are
imported as `news_corpus` and `paper_corpus` (the same way paper_corpus imports
news_corpus). Every test that writes output points the module-level OUT at
tmp_path; nothing is ever written into docs/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import news_corpus
import paper_corpus

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
DOCS = REPO / "docs"


def news_raw(**over) -> dict:
    """A minimal valid raw news record (RAW_KEYS order)."""
    r = {
        "theme": "T1",
        "title": "Acme launches open agent handoff protocol",
        "publisher": "Acme Corp",
        "authors": ["Jane Doe"],
        "date_published": "2025-03-14",
        "url": "https://example.com/news/acme-protocol",
        "date_accessed": "2026-10-15",
        "source_type": "press-release",
        "primary_source": True,
        "technologies": ["A2A"],
        "movement_operations": ["delegation"],
        "summary": "Acme announced a protocol.",
        "relevance": "Shows delegation between agents.",
        "claim_status": "vendor-claim",
        "verified_fetch": True,
        "search_query": "acme agent protocol",
        "notes": "",
    }
    r.update(over)
    return r


def news_final(id_: str = "AMN-001", citekey: str = "acme2025launches", **over) -> dict:
    return {"id": id_, "citekey": citekey, **news_raw(**over)}


def paper_raw(**over) -> dict:
    """A minimal valid raw paper record (RAW_KEYS order)."""
    r = {
        "theme": "P2",
        "title": "A Protocol for Agent Interoperability",
        "authors": ["Alice Smith", "Bob Jones"],
        "year": 2025,
        "date_published": "2025-05",
        "venue": "Proceedings of the Agents Conference",
        "publication_type": "conference",
        "peer_reviewed": True,
        "doi": "10.1145/1234567.7654321",
        "arxiv_id": "2505.01234",
        "url": "https://doi.org/10.1145/1234567.7654321",
        "date_accessed": "2026-10-15",
        "technologies": ["A2A"],
        "movement_operations": ["delegation"],
        "contribution_type": "system",
        "summary": "Proposes a protocol.",
        "relevance": "Agent-to-agent delegation.",
        "verified_metadata": True,
        "verification_source": "crossref",
        "search_query": "agent interoperability protocol",
        "notes": "",
    }
    r.update(over)
    return r


def paper_final(id_: str = "AMP-001", citekey: str = "smith2025protocol", **over) -> dict:
    return {"id": id_, "citekey": citekey, **paper_raw(**over)}


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_tool(script: str, *args: str) -> subprocess.CompletedProcess:
    """Run a tool as a CLI, exactly as a user would."""
    return subprocess.run(
        [sys.executable, str(TOOLS / script), *args],
        capture_output=True, text=True, cwd=REPO, timeout=120,
    )


@pytest.fixture
def news_out(tmp_path, monkeypatch) -> Path:
    out = tmp_path / "news"
    out.mkdir()
    monkeypatch.setattr(news_corpus, "OUT", out)
    return out


@pytest.fixture
def paper_out(tmp_path, monkeypatch) -> Path:
    out = tmp_path / "papers"
    out.mkdir()
    monkeypatch.setattr(paper_corpus, "OUT", out)
    return out
