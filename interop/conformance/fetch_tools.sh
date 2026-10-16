#!/usr/bin/env bash
# Fetch the official A2A conformance tools at the commits the expectations were recorded with,
# and give the TCK its own virtual environment (it must not share the adapter's environment).
#
#   interop/conformance/fetch_tools.sh [DEST]      # default DEST: .a2a-tools (outside git)
#
# Then: python interop/conformance/run_conformance.py --tck DEST/a2a-tck --inspector DEST/a2a-inspector
set -euo pipefail

# a2a-tck main, 2026-09-01. The newest tag (1.0.0.alpha2, 2026-05-27) predates a2a-tck PR #230,
# so its JSON-RPC client cannot reach a JSON-RPC endpoint that is not at the server root.
TCK_REPO=https://github.com/a2aproject/a2a-tck.git
TCK_COMMIT=263b9cfaf16a554bdfb166a7ba5b67716e946349
# a2a-inspector main, 2026-08-08 (the only tag, v0.1.0, is from 2025 and targets A2A v0.3).
INSPECTOR_REPO=https://github.com/a2aproject/a2a-inspector.git
INSPECTOR_COMMIT=8aa064639af106ff771d60428ef6d460f5454743

DEST=${1:-.a2a-tools}
PYTHON=${PYTHON:-python3}
mkdir -p "$DEST"

fetch() {  # fetch REPO COMMIT DIR: shallow fetch of exactly one commit
  local repo=$1 commit=$2 dir=$3
  if [ ! -d "$dir/.git" ]; then git init -q "$dir"; git -C "$dir" remote add origin "$repo"; fi
  git -C "$dir" fetch -q --depth 1 origin "$commit"
  git -C "$dir" -c advice.detachedHead=false checkout -q --force FETCH_HEAD
  test "$(git -C "$dir" rev-parse HEAD)" = "$commit"
}

fetch "$TCK_REPO" "$TCK_COMMIT" "$DEST/a2a-tck"
fetch "$INSPECTOR_REPO" "$INSPECTOR_COMMIT" "$DEST/a2a-inspector"

if command -v uv >/dev/null 2>&1; then
  # The TCK's own uv.lock pins its dependencies.
  (cd "$DEST/a2a-tck" && uv sync -q --frozen)
else
  [ -x "$DEST/a2a-tck/.venv/bin/python" ] || "$PYTHON" -m venv "$DEST/a2a-tck/.venv"
  "$DEST/a2a-tck/.venv/bin/python" -m pip install -q -e "$DEST/a2a-tck"
fi
echo "a2a-tck $TCK_COMMIT and a2a-inspector $INSPECTOR_COMMIT ready in $DEST"
