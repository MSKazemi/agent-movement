#!/usr/bin/env node
// Cross-SDK interop client for the agent-movement A2A handoff profile.
//
// Uses only the official JavaScript SDK (@a2a-js/sdk, pinned in package.json) to perform one
// handoff against the Python a2a-sdk server (python -m agent_movement.a2a_server). The profile
// mapping, canonical-JSON digests and receipt check are re-implemented here from the
// specification (docs/a2a-profile-extension.md), not imported from the Python package, so a
// passing run shows that two independent implementations agree on the wire format.
//
// Usage:
//   node handoff.mjs --url http://127.0.0.1:<port> --envelope envelope.json
//                    [--binding JSONRPC|HTTP+JSON] [--no-stream] [--no-extension]
// Prints one JSON object on stdout. Exit 0 only for a completed task whose receipt artifact
// answers exactly the sent envelope; 3 for any other outcome; 2 for usage errors.
//
// Proves DELEGATION, not migration. Synthetic data only; no authentication (experimental).

import { createHash, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

import { SendMessageRequest, TaskState, taskStateToJSON } from '@a2a-js/sdk';
import { ClientFactory, ClientFactoryOptions, ServiceParameters, withA2AExtensions } from '@a2a-js/sdk/client';

export const EXTENSION_URI = 'https://github.com/MSKazemi/agent-movement/blob/main/docs/a2a-profile-extension.md';
export const TASK_MEDIA_TYPE = 'application/vnd.agent-movement.task+json';
export const RECEIPT_ARTIFACT_NAME = 'handoff-receipt';
const BINDINGS = new Set(['JSONRPC', 'HTTP+JSON']);
// The SDK's package.json is not in its "exports" map, so read the installed copy directly.
const SDK_VERSION = JSON.parse(readFileSync(
  new URL('./node_modules/@a2a-js/sdk/package.json', import.meta.url), 'utf8')).version;

// Exact key sets from the profile spec (sec. 4 and sec. 6). Anything else is refused.
const ENVELOPE_SHAPE = {
  schema_version: null, movement_id: null, logical_task_id: null, operation: null,
  origin: ['agent_id'], destination: ['agent_id'], task: ['kind', 'text'],
  context: ['classification'], authority: ['approval_ref'], execution: ['idempotency_key'],
  observability: ['trace_id'],
};
const RECEIPT_FIELDS = ['artifact', 'artifact_digest', 'destination_agent_id', 'envelope_digest',
  'logical_task_id', 'movement_id', 'origin_agent_id', 'status', 'trace_id'];
const ARTIFACT_METADATA_FIELDS = ['artifact_digest', 'envelope_digest', 'movement_id', 'replayed', 'trace_id'];

class ProfileError extends Error {}

const sameKeys = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort());

// Canonical JSON as in agent_movement.core.canonical: sorted keys, no whitespace, UTF-8, no NaN.
export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  if (typeof value === 'number' && !Number.isFinite(value)) throw new ProfileError('non-finite number');
  return JSON.stringify(value);
}

export const digest = (value) => createHash('sha256').update(canonical(value), 'utf8').digest('hex');

export function checkEnvelopeShape(envelope) {
  if (!sameKeys(envelope, Object.keys(ENVELOPE_SHAPE))) throw new ProfileError('invalid envelope fields');
  for (const [name, inner] of Object.entries(ENVELOPE_SHAPE)) {
    if (inner === null ? typeof envelope[name] !== 'string' : !sameKeys(envelope[name], inner)) {
      throw new ProfileError(`invalid envelope field ${name}`);
    }
  }
  return envelope;
}

// Profile sec. 4: 11 allowlisted fields in Message.metadata[<URI>], {kind, text} in the one data part.
export function envelopeToA2A(envelope) {
  const v = checkEnvelopeShape(envelope);
  return {
    metadata: {
      schema_version: v.schema_version, movement_id: v.movement_id, logical_task_id: v.logical_task_id,
      operation: v.operation, origin_agent_id: v.origin.agent_id, destination_agent_id: v.destination.agent_id,
      classification: v.context.classification, approval_ref: v.authority.approval_ref,
      idempotency_key: v.execution.idempotency_key, trace_id: v.observability.trace_id,
      envelope_digest: digest(v),
    },
    data: { kind: v.task.kind, text: v.task.text },
  };
}

// Client-side capability negotiation from the public Agent Card (profile sec. 3).
export function checkCard(card, kind) {
  if (!(card.capabilities?.extensions ?? []).some((ext) => ext.uri === EXTENSION_URI)) {
    throw new ProfileError('agent card does not advertise the handoff profile extension');
  }
  if (!(card.skills ?? []).some((skill) => skill.id === `agent-movement.${kind}`)) {
    throw new ProfileError(`agent card does not advertise skill agent-movement.${kind}`);
  }
}

// Origin-side receipt check (profile sec. 6): the artifact must answer exactly this envelope.
export function verifyReceipt(envelope, data, metadata) {
  if (!sameKeys(data, RECEIPT_FIELDS)) throw new ProfileError('invalid receipt artifact fields');
  if (!sameKeys(metadata, ARTIFACT_METADATA_FIELDS)) throw new ProfileError('invalid receipt artifact metadata');
  const expected = {
    status: 'completed', movement_id: envelope.movement_id, logical_task_id: envelope.logical_task_id,
    origin_agent_id: envelope.origin.agent_id, destination_agent_id: envelope.destination.agent_id,
    trace_id: envelope.observability.trace_id, envelope_digest: digest(envelope),
  };
  for (const [name, value] of Object.entries(expected)) {
    if (data[name] !== value) throw new ProfileError(`receipt ${name} does not match the sent envelope`);
  }
  if (data.artifact_digest !== digest(data.artifact)) throw new ProfileError('receipt artifact digest mismatch');
  for (const name of ['movement_id', 'trace_id', 'envelope_digest', 'artifact_digest']) {
    if (metadata[name] !== data[name]) throw new ProfileError(`artifact metadata ${name} mismatch`);
  }
  if (typeof metadata.replayed !== 'boolean') throw new ProfileError('invalid replayed flag');
  return { ...data, replayed: metadata.replayed };
}

const stateName = (state) => taskStateToJSON(state);

export async function delegate(baseUrl, envelope, { binding = 'JSONRPC', streaming = true, activateExtension = true } = {}) {
  const factory = new ClientFactory(ClientFactoryOptions.createFrom(ClientFactoryOptions.default,
    { preferredTransports: [binding] }));
  const client = await factory.createFromUrl(baseUrl);
  const card = await client.getAgentCard();
  checkCard(card, envelope.task.kind);
  const mapped = envelopeToA2A(envelope);
  const request = SendMessageRequest.fromJSON({
    message: {
      role: 'ROLE_USER', messageId: randomUUID(), extensions: [EXTENSION_URI],
      parts: [{ data: mapped.data, mediaType: TASK_MEDIA_TYPE }],
      metadata: { [EXTENSION_URI]: mapped.metadata },
    },
  });
  const options = {
    serviceParameters: ServiceParameters.create(...(activateExtension ? [withA2AExtensions(EXTENSION_URI)] : [])),
  };
  const result = {
    sdk: `@a2a-js/sdk ${SDK_VERSION}`, binding: client.transport.protocolName, streaming,
    a2a_message_id: request.message.messageId, agent: card.name,
  };
  const states = [];
  let task;
  try {
    if (streaming) {
      for await (const event of client.sendMessageStream(request, options)) {
        const payload = event.payload;
        if (payload?.$case === 'task') {
          task = payload.value;
          states.push(stateName(payload.value.status?.state));
        } else if (payload?.$case === 'statusUpdate') {
          states.push(stateName(payload.value.status?.state));
        }
      }
    } else {
      const response = await client.sendMessage(request, options);
      if ('status' in response) {
        task = response;
        states.push(stateName(response.status?.state));
      }
    }
    if (!task) throw new ProfileError('agent returned no task');
    // Authoritative final state, fetched by A2A task ID.
    task = await client.getTask({ tenant: '', id: task.id }, options);
  } catch (error) {
    if (error instanceof ProfileError) throw error;
    return { ...result, error: { type: error.constructor?.name ?? 'Error', message: error.message } };
  }
  const final = stateName(task.status?.state);
  Object.assign(result, {
    a2a_task_id: task.id, a2a_context_id: task.contextId, final_state: final, observed_states: states,
  });
  if (!task.contextId) throw new ProfileError('task has no server-generated contextId');
  if (task.status?.state === TaskState.TASK_STATE_COMPLETED) {
    const artifacts = task.artifacts.filter((artifact) => artifact.name === RECEIPT_ARTIFACT_NAME);
    if (artifacts.length !== 1 || artifacts[0].parts.length !== 1) throw new ProfileError('expected exactly one receipt artifact');
    const [artifact] = artifacts;
    const part = artifact.parts[0];
    if (part.content?.$case !== 'data') throw new ProfileError('receipt part is not a data part');
    result.receipt = verifyReceipt(envelope, part.content.value, artifact.metadata?.[EXTENSION_URI]);
    result.receipt_media_type = part.mediaType;
    result.a2a_artifact_id = artifact.artifactId;
  }
  return result;
}

function parseArgs(argv) {
  const options = { binding: 'JSONRPC', streaming: true, activateExtension: true };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--url') options.url = argv[++i];
    else if (arg === '--envelope') options.envelope = argv[++i];
    else if (arg === '--binding') options.binding = argv[++i];
    else if (arg === '--no-stream') options.streaming = false;
    else if (arg === '--no-extension') options.activateExtension = false;
    else throw new Error(`unknown argument: ${arg}`);
  }
  if (!options.url || !options.envelope || !BINDINGS.has(options.binding)) {
    throw new Error('usage: handoff.mjs --url URL --envelope FILE|- [--binding JSONRPC|HTTP+JSON] [--no-stream] [--no-extension]');
  }
  return options;
}

async function main() {
  let options;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exit(2);
  }
  const envelope = JSON.parse(readFileSync(options.envelope === '-' ? 0 : options.envelope, 'utf8'));
  let result;
  try {
    result = await delegate(options.url, envelope, options);
  } catch (error) {
    if (!(error instanceof ProfileError)) throw error;
    result = { error: { type: 'ProfileError', message: error.message } };
  }
  process.stdout.write(`${JSON.stringify(result)}\n`);
  process.exitCode = result.final_state === 'TASK_STATE_COMPLETED' && result.receipt ? 0 : 3;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
