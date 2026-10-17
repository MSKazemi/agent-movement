"""Synthetic worker: commit via trusted pipe broker, then intentionally stall.

Used to demonstrate that a worker timeout does NOT imply its already-approved
synthetic side effect failed. No sockets, secrets or real effects.
"""
import json
import os
import time

command = {"version": 1, "operation": "delegate", "task_id": "task-1"}
os.write(int(os.environ["AMV_BROKER_REQ_FD"]),
         (json.dumps(command, sort_keys=True) + "\n").encode("utf-8"))
reply = os.read(int(os.environ["AMV_BROKER_RESP_FD"]), 256)
if json.loads(reply).get("status") != "committed":
    raise SystemExit("expected synthetic effect was not committed")
time.sleep(3600)
