# Agents, engines and models

## Agents

- The operator defines named **agents** in the configuration: a name, a
  system prompt, a model, and the engine that runs it.
- A user chooses an agent when starting a conversation.
- Users do not create agents. That is planned.
- The engine is a property of the agent. Both engines run side by side in
  one deployment. Changing an agent's engine or model takes effect at the
  next turn of its existing conversations — which is the swap the
  persistence design guarantees.
- **In this version that means the next turn after a restart.** The
  configuration is read once, at start-up, and the definitions are handed to
  the controller then; a turn looks its agent up afresh, so nothing but a
  reload of the configuration stands between this and the sentence above, and
  a reload is not built. Known limit of the first version, not of the design.

## The agent port

- The controller knows one port, `Agent`: given the agent's definition and a
  history, **stream the engine's own events** — an answer has begun, more of
  its text, more of its thinking, the answer is complete and here are its
  parts — and end either "finished" or "waiting on these tool calls"
  ([runs.md](runs.md)). **No usage**: what a turn cost is reported in the
  platform's own terms when usage reporting is built, and until then an
  engine's events carry none and no field is written for one.
- **The history is a path of the conversation ending in the user message being
  answered**, already trimmed to what the model will take, and the system
  prompt is the agent's and is not one of the messages. So there is no second
  argument for "the new message": the message to answer is the last of the
  history, which is also what a resumed turn and a regenerated one look like,
  and an engine has one thing to translate rather than two.
- **An agent named by a request that this deployment does not have is not
  there**: it is refused exactly as an id that reaches nothing is refused, and
  so is a conversation bound to an agent the operator has since removed.
- Those events carry no ids, no times and no provenance, because an engine
  has none: it was given a history and a model. The application turns them
  into the platform's messages and its own turn events, which is where an id,
  a parent, a run and a row come from. An engine that had to invent one would
  be deciding something that is not its to decide.
- Both engines are held to the order of their events by the shared contract
  suite: an answer is announced, then streamed, then completed, one at a
  time.
- **Streaming is optional; what is streamed is what is kept.** An engine
  that yields no text delta for an answer may complete it with any text —
  not every provider streams. An engine that yields any must complete with
  exactly what it streamed: what a person watched arrive is what is stored,
  so an engine whose framework rewrites the final message builds its parts
  from what it streamed, or does not stream at all.
- An engine may stream reasoning, and may return it with a finished answer.
  This version shows it, keeps it in the run's events so that a watcher can
  re-attach, and puts none of it in a message
  ([conversations.md](conversations.md)).
- **A turn produces at least one answer.** A turn that ends without one is
  a failed run ([runs.md](runs.md)), not a finished turn with nothing in
  it.
- **An engine reports a failure by raising.** Any exception ends the turn;
  the application records the run `failed` with a description of it and
  leaves the answer that was in flight uncompleted. An engine never yields
  anything after an error.
- **A cancellation is the application cancelling the engine's task.** An
  engine must not swallow `CancelledError`: it lets it through and releases
  what it holds — an HTTP response, a client, a file. What was produced
  before the cancellation stays ([runs.md](runs.md)).
- Two implementations:
  - **LangGraph** (or LangChain). Open source parts only: no LangSmith, no
    LangGraph Platform.
  - **Pydantic AI.**
- Each is confined to its own adapter sub-package, and that is enforced:
  no other code imports the framework, and the two do not import each
  other ([layout.md](../layout.md)). **The discard test:** five places name an
  adapter, and deleting it and its dependencies breaks those and nothing else
  — the import in the composition root and its one entry in the table of
  engines, the import contracts' exceptions for the sub-package, the
  sub-package's own tests, and the shared **swap fixtures**, which exist to
  name both engines at once and cannot be written without both. The
  composition tests fail too, and name no adapter: they say that both engines
  are wired, which is a claim about the table.
- Both must pass one shared contract suite. It includes the swap: a
  conversation started on one engine continues on the other.

## A turn

Both engines are stateless per turn
([ADR 0002](../adr/0002-conversation-persistence.md)). A turn executes as a
**run** ([runs.md](runs.md)): a record in the database, executed in the
background, independent of the request that started it. The controller
runs every turn the same way:

1. Load the conversation's messages from the database, and take the path
   down to the message being answered.
2. Call the agent port with the agent and that history, trimmed; publish
   the events, which the UI watches ([wire.md](wire.md)).
3. Translate each new message into the platform's format and append it to
   the conversation as it is produced.
4. The next turn starts again from step 1, with whichever engine and
   vendor the agent has at that moment.

- The LangGraph engine compiles its graph without a checkpointer; the
  Pydantic AI engine passes `message_history`. Neither remembers anything
  between turns.
- Anything that must behave the same under both engines lives above the
  port. Fitting a long history into a context window is the first example.
- No framework persistence is used. Whether to use one for the state of a
  run is not decided and not planned (ADR 0002).

## Model providers

- Goal 5: OpenAI, Anthropic, Gemini, OpenRouter, AWS Bedrock; no vendor
  privileged.
- Keys are the operator's. The configuration gives the *name* of an
  environment variable per provider (for Bedrock, the standard AWS
  credential chain). Keys are read at start-up, never stored in the
  database, never logged, never sent to the browser. Users do not supply
  keys.
- The operator declares providers and models; agents refer to a model by
  the platform's own id for it. The configuration is the platform's, not
  either framework's.
- Both engines report tokens in the platform's terms — input, output,
  model — taken from the provider's response.
- **Nothing phones home.** The engines never enable a framework's hosted
  tracing: LangSmith and Pydantic Logfire stay off whatever the
  environment says. The adapter sets this explicitly, and where a framework
  reads a variable that a switch cannot reach — LangChain's version 1
  tracer, which raises when it is asked for and version 2 is off — the
  adapter unsets the variable rather than leaving a turn to fail over it.
- **And nothing is written down.** A log of this platform never carries the
  content of a conversation. A vendor SDK's own debug logging does, and is
  switched on by an environment variable it reads when it is *imported*, so an
  adapter that only removed the variable would be too late: the adapter pins
  the vendor loggers that write request bodies — the one that emits the record
  as well as its parent, since a level set on a child is what a logger decides
  by — at a level where no request is ever a record, and removes the variable
  as well so that a subprocess does not start again from the beginning. Each
  logger's **own** level is set and not merely its effective one, or an
  operator turning their root logger up afterwards would turn the vendor's
  logging on with it. What this does not do is fight a logger an operator
  names at debug in their own configuration after start-up: that is their
  deliberate act on their own machine.
- **A vendor's endpoint is not taken from the environment either.** Every
  client is built with the endpoint it is to use: the one the operator
  configured (`base_url`, for an `openai-compatible` provider) or the
  vendor's own, named as a constant in the adapter. Left to the client,
  `ANTHROPIC_BASE_URL` and its equivalents would send a turn — and the
  operator's key — to whatever host a stale export named. For the same
  reason the key is always passed and never left to a client's
  `*_API_KEY` fallback, and a vendor-specific proxy variable is pinned off;
  an operator's proxy is `HTTPS_PROXY`, which every outbound call of the
  process obeys.

## Tools

- The first version has no tool usage. It is planned, over MCP. The port,
  the conversation format and the wire leave room for tool calls and
  results, and runs are designed for tools of any duration
  ([runs.md](runs.md)).
- Until then, a model that **asks** to use a tool fails the turn: an engine
  raises rather than passing the call over. Everything after the call would
  belong to an answer that cannot be produced, so a turn that carried on
  would store half an answer that looks whole.

## Details likely to change

- Each engine reaches the providers through its own framework's clients:
  - LangGraph: `langchain-openai`, `langchain-anthropic`,
    `langchain-google-genai`, `langchain-aws`;
  - Pydantic AI: `pydantic-ai-slim` with the provider extras needed, not
    the all-inclusive `pydantic-ai`.
  - OpenRouter, and any self-hosted OpenAI-compatible endpoint, go through
    the OpenAI-compatible client with a base URL.
- Every one of these packages passes the licence and vulnerability gates
  at its pinned version, with its transitive tree
  ([open-source.md](open-source.md)). A provider whose client fails is not
  offered by that engine until it passes.
- Not every model has to exist under both engines, but an agent's engine
  can be swapped only if its model does.
- A sketch of the configuration. It is written in the **same file** as
  sign-in ([sign-in.md](sign-in.md)), which is why the model providers are
  `[model_providers.*]` and not `[providers.*]`: that name is already the
  identity providers people sign in with, and one file cannot have a table
  that means one of them here and the other there. `timeout_seconds` (per
  model call) and `max_output_tokens` are optional; what they default to is
  the platform's and the engine's business respectively.

```toml
[model_providers.anthropic]
kind = "anthropic"
api_key_env = "ROBINAUTS_ANTHROPIC_KEY"

[models.sonnet]
provider = "anthropic"
name = "claude-sonnet-5"
timeout_seconds = 120
max_output_tokens = 8192

[agents.assistant]
title = "Assistant"
model = "sonnet"
engine = "langgraph"
system_prompt = "Play fair."
```

  The other two kinds are written the same way. **This build refuses them**
  at start-up, naming the provider, because the client that reaches them
  does not pass the dependency policy (see "Known findings" below); the
  shape is settled all the same, and `base_url` belongs to
  `openai-compatible` and to nothing else:

```toml
[model_providers.openrouter]
kind = "openai-compatible"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "ROBINAUTS_OPENROUTER_KEY"
```

## Known findings

- `langgraph-checkpoint-postgres` depends on `psycopg`, which is
  LGPL-3.0-only. It cannot be adopted as it is (ADR 0002). The LangGraph
  core is not affected.
- `langchain-openai` requires `tiktoken`, which states its licence as the
  licence *text* and no identifier, and which in turn requires `regex`,
  `Apache-2.0 AND CNRI-Python`. Neither resolves under the policy, so the
  client is not adopted and the LangGraph engine offers **Anthropic alone**
  for now: OpenAI, OpenRouter and every other OpenAI-compatible endpoint
  wait for a tree that passes ([DEPENDENCIES.md](../../DEPENDENCIES.md),
  "Known exclusions"). The configuration still names the three kinds — the
  vocabulary is the platform's — and a deployment asking for a kind this
  build cannot reach is refused at start-up, saying so.
- The same tree keeps the same kinds out of the **Pydantic AI** engine:
  `pydantic-ai-slim[openai]` requires `tiktoken` too. So both engines offer
  Anthropic alone, and the swap holds for every model either of them has.
- `langsmith` is a hard dependency of `langchain-core`, and the LangGraph
  adapter imports it for **one call**: `langsmith.configure(enabled=False)`,
  made when the engine is constructed, which is the switch langchain-core
  itself consults before the environment. Nothing else in the platform uses
  it, nothing is sent to it, no tracer is ever attached and no client is
  ever built. Because it is imported rather than merely installed, it is a
  direct dependency and is pinned as one.
- **`ANTHROPIC_LOG`**: the Anthropic SDK — which both engines reach the vendor
  through — reads it at import and, on `debug`, writes every request's options
  to standard error, `json_data` included: the system prompt and every message
  of the conversation. Both adapters answer it the same way, in the two halves
  it needs (above): the SDK's loggers are pinned when the engine is built, and
  the variable is removed.
- `logfire-api` arrives with `pydantic-graph`, and `opentelemetry-api` with
  `pydantic-ai-slim`. Neither is imported anywhere in the platform, and both
  are named in the import rule all the same
  ([layout.md](../layout.md)). Pydantic AI has **no environment switch** for
  tracing — it instruments a run only when an agent's `instrument` says so,
  which `logfire.instrument_pydantic_ai()` sets process-wide — so the adapter
  turns it off per agent, where the answer beats the process-wide one, and
  unsets no variable because there is none to unset. It does set the
  framework's `BANNER_ENABLED` to `False`: on its first turn Pydantic AI
  otherwise writes an advertisement for its hosted observability to standard
  error, which is not a thing a server's log is for. One part of this is the
  lock's rather than the code's: `pydantic-graph` opens spans through
  `logfire_api`, which is a no-op shim that **replaces itself with the real
  `logfire`** the moment that package is importable — outside anything the
  per-agent switch reaches. So `logfire` not being in the locked set is part
  of the guarantee, and a test asserts it.
