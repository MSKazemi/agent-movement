"""Optional A2A v1 origin client built on the official ``a2a-sdk``.

Requires ``pip install -e '.[a2a]'``. Resolves the destination Agent Card,
refuses to send unless the card advertises the handoff profile extension and
the needed skill, sends the mapped envelope with the SDK client over the
JSON-RPC or HTTP+JSON binding, records the observed task lifecycle, and checks
that the returned receipt artifact answers exactly the envelope that was sent.
By default it sends no ``contextId`` and uses the one the server generates.

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
from a2a.client import A2ACardResolver, ClientCallContext, ClientConfig, ClientFactory
from a2a.client.service_parameters import ServiceParametersFactory, with_a2a_extensions
from a2a.helpers import new_data_part
from a2a.types import AgentCard, GetTaskRequest, Message, Role, SendMessageRequest, TaskState
from a2a.utils.constants import TransportProtocol
from a2a.utils.errors import A2AError
from google.protobuf.json_format import MessageToDict

from .a2a_profile import (
    CLIENT_CONTEXT_BOUND,
    CLIENT_CONTEXT_REJECTED,
    EXTENSION_URI,
    EXTENSION_URIS,
    LEGACY_EXTENSION_URI,
    RECEIPT_ARTIFACT_NAME,
    TASK_MEDIA_TYPE,
    ProfileError,
    envelope_to_a2a,
    skill_id,
    verify_receipt,
)
from .core import ContractError

BINDINGS = {"JSONRPC": TransportProtocol.JSONRPC, "HTTP+JSON": TransportProtocol.HTTP_JSON}


class CapabilityMismatch(ProfileError):
    """The destination Agent Card does not advertise what this handoff needs."""


def check_card(card: AgentCard, kind: str, *, extension_uri: str = EXTENSION_URI,
               client_context_id: bool = False) -> None:
    """Client-side capability negotiation from the public Agent Card.

    With ``client_context_id`` the card must also say that the server accepts a
    client-supplied contextId; A2A v1.0 sec. 3.4.1 says clients SHOULD NOT send
    one unless they understand how the server handles it.
    """
    if extension_uri not in EXTENSION_URIS:
        raise ProfileError("unknown handoff profile extension URI")
    advertised = [ext for ext in card.capabilities.extensions if ext.uri == extension_uri]
    if not advertised:
        raise CapabilityMismatch("agent card does not advertise the handoff profile extension")
    if not any(skill.id == skill_id(kind) for skill in card.skills):
        raise CapabilityMismatch("agent card does not advertise skill " + skill_id(kind))
    if client_context_id:
        # Profile 0.1 (the deprecated URN) always accepted a bound client contextId.
        default = CLIENT_CONTEXT_BOUND if extension_uri == LEGACY_EXTENSION_URI else CLIENT_CONTEXT_REJECTED
        policy = MessageToDict(advertised[0].params).get("client_context_id", default)
        if policy != CLIENT_CONTEXT_BOUND:
            raise CapabilityMismatch("agent does not accept client-supplied context IDs "
                                     f"(client_context_id: {policy})")


def build_message(envelope: dict[str, Any], metadata_overrides: dict[str, Any] | None = None, *,
                  extension_uri: str = EXTENSION_URI, context_id: str = "") -> Message:
    """Map an envelope to an A2A message.

    ``context_id`` is empty by default so that the server generates it. Set it
    (to the logical task ID) only for a server that opted in. ``metadata_overrides``
    exists only to craft non-conforming messages for negative compatibility tests.
    """
    mapped = envelope_to_a2a(envelope)
    mapped["metadata"].update(metadata_overrides or {})
    return Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), context_id=context_id,
                   parts=[new_data_part(mapped["data"], media_type=TASK_MEDIA_TYPE)],
                   metadata={extension_uri: mapped["metadata"]}, extensions=[extension_uri])


async def fetch_card(base_url: str, http: httpx.AsyncClient) -> AgentCard:
    return await A2ACardResolver(http, base_url).get_agent_card()


async def delegate(base_url: str, envelope: dict[str, Any], *, binding: str = "JSONRPC",
                   streaming: bool = True, activate_extension: bool = True,
                   check_capabilities: bool = True, timeout: float = 10.0,
                   metadata_overrides: dict[str, Any] | None = None,
                   extension_uri: str = EXTENSION_URI,
                   context_id: str | None = None) -> dict[str, Any]:
    """Send one envelope as an A2A task; return IDs, lifecycle and verified receipt.

    By default no ``contextId`` is sent and the server generates one, returned
    as ``a2a_context_id``. ``context_id`` opts in to a client-supplied value; the
    profile binds it to ``logical_task_id`` (any other value is refused).
    ``extension_uri`` selects the profile URI to activate (the deprecated URN
    alias is accepted for one profile version).

    A2A protocol errors (raised before a task exists) are returned as
    ``{"error": {...}}`` rather than raised, so callers can assert on them.
    """
    async with httpx.AsyncClient(timeout=timeout) as http:
        card = await fetch_card(base_url, http)
        if check_capabilities:
            check_card(card, envelope["task"]["kind"], extension_uri=extension_uri,
                       client_context_id=context_id is not None)
        config = ClientConfig(streaming=streaming, httpx_client=http,
                              supported_protocol_bindings=[BINDINGS[binding]])
        client = ClientFactory(config).create(card)
        params = ServiceParametersFactory.create(
            [with_a2a_extensions([extension_uri])] if activate_extension else [])
        call = ClientCallContext(service_parameters=params, timeout=timeout)
        message = build_message(envelope, metadata_overrides, extension_uri=extension_uri,
                                context_id=context_id or "")
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
    # Server-generated contextIds are opaque (A2A v1.0 sec. 3.4.1): only check presence, or
    # that an accepted client-supplied value was preserved.
    if not final.context_id or (context_id and final.context_id != context_id):
        raise ProfileError("task contextId was not generated or not preserved by the agent")
    result: dict[str, Any] = {
        "binding": binding, "streaming": streaming, "a2a_message_id": message.message_id,
        "a2a_task_id": final.id, "a2a_context_id": final.context_id,
        "context_id_source": "client" if context_id else "server",
        "extension_uri": extension_uri,
        "final_state": TaskState.Name(final.status.state), "observed_states": states,
        "agent": card.name,
    }
    if final.status.state == TaskState.TASK_STATE_COMPLETED:
        artifacts = [a for a in final.artifacts if a.name == RECEIPT_ARTIFACT_NAME]
        if len(artifacts) != 1 or len(artifacts[0].parts) != 1:
            raise ProfileError("expected exactly one receipt artifact")
        artifact = artifacts[0]
        metadata = MessageToDict(artifact.metadata).get(extension_uri)
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
    parser.add_argument("--client-context-id", action="store_true",
                        help="opt in: send contextId = logical_task_id (the server must advertise "
                             "client_context_id: bound-to-logical-task-id); default: server-generated")
    parser.add_argument("--legacy-extension-uri", action="store_true",
                        help=f"activate the deprecated alias {LEGACY_EXTENSION_URI} instead of {EXTENSION_URI}")
    options = parser.parse_args()
    raw = sys.stdin.read() if options.envelope == "-" else Path(options.envelope).read_text("utf-8")
    envelope = json.loads(raw)
    try:
        result = asyncio.run(delegate(options.url, envelope, binding=options.binding,
                                      streaming=not options.no_stream,
                                      check_capabilities=not options.skip_card_check,
                                      extension_uri=(LEGACY_EXTENSION_URI if options.legacy_extension_uri
                                                     else EXTENSION_URI),
                                      context_id=(envelope.get("logical_task_id")
                                                  if options.client_context_id else None),
                                      metadata_overrides=({"schema_version": options.schema_version_override}
                                                          if options.schema_version_override else None)))
    except ContractError as exc:  # includes ProfileError and CapabilityMismatch
        result = {"error": {"type": type(exc).__name__, "message": str(exc)}}
    print(json.dumps(result, sort_keys=True), flush=True)
    if result.get("final_state") != "TASK_STATE_COMPLETED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
