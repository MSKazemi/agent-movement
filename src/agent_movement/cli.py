"""Unified ``agent-movement`` command line: one entry point for every local experiment.

Each subcommand is a thin dispatcher. It forwards its arguments UNCHANGED to the
existing ``main()`` of one module, so that module's own argparse parser stays the
single definition of the subcommand's flags, ``--help`` text and exit codes, and
every ``python -m agent_movement.<module>`` entry point keeps working on its own.
This module declares no experiment flags of its own.

The one thing it adds is a uniform optional-extra check: a subcommand whose
optional extra is not installed prints an install hint and exits 2 instead of
failing with an ImportError or a module-specific message. ``--help`` skips that
check wherever the module can render its help without the extra. The only flag
the CLI reads (never parses or validates) is ``peer-demo --alg``, because only
``--alg Ed25519`` needs the ``ed25519`` extra; if that flag is renamed the check
simply stops firing and the module's own message is shown.

Standard library only.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import platform
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import metadata
from typing import Any, Callable, Iterator, Sequence

PROG = "agent-movement"
DISTRIBUTION = "agent-movement-lab"
MISSING_EXTRA_EXIT = 2

# Optional extra -> the importable modules it provides (see [project.optional-dependencies]).
EXTRAS: dict[str, tuple[str, ...]] = {
    "a2a": ("a2a", "uvicorn"),
    "ed25519": ("cryptography",),
    "relocation": ("langgraph", "langgraph.checkpoint.sqlite"),
    "signing": ("cryptography",),
}


@dataclass(frozen=True)
class Command:
    """One subcommand: where its arguments go and which optional extra it needs."""

    name: str
    target: str  # "package.module:function"; the function takes the forwarded argv
    summary: str
    module: str  # the equivalent `python -m` entry point, for the reference docs
    extra: str | None = None
    # (option, value): the extra is needed only when the forwarded argv sets option=value.
    extra_when: tuple[str, str] | None = None
    # Subcommands this CLI adds in front of the module's own parser (bench smoke).
    local_subcommands: tuple[str, ...] = ()


COMMANDS: dict[str, Command] = {c.name: c for c in (
    Command("demo", "agent_movement.demo:main", "core loopback handoff, replay, denial and stale-epoch fencing",
            "agent_movement.demo"),
    Command("a2a-demo", "agent_movement.a2a_demo:main", "A2A v1 delegation demo on the official a2a-sdk",
            "agent_movement.a2a_demo", extra="a2a"),
    Command("peer-demo", "agent_movement.peer_demo:main",
            "authenticated peer handoff (HS256; --alg Ed25519 needs the 'ed25519' extra)",
            "agent_movement.peer_demo", extra="ed25519", extra_when=("--alg", "Ed25519")),
    Command("relocate", "agent_movement.relocation_demo:main",
            "same-runtime LangGraph checkpoint relocation and fault matrix",
            "agent_movement.relocation_demo", extra="relocation"),
    Command("bench", "agent_movement.mobilitybench:main",
            "MobilityBench v0.1: verify | run | schedule | report; 'bench smoke' = legacy 20-case smoke",
            "agent_movement.mobilitybench", local_subcommands=("smoke",)),
    Command("receipts", "agent_movement.receipts:main",
            "offline verifier for signed movement receipts: verify | timeline | make-fixtures",
            "agent_movement.receipts", extra="signing"),
)}

BUILTINS = {"version": "print the package version, the Python version and which optional extras are installed"}


def missing_modules(extra: str) -> list[str]:
    """Modules of ``extra`` that cannot be imported in this environment."""
    missing = []
    for name in EXTRAS[extra]:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):  # a missing parent package raises for dotted names
            found = False
        if not found:
            missing.append(name)
    return missing


def install_hint(command: str, extra: str, missing: Sequence[str]) -> str:
    return (f"{PROG} {command}: needs the optional '{extra}' extra (not importable: {', '.join(missing)}).\n"
            f"Install it from the repository root with: python -m pip install -e '.[{extra}]'")


def _wants_help(args: Sequence[str]) -> bool:
    head = list(args[:args.index("--")]) if "--" in args else list(args)
    return "-h" in head or "--help" in head


def _option_value(args: Sequence[str], option: str) -> str | None:
    """The last value given for ``option`` (``--opt value`` or ``--opt=value``), if any."""
    value = None
    for i, arg in enumerate(args):
        if arg == "--":
            break
        if arg == option and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith(option + "="):
            value = arg.partition("=")[2]
    return value


def needs_extra(command: Command, args: Sequence[str]) -> bool:
    """Whether running ``command`` with ``args`` needs its optional extra."""
    if command.extra is None or _wants_help(args):
        return False
    if command.extra_when is None:
        return True
    option, value = command.extra_when
    return _option_value(args, option) == value


def _exit_code(code: Any) -> int:
    """Map a SystemExit code to a process exit status the way the interpreter does."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _resolve(command: Command, args: list[str]) -> tuple[str, str, list[str]]:
    """The target, its prog name and the argv it receives. Only ``bench smoke`` is rewritten."""
    prog = f"{PROG} {command.name}"
    if command.name == "bench":
        if args[:1] == ["smoke"]:
            return "agent_movement.mobilitybench:main", f"{prog} smoke", args[1:]
        if not args or args[0] in ("-h", "--help"):
            # Show the v0.1 suite's subcommands; the legacy smoke parser would list only --output.
            return "agent_movement.mobilitybench_v01:main", prog, args
    return command.target, prog, args


def _load(target: str) -> Callable[..., Any]:
    module_name, _, attr = target.partition(":")
    return getattr(importlib.import_module(module_name), attr)


@contextmanager
def _invoked_as(prog: str, args: list[str]) -> Iterator[None]:
    """While the call lasts, ``sys.argv`` is ``[prog, *args]``.

    Parsers without an explicit prog take their usage name from ``sys.argv[0]``, and a
    ``main()`` without an argv parameter reads ``sys.argv[1:]``. Parsers that hard-code
    ``prog="python -m agent_movement.<module>"`` keep showing that equivalent form.
    """
    saved = sys.argv
    sys.argv = [prog, *args]
    try:
        yield
    finally:
        sys.argv = saved


def _call(func: Callable[..., Any], args: list[str]) -> int:
    """Call ``func`` with ``args`` (or with none, for a ``main()`` that takes no argv)."""
    try:
        result = func(args) if inspect.signature(func).parameters else func()
    except SystemExit as exc:
        return _exit_code(exc.code)
    return _exit_code(result)


def dispatch(name: str, args: Sequence[str]) -> int:
    """Run subcommand ``name`` with ``args`` forwarded unchanged; return its exit status."""
    command, args = COMMANDS[name], list(args)
    if command.extra and needs_extra(command, args):
        missing = missing_modules(command.extra)
        if missing:
            print(install_hint(name, command.extra, missing), file=sys.stderr)
            return MISSING_EXTRA_EXIT
    target, prog, forwarded = _resolve(command, args)
    try:
        func = _load(target)
    except ImportError:
        # Only a missing optional extra becomes a hint (e.g. `relocate --help` without it);
        # any other ImportError is a bug and propagates.
        missing = missing_modules(command.extra) if command.extra and not command.extra_when else []
        if not missing:
            raise
        print(install_hint(name, str(command.extra), missing), file=sys.stderr)
        return MISSING_EXTRA_EXIT
    with _invoked_as(prog, forwarded):
        return _call(func, forwarded)


def package_version() -> str:
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return "unknown (package not installed; running from a source tree)"


def version_text() -> str:
    extras = " ".join(f"{name}={'no' if missing_modules(name) else 'yes'}" for name in EXTRAS)
    return (f"{DISTRIBUTION} {package_version()} (Python {platform.python_version()})\n"
            f"optional extras: {extras}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Synthetic, local agent-movement experiments (research prototypes, not production). "
                    "Every subcommand forwards its arguments unchanged to the module named in "
                    "docs/cli.md; run '%(prog)s <command> --help' for its options.",
        epilog="Exit codes: 0 success; 1 a check failed; 2 usage error or missing optional extra "
               "(an install hint is printed); receipts verify also uses 3 for an unverifiable bundle.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for command in COMMANDS.values():
        sub.add_parser(command.name, help=command.summary, add_help=False)
    for name, summary in BUILTINS.items():
        sub.add_parser(name, help=summary)
    return parser


def version_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=f"{PROG} version", description=BUILTINS["version"])


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] in COMMANDS:
            return dispatch(argv[0], argv[1:])
        if argv and argv[0] == "version":
            version_parser().parse_args(argv[1:])
            print(version_text())
            return 0
        parser = build_parser()
        parser.parse_args(argv)  # prints help, --version or a usage error, and exits
        parser.print_usage(sys.stderr)  # only reached for odd input such as `-- demo`
        return 2
    except SystemExit as exc:
        return _exit_code(exc.code)


if __name__ == "__main__":
    raise SystemExit(main())
