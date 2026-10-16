"""Regression tests for the A2A v1.0 conformance fixes found by the official A2A TCK (issue #28).

Each test pins one behaviour that the TCK (a2aproject/a2a-tck) flagged against the adapter
server and that was fixed in a2a_server.py; the run and its results are recorded in
docs/a2a-adapter.md ("Conformance"). Skipped unless the optional extra is installed:
python -m pip install -e '.[a2a]'. The destination worker runs as a separate OS process.
"""

import http.client
import json
import unittest
import urllib.parse

from agent_movement.a2a_profile import EXTENSION_URI, TASK_MEDIA_TYPE
from test_a2a_adapter import HAVE_A2A, SKIP_REASON, _A2AServerCase, envelope


@unittest.skipUnless(HAVE_A2A, SKIP_REASON)
class A2AConformanceFixTests(_A2AServerCase):

    def request(self, method, path, body=None, headers=None):
        """One raw HTTP exchange without following redirects: (status, headers, parsed body)."""
        url = urllib.parse.urlsplit(self.url)
        connection = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
        try:
            data = None if body is None else json.dumps(body).encode()
            connection.request(method, path, body=data, headers={
                "A2A-Version": "1.0", "Content-Type": "application/json", **(headers or {})})
            response = connection.getresponse()
            raw = response.read()
            content_type = response.getheader("Content-Type") or ""
            parsed = json.loads(raw) if raw and content_type.startswith("application/json") else raw
            return response.status, {k.lower(): v for k, v in response.getheaders()}, parsed
        finally:
            connection.close()

    def send(self, message, binding="JSONRPC", extensions=EXTENSION_URI):
        headers = {"A2A-Extensions": extensions} if extensions else {}
        if binding == "JSONRPC":
            return self.request("POST", "/a2a/jsonrpc", {"jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                                                         "params": {"message": message}}, headers)
        return self.request("POST", "/a2a/rest/message:send", {"message": message}, headers)

    # --- Routing (TCK JSON-RPC client posts to "<interface url>/") ------------------------

    def test_jsonrpc_trailing_slash_redirects_to_interface_url(self):
        status, headers, _ = self.request("POST", "/a2a/jsonrpc/", {})
        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], self.url + "/a2a/jsonrpc")

    def test_rest_tenant_segment_follows_the_interface_url(self):
        # A2A v1.0 a2a.proto: "/{tenant}/tasks/{id}" relative to the HTTP+JSON interface URL.
        status, _, body = self.request("GET", "/a2a/rest/some-tenant/tasks/no-such-task")
        self.assertEqual((status, body["error"]["status"]), (404, "NOT_FOUND"))
        status, _, _ = self.request("GET", "/some-tenant/a2a/rest/tasks/no-such-task")
        self.assertEqual(status, 404)  # no root-level tenant mount any more: plain Starlette 404

    # --- Agent Card caching (A2A v1.0 sec. 8.6.1, SHOULD) ---------------------------------

    def test_agent_card_sends_cache_control_and_etag(self):
        status, headers, _ = self.request("GET", "/.well-known/agent-card.json")
        self.assertEqual(status, 200)
        self.assertIn("max-age=", headers["cache-control"])
        self.assertTrue(headers["etag"])
        status, _, _ = self.request("GET", "/.well-known/agent-card.json",
                                    headers={"If-None-Match": headers["etag"]})
        self.assertEqual(status, 304)

    # --- Error mapping before the profile check (A2A v1.0 sec. 3.1.1, 3.4.2) -------------

    def test_unknown_task_id_gives_task_not_found_on_both_bindings(self):
        message = {"role": "ROLE_USER", "messageId": "m-unknown-task", "taskId": "no-such-task",
                   "parts": [{"text": "continue"}]}
        _, _, body = self.send(message)
        self.assertEqual(body["error"]["code"], -32001)
        status, _, body = self.send(message, binding="HTTP+JSON")
        self.assertEqual((status, body["error"]["details"][0]["reason"]), (404, "TASK_NOT_FOUND"))
        # Without the profile activated the same message still gets TaskNotFoundError.
        _, _, body = self.send(message, extensions=None)
        self.assertEqual(body["error"]["code"], -32001)
        self.assertEqual([r["outcome"] for r in self.correlation(a2a_message_id="m-unknown-task")],
                         ["rejected.TaskNotFoundError"] * 3)

    def test_unsupported_part_media_type_gives_content_type_not_supported(self):
        message = {"role": "ROLE_USER", "messageId": "m-media",
                   "parts": [{"raw": "dGNr", "mediaType": "application/x-unsupported"}]}
        _, _, body = self.send(message)
        self.assertEqual(body["error"]["code"], -32005)
        _, _, body = self.send(message, binding="HTTP+JSON")
        self.assertEqual(body["error"]["details"][0]["reason"], "CONTENT_TYPE_NOT_SUPPORTED")

    def test_message_to_existing_task_is_unsupported_operation(self):
        value = envelope("movement-cont", "op-cont")
        first = self.delegate(value)
        self.assertEqual(first["final_state"], "TASK_STATE_COMPLETED")
        message = self.mapped_message_dict(value)
        message["taskId"] = first["a2a_task_id"]
        _, _, body = self.send(message)
        self.assertEqual(body["error"]["code"], -32004)
        self.assertEqual(len(self.completed_movements("movement-cont")), 1)

    def test_profile_rejections_are_unchanged(self):
        # A plain-text part (no media type) and a missing extension keep their profile errors.
        message = {"role": "ROLE_USER", "messageId": "m-text", "parts": [{"text": "hello"}]}
        self.assertEqual(self.send(message)[2]["error"]["code"], -32602)
        self.assertEqual(self.send(message, extensions=None)[2]["error"]["code"], -32008)
        part = self.mapped_message_dict(envelope("movement-media-ok", "op-media-ok"))["parts"][0]
        self.assertEqual(part["mediaType"], TASK_MEDIA_TYPE)


if __name__ == "__main__":
    unittest.main()
