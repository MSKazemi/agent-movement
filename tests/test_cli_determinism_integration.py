"""CLI-level tests: byte-identical rebuilds, deterministic merge, and the committed corpora.

All tools run as subprocesses with sys.executable and --out pointing into tmp_path.
The committed docs/ data is only read (and copied); nothing is written into docs/.
"""
from __future__ import annotations

import shutil

import pytest

from conftest import DOCS, news_raw, paper_raw, run_tool, write_jsonl

CORPORA = {
    # script, canonical data file, generated outputs, committed corpus dir
    "news": ("news_corpus.py", "news.jsonl", ["news.csv", "news.bib", "digest.md", "stats.json"],
             DOCS / "news-corpus"),
    "paper": ("paper_corpus.py", "papers.jsonl", ["papers.csv", "papers.bib", "digest.md", "stats.json"],
              DOCS / "paper-corpus"),
}


def _snapshot(d):
    return {p.name: p.read_bytes() for p in sorted(d.iterdir()) if p.is_file()}


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_build_twice_is_byte_identical(tmp_path, corpus):
    script, data, outputs, src = CORPORA[corpus]
    snaps = []
    for name in ("a", "b"):
        d = tmp_path / name
        d.mkdir()
        shutil.copy(src / data, d / data)
        res = run_tool(script, "build", "--out", str(d))
        assert res.returncode == 0, res.stdout + res.stderr
        snaps.append(_snapshot(d))
    assert set(snaps[0]) == {data, *outputs}
    assert snaps[0] == snaps[1]
    # Rebuilding in place is idempotent too.
    res = run_tool(script, "build", "--out", str(tmp_path / "a"))
    assert res.returncode == 0
    assert _snapshot(tmp_path / "a") == snaps[0]


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_rebuild_reproduces_committed_outputs(tmp_path, corpus):
    """The committed generated files are exactly what the tool produces from the committed data."""
    script, data, outputs, src = CORPORA[corpus]
    shutil.copy(src / data, tmp_path / data)
    res = run_tool(script, "build", "--out", str(tmp_path))
    assert res.returncode == 0, res.stdout + res.stderr
    for name in outputs:
        assert (tmp_path / name).read_bytes() == (src / name).read_bytes(), f"{name} drifted from {data}"


def _news_raw_set():
    titles = ["Acme launches open agent handoff protocol", "Regulator publishes agent identity guidance",
              "Durable execution engine adds agent checkpoints", "MCP registry reaches general availability",
              "Acme Launches Open Agent Handoff Protocol!"]
    themes = ["T1", "T3", "T4", "T2", "T1"]
    return [news_raw(theme=th, title=t, url=f"https://e.com/{i}", date_published=f"2025-0{i + 1}-01",
                     primary_source=bool(i % 2))
            for i, (t, th) in enumerate(zip(titles, themes))]


def _paper_raw_set():
    return [
        paper_raw(),
        paper_raw(publication_type="preprint", peer_reviewed=False, venue="arXiv", doi="",
                  url="https://arxiv.org/abs/2505.01234", verification_source="arxiv"),
        paper_raw(title="Mobile Agents: An Overview", year=1998, date_published="1998", doi="10.1007/1",
                  arxiv_id="", url="https://e.org/1", publication_type="journal", authors=["José Müller"]),
        paper_raw(title="Durable Execution for LLM Agents", doi="10.1145/2", arxiv_id="2506.00001",
                  url="https://e.org/2", theme="P5"),
        paper_raw(title="Unverified Thing", doi="10.1145/3", arxiv_id="", url="https://e.org/3",
                  verified_metadata=False),
    ]


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_merge_twice_is_byte_identical(tmp_path, corpus):
    script = CORPORA[corpus][0]
    rows = _news_raw_set() if corpus == "news" else _paper_raw_set()
    raw = write_jsonl(tmp_path / "raw" / "theme.jsonl", rows)
    extra = ["--target", "3"] if corpus == "news" else []
    snaps = []
    for name in ("a", "b"):
        d = tmp_path / name
        res = run_tool(script, "merge", str(raw), *extra, "--out", str(d))
        assert res.returncode == 0, res.stdout + res.stderr
        snaps.append(_snapshot(d))
    assert snaps[0] == snaps[1]
    assert {"excluded.jsonl", "flow.json"} <= set(snaps[0])
    check = run_tool(script, "check", "--out", str(tmp_path / "a"))
    assert check.returncode == 0, check.stdout


@pytest.mark.parametrize("corpus,expected", [("news", 100), ("paper", 75)])
def test_check_passes_on_committed_corpus(corpus, expected):
    script, _, _, src = CORPORA[corpus]
    res = run_tool(script, "check", "--out", str(src))
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.strip() == f"ok: {expected} records valid"


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_check_default_out_is_committed_corpus(corpus):
    """Without --out, check reads the committed corpus (read-only) and passes."""
    res = run_tool(CORPORA[corpus][0], "check")
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.startswith("ok: ")


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_unknown_command_prints_usage_and_fails(corpus):
    res = run_tool(CORPORA[corpus][0], "frobnicate")
    assert res.returncode != 0
    assert "Usage:" in res.stderr
