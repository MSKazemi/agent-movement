#!/usr/bin/env python3
"""Freeze a MobilityBench fixture release: ground truth + SHA-256 manifest (maintainers only).

Usage:
  python3 tools/mobilitybench_freeze.py [--fixtures DIR] [--check]

Reads tasks.jsonl, recomputes ground_truth.jsonl with the full-knowledge,
fault-free reference interpreter, then writes MANIFEST.json (per-file SHA-256
and the release digest). `--check` writes nothing and exits 1 if the committed
ground truth or manifest differ from a fresh computation.

A frozen release must never be edited in place: changing any task, rubric or
ground truth requires a new suite version and a new fixture directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_movement.mobilitybench_v01 import (FIXTURE_ROOT, FIXTURE_FILES, MANIFEST_NAME,  # noqa: E402
                                              SUITE_VERSION, build_ground_truth, file_digests,
                                              load_fixtures, release_digest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_ROOT / SUITE_VERSION)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    fx = load_fixtures(directory=args.fixtures, verify=False)
    truth = "".join(json.dumps(build_ground_truth(t), sort_keys=True, ensure_ascii=False) + "\n"
                    for t in fx.tasks)
    truth_path = args.fixtures / "ground_truth.jsonl"
    if args.check:
        if not truth_path.exists() or truth_path.read_text(encoding="utf-8") != truth:
            print("ground_truth.jsonl differs from the reference interpreter", file=sys.stderr)
            return 1
    else:
        truth_path.write_text(truth, encoding="utf-8")
    files = file_digests(args.fixtures)
    manifest = json.dumps({"suite_version": SUITE_VERSION, "files": files,
                           "release_digest": release_digest(files),
                           "file_order": list(FIXTURE_FILES)}, indent=2, sort_keys=True) + "\n"
    manifest_path = args.fixtures / MANIFEST_NAME
    if args.check:
        if not manifest_path.exists() or manifest_path.read_text(encoding="utf-8") != manifest:
            print("MANIFEST.json differs from the fixture files", file=sys.stderr)
            return 1
        print("fixtures, ground truth and manifest are consistent")
        return 0
    manifest_path.write_text(manifest, encoding="utf-8")
    print(json.dumps({"release_digest": release_digest(files), "tasks": len(fx.tasks)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
