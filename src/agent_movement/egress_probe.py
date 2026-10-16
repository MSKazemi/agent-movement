"""Controlled synthetic adversary: runs only behind the test supervisor."""
import ctypes
import errno
import http.client
import json
import os
import socket
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

port = int(os.environ["AMV_PROBE_PORT"])
result = {}


def attempt(name, fn):
    try:
        fn()
        result[name] = "allowed"
    except OSError as exc:
        result[name] = "blocked" if exc.errno == errno.EPERM else "unexpected_errno"


def tcp_send(route):
    with socket.create_connection(("127.0.0.1", port), timeout=1) as sock:
        sock.sendall((route + " fake-canary-only\n").encode())


attempt("tcp", lambda: tcp_send("raw"))
def http_send(route):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        conn.request("POST", route, body=b"fake-canary-only")
    finally:
        conn.close()


attempt("legacy_http", lambda: http_send("/legacy"))
attempt("a2a_http", lambda: http_send("/a2a"))
attempt("udp", lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
attempt("ipv6", lambda: socket.socket(socket.AF_INET6, socket.SOCK_STREAM))
attempt("unix", lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM))
attempt("spawn", lambda: subprocess.run([sys.executable, "-c", "pass"], check=True))
if hasattr(os, "fork"):
    attempt("fork", os.fork)

libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
libc.syscall.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_long]
fd = libc.syscall(41, socket.AF_INET, socket.SOCK_STREAM, 0)
result["raw_syscall"] = "blocked" if fd == -1 and ctypes.get_errno() == errno.EPERM else "allowed"
if fd >= 0:
    os.close(fd)

req = {"version": 1, "operation": os.environ["AMV_PROBE_OP"],
       "task_id": os.environ["AMV_PROBE_TASK"]}
os.write(int(os.environ["AMV_BROKER_REQ_FD"]),
         (json.dumps(req, sort_keys=True) + "\n").encode())
response = os.read(int(os.environ["AMV_BROKER_RESP_FD"]), 256)
result["broker"] = json.loads(response)["status"]
print(json.dumps(result, sort_keys=True))
