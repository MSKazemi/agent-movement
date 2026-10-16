"""Loopback-only HTTP wrapper for ``PeerReceiver``. Synthetic test keys only; NOT A2A, NO TLS."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .core import SQLiteStore, _fields, parse_json
from .http import LocalServer
from .peer import PeerReceiver
from .trust import TrustStore, import_enc_key, import_key


def make_peer_server(receiver: PeerReceiver | None = None, port: int = 0) -> LocalServer:
    """Bind 127.0.0.1 only. ``receiver`` may be attached later via ``server.receiver``."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return  # request lines could carry attacker-chosen paths; traces are sanitized instead

        def respond(self, status: int, body: dict[str, object]) -> None:
            payload = json.dumps(body, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            self.respond(*server.receiver.handle("GET", self.path, b""))

        def do_POST(self) -> None:
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
            self.respond(*server.receiver.handle("POST", self.path, self.rfile.read(size)))

    server = LocalServer(("127.0.0.1", port), Handler)
    server.receiver = receiver
    return server


def load_receiver(config_path: Path) -> PeerReceiver:
    """Provisioning file written by the synthetic test CA (see peer_demo). Never real keys.

    An optional ``enc_key`` (X25519, HPKE) must match the ``enc_key`` in the receiver card.
    """
    raw = parse_json(config_path.read_bytes())
    base = {"card", "key", "trust", "capabilities", "db"}
    config = _fields(raw, base | {"enc_key"} if isinstance(raw, dict) and "enc_key" in raw else base,
                     "receiver config")
    enc_key = import_enc_key(config["enc_key"]) if "enc_key" in config else None
    return PeerReceiver(config["card"], import_key(config["key"]), TrustStore.from_dict(config["trust"]),
                        SQLiteStore(config["db"]), config["capabilities"], enc_key=enc_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only authenticated synthetic receiver (NOT A2A)")
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args()
    receiver = load_receiver(options.config)
    if not receiver.endpoint.startswith("http://127.0.0.1:"):
        raise SystemExit("receiver card endpoint must be loopback HTTP")
    port = int(receiver.endpoint.rsplit(":", 1)[1])  # bind exactly the port the CA certified
    server = make_peer_server(receiver, port)
    print(json.dumps({"port": server.server_port, "agent": receiver.agent_id}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
