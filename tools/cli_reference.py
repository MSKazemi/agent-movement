#!/usr/bin/env python3
"""Generate or check the CLI reference in docs/cli.md from the live ``--help`` output.

    python tools/cli_reference.py           # rewrite the generated block of docs/cli.md
    python tools/cli_reference.py --check   # exit 1 if docs/cli.md disagrees with --help

Every section is the real ``agent-movement ... --help`` text, captured in-process from
the parsers the subcommands forward to, so a flag added to a module shows up here
without touching the CLI. Sub-subcommands are discovered from the parsers themselves
(the ``{a,b,c}`` line of a subparser group), never listed by hand.

``--check`` compares the text with all whitespace removed, so line wrapping (which
argparse also does after hyphens) and Python-version layout changes do not count as drift. A command whose help cannot be rendered in
this environment (``relocate`` needs the optional ``relocation`` extra just to import)
is skipped and reported, not failed; regenerating needs every extra installed.

Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import sys
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))  # document the working tree, installed or not

from agent_movement import cli  # noqa: E402

DOC = ROOT / "docs" / "cli.md"
BEGIN = "<!-- BEGIN GENERATED CLI REFERENCE: edit tools/cli_reference.py, then run `make cli-docs` -->"
END = "<!-- END GENERATED CLI REFERENCE -->"
WIDTH = "100"
SUBCOMMANDS = re.compile(r"^  \{([^}]+)\}", re.MULTILINE)
SECTION = re.compile(r"^### `(?P<title>[^`]+)`\n+```text\n(?P<body>.*?)\n```", re.MULTILINE | re.DOTALL)
MAX_DEPTH = 3


@contextlib.contextmanager
def _stable_terminal() -> Iterator[None]:
    """Fixed help width and no ANSI colour (Python 3.14+ argparse can colour help)."""
    keys = ("COLUMNS", "NO_COLOR", "PYTHON_COLORS", "FORCE_COLOR")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(COLUMNS=WIDTH, NO_COLOR="1", PYTHON_COLORS="0")
    os.environ.pop("FORCE_COLOR", None)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def help_text(path: list[str]) -> tuple[int, str]:
    """Exit status and stdout of ``agent-movement <path> --help``, run in-process."""
    out, err = io.StringIO(), io.StringIO()
    with _stable_terminal(), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([*path, "--help"])
    return code, out.getvalue().rstrip() + "\n"


def collect() -> tuple[dict[str, str], list[str]]:
    """All renderable help sections keyed by title, plus the titles that could not render."""
    sections: dict[str, str] = {}
    unavailable: list[str] = []

    def visit(path: list[str], extra_children: tuple[str, ...] = ()) -> None:
        title = " ".join([cli.PROG, *path])
        code, text = help_text(path)
        if code != 0:
            unavailable.append(title)
            return
        sections[title] = text
        if len(path) >= MAX_DEPTH:
            return
        children = [c for m in SUBCOMMANDS.finditer(text) for c in m.group(1).split(",")] if path else []
        for child in [*children, *extra_children]:
            visit([*path, child])

    visit([])
    for command in cli.COMMANDS.values():
        visit([command.name], command.local_subcommands)
    for name in cli.BUILTINS:
        visit([name])
    return sections, unavailable


def command_table() -> str:
    rows = ["| Command | Forwards to | Optional extra |", "|---|---|---|"]
    for c in cli.COMMANDS.values():
        needs = [f"`{c.extra}`"] if c.extra else []
        needs += [f"`{extra}` (only for `{option} {value}`)" for option, value, extra in c.extra_if]
        extra = ", ".join(needs) or "none"
        rows.append(f"| `{cli.PROG} {c.name}` | `python -m {c.module}` | {extra} |")
        rows += [f"| `{cli.PROG} {c.name} {s}` | `python -m {c.module}` (legacy {s}, no subcommand) | {extra} |"
                 for s in c.local_subcommands]
    rows.append(f"| `{cli.PROG} version` | built into the CLI | none |")
    return "\n".join(rows)


def render(sections: dict[str, str]) -> str:
    parts = [BEGIN, "", command_table(), ""]
    for title, text in sections.items():
        parts += [f"### `{title}`", "", "```text", text.rstrip(), "```", ""]
    parts.append(END)
    return "\n".join(parts)


def _block(doc: str) -> str:
    start, end = doc.find(BEGIN), doc.find(END)
    if start < 0 or end < start:
        raise SystemExit(f"{DOC}: generated-block markers not found")
    return doc[start:end + len(END)]


def _norm(text: str) -> str:
    # Drop all whitespace: argparse wraps at a width-dependent column and also after hyphens.
    return "".join(text.split())


def check(doc_text: str | None = None) -> tuple[list[str], list[str]]:
    """Differences between docs/cli.md and the live help, and the titles skipped here."""
    block = _block(DOC.read_text(encoding="utf-8") if doc_text is None else doc_text)
    documented = {m["title"]: m["body"] for m in SECTION.finditer(block)}
    live, unavailable = collect()
    skipped = sorted(t for t in documented if t not in live and any(
        t == u or t.startswith(u + " ") for u in unavailable))
    problems = []
    if _norm(command_table()) not in _norm(block):
        problems.append("command table differs from agent_movement.cli.COMMANDS")
    for title, text in live.items():
        if title not in documented:
            problems.append(f"`{title} --help` is not documented")
        elif _norm(documented[title]) != _norm(text):
            problems.append(f"`{title} --help` differs from the documented text")
    for title in documented:
        if title not in live and title not in skipped:
            problems.append(f"`{title}` is documented but no longer exists")
    return problems, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="verify docs/cli.md instead of rewriting it")
    options = parser.parse_args(argv)
    if options.check:
        problems, skipped = check()
        for title in skipped:
            print(f"skipped (help needs a missing optional extra): {title}")
        for problem in problems:
            print(f"docs/cli.md: {problem}", file=sys.stderr)
        if problems:
            print("docs/cli.md is stale; regenerate with `make cli-docs` (needs every optional extra)",
                  file=sys.stderr)
            return 1
        print("docs/cli.md: ok (matches live --help output)")
        return 0
    sections, unavailable = collect()
    if unavailable:
        print("cannot regenerate: --help failed for " + ", ".join(unavailable)
              + "; install every optional extra first", file=sys.stderr)
        return 2
    doc = DOC.read_text(encoding="utf-8")
    DOC.write_text(doc.replace(_block(doc), render(sections)), encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)} ({len(sections)} help sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
