"""Loopback-only demonstration transport. NOT A2A and NOT production auth.

``--receipts-log FILE`` (default off) makes the receiver sign movement receipts for its
accept/reject decisions with an ephemeral synthetic key (issue #32, ``signing`` extra).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .core import Approval, Conflict, ContractError, HandoffReceiver, PolicyDenied, SQLiteStore, parse_json


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True


def _record(event: Any, *args: Any) -> None:
    """Receipt emission must never change the HTTP outcome of a handoff."""
    try:
        event(*args)
    except Exception:
        pass


def make_server(receiver: HandoffReceiver, port: int = 0,
                read_timeout: float = 10.0, receipts: Any = None) -> LocalServer:
    """``receipts`` is an optional ``live_receipts.ReceiptEmitter``; None (default) emits nothing."""
    class Handler(BaseHTTPRequestHandler):
        # Per-socket timeout: a client that declares a Content-Length and then
        # stalls must not pin a handler thread forever (TimeoutError closes it).
        timeout = read_timeout

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
            body = self.rfile.read(size)  # TimeoutError propagates; the base class closes the socket
            try:
                message = parse_json(body)
                receipt = receiver.receive(message)
            except ContractError:
                self.respond(400, {"error": "invalid_contract"})
            except PolicyDenied:
                if receipts is not None:  # the envelope was valid; the receiver's policy refused it
                    _record(receipts.rejected, message)
                self.respond(403, {"error": "approval_denied"})
            except Conflict:
                self.respond(409, {"error": "idempotency_conflict"})
            except Exception:
                # Never drop the connection without an answer (e.g. sqlite "database is locked").
                self.respond(500, {"error": "internal_error"})
            else:
                if receipts is not None:  # signed before answering, so the log is complete on return
                    _record(receipts.accepted, message, receipt)
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
    parser.add_argument("--receipts-log", type=Path, metavar="FILE",
                        help="opt in: sign accept/reject receipts with an ephemeral synthetic key and append "
                             "them to FILE; the public key is advertised on stdout (needs the 'signing' extra)")
    options = parser.parse_args()
    approval = Approval(options.approval, options.task_id, options.origin_id,
                        options.receiver_id, options.kind,
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    receipts = None
    if options.receipts_log is not None:
        from .live_receipts import ReceiptEmitter
        from .receipts import ReceiptError
        try:
            receipts = ReceiptEmitter(options.receipts_log, name=options.receiver_id)
        except ReceiptError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    receiver = HandoffReceiver(options.receiver_id, SQLiteStore(options.db), [approval])
    server = make_server(receiver, options.port, receipts=receipts)
    advertised: dict[str, Any] = {"port": server.server_port, "agent": options.receiver_id}
    if receipts is not None:
        advertised["receipt_key"] = receipts.descriptor()  # public half only
    print(json.dumps(advertised), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
