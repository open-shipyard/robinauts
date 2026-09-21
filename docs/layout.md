# Robinauts — project layout and architecture

Status: draft v1. Goals and design principles are in
[specs/core.md](specs/core.md); decisions are in [adr/](adr/).

The backend follows a variation of hexagonal architecture. The package is
split into layers with strict, one-directional dependencies. The rules are
enforced mechanically from the first scaffold (see section 5).

## 1. Directory tree

```
robinauts/
  docs/
  frontend/                   # the UI (ADR 0001)
  backend/
    pyproject.toml
    main.py                   # infrastructure: script wrapper
    src/robinauts/
      __init__.py
      app.py                  # infrastructure: composition root, exposes create_app()
      cli.py                  # infrastructure: argument parsing, the `robinauts` console script
      domain/                 # dataclasses, enums, constants, exceptions
      core/                   # pure functions, no IO
      ports/                  # ABCs the application depends on
      application/            # control flow and business rules
      api/                    # inbound HTTP: translates requests into application calls
      adapters/               # communication with the external world
        agents/
          langgraph/          # the ONLY place LangGraph / LangChain are imported
          pydantic_ai/        # the ONLY place Pydantic AI is imported
      datastore/              # adapters for owned state (the database)
    tests/
```

The package lives under `src/` so that the root-level `main.py` never
shadows it. `main.py` is a minimal `if __name__ == "__main__"` wrapper
around `robinauts.cli.run()`.

## 2. Layers

### domain

Shared vocabulary. Dataclasses, enums, constants and exceptions: the
platform's own conversation format (`Conversation`, `Message`, message
parts, `Role`), `TurnEvent` (what a running turn streams), `UsageRecord`,
`Principal`, `RobinautsError` and friends.

The conversation format is the one ADR 0002 refers to: owned by the
platform, not shaped by any agent framework or model vendor.

Minimal logic is accepted with caution (validation in `__post_init__`,
simple derived properties). Anything more belongs in core.

Depends on nothing inside robinauts. Everything may depend on it.

### core

Pure functions. No IO, no clock, no randomness, no global state. Every
function is testable with input and output alone.

Complicated logic must live here: validating a conversation, trimming or
summarising-selection of a history to fit a context window, aggregating
usage records, matching an identity against the sign-in allow list,
checking ID token claims (with `now` passed in), config validation from raw
dicts into domain objects.

Depends on domain only.

### ports

Abstract base classes describing what the application needs from the
outside world. Version 1 ports, to be refined as the specs grow:

- `Agent`: run one turn — given a history and a new user message, stream
  `TurnEvent`s and return the new messages and their token usage.
  Implementations: LangGraph and Pydantic AI.
- `ConversationStore`: read and append conversations and messages.
- `UsageStore`: record and query token usage per model and conversation.
- `CredentialStore`: sessions, pending sign-ins, API tokens.
- `IdentityProvider`: the OIDC exchange with a sign-in provider.
- `ConfigSource`: load configuration as domain objects.
- `Clock`: current time.

Depends on domain only.

### application

Control flow and business rules. Orchestrates a turn exactly as ADR 0002
describes it: load the history, call the agent port, stream, append the new
messages, record usage. Also the sign-in flow, conversation management
(list, rename, delete) and usage export.

This is the "controller" of the core spec: it knows the `Agent` port and
nothing about any agent framework.

Stateful only through the store ports. Receives all port implementations
by injection; never constructs them.

Depends on ports, core and domain.

### api

The inbound side: HTTP routes and the streaming endpoint the UI talks to.
It translates requests into application calls and application results into
responses. It decides nothing.

fetchy, where this convention comes from, is a command-line tool and has no
such layer; a server needs one. It is kept apart from `adapters` because it
points the other way: it calls the application, where an adapter is called
by it.

Depends on application and domain. Must not reference core, ports,
adapters or datastore.

### adapters

Communication with the external world: the two agent engines, the OIDC
client, the config reader.

Each agent adapter translates between the platform's conversation format
and its framework's format, in both directions, on every turn (ADR 0002).
The frameworks are confined to their own sub-package:

- only `adapters/agents/langgraph/` may import `langgraph`, `langchain` or
  `langchain_core`;
- only `adapters/agents/pydantic_ai/` may import `pydantic_ai`;
- the two do not import each other.

This is the backend's counterpart of the frontend seam in ADR 0001.
**The discard test:** deleting either sub-package and its dependencies must
leave exactly one thing broken — the line in `app.py` that constructs it.

Depends on ports and domain. Must not reference core, datastore,
application or api.

### datastore

A special case of adapter for owned state: where application state lives.
It implements the store ports (`ConversationStore`, `UsageStore`,
`CredentialStore`) over the one database of the deployment. Its schema is
entirely the platform's; no framework creates or migrates tables in it
(ADR 0002).

Same dependency rules as adapters: ports and domain only.

### infrastructure

`src/robinauts/app.py`, `src/robinauts/cli.py` and `main.py`. Builds the
concrete adapters and datastore, injects them into the application, mounts
the api, and exposes `create_app()`. This is the only place that references
adapters, datastore, application and api together — and therefore the only
place where the choice of agent engine is made. `cli.py` is also installed
as the `robinauts` console script.

## 3. Dependency matrix

Rows may import columns marked ✓.

| from \ to        | domain | core | ports | application | api | adapters | datastore |
|------------------|:------:|:----:|:-----:|:-----------:|:---:|:--------:|:---------:|
| domain           |   –    |      |       |             |     |          |           |
| core             |   ✓    |  –   |       |             |     |          |           |
| ports            |   ✓    |      |   –   |             |     |          |           |
| application      |   ✓    |  ✓   |   ✓   |      –      |     |          |           |
| api              |   ✓    |      |       |      ✓      |  –  |          |           |
| adapters         |   ✓    |      |   ✓   |             |     |    –     |           |
| datastore        |   ✓    |      |   ✓   |             |     |          |     –     |
| infrastructure   |   ✓    |  ✓   |   ✓   |      ✓      |  ✓  |    ✓     |     ✓     |

Third-party libraries: domain and core use the standard library plus pure
parsing or validation libraries where needed, as long as the function stays
free of IO. The web framework (FastAPI) and `ag-ui-protocol`
are confined to api and infrastructure. The database driver
(`asyncpg`) is confined to datastore. Agent frameworks are confined to
their adapter sub-package. HTTP clients are confined to adapters.

## 4. Responsibilities by concern

| concern | layer |
|---|---|
| the platform's conversation format | domain |
| fitting a history into a context window | core, called by application |
| the turn lifecycle (ADR 0002) | application |
| platform format <-> framework format | adapters (each agent adapter) |
| talking to model providers, API keys in use | adapters (agent adapters) |
| conversations, messages, usage, sessions at rest | datastore |
| token usage per model and conversation | application records, datastore stores, core aggregates |
| allow-list matching, ID token claim checks | core, with `now` from the clock port |
| OIDC discovery and code exchange | adapters (identity provider) |
| cookies, CSRF checks, request parsing, streaming responses | api |
| config reading, validation into domain | adapters read, core validates |
| wiring, injection, choice of agent engine | infrastructure |

## 5. Enforcement

The dependency matrix is enforced with
[import-linter](https://import-linter.readthedocs.io/) contracts declared
in `backend/pyproject.toml` and run in the test suite
(`tests/unit/test_architecture.py`) from the first scaffold. Contracts
cover:

- domain imports nothing from robinauts
- core imports only domain
- ports import only domain
- application imports only ports, core, domain
- api imports only application and domain
- adapters and datastore import only ports and domain
- nothing except infrastructure imports adapters, datastore or api
- LangGraph and LangChain are imported only under
  `adapters/agents/langgraph`
- Pydantic AI is imported only under `adapters/agents/pydantic_ai`
- the two agent adapters do not import each other

## 6. Testing strategy

- **core and domain**: plain unit tests, input and output only.
- **application**: unit tests with in-memory fakes for every port (fake
  agent, fake clock, fake stores, fake identity provider). This is where
  the turn lifecycle, sign-in rules and usage recording are proven.
- **agent adapters**: one shared contract suite that both implementations
  must pass, run against recorded or stubbed model responses. It includes
  the swap: a conversation started on one adapter continues on the other.
  Live-provider tests, if any, are opt-in.
- **datastore**: the store contract suites against a real database.
- **api**: route tests over the application wired with fakes.
- **infrastructure**: one smoke test that wires everything and runs a turn
  end to end against a stubbed model.

Tests that touch the network, the file system, a database or a local
server carry the `io` marker.

## 7. Conventions

- Python 3.12, `pyproject.toml`, src layout, pytest, ruff, black, line
  length 100.
- Ports are ABCs; fakes for tests live under `tests/` and implement the
  same ABCs.
- Every source file starts with the licence header:
  `# SPDX-License-Identifier: Apache-2.0` and
  `# Copyright The Robinauts Authors`.
