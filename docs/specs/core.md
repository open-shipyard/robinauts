# Robinauts — Core Spec

Robinauts is a conversational agents platform: a web UI, a backend and a set
of libraries that a company runs on its own servers.

## Goals

### 1. Open source without restrictions

- Everything is Apache-2.0: the platform, the tools and the libraries.
- It is safe to run as an internal corporate platform and safe to embed in a
  commercial product. No component adds a restriction to either use.
- Every dependency is scanned, transitively, against a licence allowlist. A
  dependency that fails the scan breaks the build.

### 2. Secure and corporate-ready

- Security is a primary design constraint, not a later hardening pass.
- Sign-in is through the company's identity provider (Okta, Google).
- The platform fits how a company operates software: access control, supply
  chain hygiene, and a deployment an internal platform team can own.

### 3. Data stays on the hosting company's servers

- Conversations, history, memories and all other stored data live only in the
  hosted environment.
- The platform sends nothing to the Robinauts project or to any third party:
  no telemetry, no CDN, no hosted service it depends on.
- The only data that leaves is what a conversation sends to the model
  providers the operator has configured (goal 5).

### 4. Compose over build

- Select the best existing component for each part. Build only the glue and
  the parts that are missing.
- Components talk to each other through open, vendor-neutral standards:
  MCP, A2A and the emerging AG-UI.
- As a result the platform is extensible and its components are swappable.

### 5. Bring your own API key

- The operator supplies their own model provider credentials.
- The platform works well with any major vendor: OpenAI, Anthropic, Gemini,
  OpenRouter, AWS Bedrock.
- No vendor is privileged; switching or mixing providers is ordinary use.

### 6. Minimal deployment footprint

- One frontend (the UI), one backend, one database. Nothing else is required
  to run the platform.

### 7. Usage reporting

- The platform tracks token usage per model and per conversation.
- An API exports the usage records, so a company can feed them into its own
  reporting or cost tooling.

## Design principles and technical specs

### Stack

- The backend is Python.
- The frontend, in this first version, is built on the open source
  [assistant-ui](https://github.com/assistant-ui/assistant-ui) library, on
  Tailwind CSS. It sits behind an explicit seam so that it can be discarded:
  see [ADR 0001](../adr/0001-chat-ui-assistant-ui-with-tailwind.md).
- One frontend, one backend, one database (goal 6).

### Dependency scanning from day zero

- Security scans and licence scans of dependencies exist from the first
  commit, for both the Python and the JavaScript side. They are not added
  later.
- Both are blocking checks: a vulnerable or disallowed dependency fails the
  build (goal 1).

### Hexagonal architecture

- The backend follows hexagonal architecture (ports and adapters).
- The core holds the application logic and depends on nothing outside
  itself. Everything external — the database, the model providers, the agent
  framework, the HTTP layer — is reached through a port and implemented by an
  adapter.
- A port is a Python abstract base class (`abc.ABC`).

### The agent engine is a port

- The controller — the main application flow — is independent of any agent
  framework. It knows only the agent port.
- There are two implementations of the agent port:
  - one on LangGraph, or LangChain. Only their open source parts are used;
    none of their commercial or hosted offerings.
  - one on Pydantic AI.
- The two are swappable at any time: by configuration, with no change to the
  controller and no change to stored data.

### Persistence is framework-neutral and vendor-neutral

- Conversations are persisted in the database, in a format the platform
  owns. The format is not the format of any agent framework or any model
  vendor.
- Any conversation can be continued with any framework and any vendor. A
  conversation started on LangGraph with one vendor can take its next turn
  on Pydantic AI with another.
- It follows that a framework's own persistence (checkpointers, message
  stores, memory) is never the source of truth. An adapter translates
  between the platform's format and its framework's format on each turn.

### Tool usage

- The first version has no tool usage.
- Tool usage is planned. The agent port and the persisted conversation
  format are designed so that tool calls and tool results can be added
  without breaking them.
