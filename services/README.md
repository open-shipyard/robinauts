# Services

Services an operator deploys beside Robinauts, or beside any other MCP client.
Each is a folder here and a project of its own. The platform does not need any
of them: Robinauts reaches one the way it reaches any tool server, with one
`[tool_servers.<id>]` entry in its configuration
([docs/specs/operations.md](../docs/specs/operations.md)).

They differ from the servers under [mcp/](../mcp/README.md), which exist to try
the platform with and depend on the MCP SDK alone: a service is meant to be run
in a company, and may have dependencies of its own, some of them optional.

What they have in common:

- **It stands alone.** It imports nothing of `backend/`, and nothing under
  `backend/src` names it (`scripts/check-extra-workers.sh` checks that).
- **It uses the MCP SDK the backend already has**, at the version
  `backend/uv.lock` pins.
- **It keeps the backend's rules**: hexagonal, with ports as `abc.ABC` and its
  layers enforced by import-linter in its own `pyproject.toml`; nothing phones
  home; secrets named by environment variable, never stored or logged; tests
  placed by [docs/testing/testing-strategy.md](../docs/testing/testing-strategy.md).
- **It is checked like the rest of the repository**: SPDX headers on every
  file, its lock under the licence gate with every extra synced
  (`scripts/check-licences.sh`), and ruff, black, its import contracts and its
  tests (`scripts/check-services.sh`).

The services:

| folder | what it serves | state |
| --- | --- | --- |
| [sql-analytics/](sql-analytics/README.md) | SQL Analytics: an agent finds and queries the company's SQL databases over MCP | milestone M0, the skeleton |
