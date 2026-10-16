#!/usr/bin/env python3
"""Validate data/test-registry.csv, the single registry of documented test cases.

Stdlib only. Test files are parsed with ``ast`` and never imported, so the check needs
none of the optional extras. It fails (exit 1) when:

- the header is not exactly the registry columns;
- an ID is malformed or duplicated, or an alias is malformed or is itself a registry ID;
- a status is not ``implemented``, ``partial`` or ``planned``;
- an ``implemented`` or ``partial`` row names no test, or a ``planned`` row names one;
- an implementing test is not a ``tests/<file>.py::[Class::]test_name`` node ID that pytest
  would collect (a test class also runs the methods it inherits from base or mixin classes
  of the same file, so ``Subclass::test_inherited`` is valid; a mixin itself is not collected);
- with ``--strict`` only: a test defined in a registered test file is run by no node that a
  row names (an inherited test is covered by any one of the classes that run it). Without
  ``--strict`` these are printed as warnings;
- a ``source_docs`` path does not exist, or a ``threat_asi`` value is not ASI01..ASI10;
- a document refers to a registry-style ID that is neither a registry ID nor an alias.

Usage: python tools/check_test_registry.py [--root DIR] [--registry CSV] [--stats]
"""
from __future__ import annotations

import argparse
import ast
import csv
import re
import sys
from collections import Counter
from pathlib import Path

COLUMNS = ["id", "title", "source_docs", "threat_asi", "status", "implementing_tests", "aliases", "notes"]
STATUSES = ("implemented", "partial", "planned")
ID_RE = re.compile(r"^(?:T\d{2}|E\d{2}|COM-T\d{3}|SEC-\d{2}|REG-\d{3})$")
ASI_RE = re.compile(r"^ASI(?:0[1-9]|10)$")
NODE_RE = re.compile(r"^(tests/[\w/.-]+\.py)::(?:([A-Za-z_]\w*)::)?(test\w*)$")
# Prefixed IDs are unambiguous, so every scanned document is checked for them.
PREFIXED_REF = re.compile(r"\b(?:COM-T\d{3}|SEC-\d{2}|REG-\d{3})\b")
# Bare T01/E01 also name other things (e.g. glossary decisions T10-T13), so they are
# checked only in the documents a registry row cites as its source.
BARE_REF = re.compile(r"\b[TE]\d{2}\b")
EXCLUDED_DIRS = ("docs/news-corpus/", "docs/paper-corpus/")


def split(cell: str) -> list[str]:
    return [part.strip() for part in (cell or "").split(";") if part.strip()]


def collect_nodes(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """(nodes, definitions) of one test file, from its ``ast`` only.

    ``nodes`` maps every collectable node suffix (``Class::test_x`` or module-level ``test_x``)
    to the definition it runs, ``Owner::test_x``: a test class runs the methods it inherits
    from base or mixin classes of the same file, resolved in method resolution order.
    ``definitions`` maps each test definition that some node runs to one such node, so
    that an unregistered definition can be reported with a node ID that would register it.
    A class is collectable when its name starts with ``Test`` or it derives from a
    ``*TestCase`` class (as pytest collects unittest classes); a mixin is not.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def bases(cls: ast.ClassDef) -> list[str]:
        return [b.id for b in cls.bases if isinstance(b, ast.Name) and b.id in classes]

    def mro(name: str, seen: frozenset[str] = frozenset()) -> list[str]:
        """C3 linearization restricted to this file's classes (external bases are ignored)."""
        if name in seen:
            return [name]
        seqs = [mro(b, seen | {name}) for b in bases(classes[name])] + [bases(classes[name])]
        out = [name]
        while any(seqs):
            seqs = [s for s in seqs if s]
            head = next((s[0] for s in seqs if not any(s[0] in t[1:] for t in seqs)), seqs[0][0])
            out.append(head)
            seqs = [s[1:] if s[0] == head else s for s in seqs]
        return out

    def is_testcase(name: str) -> bool:
        return any(isinstance(b, ast.Attribute) and b.attr.endswith("TestCase")
                   or isinstance(b, ast.Name) and b.id.endswith("TestCase")
                   for c in mro(name) for b in classes[c].bases)

    def own(name: str) -> list[str]:
        return [m.name for m in classes[name].body if isinstance(m, funcs) and m.name.startswith("test")]

    nodes = {n.name: n.name for n in tree.body if isinstance(n, funcs) and n.name.startswith("test")}
    for name in classes:
        if not (name.startswith("Test") or is_testcase(name)):
            continue
        for owner in reversed(mro(name)):  # nearest definition wins
            for method in own(owner):
                nodes[f"{name}::{method}"] = f"{owner}::{method}"
    definitions = {definition: node for node, definition in nodes.items() if node == definition}
    for node, definition in sorted(nodes.items()):  # a mixin's test: suggest a class that runs it
        definitions.setdefault(definition, node)
    return nodes, definitions


def scanned_documents(root: Path, registry: Path) -> list[Path]:
    paths = [root / "README.md", *sorted((root / "docs").rglob("*.md")), *sorted((root / "data").glob("*.csv"))]
    out = []
    for path in paths:
        rel = path.relative_to(root).as_posix()
        if path.is_file() and path.resolve() != registry.resolve() and not rel.startswith(EXCLUDED_DIRS):
            out.append(path)
    return out


def check(root: Path, registry: Path) -> tuple[list[str], list[str], dict]:
    errors: list[str] = []
    if not registry.is_file():
        return [f"{registry}: registry file not found"], {}
    with registry.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            return [f"{registry.name}: header must be {','.join(COLUMNS)}, got {reader.fieldnames}"], {}
        rows = list(reader)

    ids = Counter(row["id"] for row in rows)
    aliases: set[str] = set()
    sources: set[str] = set()
    covered: dict[str, set[str]] = {}  # test file -> definitions run by nodes that rows name
    parsed: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    nodes = 0

    for line, row in enumerate(rows, start=2):
        rid = row["id"]
        where = f"{registry.name}:{line} ({rid or 'no id'})"
        if not ID_RE.match(rid):
            errors.append(f"{where}: malformed id")
        if ids[rid] > 1:
            errors.append(f"{where}: duplicate id")
        if not row["title"].strip():
            errors.append(f"{where}: empty title")
        status = row["status"]
        if status not in STATUSES:
            errors.append(f"{where}: unknown status {status!r} (use {', '.join(STATUSES)})")
        for alias in split(row["aliases"]):
            if not ID_RE.match(alias):
                errors.append(f"{where}: malformed alias {alias!r}")
            elif alias in ids:
                errors.append(f"{where}: alias {alias} is also a registry id; keep one canonical row")
            aliases.add(alias)
        for asi in split(row["threat_asi"]):
            if not ASI_RE.match(asi):
                errors.append(f"{where}: threat_asi {asi!r} is not ASI01..ASI10")
        docs = split(row["source_docs"])
        if not docs:
            errors.append(f"{where}: no source_docs")
        for doc in docs:
            if not (root / doc).is_file():
                errors.append(f"{where}: source doc {doc} does not exist")
            sources.add(doc)

        tests = split(row["implementing_tests"])
        if status in ("implemented", "partial") and not tests:
            errors.append(f"{where}: status {status} needs at least one implementing test")
        if status == "planned" and tests:
            errors.append(f"{where}: a planned row names no implementing test (use partial)")
        for node in tests:
            match = NODE_RE.match(node)
            if not match:
                errors.append(f"{where}: {node!r} is not a tests/<file>.py::[Class::]test_name node id")
                continue
            file, cls, func = match.groups()
            if file not in parsed:
                path = root / file
                if not path.is_file():
                    errors.append(f"{where}: {node}: test file {file} does not exist")
                    continue
                parsed[file] = collect_nodes(path)
            suffix = f"{cls}::{func}" if cls else func
            if suffix not in parsed[file][0]:
                errors.append(f"{where}: {node}: no such test")
                continue
            covered.setdefault(file, set()).add(parsed[file][0][suffix])
            nodes += 1

    # Completeness is reported, not enforced by default: tests are added in parallel PRs, and a
    # new test should not turn CI red before its registry row exists. Use --strict to enforce it.
    unregistered: list[str] = []
    for file in sorted(covered):
        for definition, node in sorted(parsed[file][1].items()):
            if definition not in covered[file]:
                unregistered.append(f"{registry.name}: test {file}::{definition} is not registered; add "
                              f"{file}::{node} to a row (or a new REG-nnn row), since {file} has registered tests")

    known = set(ids) | aliases
    for path in scanned_documents(root, registry):
        rel = path.relative_to(root).as_posix()
        patterns = (PREFIXED_REF, BARE_REF) if rel in sources else (PREFIXED_REF,)
        for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in patterns:
                for ref in pattern.findall(text):
                    if ref not in known:
                        errors.append(f"{rel}:{number}: {ref} is not a registry id or alias")

    stats = {"rows": len(rows), "status": Counter(row["status"] for row in rows), "nodes": nodes,
             "aliases": len(aliases), "files": len(covered),
             "by_file": Counter(n.split("::")[0] for row in rows for n in split(row["implementing_tests"])),
             "rows_by_file": Counter(f for row in rows
                                     for f in {n.split("::")[0] for n in split(row["implementing_tests"])})}
    return errors, unregistered, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository root (default: the parent of tools/)")
    parser.add_argument("--registry", type=Path, help="registry CSV (default: <root>/data/test-registry.csv)")
    parser.add_argument("--stats", action="store_true", help="also print rows per status and per test file")
    parser.add_argument("--strict", action="store_true",
                        help="also fail when a test in a registered test file has no registry row")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    registry = args.registry or root / "data" / "test-registry.csv"
    errors, unregistered, stats = check(root, registry)
    if args.strict:
        errors += unregistered
    else:
        for warning in unregistered:
            print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"check-tests-registry: {len(errors)} error(s)", file=sys.stderr)
        return 1
    status = ", ".join(f"{stats['status'][s]} {s}" for s in STATUSES)
    print(f"check-tests-registry: ok ({stats['rows']} rows: {status}; {stats['aliases']} aliases; "
          f"{stats['nodes']} test references resolved in {stats['files']} test files; "
          f"{len(unregistered)} unregistered test(s) in those files{'' if unregistered else ', all registered'})")
    if args.stats:
        for file in sorted(stats["rows_by_file"]):
            print(f"  {file}: {stats['rows_by_file'][file]} rows, {stats['by_file'][file]} test references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
