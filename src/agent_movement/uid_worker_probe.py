"""Synthetic probe executed by a distinct non-root Linux worker (issue #98).

Run only under the root-owned egress_lab supervisor; it receives no credentials.
Every path and payload is a disposable test value, never a real secret/tool.
"""

from __future__ import annotations

import errno
import http.client
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

results: dict[str, Any] = {
    "uid": os.geteuid(),
    "gid": os.getegid(),
    "real_saved_uids": os.getresuid(),
    "real_saved_gids": os.getresgid(),
    "supplementary_groups": os.getgroups(),
}


def check(name: str, action: Callable[[], object]) -> None:
    try:
        action()
    except PermissionError as exc:
        results[name] = "blocked" if exc.errno in (errno.EACCES, errno.EPERM) else "unexpected_errno"
    except OSError as exc:
        results[name] = "blocked" if exc.errno == errno.EPERM else "unexpected_errno"
    else:
        results[name] = "allowed"


def send_http(path: str) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", int(os.environ["AMV_PROBE_PORT"]), timeout=1)
    try:
        conn.request("POST", path, body=b'{"synthetic":"unauthorized"}',
                     headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        response.read()
    finally:
        conn.close()


check("legacy_http", lambda: send_http("/v0/handoffs"))
check("a2a_jsonrpc", lambda: send_http("/a2a/jsonrpc"))
check("a2a_rest", lambda: send_http("/a2a/rest/v1/message:send"))
check("peer_preflight", lambda: send_http("/v0/preflight"))
check("tool_service", lambda: send_http("/v0/effects"))
check("tcp", lambda: socket.create_connection(("127.0.0.1", int(os.environ["AMV_PROBE_PORT"])), 1))
check("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
check("unix", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
check("spawn", lambda: subprocess.run([sys.executable, "-c", "pass"], check=True))
check("reacquire_root", lambda: os.setuid(0))

for key, name in (
    ("AMV_TEST_PROTECTED_FILE", "protected_file"),
    ("AMV_TEST_PROTECTED_DB", "protected_db"),
):
    if key in os.environ:
        check(name, lambda file=Path(os.environ[key]): file.read_bytes())

if "AMV_TEST_PARENT_PID" in os.environ:
    pid = os.environ["AMV_TEST_PARENT_PID"]
    check("parent_proc_environ", lambda: Path(f"/proc/{pid}/environ").read_bytes())
    if "AMV_TEST_PARENT_FD" in os.environ:
        descriptor = os.environ["AMV_TEST_PARENT_FD"]
        def inspect_parent_fd() -> None:
            fd = os.open(f"/proc/{pid}/fd/{descriptor}", os.O_RDONLY)
            os.close(fd)
        check("parent_private_fd", inspect_parent_fd)

# Check what the worker inherited independently of the parent's reported args.
try:
    targets = []
    for name in os.listdir("/proc/self/fd"):
        with suppress(OSError):
            targets.append(os.readlink(f"/proc/self/fd/{name}"))
    results["protected_fd_inherited"] = any(
        p in targets for p in (
            os.environ.get("AMV_TEST_PROTECTED_FILE", "<not-provisioned-file>"),
            os.environ.get("AMV_TEST_PROTECTED_DB", "<not-provisioned-db>"),
        )
    )
except OSError:
    results["protected_fd_inherited"] = "unobserved"

request = {
    "version": 1,
    "operation": os.environ["AMV_PROBE_OP"],
    "task_id": os.environ["AMV_PROBE_TASK"],
}
os.write(int(os.environ["AMV_BROKER_REQ_FD"]),
         (json.dumps(request, sort_keys=True) + "\n").encode("utf-8"))
raw = os.read(int(os.environ["AMV_BROKER_RESP_FD"]), 256)
results["broker"] = json.loads(raw)["status"]
print(json.dumps(results, sort_keys=True))
