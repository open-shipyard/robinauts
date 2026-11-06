# Layer references rules

Anything not allowed is forbidden. A rule names a package and covers everything
under it. `backend/pyproject.toml` enforces these; `tests/tooling/test_architecture.py`
runs them.

## Top level

agent_engines -> nothing from robinauts
tools -> agent_engines.contract, controller.contract
controller -> agent_engines.contract, tools.contract; a tool and the worker, by composition alone
worker -> controller.contract, controller.broker.contract, agent_engines.contract, tools.contract
web -> controller.contract, controller.broker.contract, controller.composition

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

contract -> nothing from robinauts
broker.contract -> contract
broker (in_process) -> contract, broker.contract, ports
ports -> contract, broker.contract
core -> contract, broker.contract, ports, agent_engines.contract; pure functions, no I/O
adapters -> contract, broker.contract, ports
application -> contract, broker.contract, ports, core, agent_engines.contract, tools.contract
composition -> contract, broker, ports, core, adapters, application, tools, worker; imported by web alone

## Inside worker

worker -> its own modules, and the contracts named at the top level; nothing of
controller but contract and broker.contract

## Third-party libraries, where each may be imported

langchain, langchain_core, langchain_*, langgraph, langchain_mcp_adapters, langsmith -> langchain_engine
pydantic_ai, pydantic_graph, fastmcp, logfire, logfire_api, opentelemetry -> pydantic_ai_engine
anthropic, openai, mcp -> langchain_engine, pydantic_ai_engine
asyncpg, sqlite3, aiosqlite -> langchain_engine, pydantic_ai_engine, controller.adapters
httpx -> web, langchain_engine, pydantic_ai_engine
fastapi, starlette, uvicorn, ag_ui -> web
qrcodegen -> web
