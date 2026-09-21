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

## The agent port

- The controller knows one port, `Agent`: given a history and a new user
  message, **stream the engine's own events** — an answer has begun, more of
  its text, more of its thinking, the answer is complete and here are its
  parts — with the tokens they cost, and end either "finished" or "waiting on
  these tool calls" ([runs.md](runs.md)).
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
  This version shows it and stores none of it
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
  other ([layout.md](../layout.md)). **The discard test:** deleting either
  adapter and its dependencies breaks one line, the one in the composition
  root that constructs it.
- Both must pass one shared contract suite. It includes the swap: a
  conversation started on one engine continues on the other.

## A turn

Both engines are stateless per turn
([ADR 0002](../adr/0002-conversation-persistence.md)). A turn executes as a
**run** ([runs.md](runs.md)): a record in the database, executed in the
background, independent of the request that started it. The controller
runs every turn the same way:

1. Load the conversation's messages from the database.
2. Call the agent port with the history and the new user message; publish
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
  environment says. The adapter sets this explicitly.

## Tools

- The first version has no tool usage. It is planned, over MCP. The port,
  the conversation format and the wire leave room for tool calls and
  results, and runs are designed for tools of any duration
  ([runs.md](runs.md)).

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
- A sketch of the configuration:

```toml
[providers.anthropic]
kind = "anthropic"
api_key_env = "ROBINAUTS_ANTHROPIC_KEY"

[providers.openrouter]
kind = "openai-compatible"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "ROBINAUTS_OPENROUTER_KEY"

[models.sonnet]
provider = "anthropic"
name = "claude-sonnet-5"

[agents.assistant]
title = "Assistant"
model = "sonnet"
engine = "pydantic-ai"        # or "langgraph"
system_prompt = "..."
```

## Known findings

- `langgraph-checkpoint-postgres` depends on `psycopg`, which is
  LGPL-3.0-only. It cannot be adopted as it is (ADR 0002). The LangGraph
  core is not affected.
