# The frameworks own the loop: progress

The plan is [framework-loop-plan.md](framework-loop-plan.md). The codebase
map is "What exists" in [poc-progress.md](poc-progress.md),
[model-selection-progress.md](model-selection-progress.md) and
[mcp-progress.md](mcp-progress.md); this file records what this change
made of it, and what it took away. Built on `claude/modest-newton-69yxl6`
from the head of the MCP work, 2026-09-30, in one commit rather than the
one-per-step the plan asked for: the steps were built in the plan's order
and the suite was green at the end of each, but the deletions of step 7
were what let steps 2 to 6 collect and import, so the branch was not
committable in between. Rebased the same day onto `main`, which had taken
the MCP work re-signed and, after it, the OpenAI kinds ("Rebased onto
main", below).

## What exists

- **ADR 0005**: the framework owns the loop, the context and the model's
  memory; the platform keeps the transcript. Supersedes ADR 0004 and the
  rest of ADR 0002's decision (the record is still the platform's; the
  frameworks are no longer stateless per turn; a conversation stays with
  its engine). The specs say it as behaviour: `core.md` ("The agent engine
  is a port", "The transcript is the platform's; the memory is the
  framework's", the one-page), `agents.md` (rewritten: the port, a turn,
  tools, the sketch with `context_window` and without `prefix`, the known
  findings), `runs.md` ("Tools", the run's memory, the order of a run's
  events with a call's arguments in one piece), `conversations.md` (the
  format is the transcript; the memory; the signed blocks live in the
  memory; what crosses a change of engine or model), `wire.md`,
  `operations.md`, `backend.md`, `layout.md` (the port, the adapters
  section, the import rules, the responsibilities table, the discard test,
  the testing strategy).
- **The port** (`ports/agents.py`): `Agent.stream(agent, prompt, *, model,
  state) -> AsyncGenerator[Event, None]`, the examples' `AgentBackend` made
  async and stateless per call. **The events** (`domain/events.py`):
  `TextDelta`, `ReasoningDelta`, `ToolCall(call_id, name, arguments)`,
  `ToolResult(call_id, name, output, is_error)` and `Done(text, state)`,
  the state bytes bounded by `MAX_ENGINE_STATE_BYTES` (64 MiB).
  `core.check_backend_events(events, cut_short=)` holds an adapter to the
  order: text and reasoning before `Done`, a result answers a call announced
  before it once and under its name, `Done` last and once with every call
  answered. The eight engine events of `domain/turn.py` are gone; the
  platform's published pieces are `TextPiece`, `ReasoningPiece` and
  `ArgumentsPiece` (their written form unchanged, so nothing stored moved).
- **The memory on the run** (`runs.engine_state bytea`;
  `ConversationStore.end_run(..., engine_state=)` and
  `engine_state(run_id)`; the schema pin re-recorded, version still 1).
  The application (`application/turns.py`, `_memory`) resumes a turn from
  the nearest finished run of the same engine on the visible path above
  the question, so a fork of the transcript is a fork of the memory; a
  state written by another engine is not read (a line in the log, the turn
  begins from nothing); a run that did not finish stores none.
- **The application's round** (`Turns._round`): one stream per turn. A
  `TextDelta`, `ReasoningDelta` or `ToolCall` with no answer open opens
  one; a call is published as `CallStarted`, one `ArgumentsPiece` holding
  the JSON whole, and `CallCompleted`; the first `ToolResult` completes the
  answer with its calls and opens the tool message under it, each result
  is a `ResultLanded`, and the tool message completes when every call has
  its result (`check_answers_calls`); `Done` completes what is open — the
  streamed text wins over `Done.text`, which is the answer only when
  nothing was streamed — and ends the turn with the state. A turn that
  ends without an answer, or stops with an answer open or a call
  unanswered, is a failed run as before (`NO_ANSWER`, `UNFINISHED_ANSWER`).
  A `Done` arriving with calls announced and none answered is refused
  ("a turn ends with every call it announced answered"; found by the
  lifecycle tests). The loop, `_tools_for`, `_answered`, `_called`, the
  rounds bound and its failures, `NO_SUCH_TOOL`, `tool_servers`,
  `max_tool_rounds` are gone.
- **The LangChain adapter** (`adapters/agents/langgraph/engine.py`, 1174
  lines, was 1345 on `main`): `create_agent(chat, tools, system_prompt, middleware)`
  over the tools `langchain-mcp-adapters` lists for the agent's servers
  (`MultiServerMCPClient`, Streamable HTTP, `tool_name_prefix=True`,
  `handle_tool_errors=True`; the credential from
  `adapters.credential_header`), the history read from the state plus the
  question, `astream` with `messages`, `updates` and `values`: text and
  reasoning off the model node's chunks alone (the summarising middleware
  calls the model too), calls and results off the `model` and `tools`
  nodes' updates, the final state off the last values, written with
  `messages_to_dict`. Middleware: `SummarizationMiddleware` at
  `SUMMARIZE_AT` (0.8) of the window, keeping `KEEP_MESSAGES` (20), and
  `AnthropicPromptCachingMiddleware`. The window: `context_window`, then
  the profile's `max_input_tokens`, then `DEFAULT_CONTEXT_WINDOW` (200k).
  The bound: `RECURSION_LIMIT` from `MAX_TOOL_ROUNDS` (25) and
  `STEPS_PER_ROUND` (3: the summarising step, the model, the tools);
  `GraphRecursionError` fails the turn. A third middleware,
  `signed_blocks_only`, wraps every model call and drops the thinking
  blocks the vendor would refuse back -- a `thinking` block with no
  signature, which GPT through OpenRouter's Messages API sends -- from what
  is sent, for that call only; the memory keeps them (the fix `main`
  carried in its own replay, kept). Everything pinned before is pinned
  still: the endpoint, the key as an argument and a header, no retries, the
  loggers held, tracing off, the two v1 variables removed; and the OpenAI
  kinds are reached as `main` reaches them (`_openai_chat_model`: the two
  clients built here, every fallback an argument, the ceiling in the field
  the kind takes through `_ChatCompletions`).
- **The Pydantic AI adapter** (`adapters/agents/pydantic_ai/engine.py`,
  1184 lines, was 1476 on `main`): `Agent(model, name, instructions, toolsets,
  capabilities=[ProcessHistory(within(window))])` with one `MCPToolset`
  per server (`id`, the credential as headers, `init_timeout` and
  `read_timeout` from `timeout_seconds`, `tool_error_behavior="failed"`,
  `.prefixed(server.id)`), `instrument = False`; `run_stream_events(prompt,
  message_history, model_settings, usage_limits)`: text and thinking off
  the part events, a call off `FunctionToolCallEvent` with its arguments
  whole, a result off `FunctionToolResultEvent` (a failed return or a retry
  prompt is an error result), the state off the result's `all_messages()`
  through `ModelMessagesTypeAdapter`. The context: `within(window)` drops
  the oldest exchanges (a question and everything up to the next) while
  the rest measures over `TRIM_AT` (0.8) of the window at
  `CHARS_PER_TOKEN` (4), before every model call and on the memory handed
  back, never the latest exchange. The cache: `anthropic_cache_instructions`,
  `anthropic_cache_tool_definitions`, and `anthropic_cache` at the vendor
  or `anthropic_cache_messages` at a gateway. The bound:
  `UsageLimits(request_limit=REQUEST_LIMIT)`, `MAX_TOOL_ROUNDS + 1`;
  `UsageLimitExceeded` fails the turn. A model that answers with neither
  text nor a call is asked again by the framework once, then the turn
  fails — the framework's own retry, now wanted. The OpenAI kinds are
  reached as `main` reaches them (`_openai_model`, the client built here,
  the ceiling field through the profile), and of `main`'s stream class one
  thing is kept: a name sent again on every delta of a call is taken as the
  same name (`_ChatCompletionsStream`), so the framework runs the tool it
  has; the rest of it -- refusing an unnamed call, the thinking tags, the
  schema transformer -- is left to the framework.
- **Configuration**: `[models.*].context_window` (tokens, optional, at
  most `MAX_CONTEXT_WINDOW`); `[mcp_servers.*]` without `prefix`;
  `adapters.credential_header(server, secrets)` is the one spelling of
  `Bearer` / `Basic` / none for both frameworks' clients. The engines are
  built as `adapter(models, keys, tool_secrets)`; an agent handed in
  without its engine is checked against the configured servers. The
  import contracts allow `langchain_mcp_adapters` under the LangChain
  adapter, `fastmcp` under the Pydantic AI adapter, and `mcp` under both.
- **Gone**: the `ToolServers` port and its fake and contract; the MCP
  client of our own (`adapters/tools/`, 745 lines) and its unit and live
  tests; `core/tools.py` and the naming rules; `ToolDefinition`,
  `ListedTool`, the old `ToolResult`, `NO_RESULT`, `unanswered_calls`,
  `tools_for_request`, `NO_LONGER_OFFERED`, `ToolServerError`; the swap
  fixtures (`tests/engines.py`, `test_engine_swap.py`, the swap in
  `test_create_app.py`); the vendor's blocks in `extras` and everything
  that carried them.
- **Tests**: the contract suite (`tests/contracts/agents.py`) rewritten to
  the eight situations of the plan, subclassed by both adapters over their
  framework's own scripted model (a `BaseChatModel` with one response per
  call; a `FunctionModel` the same) and tools that are plain functions; the
  fake engine scripts the five events (`says`, `calls`, `results`, `Gate`,
  `Raise`); the lifecycle, watch, route, composition and store suites
  rewritten for the port and the memory. `main`'s tests of both engines
  over OpenAI's protocol (`tests/unit/test_engines_over_chat_completions.py`,
  over the scripted vendor of `tests/chat_completions.py`) are rewritten
  for the port: the kinds, the client, the request's endpoint and
  signature and ceiling, a streamed answer, a tool round the framework runs
  through the real OpenAI client, a refusal -- and not the byte-for-byte
  parity of the two engines' requests, which is no longer a claim. The
  live tests run on `main`'s shared `tests/live_turns.py`, ported. 3041
  tests pass.

## The numbers

Against `main` at 31398ca, after the rebase (`git diff --numstat
origin/main`, the new files counted):

| area | added | deleted | net |
|---|---:|---:|---:|
| `backend/src` | 1752 | 4043 | −2291 |
| `backend/tests` | 2515 | 6039 | −3524 |
| docs (this plan, this note and ADR 0005 among them), `DEPENDENCIES.md`, `demo`, `README.md` | 1159 | 536 | +623 |
| `uv.lock`, `pyproject.toml` | 749 | 18 | +731 |
| whole | 6175 | 10636 | **−4461** |

`application/turns.py` is 2219 lines, was 2390; the two adapters together
2358, were 2821; the MCP client's 745 are gone, and so are the swap fixtures
and the parity tests.

## The checks

- `scripts/check-lint.sh`: green. `scripts/check-tests.sh`: green, 3261
  passed and 6 skipped -- the live tests, which need a key -- with a
  PostgreSQL 16 given and required (`ROBINAUTS_REQUIRE_POSTGRES=1`). Without
  one the Postgres suite skips, and it did until CI ran it: the two tests
  of `tests/integration/test_postgres_run_executor.py` still scripted two
  answers in one turn, the old port's shape, and the first failed on
  `nothing follows the end of a turn`. Both were ported to a tool round,
  as their unit twin in `test_run_watch.py` had been.
  `scripts/check-reuse.sh`: green. `scripts/check-audit.sh`: green (109
  packages, no known vulnerability), all re-run on the restricted lock.
- `scripts/check-licences.sh`: **green**, on 110 locked packages. It was red
  on two, as the plan said it would be. `MIT-0`, `cffi`'s licence, joined
  the allowed list by the owner's decision (2026-09-30). The exception the
  owner asked for `pywin32` was not written: the 312 wheel, read for it,
  carries `adodbapi` under LGPL-2.1, which is forbidden and which no
  exception covers. The owner chose the platforms instead: the lock is
  resolved for Linux and macOS only (`[tool.uv] environments`), which took
  `pywin32`, `pywin32-ctypes`, `colorama` and `httpx2-jsfetch` out of it and
  the `colorama` row out of the development-only table; Windows is not a
  target ([DEPENDENCIES.md](../../DEPENDENCIES.md), "Known exclusions";
  [deployment.md](../deployment.md)). Everything else the new tree brings
  passes, `tiktoken` and `regex` included, which `main` settled.
- `scripts/check-dco.sh`: red until the taker-over signs the commit, as
  with the MCP branch: the recipe is in [mcp-progress.md](mcp-progress.md)
  ("Where it stands").
- The npm licence gate (`node scripts/check-licences.mjs`, the first step of
  `scripts/check-frontend.sh`) and its tests (`src/test/licence-gate.test.ts`):
  green, run because the `MIT-0` decision took two rows out of the
  JavaScript table, which that gate would otherwise fail as rows nobody
  needs. The script itself did not run here: this machine has node 22, and
  `frontend/.nvmrc` asks for 24.
- Not run here: the wheel gate (no change on the wire), and the live tests
  (`tests/live/`, which need a key; they are on the port and collect).

## Rebased onto main

`main` took the MCP work re-signed -- the same trees under new commits --
and after it the demo script, the licence list (CNRI-Python allowed,
`tiktoken` excepted), the OpenAI client dependencies, **the `openai` and
`openai-compatible` kinds in both engines**, README updates, and a fix that
keeps and replays only the thinking blocks the vendor takes back. The one
commit of this change was rebased onto it (`git rebase --onto origin/main
5b4dbc5`), which turned the history-rewrite conflict into the real one: the
OpenAI support, added to the adapters this change had rewritten.

What was carried over from `main`, and how:

- **The four kinds under both engines.** `endpoint_of`, `chat_model`, the
  OpenAI endpoint and key header, the variables cleared and the loggers
  pinned (six now), the ceiling field per kind, `ChatOpenAI` handed clients
  the adapter built, `OpenAIChatModel` over a client built the same way --
  all as `main` had them, on the rewritten adapters.
- **The unsigned thinking blocks.** `main` dropped them where the LangGraph
  adapter replayed the transcript by hand; here the framework replays its
  own memory, so the drop is a middleware over every model call
  (`signed_blocks_only`), and the memory keeps the blocks as they arrived.
- **The repeated tool name** on a compatible server's deltas: kept on the
  Pydantic AI side, as the one part of `main`'s stream class the framework
  does not do; `main` had it on both sides by way of the hand-assembled
  calls, which are gone, and the difference is recorded in `agents.md`.
- **Not carried**: the byte-for-byte parity of the two engines' requests
  (the message respelling in `_ChatCompletions`, the thinking tags and the
  schema transformer switched off in the Pydantic AI profile, and the tests
  and the spec bullets that stated it). Each engine keeps a memory of its
  own now, and writes the request from it as its framework does.

## Deferred

- **A turn that did not end leaves no memory** (ADR 0005, "Costs"). A
  state per step of the loop is the remedy if it matters.
- **Tools that outlast a process** are further off than they were: a
  suspended run is now a question for each framework's deferred-tool
  support, not for the record alone (`runs.md`, "Tools").
- The Pydantic AI adapter measures the history at four characters a token;
  the LangChain adapter with langchain-core's approximate counter. Neither
  is the vendor's tokeniser, and both trim early rather than late.
- `openai` and `openai-compatible` are still refused: nothing here changes
  the `tiktoken` question.
- The `schema.sql` comment on the `tool` role still calls it reserved; the
  schema was re-pinned for `engine_state` and the comment was left, to keep
  this change to what the plan named.
