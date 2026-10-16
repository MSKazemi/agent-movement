#!/usr/bin/env python3
"""Check research-question and study identifiers in the Markdown docs (stdlib only).

Two checks, both described in docs/question-id-crosswalk.md (issue #34):

1. **No bare Q#/S# IDs.** A token such as ``Q3``, ``S1`` or ``[S7]`` (word
   boundary on both sides) is ambiguous: before issue #34 it could mean a
   human-impact question, an agenda question, a stage, a flagship study or a
   source citation, depending on the file. Use a prefixed ID instead
   (AM-, HQ-, SQ-, SH-, ST-, FM-, FS-, or [SRC-n] for a citation label).
2. **Prefixed IDs must exist.** Every AM-, HQ-, SQ-, SH-, ST-, FM- and FS- ID
   used anywhere must be defined in the family's source document, so a typo
   such as ``HQ-21`` fails.

Text inside fenced code blocks, inline code spans, HTML comments and URLs is
ignored, as is any line containing ``check-ids: ignore``. The generated corpora
(docs/news-corpus/, docs/paper-corpus/) are not scanned: they are data
regenerated from raw/ by tools/*_corpus.py (where, e.g., "Q3 2025" is a calendar
quarter) and are edited only through their audit files.

Usage:
  python3 tools/check_ids.py [PATH ...]   # default: README.md docs
Exit status: 0 when clean, 1 when any finding is reported.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PATHS = ("README.md", "docs")
EXCLUDED_DIRS = ("docs/news-corpus", "docs/paper-corpus")
CROSSWALK = "docs/question-id-crosswalk.md"
IGNORE_MARKER = "check-ids: ignore"

# A hyphenated local identifier such as HB-S01 is prefixed, not a bare S01.\n# A word boundary alone also matches after a hyphen; exclude that left context.\nBARE_ID = re.compile(r"(?<![\w-])[QS]\d+\b")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# Spans whose text is not prose; each is blanked to spaces so columns stay true.
NOISE = (
    re.compile(r"<!--.*?-->"),
    re.compile(r"(`+).+?\1"),           # inline code
    re.compile(r"\]\([^)\s]*\)"),       # Markdown link target
    re.compile(r"<[a-z][a-z0-9+.-]*:[^>\s]*>", re.I),  # autolink
    re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I),     # bare URL
)

# family -> (defining document, regex whose group 1 is a defined ID)
DEFINITIONS = {
    "AM": ("docs/open-questions.md", r"^\| (AM-\d\d) \|"),
    "HQ": ("docs/top-20-human-impact-questions-for-agentic-ai.md", r"^### (HQ-\d\d)\. "),
    "SQ": ("docs/strategic-target-and-scientific-agenda.md", r"^\| \*\*P\d / (SQ-\d\d)\*\* \|"),
    "SH": ("docs/strategic-target-and-scientific-agenda.md", r"^\*\*(SH-\d) — "),
    "ST": ("docs/strategic-target-and-scientific-agenda.md", r"^\| \*\*(ST-\d) — "),
    "FM": ("docs/2031-frontier-research-agenda.md", r"^\| \*\*(FM-\d\d)\*\* \|"),
    "FS": ("docs/2031-frontier-research-agenda.md", r"^### Study (FS-\d) — "),
}
PREFIXED_ID = re.compile(r"\b(AM|HQ|SQ|FM)-\d\d\b|\b(SH|ST|FS)-\d\b")


def prose_lines(text: str):
    """Yield (line number, line) for prose, blanking code, comments and URLs."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            continue
        if IGNORE_MARKER in line:
            continue
        for pattern in NOISE:
            line = pattern.sub(lambda m: " " * len(m.group(0)), line)
        yield number, line


def bare_ids(text: str) -> list[tuple[int, int, str]]:
    """Return (line, column, token) for every bare Q#/S# token in prose."""
    return [(number, m.start() + 1, m.group(0))
            for number, line in prose_lines(text) for m in BARE_ID.finditer(line)]


def defined_ids(root: Path) -> dict[str, set[str]]:
    """Map each ID family to the IDs defined in its source document (missing file -> absent)."""
    found: dict[str, set[str]] = {}
    for family, (relpath, pattern) in DEFINITIONS.items():
        path = root / relpath
        if path.is_file():
            found[family] = set(re.findall(pattern, path.read_text(encoding="utf-8"), re.M))
    return found


def undefined_ids(text: str, defined: dict[str, set[str]]) -> list[tuple[int, int, str]]:
    """Return (line, column, ID) for prefixed IDs not defined in their family's document."""
    out = []
    for number, line in prose_lines(text):
        for m in PREFIXED_ID.finditer(line):
            ident = m.group(0)
            family = ident.split("-")[0]
            if family in defined and ident not in defined[family]:
                out.append((number, m.start() + 1, ident))
    return out


def markdown_files(root: Path, paths: list[str]) -> list[Path]:
    """Markdown files under the given paths (relative to root), minus the generated corpora."""
    root = root.resolve()
    excluded = [root / d for d in EXCLUDED_DIRS]
    files: set[Path] = set()
    for p in paths:
        path = (root / p).resolve()
        for f in (path.rglob("*.md") if path.is_dir() else [path]):
            if f.is_file() and not any(f.is_relative_to(d) for d in excluded):
                files.add(f)
    return sorted(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS),
                        help="Markdown files or directories (default: README.md docs)")
    parser.add_argument("--root", type=Path, default=REPO, help="repository root (default: this repo)")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    files = markdown_files(root, args.paths)
    defined = defined_ids(root)
    findings = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(root) if f.is_relative_to(root) else f
        for line, col, token in bare_ids(text):
            print(f"{rel}:{line}:{col}: ambiguous bare ID '{token}': use a prefixed ID (see {CROSSWALK})")
            findings += 1
        for line, col, ident in undefined_ids(text, defined):
            source = DEFINITIONS[ident.split("-")[0]][0]
            print(f"{rel}:{line}:{col}: unknown ID '{ident}': not defined in {source}")
            findings += 1
    if findings:
        print(f"check-ids: {findings} finding(s) in {len(files)} Markdown files")
        return 1
    counts = ", ".join(f"{k} {len(v)}" for k, v in defined.items())
    print(f"check-ids: ok ({len(files)} Markdown files, no bare Q#/S# IDs; defined IDs: {counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
