#!/usr/bin/env python3
"""Freeze a MobilityBench fixture release: ground truth + SHA-256 manifest (maintainers only).

Usage:
  python3 tools/mobilitybench_freeze.py [--suite v0.1|v0.2] [--fixtures DIR] [--check]

Reads tasks.jsonl, recomputes ground_truth.jsonl with the full-knowledge,
fault-free reference interpreter (and, for v0.2, schedule.jsonl from the seeded
fault generator), then writes MANIFEST.json (per-file SHA-256 and the release
digest). `--check` writes nothing and exits 1 if the committed ground truth,
schedule or manifest differ from a fresh computation.

A frozen release must never be edited in place: changing any task, rubric or
ground truth requires a new suite version and a new fixture directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_movement.mobilitybench_v01 import (FIXTURE_ROOT, MANIFEST_NAME, SUITE_SPECS,  # noqa: E402
                                              build_ground_truth, file_digests, load_fixtures,
                                              release_digest, schedule_rows)


def _sync(path: Path, text: str, check: bool) -> bool:
    """Write `text` to `path`, or with `check` report whether the committed file equals it."""
    if check:
        return path.exists() and path.read_text(encoding="utf-8") == text
    path.write_text(text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", default="v0.1", choices=sorted(SUITE_SPECS))
    parser.add_argument("--fixtures", type=Path, default=None,
                        help="fixture directory (default: the packaged release of --suite)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    spec = SUITE_SPECS[args.suite]
    root = args.fixtures if args.fixtures is not None else FIXTURE_ROOT / spec.version
    fx = load_fixtures(args.suite, directory=root, verify=False, check_schedule=False)
    truth = "".join(json.dumps(build_ground_truth(t), sort_keys=True, ensure_ascii=False) + "\n"
                    for t in fx.tasks)
    if not _sync(root / "ground_truth.jsonl", truth, args.check):
        print("ground_truth.jsonl differs from the reference interpreter", file=sys.stderr)
        return 1
    if "schedule.jsonl" in spec.files:
        schedule = "".join(json.dumps(row, sort_keys=True) + "\n"
                           for row in schedule_rows(fx.tasks, fx.seeds["seeds"], args.suite))
        if not _sync(root / "schedule.jsonl", schedule, args.check):
            print("schedule.jsonl differs from the seeded fault generator", file=sys.stderr)
            return 1
    files = file_digests(root, spec.files)
    manifest = json.dumps({"suite_version": spec.version, "files": files,
                           "release_digest": release_digest(files),
                           "file_order": list(spec.files)}, indent=2, sort_keys=True) + "\n"
    if not _sync(root / MANIFEST_NAME, manifest, args.check):
        print("MANIFEST.json differs from the fixture files", file=sys.stderr)
        return 1
    if args.check:
        print(f"{spec.version}: fixtures, ground truth{', schedule' if 'schedule.jsonl' in spec.files else ''} "
              "and manifest are consistent")
        return 0
    print(json.dumps({"release_digest": release_digest(files), "tasks": len(fx.tasks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
