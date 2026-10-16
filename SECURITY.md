# Security policy

## Scope

Agent Movement is a **research prototype**. The Python package in `src/agent_movement` contains synthetic, local experiments: a loopback task handoff with simulated-effect fencing, an optional A2A v1 adapter, authenticated peer handoff, same-runtime LangGraph checkpoint relocation, signed movement receipts and the MobilityBench harness. It runs on synthetic data only. It is **not production software**, has no releases, and is not meant to be deployed on a network or exposed to untrusted traffic (see the [README](README.md) and [local implementation notes](docs/local-implementation.md)).

Reports are still welcome, because the prototypes are used as evidence in the research documents. In scope:

- code in `src/agent_movement/` that fails to enforce a property it claims to enforce, for example a forged or tampered movement receipt that the verifier accepts, a peer-authentication or grant check that can be bypassed, or a stale epoch that the fencing check accepts;
- the corpus and benchmark tools in `tools/` (for example unsafe file handling);
- the GitHub Actions workflows in `.github/workflows/`;
- any real secret, credential or personal data that was committed to this repository by mistake.

Out of scope:

- running the prototypes on a public network or behind a proxy, which the documentation already says not to do;
- behaviour that is already documented as a limitation or known gap, for example the unauthenticated A2A adapter ([docs/a2a-adapter.md](docs/a2a-adapter.md)) or the MobilityBench checks marked as known gaps;
- vulnerabilities in upstream projects such as `a2a-sdk`, LangGraph or `cryptography`. Report those to the upstream project;
- factual errors in the research documents and threat models. Report those with the **Research claim correction** issue form instead.

## Supported versions

There are no releases. Only the latest commit on `main` is supported.

## Reporting a vulnerability

Do **not** open a public issue, pull request or discussion for a vulnerability.

Report it privately through GitHub's private vulnerability reporting: open
**<https://github.com/MSKazemi/agent-movement/security/advisories/new>**
(or the **Security** tab → **Report a vulnerability**).

Please include:

- the commit SHA you tested;
- the affected file, module or command;
- reproduction steps that use synthetic data only;
- the expected and the observed behaviour, and the impact you see;
- your Python version and the optional extras you installed (`a2a`, `ed25519`, `relocation`, `signing`).

## What not to include

- **No real secrets.** Never put real API keys, tokens, passwords, private keys, signing keys or cookies in a report, a reproduction or a test fixture. Use clearly fake placeholder values, or keys you generated only for the test.
- No personal data, private conversations or confidential task payloads.
- If you found a real secret committed to this repository, give its path and commit SHA, but do not copy the value into the report.

Test only against a local copy of the code that you run yourself. Do not probe systems or accounts that belong to anyone else.

## What happens next

This is a research project with a single maintainer, so handling is best effort and there is no guaranteed response time. Confirmed issues are fixed on `main`. Where it helps users of the code, the fix is described in a GitHub Security Advisory, and reporters are credited unless they ask not to be.
