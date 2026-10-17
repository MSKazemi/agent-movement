"""Synthetic direct HTTP probes for *actual* local adapter listeners.

Run ONLY under egress_lab.run_guarded_agent in a local test. The deliberately
valid legacy envelope is public/synthetic; no credentials or external hosts.
The same script targets a listener's real legacy, A2A, and peer ingress paths.
"""

from __future__ import annotations

import errno
import http.client
import json
import os

port = int(os.environ["AMV_PROBE_PORT"])
legacy_envelope = {
    "schema_version": "0.1.0-draft",
    "movement_id": "movement-unguarded-probe",
    "logical_task_id": "task-1",
    "operation": "delegate",
    "origin": {"agent_id": "agent-a"},
    "destination": {"agent_id": "agent-b"},
    "task": {"kind": "word_count", "text": "synthetic adapter probe"},
    "context": {"classification": "synthetic"},
    "authority": {"approval_ref": "approval-1"},
    "execution": {"idempotency_key": "op-adapter-probe"},
    "observability": {"trace_id": "trace-adapter-probe"},
}
a2a_request = {
    "jsonrpc": "2.0", "id": "adapter-probe",
    "method": "SendMessage",
    "params": {
        "message": {
            "role": "ROLE_USER", "messageId": "adapter-probe",
            "parts": [{"text": "synthetic adapter probe"}],
        },
    },
}
cases = (
    ("legacy_http", "/v0/handoffs", legacy_envelope),
    ("a2a_http", "/a2a/jsonrpc", a2a_request),
    ("peer_http", "/v0/preflight", {"type": "synthetic-probe"}),
)
result: dict[str, str] = {}
for name, path, body in cases:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        conn.request(
            "POST", path, body=json.dumps(body, sort_keys=True).encode("utf-8"),
            headers={"Content-Type": "application/json", "A2A-Version": "1.0"},
        )
    except OSError as exc:
        result[name] = "blocked" if exc.errno == errno.EPERM else "unexpected_errno"
    else:
        # The socket write itself was permitted; response content is irrelevant.
        result[name] = "sent"
    finally:
        conn.close()

command = {
    "version": 1,
    "operation": os.environ["AMV_PROBE_OP"],
    "task_id": os.environ["AMV_PROBE_TASK"],
}
os.write(int(os.environ["AMV_BROKER_REQ_FD"]),
         (json.dumps(command, sort_keys=True) + "\n").encode("utf-8"))
response = os.read(int(os.environ["AMV_BROKER_RESP_FD"]), 256)
result["broker"] = json.loads(response)["status"]
print(json.dumps(result, sort_keys=True))
