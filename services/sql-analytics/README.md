# SQL Analytics

An MCP server an agent asks questions of the company's SQL databases through.
It runs on its own, next to Robinauts or next to any other MCP client.

**State: milestone M0, the skeleton.** The service starts, reads and checks its
configuration, refuses a request without a known token or with a `Host` it does
not serve, and answers one tool, `list_sources`. Every gate of the repository
runs on it. It does not connect to a database yet: the query pipeline and the
DuckDB and SQLite connectors are milestone M1.

| milestone | what it adds |
| --- | --- |
| **M0** | the project, its lock and extras, configuration, bearer tokens, `/healthz`, `list_sources`, import contracts, the gates |
| M1 | the query pipeline on DuckDB and SQLite: parse, guard, parameters, limit, transpile, run, keep, encode; the catalog and query tools; the RealWorld demo data |
| M2 | the view: results shown in a host's panel |
| M3 | PostgreSQL |
| M4 | Snowflake, BigQuery, Spark, each once its dependency tree passes the licence gate |
| M5 | stored queries, quotas, cancellation, the operator's guide: 0.1.0, the first release |

## Running it

From this folder:

```bash
uv sync
SQL_ANALYTICS_TOKEN_ROBINAUTS=... uv run robinauts-sql-analytics check --config sql-analytics.toml
SQL_ANALYTICS_TOKEN_ROBINAUTS=... uv run robinauts-sql-analytics serve --config sql-analytics.toml
```

`--config` may be given as `SQL_ANALYTICS_CONFIG` instead. The service listens
on `http://127.0.0.1:8770`: `/mcp` is the MCP server (streamable HTTP,
stateless, JSON answers), `/healthz` says the process is up and needs no token.
TLS is the reverse proxy's.

## Configuration

```toml
[server]
host = "127.0.0.1"                         # the default
port = 8770                                # the default
allowed_hosts = ["sql.internal.example"]   # Host header check (DNS rebinding)

[store]
metadata = "sqlite"                        # or "postgres", with dsn_env
path = "/var/lib/sql-analytics"            # metadata file and kept results

[results]                                  # every value here is the default
max_rows = 100000                          # rows kept per result
model_chars = 8000                         # text budget for the model
page_rows = 200
page_bytes = 1000000
ttl_hours = 24

[principals.robinauts]
token_env = "SQL_ANALYTICS_TOKEN_ROBINAUTS"   # compared in constant time, never stored
sources = ["realworld", "realworld_pg"]

[sources.realworld]
kind = "duckdb"
description = "Conduit, the RealWorld blogging app: users, follows, articles, tags, favorites, comments."
path = "/var/lib/sql-analytics/demo/realworld.duckdb"

[sources.realworld_pg]
kind = "postgres"
description = "The same Conduit data in PostgreSQL, schema realworld."
dsn_env = "REALWORLD_PG_DSN"
schema = "realworld"
timeout_seconds = 30
```

The file is read and checked whole at start-up. An unknown key, a missing key,
a value of the wrong type, a source of a kind this version cannot reach, a
principal naming an unknown source, an environment variable that is not set, a
token shorter than 16 characters or two principals holding the same token:
each stops the start, and every reason is printed at once. `check` does the
same and stops; once the connectors exist it will also connect to each source.

A source's kind is `duckdb` or `sqlite` (`path`), or `postgres` (`dsn_env`).
Each also takes `description` (required), `schema`, `timeout_seconds` and
`max_rows`. The default schema is `main` for DuckDB and SQLite and `public` for
PostgreSQL.

**The caller is the credential.** A principal is the token a request came with,
and it sees only the sources its configuration names. Behind Robinauts, every
person using an agent that names this tool server is the same principal.

From Robinauts:

```toml
[tool_servers.sql]
url = "http://127.0.0.1:8770/mcp"
auth = "bearer"
secret_env = "SQL_ANALYTICS_TOKEN_ROBINAUTS"
```

## Extras

DuckDB and SQLite come with the service. Every other database is an extra:

| extra | driver | state |
| --- | --- | --- |
| `postgres` | `asyncpg`, at the version the backend pins | declared |
| `snowflake` | `snowflake-connector-python` | not declared: brings `protobuf` |
| `bigquery` | `google-cloud-bigquery`, `google-cloud-bigquery-storage` | not declared: brings `protobuf`, `pyasn1-modules`, `python-dateutil` |
| `spark` | `pyspark-client` (Spark Connect) | not declared: brings `protobuf` and, through `pandas`, `python-dateutil`; publishes no wheel |

The three that are not declared fail the licence gate today, not because their
licences are refused but because the gate cannot read them: `protobuf` states
"3-Clause BSD License", `pyasn1-modules` the family "BSD", and
`python-dateutil` "Dual License", none of which names an identifier, and the
gate fails closed ([DEPENDENCIES.md](../../DEPENDENCIES.md)). `pyspark-client`
also ships only a source distribution, which the gate's `--no-build` sync
refuses. Each is settled in a pull request of its own before its connector is
written (M4): read the licence by hand and add a row to DEPENDENCIES.md, or
leave the database out.

## Architecture

```
src/sql_analytics/
  contract/       the records every layer shares: Principal, SourceInfo, Secret
  core/           pure functions, no I/O (the query pipeline's steps, from M1)
  ports/          abc.ABC: a database, the result store, the metadata (from M1)
  application/    the use cases: catalog.py
  adapters/
    mcp/          server.py: the tools
    http/         app.py (the ASGI app: Host check, /healthz, /mcp), auth.py
  config.py       the TOML file, read and checked; secrets by environment name
  composition.py  the one place adapters are chosen and built
  cli.py          robinauts-sql-analytics serve | check
```

The rules, enforced by import-linter from this project's `pyproject.toml` and
run by `tests/tooling/test_architecture.py`:

- `contract` imports nothing of the service. `core` and `ports` import
  `contract` alone; `application` imports `contract`, `ports` and `core`;
  `config` imports `contract` alone.
- Adapters import neither `config`, `composition` nor `cli`, and no adapter
  imports another. Only `composition` imports an adapter, and only `cli`
  imports `composition`.
- `mcp` only under `adapters.mcp` and `adapters.http`; `starlette` and
  `uvicorn` only under `adapters.http` and `cli`; `sqlglot` only under `core`;
  `duckdb`, `pyarrow` and `asyncpg` in none of the modules written so far
  (each module that needs one is added to its rule when it is written).

## Tests

Placed by [docs/testing/testing-strategy.md](../../docs/testing/testing-strategy.md):
`unit/` (configuration, the bearer token), `fast/` (the catalog), `api/` (the
service started as its command and spoken to over HTTP), `tooling/` (the import
contracts). `scripts/check-services.sh`, from the root of the repository, runs
them with ruff, black and import-linter.
