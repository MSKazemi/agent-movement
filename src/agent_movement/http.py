"""Loopback-only demonstration transport. NOT A2A and NOT production auth."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Approval, Conflict, ContractError, HandoffReceiver, PolicyDenied, SQLiteStore, parse_json


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


def make_server(receiver: HandoffReceiver, port: int = 0) -> LocalServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def respond(self, status: int, body: dict[str, object]) -> None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            if self.path == "/health":
                self.respond(200, {"status": "ready", "agent": receiver.name})
            else:
                self.respond(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/v0/handoffs":
                self.respond(404, {"error": "not_found"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                self.respond(415, {"error": "content_type_required"})
                return
            try:
                size = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.respond(400, {"error": "invalid_content_length"})
                return
            if not 0 < size <= 16384:
                self.respond(413, {"error": "body_too_large_or_empty"})
                return
            try:
                message = parse_json(self.rfile.read(size))
                receipt = receiver.receive(message)
            except ContractError:
                self.respond(400, {"error": "invalid_contract"})
            except PolicyDenied:
                self.respond(403, {"error": "approval_denied"})
            except Conflict:
                self.respond(409, {"error": "idempotency_conflict"})
            else:
                self.respond(200, receipt)

    # Intentionally impossible to expose on a public interface via this API.
    return LocalServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only synthetic receiver (NOT A2A)")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--receiver-id", default="agent-b")
    parser.add_argument("--origin-id", default="agent-a")
    parser.add_argument("--task-id", default="demo-task")
    parser.add_argument("--approval", default="demo-approval")
    parser.add_argument("--kind", choices=["sha256", "word_count"], default="word_count")
    options = parser.parse_args()
    approval = Approval(options.approval, options.task_id, options.origin_id,
                        options.receiver_id, options.kind,
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    receiver = HandoffReceiver(options.receiver_id, SQLiteStore(options.db), [approval])
    server = make_server(receiver, options.port)
    print(json.dumps({"port": server.server_port, "agent": options.receiver_id}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
