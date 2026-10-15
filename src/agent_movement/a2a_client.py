"""Optional A2A v1 origin client built on the official ``a2a-sdk``.

Requires ``pip install -e '.[a2a]'``. Resolves the destination Agent Card,
refuses to send unless the card advertises the handoff profile extension and
the needed skill, sends the mapped envelope with the SDK client over the
JSON-RPC or HTTP+JSON binding, records the observed task lifecycle, and checks
that the returned receipt artifact answers exactly the envelope that was sent.

Proves DELEGATION, not migration. No authentication (experimental).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
from google.protobuf.json_format import MessageToDict

from a2a.client import A2ACardResolver, ClientCallContext, ClientConfig, ClientFactory
from a2a.client.service_parameters import ServiceParametersFactory, with_a2a_extensions
from a2a.helpers import new_data_part
from a2a.types import AgentCard, GetTaskRequest, Message, Role, SendMessageRequest, TaskState
from a2a.utils.constants import TransportProtocol
from a2a.utils.errors import A2AError

from .core import ContractError
from .a2a_profile import (EXTENSION_URI, RECEIPT_ARTIFACT_NAME, TASK_MEDIA_TYPE, ProfileError,
                          envelope_to_a2a, skill_id, verify_receipt)

BINDINGS = {"JSONRPC": TransportProtocol.JSONRPC, "HTTP+JSON": TransportProtocol.HTTP_JSON}


class CapabilityMismatch(ProfileError):
    """The destination Agent Card does not advertise what this handoff needs."""


def check_card(card: AgentCard, kind: str) -> None:
    """Client-side capability negotiation from the public Agent Card."""
    if not any(ext.uri == EXTENSION_URI for ext in card.capabilities.extensions):
        raise CapabilityMismatch("agent card does not advertise the handoff profile extension")
    if not any(skill.id == skill_id(kind) for skill in card.skills):
        raise CapabilityMismatch("agent card does not advertise skill " + skill_id(kind))


def build_message(envelope: dict[str, Any], metadata_overrides: dict[str, Any] | None = None) -> Message:
    """Map an envelope to an A2A message. ``metadata_overrides`` exists only to
    craft non-conforming messages for negative compatibility tests."""
    mapped = envelope_to_a2a(envelope)
    mapped["metadata"].update(metadata_overrides or {})
    return Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), context_id=mapped["context_id"],
                   parts=[new_data_part(mapped["data"], media_type=TASK_MEDIA_TYPE)],
                   metadata={EXTENSION_URI: mapped["metadata"]}, extensions=[EXTENSION_URI])


async def fetch_card(base_url: str, http: httpx.AsyncClient) -> AgentCard:
    return await A2ACardResolver(http, base_url).get_agent_card()


async def delegate(base_url: str, envelope: dict[str, Any], *, binding: str = "JSONRPC",
                   streaming: bool = True, activate_extension: bool = True,
                   check_capabilities: bool = True, timeout: float = 10.0,
                   metadata_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send one envelope as an A2A task; return IDs, lifecycle and verified receipt.

    A2A protocol errors (raised before a task exists) are returned as
    ``{"error": {...}}`` rather than raised, so callers can assert on them.
    """
    async with httpx.AsyncClient(timeout=timeout) as http:
        card = await fetch_card(base_url, http)
        if check_capabilities:
            check_card(card, envelope["task"]["kind"])
        config = ClientConfig(streaming=streaming, httpx_client=http,
                              supported_protocol_bindings=[BINDINGS[binding]])
        client = ClientFactory(config).create(card)
        params = ServiceParametersFactory.create(
            [with_a2a_extensions([EXTENSION_URI])] if activate_extension else [])
        call = ClientCallContext(service_parameters=params, timeout=timeout)
        message = build_message(envelope, metadata_overrides)
        states: list[str] = []
        task = None
        try:
            async for event in client.send_message(SendMessageRequest(message=message), context=call):
                kind = event.WhichOneof("payload")
                if kind == "task":
                    task = event.task
                    states.append(TaskState.Name(event.task.status.state))
                elif kind == "status_update":
                    states.append(TaskState.Name(event.status_update.status.state))
            if task is None:
                raise ProfileError("agent returned no task")
            # Authoritative final state, fetched by A2A task ID.
            final = await client.get_task(GetTaskRequest(id=task.id), context=call)
        except A2AError as exc:
            return {"binding": binding, "a2a_message_id": message.message_id,
                    "error": {"type": type(exc).__name__, "message": exc.message}}
        finally:
            await client.close()
    result: dict[str, Any] = {
        "binding": binding, "streaming": streaming, "a2a_message_id": message.message_id,
        "a2a_task_id": final.id, "a2a_context_id": final.context_id,
        "final_state": TaskState.Name(final.status.state), "observed_states": states,
        "agent": card.name,
    }
    if final.status.state == TaskState.TASK_STATE_COMPLETED:
        artifacts = [a for a in final.artifacts if a.name == RECEIPT_ARTIFACT_NAME]
        if len(artifacts) != 1 or len(artifacts[0].parts) != 1:
            raise ProfileError("expected exactly one receipt artifact")
        artifact = artifacts[0]
        metadata = MessageToDict(artifact.metadata).get(EXTENSION_URI)
        result["receipt"] = verify_receipt(envelope, MessageToDict(artifact.parts[0].data), metadata)
        result["a2a_artifact_id"] = artifact.artifact_id
    elif final.status.HasField("message") and final.status.message.parts:
        result["reason"] = MessageToDict(final.status.message.parts[0].data).get("error")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental A2A v1 origin client (synthetic data only)")
    parser.add_argument("--url", required=True, help="base URL of the destination worker")
    parser.add_argument("--envelope", required=True, help="path to a handoff envelope JSON file, or '-'")
    parser.add_argument("--binding", choices=sorted(BINDINGS), default="JSONRPC")
    parser.add_argument("--no-stream", action="store_true", help="use blocking message:send")
    parser.add_argument("--skip-card-check", action="store_true",
                        help="send even if the card lacks the capability (negative tests)")
    parser.add_argument("--schema-version-override",
                        help="send a non-conforming schema_version in the metadata (negative tests)")
    options = parser.parse_args()
    raw = sys.stdin.read() if options.envelope == "-" else Path(options.envelope).read_text("utf-8")
    envelope = json.loads(raw)
    try:
        result = asyncio.run(delegate(options.url, envelope, binding=options.binding,
                                      streaming=not options.no_stream,
                                      check_capabilities=not options.skip_card_check,
                                      metadata_overrides=({"schema_version": options.schema_version_override}
                                                          if options.schema_version_override else None)))
    except ContractError as exc:  # includes ProfileError and CapabilityMismatch
        result = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    print(json.dumps(result, sort_keys=True), flush=True)
    if result.get("final_state") != "TASK_STATE_COMPLETED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
