# Layer references rules

Anything not allowed is forbidden. A rule names a package and covers everything
under it. `backend/pyproject.toml` enforces these; `tests/tooling/test_architecture.py`
runs them.

Each package is reached through its `contract` alone. A package's internals are
imported by its own modules and by `controller.composition`, which builds them.

## Top level

agent_engines -> nothing from robinauts
tools -> agent_engines.contract, controller.contract
controller -> agent_engines.contract, tools.contract; a tool and the worker, by composition alone
worker -> controller.contract, web.contract, agent_engines.contract, tools.contract
web -> controller.contract, controller.composition

Only controller.composition imports the worker, or a tool. Only web imports
controller.composition. Only the worker imports web.contract from outside web.

## Inside agent_engines

contract -> nothing from robinauts
echo_engine -> contract
langchain_engine -> contract + langchain deps + postgres
pydantic_ai_engine -> contract + pydantic ai deps + postgres
no engine imports another

## Inside tools

contract -> agent_engines.contract, controller.contract
each tool (sessions) -> contract, agent_engines.contract, controller.contract
no tool imports another; only controller.composition imports a tool

## Inside controller

contract -> nothing from robinauts outside controller.contract
contract.broker -> contract.domain; contract.domain and contract.ports never import it
ports -> contract
core -> contract, ports, agent_engines.contract; pure functions, no I/O
adapters -> contract, ports
application -> contract, ports, core, agent_engines.contract, tools.contract
composition -> contract, ports, core, adapters, application, tools, worker; imported by web alone

`contract.broker` is the turn broker's contract: the `TurnBroker` port, the
records that cross it (tasks, stored messages and events), and how a message
and an event are written as documents. The worker reaches the core through it.
Its in-process implementation, over the store, is `application/turn_broker.py`.

## Inside worker

worker -> its own modules, and the packages named at the top level; nothing of
controller but controller.contract, and nothing of web but web.contract
http_turn_broker -> the one module of the worker that may import httpx

The worker's modules: `worker` (claims and runs the tasks), `turns` (runs one
turn), `tools`, `engines`, `engine_settings`, `failures`, `agent_engine_store`
(the engines' store, a port with a pool-backed implementation the composition
hands its pool functions), and `http_turn_broker` (the turn broker over HTTP,
for a worker in a process of its own).

## Inside web

contract -> controller.contract; nothing else of web
the rest of web -> controller.contract, controller.composition, web.contract

`web.contract.broker.wire` is the turn broker over HTTP: the routes and bodies
that `web/worker_api.py` serves and `worker/http_turn_broker.py` calls.

## Third-party libraries, where each may be imported

langchain, langchain_core, langchain_*, langgraph, langchain_mcp_adapters, langsmith -> langchain_engine
pydantic_ai, pydantic_graph, fastmcp, logfire, logfire_api, opentelemetry -> pydantic_ai_engine
anthropic, openai, mcp -> langchain_engine, pydantic_ai_engine
asyncpg, sqlite3, aiosqlite -> langchain_engine, pydantic_ai_engine, controller.adapters
httpx -> web, worker.http_turn_broker, langchain_engine, pydantic_ai_engine
fastapi, starlette, uvicorn, ag_ui -> web
qrcodegen -> web

## Keeping the rules up to date

`pyproject.toml` writes most of these rules as lists of what is forbidden, so a
new package is not covered until it is added to those lists. A new top-level
package, a new engine, a new tool or a new module of web must be added where
the rules name its siblings one by one:

- a new engine: the five rules that list the engines (the engines' contract,
  engine independence, controller, tools and worker).
- a new tool: the two rules that list `tools.sessions` (the tool named by
  composition alone, and the worker).
- a new module of web: the rule that keeps `web.contract` apart from the rest
  of web.
- a new top-level package: the rules of every package that may not import it.

The worker's exception for `web.contract` is written as a pattern, so a new
module of web is out of the worker's reach without any edit.
