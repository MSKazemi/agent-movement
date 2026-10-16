"""tools/check_test_registry.py on a synthetic repository built in tmp_path."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

import check_test_registry as ctr

TEST_FILE = '''\
import unittest

raise RuntimeError("the registry check must never import a test file")


class Mixin:  # not collected by pytest: neither Test* nor a TestCase
    def test_mixed(self):
        pass


class Base(unittest.TestCase):
    def test_inherited(self):
        pass


class Cases(Mixin, Base):
    def test_one(self):
        pass

    def helper(self):
        pass


def test_function():
    pass
'''
ALL_NODES = ["tests/test_x.py::Cases::test_one", "tests/test_x.py::Base::test_inherited",
             "tests/test_x.py::test_function", "tests/test_x.py::Cases::test_mixed"]


def row(id_, status="implemented", tests=(), **over):
    return {"id": id_, "title": f"case {id_}", "source_docs": "docs/guide.md", "threat_asi": "ASI07",
            "status": status, "implementing_tests": ";".join(tests), "aliases": "", "notes": "", **over}


def make_repo(root: Path, rows, guide="Cases T01 and COM-T001 are registered.\n", other="Decision T19.\n"):
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_x.py").write_text(TEST_FILE, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "guide.md").write_text(guide, encoding="utf-8")
    (root / "docs" / "glossary.md").write_text(other, encoding="utf-8")
    (root / "data").mkdir()
    with (root / "data" / "test-registry.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ctr.COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return root


def run(root: Path, capsys, *extra: str) -> tuple[int, str]:
    code = ctr.main(["--root", str(root), *extra])
    out = capsys.readouterr()
    return code, out.out + out.err


def valid_rows():
    return [row("T01", tests=[ALL_NODES[0], ALL_NODES[1], ALL_NODES[3]]),
            row("COM-T001", "partial", [ALL_NODES[2]], aliases="E07"), row("SEC-01", "planned")]


def test_valid_registry_passes_without_importing_tests(tmp_path, capsys):
    code, out = run(make_repo(tmp_path, valid_rows()), capsys)
    assert code == 0, out
    assert "3 rows: 1 implemented, 1 partial, 1 planned" in out


def test_inherited_method_resolves_through_subclass(tmp_path, capsys):
    # Cases runs Base.test_inherited, so registering the subclass node alone covers it.
    rows = valid_rows()
    rows[0]["implementing_tests"] = rows[0]["implementing_tests"].replace(
        "tests/test_x.py::Base::test_inherited", "tests/test_x.py::Cases::test_inherited")
    code, out = run(make_repo(tmp_path, rows), capsys)
    assert code == 0, out


def test_mixin_test_must_be_registered_through_a_collected_class(tmp_path, capsys):
    rows = valid_rows()
    rows[0]["implementing_tests"] = ";".join(ALL_NODES[:2])
    code, out = run(make_repo(tmp_path, rows), capsys, "--strict")
    assert code == 1
    assert ("test tests/test_x.py::Mixin::test_mixed is not registered; "
            "add tests/test_x.py::Cases::test_mixed") in out


@pytest.mark.parametrize("node, message", [
    ("tests/test_x.py::Cases::test_missing", "no such test"),
    ("tests/test_x.py::Mixin::test_mixed", "no such test"),  # pytest does not collect a mixin
    ("tests/test_x.py::Cases::helper", "is not a tests/<file>.py::[Class::]test_name node id"),
    ("tests/test_gone.py::test_one", "test file tests/test_gone.py does not exist"),
    ("test_x.py::test_function", "node id"),
])
def test_unknown_test_node_fails(tmp_path, capsys, node, message):
    rows = valid_rows()
    rows[0]["implementing_tests"] += ";" + node
    code, out = run(make_repo(tmp_path, rows), capsys)
    assert code == 1
    assert message in out


def test_unregistered_test_in_registered_file_fails_only_with_strict(tmp_path, capsys):
    rows = valid_rows()
    rows[1] = row("COM-T001", "planned", aliases="E07")
    repo = make_repo(tmp_path, rows)
    code, out = run(repo, capsys)
    assert code == 0, out
    assert "warning: " in out and "test tests/test_x.py::test_function is not registered" in out
    code, out = run(repo, capsys, "--strict")
    assert code == 1
    assert "test tests/test_x.py::test_function is not registered" in out


@pytest.mark.parametrize("change, message", [
    (lambda rows: rows.append(row("T01", "planned")), "duplicate id"),
    (lambda rows: rows[2].update(status="done"), "unknown status 'done'"),
    (lambda rows: rows[2].update(id="X-1"), "malformed id"),
    (lambda rows: rows[2].update(implementing_tests=ALL_NODES[0]), "a planned row names no implementing test"),
    (lambda rows: rows.append(row("REG-001")), "needs at least one implementing test"),
    (lambda rows: rows[1].update(aliases="T01"), "alias T01 is also a registry id"),
    (lambda rows: rows[2].update(threat_asi="ASI11"), "is not ASI01..ASI10"),
    (lambda rows: rows[2].update(source_docs="docs/missing.md"), "source doc docs/missing.md does not exist"),
])
def test_invalid_rows_fail(tmp_path, capsys, change, message):
    rows = valid_rows()
    change(rows)
    code, out = run(make_repo(tmp_path, rows), capsys)
    assert code == 1
    assert message in out


def test_doc_reference_to_unknown_id_fails(tmp_path, capsys):
    code, out = run(make_repo(tmp_path, valid_rows(), guide="See T02, E07 and COM-T002.\n"), capsys)
    assert code == 1
    assert "docs/guide.md:1: T02 is not a registry id or alias" in out
    assert "docs/guide.md:1: COM-T002 is not a registry id or alias" in out
    assert "E07 is not" not in out  # an alias is a known ID


def test_bare_ids_are_checked_only_in_source_docs(tmp_path, capsys):
    # docs/glossary.md is no row's source: its "T19" is a different label and is ignored,
    # but a prefixed ID is unambiguous and is checked everywhere.
    assert run(make_repo(tmp_path, valid_rows()), capsys)[0] == 0
    code, out = run(make_repo(tmp_path / "b", valid_rows(), other="Decision T19 and REG-404.\n"), capsys)
    assert code == 1
    assert "docs/glossary.md:1: REG-404" in out
    assert "T19" not in out


def test_wrong_header_fails(tmp_path, capsys):
    root = make_repo(tmp_path, valid_rows())
    path = root / "data" / "test-registry.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("aliases,", ""), encoding="utf-8")
    code, out = run(root, capsys)
    assert code == 1
    assert "header must be" in out
