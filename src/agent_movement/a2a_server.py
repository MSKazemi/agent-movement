"""Optional A2A v1 destination worker built on the official ``a2a-sdk``.

Requires ``pip install -e '.[a2a]'``. It wraps the unchanged local
:class:`~agent_movement.core.HandoffReceiver`: the A2A SDK owns all protocol
framing (Agent Card, JSON-RPC and HTTP+JSON bindings, task lifecycle, SSE),
while this module only (1) admits requests that match the experimental
handoff profile and the advertised skills, and (2) maps the receiver's receipt
to a structured A2A artifact.

This proves DELEGATION of one allowlisted pure task, NOT agent migration.
There is no authentication: agent IDs remain claims, and the Agent Card
declares no security scheme. Loopback only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette

from a2a.helpers import new_data_part, new_task
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandlerV2
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes, create_rest_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (AgentCapabilities, AgentCard, AgentExtension, AgentInterface, AgentSkill,
                       ExtensionSupportRequiredError, InvalidParamsError, Message, Role,
                       SendMessageRequest, TaskState, UnsupportedOperationError)
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

from .a2a_profile import (EXTENSION_URI, KINDS, RECEIPT_MEDIA_TYPE, TASK_MEDIA_TYPE,
                          A2ACorrelationLog, a2a_to_envelope,
                          receipt_to_artifact, skill_id)
from .core import (SCHEMA_VERSION, Approval, Conflict, ContractError, HandoffReceiver, PolicyDenied,
                   SQLiteStore)

JSONRPC_PATH = "/a2a/jsonrpc"
REST_PREFIX = "/a2a/rest"


def build_agent_card(base_url: str, receiver_id: str, kinds: list[str]) -> AgentCard:
    """Agent Card for the destination worker; advertises only the enabled kinds."""
    skills = [AgentSkill(
        id=skill_id(kind), name=f"Delegated {kind}",
        description=(f"Pure, allowlisted '{kind}' over synthetic/public text, executed only with a "
                     "receiver-side approval. No tools, no side effects."),
        tags=["agent-movement", "delegation", "experimental"],
        input_modes=[TASK_MEDIA_TYPE], output_modes=[RECEIPT_MEDIA_TYPE]) for kind in kinds]
    profile = AgentExtension(
        uri=EXTENSION_URI, required=True,
        description=("Experimental agent-movement handoff profile: envelope fields in "
                     "Message.metadata, one structured task part, receipt artifact."),
        params={"schema_version": SCHEMA_VERSION, "operations": ["delegate"],
                "destination_agent_id": receiver_id, "proves": "delegation-not-migration",
                "authentication": "none-experimental"})
    return AgentCard(
        name=f"agent-movement receiver ({receiver_id})",
        description=("Experimental local A2A destination worker. Delegation of allowlisted pure tasks "
                     "only; not migration; unauthenticated; loopback only."),
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=base_url + JSONRPC_PATH, protocol_binding=TransportProtocol.JSONRPC,
                           protocol_version=PROTOCOL_VERSION_CURRENT),
            AgentInterface(url=base_url + REST_PREFIX, protocol_binding=TransportProtocol.HTTP_JSON,
                           protocol_version=PROTOCOL_VERSION_CURRENT),
        ],
        capabilities=AgentCapabilities(streaming=True, push_notifications=False,
                                       extended_agent_card=False, extensions=[profile]),
        default_input_modes=[TASK_MEDIA_TYPE],
        default_output_modes=[RECEIPT_MEDIA_TYPE],
        skills=skills,
    )


def decode_message(message: Message, request_metadata: Any = None, bound_task_id: str = "") -> dict[str, Any]:
    """Map an inbound A2A message to a validated envelope or raise ``ContractError``.

    ``bound_task_id`` is the server-assigned A2A task ID that the SDK writes
    into the message after admission; a client-chosen task ID is refused.
    """
    if request_metadata:
        raise ContractError("request-level metadata is not accepted")
    if message.role != Role.ROLE_USER:
        raise ContractError("handoff must be a user-role message")
    if message.task_id != bound_task_id or message.reference_task_ids:
        raise ContractError("task continuation and references are not supported")
    if list(message.extensions) != [EXTENSION_URI]:
        raise ContractError("message must declare exactly the handoff profile extension")
    if len(message.parts) != 1:
        raise ContractError("handoff message must contain exactly one part")
    part = message.parts[0]
    if (part.WhichOneof("content") != "data" or part.media_type != TASK_MEDIA_TYPE
            or part.filename or len(part.metadata)):
        raise ContractError("handoff part must be one structured task data part")
    metadata = MessageToDict(message.metadata)
    if set(metadata) != {EXTENSION_URI}:
        raise ContractError("message metadata must contain only the handoff profile")
    return a2a_to_envelope(metadata[EXTENSION_URI], MessageToDict(part.data), message.context_id)


class HandoffRequestHandler(DefaultRequestHandlerV2):
    """SDK request handler with profile admission before any task is created."""

    def __init__(self, *, executor: "HandoffExecutor", agent_card: AgentCard,
                 kinds: list[str], log: A2ACorrelationLog):
        super().__init__(agent_executor=executor, task_store=InMemoryTaskStore(),
                         agent_card=agent_card, validate_input_modes=True)
        self.kinds = frozenset(kinds)
        self.log = log

    async def _admit(self, params: SendMessageRequest, context: Any) -> None:
        message_id = params.message.message_id or "missing"
        try:
            if EXTENSION_URI not in context.requested_extensions:
                raise ExtensionSupportRequiredError(
                    message=f"client must activate required extension {EXTENSION_URI}")
            try:
                envelope = decode_message(params.message, MessageToDict(params.metadata))
            except ContractError as exc:
                raise InvalidParamsError(message=f"handoff profile rejected: {exc}") from None
            if envelope["task"]["kind"] not in self.kinds:
                raise UnsupportedOperationError(
                    message="capability not advertised by this agent: " + skill_id(envelope["task"]["kind"]))
        except (ExtensionSupportRequiredError, InvalidParamsError, UnsupportedOperationError) as exc:
            await asyncio.to_thread(self.log.record, message_id=message_id,
                                    outcome="rejected." + type(exc).__name__)
            raise

    async def on_message_send(self, params: SendMessageRequest, context: Any):
        await self._admit(params, context)
        return await super().on_message_send(params, context)

    async def on_message_send_stream(self, params: SendMessageRequest, context: Any):
        await self._admit(params, context)
        async for event in super().on_message_send_stream(params, context):
            yield event


class HandoffExecutor(AgentExecutor):
    """Runs the unchanged core receiver; emits SUBMITTED, WORKING, artifact, terminal state."""

    def __init__(self, receiver: HandoffReceiver, log: A2ACorrelationLog):
        self.receiver = receiver
        self.log = log

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id, context_id = context.task_id or "", context.context_id or ""
        message = context.message
        # No history is stored on the task: the A2A task store keeps IDs and results only.
        await event_queue.enqueue_event(new_task(task_id, context_id, TaskState.TASK_STATE_SUBMITTED))
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()
        envelope = None
        try:
            envelope = decode_message(message, bound_task_id=task_id)  # defense in depth
            receipt = await asyncio.to_thread(self.receiver.receive, envelope)
        except (ContractError, PolicyDenied, Conflict) as exc:
            reason = {PolicyDenied: "approval_denied", Conflict: "idempotency_conflict"}.get(
                type(exc), "invalid_contract")
            await asyncio.to_thread(self.log.record, message_id=message.message_id, outcome=reason,
                                    task_id=task_id, context_id=context_id, envelope=envelope)
            await updater.reject(updater.new_agent_message(
                [new_data_part({"error": reason}, media_type="application/json")]))
            return
        artifact = receipt_to_artifact(receipt)
        await updater.add_artifact(
            [new_data_part(artifact["data"], media_type=RECEIPT_MEDIA_TYPE)],
            artifact_id=artifact["artifact_id"], name=artifact["name"],
            metadata={EXTENSION_URI: artifact["metadata"]}, extensions=[EXTENSION_URI],
            last_chunk=True)
        await asyncio.to_thread(
            self.log.record, message_id=message.message_id,
            outcome="replayed" if receipt["replayed"] else "completed", task_id=task_id,
            context_id=context_id, envelope=envelope, artifact_digest=receipt["artifact_digest"])
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError(message="synthetic handoffs complete synchronously")


def build_app(*, db: Path, base_url: str, receiver_id: str, approvals: list[Approval],
              kinds: list[str]) -> Starlette:
    unknown = set(kinds) - set(KINDS)
    if not kinds or unknown:
        raise ValueError("kinds must be a non-empty subset of " + ", ".join(KINDS))
    store = SQLiteStore(db)
    log = A2ACorrelationLog(db)
    card = build_agent_card(base_url, receiver_id, kinds)
    handler = HandoffRequestHandler(executor=HandoffExecutor(HandoffReceiver(receiver_id, store, approvals), log),
                                    agent_card=card, kinds=kinds, log=log)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette):
        yield
        await handler.aclose()

    routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, JSONRPC_PATH),
              *create_rest_routes(handler, path_prefix=REST_PREFIX)]
    return Starlette(routes=routes, lifespan=lifespan)


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Experimental A2A v1 destination worker (loopback only)")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--receiver-id", default="agent-b")
    parser.add_argument("--origin-id", default="agent-a")
    parser.add_argument("--task-id", default="demo-task")
    parser.add_argument("--approval", default="demo-approval")
    parser.add_argument("--kind", choices=KINDS, default="word_count", help="approved task kind")
    parser.add_argument("--advertise", choices=KINDS, action="append",
                        help="kinds advertised as skills (default: only --kind)")
    options = parser.parse_args()
    approval = Approval(options.approval, options.task_id, options.origin_id, options.receiver_id,
                        options.kind, expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    # Intentionally impossible to bind a public interface through this CLI.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", options.port))
    sock.listen(64)  # queue early connections until uvicorn starts accepting
    port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"
    app = build_app(db=options.db, base_url=base_url, receiver_id=options.receiver_id,
                    approvals=[approval], kinds=options.advertise or [options.kind])
    print(json.dumps({"port": port, "agent": options.receiver_id, "url": base_url}), flush=True)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
