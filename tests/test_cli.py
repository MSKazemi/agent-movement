"""Unified `agent-movement` CLI: dispatch, argument forwarding, extras hints and docs/cli.md.

Dispatch tests replace the target `main()` with a recorder, so they need no optional
extra and run no experiment. End-to-end tests run the real CLI as a child process
(`python -m agent_movement ...`) on synthetic data; those needing an extra skip without it.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import cli_reference
from agent_movement import cli

REPO = Path(__file__).resolve().parent.parent
RECEIPTS = REPO / "tests" / "fixtures" / "movement-receipts"


def has_extra(extra: str) -> bool:
    return not cli.missing_modules(extra)


def child_env() -> dict[str, str]:
    """src/ on PYTHONPATH, so children find the package without an install (corpus CI)."""
    src = str(REPO / "src")
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in (src, os.environ.get("PYTHONPATH")) if p)}


def run_cli(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "agent_movement", *args], capture_output=True, text=True,
                          cwd=REPO, env=child_env(), timeout=timeout)


class Recorder:
    """Stands in for a module's main(): records what it receives and returns a fixed code."""

    def __init__(self, result=0):
        self.calls: list[tuple[list[str], str]] = []
        self.result = result

    def __call__(self, argv):
        self.calls.append((list(argv), sys.argv[0]))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def recorded(monkeypatch):
    """Route every dispatch to one Recorder, as if every optional extra were installed."""
    recorder, targets = Recorder(), []
    monkeypatch.setattr(cli, "missing_modules", lambda extra: [])

    def load(target):
        targets.append(target)
        return recorder
    monkeypatch.setattr(cli, "_load", load)
    recorder.targets = targets
    return recorder


# --- packaging and top level -------------------------------------------------------------

def test_cli_console_script_is_declared_in_pyproject():
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["scripts"]["agent-movement"] == "agent_movement.cli:main"


def test_cli_top_level_help_lists_every_subcommand(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    listed = {line.split()[0] for line in out.splitlines() if line.startswith("    ") and line.split()}
    for name in [*cli.COMMANDS, *cli.BUILTINS]:  # layout differs across Python versions
        assert name in listed, name
    for issue_command in ("demo", "a2a-demo", "peer-demo", "relocate", "bench", "receipts", "version"):
        assert issue_command in [*cli.COMMANDS, *cli.BUILTINS]


@pytest.mark.parametrize("argv", [[], ["no-such-command"], ["--no-such-flag"]])
def test_cli_usage_errors_exit_2(argv, capsys):
    assert cli.main(argv) == 2
    assert "usage: agent-movement" in capsys.readouterr().err


def test_cli_version_reports_package_python_and_extras(capsys):
    assert cli.main(["version"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{cli.DISTRIBUTION} ")
    for extra in cli.EXTRAS:
        assert f"{extra}=yes" in out or f"{extra}=no" in out
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("agent-movement ")


# --- dispatch and forwarding -------------------------------------------------------------

FUTURE_ARGS = ["verify", "bundle", "--trust", "anchors.json", "--now=2026-10-16T00:00:00Z",
               "--flag-added-later", "x", "--", "-literal"]


@pytest.mark.parametrize("name", sorted(cli.COMMANDS))
def test_cli_forwards_arguments_unchanged(recorded, name):
    """Flags the CLI has never heard of reach the module untouched (receipts #21, bench #22/#31)."""
    args = FUTURE_ARGS if name != "bench" else ["run", *FUTURE_ARGS[1:]]
    assert cli.main([name, *args]) == 0
    assert recorded.calls == [(args, f"agent-movement {name}")]
    assert recorded.targets == [cli.COMMANDS[name].target]


def test_cli_bench_routes_smoke_help_and_suite(recorded):
    cli.main(["bench", "smoke", "--output", "x.jsonl"])
    cli.main(["bench", "--help"])
    cli.main(["bench"])
    cli.main(["bench", "run", "--subset", "smoke", "--out", "-"])
    cli.main(["bench", "--output", "y.jsonl"])  # legacy form, same as the module
    assert recorded.targets == ["agent_movement.mobilitybench:main", "agent_movement.mobilitybench_v01:main",
                                "agent_movement.mobilitybench_v01:main", "agent_movement.mobilitybench:main",
                                "agent_movement.mobilitybench:main"]
    assert recorded.calls[0] == (["--output", "x.jsonl"], "agent-movement bench smoke")
    assert recorded.calls[3][0] == ["run", "--subset", "smoke", "--out", "-"]


def test_cli_maps_target_exit_statuses(monkeypatch, capsys):
    monkeypatch.setattr(cli, "missing_modules", lambda extra: [])
    for result, expected in [(None, 0), (0, 0), (1, 1), (3, 3), (SystemExit(None), 0), (SystemExit(2), 2),
                             (SystemExit("demo check failed"), 1)]:
        monkeypatch.setattr(cli, "_load", lambda target, r=result: Recorder(r))
        assert cli.main(["demo"]) == expected, result
    assert "demo check failed" in capsys.readouterr().err


def test_cli_restores_sys_argv_after_dispatch(recorded):
    before = list(sys.argv)
    cli.main(["receipts", "verify", "x"])
    assert sys.argv == before


def test_cli_calls_zero_argument_main_with_argv_in_sys_argv(monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "_load", lambda target: lambda: seen.append(list(sys.argv)))
    assert cli.main(["demo", "--opt", "1"]) == 0
    assert seen == [["agent-movement demo", "--opt", "1"]]


# --- optional extras ---------------------------------------------------------------------

@pytest.mark.parametrize("argv, extra", [
    (["a2a-demo"], "a2a"),
    (["relocate", "--json", "out.json"], "relocation"),
    (["receipts", "verify", "bundle"], "signing"),
    (["peer-demo", "--alg", "Ed25519"], "ed25519"),
    (["peer-demo", "--alg=Ed25519"], "ed25519"),
    (["peer-demo", "--delivery", "hpke"], "hpke"),
    (["peer-demo", "--alg", "Ed25519", "--delivery=hpke"], "hpke"),
])
def test_cli_missing_extra_prints_install_hint_and_exits_2(monkeypatch, capsys, argv, extra):
    monkeypatch.setattr(cli, "missing_modules", lambda e: ["fake_module"] if e == extra else [])
    monkeypatch.setattr(cli, "_load", lambda target: pytest.fail("must not run without its extra"))
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert f"needs the optional '{extra}' extra" in err
    assert f"python -m pip install -e '.[{extra}]'" in err


@pytest.mark.parametrize("argv", [["peer-demo"], ["peer-demo", "--alg", "HS256"],
                                  ["peer-demo", "--delivery", "plaintext"], ["a2a-demo", "--help"],
                                  ["receipts", "verify", "--help"]])
def test_cli_extra_not_required_for_core_mode_or_help(recorded, monkeypatch, argv):
    monkeypatch.setattr(cli, "missing_modules", lambda extra: ["fake_module"])
    assert cli.main(argv) == 0
    assert recorded.calls


def test_cli_import_error_becomes_hint_only_when_the_extra_is_missing(monkeypatch, capsys):
    def broken(target):
        raise ImportError("langgraph")
    monkeypatch.setattr(cli, "_load", broken)
    monkeypatch.setattr(cli, "missing_modules", lambda extra: ["langgraph"])
    assert cli.main(["relocate", "--help"]) == 2  # help of a module that needs the extra to import
    assert "'relocation' extra" in capsys.readouterr().err
    monkeypatch.setattr(cli, "missing_modules", lambda extra: [])
    with pytest.raises(ImportError):  # a genuine bug is never disguised as a missing extra
        cli.main(["relocate"])


@pytest.mark.skipif(has_extra("relocation"), reason="needs an environment WITHOUT the relocation extra")
def test_cli_relocate_without_extra_exits_2_end_to_end():
    done = run_cli("relocate")
    assert done.returncode == 2, done.stderr
    assert "pip install -e '.[relocation]'" in done.stderr


# --- --help everywhere -------------------------------------------------------------------

HELP_PATHS = [[name] for name in [*cli.COMMANDS, *cli.BUILTINS]] + [
    ["bench", sub] for sub in ("verify", "run", "schedule", "report", "smoke")] + [
    ["receipts", sub] for sub in ("verify", "timeline", "make-fixtures")]


@pytest.mark.parametrize("path", HELP_PATHS, ids=" ".join)
def test_cli_every_subcommand_has_help(path, capsys):
    if path[0] == "relocate" and not has_extra("relocation"):
        pytest.skip("relocate --help imports LangGraph (optional relocation extra)")
    assert cli.main([*path, "--help"]) == 0
    assert capsys.readouterr().out.startswith("usage: ")


def test_cli_module_entry_points_still_work():
    for module in ("agent_movement", "agent_movement.cli", "agent_movement.demo", "agent_movement.a2a_demo",
                   "agent_movement.peer_demo", "agent_movement.mobilitybench", "agent_movement.receipts"):
        done = subprocess.run([sys.executable, "-m", module, "--help"], capture_output=True, text=True,
                              cwd=REPO, env=child_env(), timeout=60)
        assert done.returncode == 0, (module, done.stderr)
        assert done.stdout.startswith("usage: "), module


# --- happy paths, end to end -------------------------------------------------------------

def test_cli_version_and_core_demos_exit_0():
    for args in (["version"], ["demo"], ["peer-demo"]):
        done = run_cli(*args)
        assert done.returncode == 0, (args, done.stderr)


def test_cli_bench_happy_paths_exit_0(tmp_path):
    results, report, smoke = tmp_path / "results.jsonl", tmp_path / "report.md", tmp_path / "smoke.jsonl"
    for args in (["bench", "verify", "--suite", "v0.1"],
                 ["bench", "run", "--suite", "v0.1", "--subset", "smoke", "--out", str(results)],
                 ["bench", "report", "--in", str(results), "--out", str(report)],
                 ["bench", "schedule", "--subset", "smoke"],
                 ["bench", "smoke", "--output", str(smoke)]):
        done = run_cli(*args)
        assert done.returncode == 0, (args, done.stderr)
    assert results.stat().st_size and report.stat().st_size and smoke.stat().st_size


@pytest.mark.skipif(not has_extra("signing"), reason="optional signing extra not installed")
def test_cli_receipts_verify_happy_path_exits_0():
    done = run_cli("receipts", "verify", str(RECEIPTS / "01-valid-delegation"),
                   "--trust", str(RECEIPTS / "trust.json"), "--now", "2026-10-16T00:00:00Z")
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.mark.skipif(not has_extra("ed25519"), reason="optional ed25519 extra not installed")
def test_cli_peer_demo_ed25519_exits_0():
    done = run_cli("peer-demo", "--alg", "Ed25519")
    assert done.returncode == 0, done.stderr


@pytest.mark.skipif(not has_extra("a2a"), reason="optional a2a extra not installed")
def test_cli_a2a_demo_exits_0():
    done = run_cli("a2a-demo")
    assert done.returncode == 0, done.stderr


# --- docs/cli.md -------------------------------------------------------------------------

def test_cli_reference_doc_matches_live_help():
    problems, skipped = cli_reference.check()
    assert problems == [], "\n".join(problems) + "\nregenerate with: make cli-docs"
    if importlib.util.find_spec("langgraph") is None:
        # Without the extra the whole `relocate` subtree (incl. `relocate reconcile ...`) is skipped.
        assert "agent-movement relocate" in skipped
        assert all(t == "agent-movement relocate" or t.startswith("agent-movement relocate ") for t in skipped)


def test_cli_reference_check_detects_drift():
    doc = cli_reference.DOC.read_text(encoding="utf-8")
    renamed = doc.replace("--no-timing", "--no-timings", 1)
    assert any("bench run --help` differs" in p for p in cli_reference.check(renamed)[0])
    dropped = doc.replace("### `agent-movement bench report`", "### `agent-movement bench gone`", 1)
    problems = cli_reference.check(dropped)[0]
    assert any("bench report --help` is not documented" in p for p in problems)
    assert any("bench gone` is documented but no longer exists" in p for p in problems)


def test_cli_reference_ignores_line_wrapping():
    doc = cli_reference.DOC.read_text(encoding="utf-8")
    rewrapped = doc.replace("show this help message and exit", "show this help\n      message and exit")
    assert cli_reference.check(rewrapped)[0] == []
