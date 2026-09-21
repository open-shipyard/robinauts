# Backend

Python. The layers, what goes where, and the enforced dependency rules are
in [layout.md](../layout.md). This document holds the component choices.

## Web

- FastAPI on uvicorn.
- FastAPI, Starlette and uvicorn are imported only in the `api` layer and
  the composition root. The application never sees a request object.
- The OpenAPI document is committed as a snapshot; a test keeps it in step
  with the code. The streaming turn endpoint is outside it
  ([wire.md](wire.md)).
- The backend also serves the built frontend
  ([frontend.md](frontend.md)).

## Background work

- Runs and housekeeping execute inside the backend process, on the event
  loop that serves requests. There is no separate worker or queue
  ([runs.md](runs.md)).
- The ASGI lifespan opens and closes what the process holds: the database
  pool, the run executor, the housekeeping tasks.

## Database

- PostgreSQL is the one database, and it is always required. There is no
  run mode without it; in-memory stores exist only as test fakes.
- Everything stored lives there: conversations, runs and their events,
  attachments, search indexes, users, sessions, projects, audit.
- No ORM. SQL is hand-written in the `datastore` layer, which implements
  the store ports and returns domain objects.
- Where expiry is involved, time comes from the database clock; stores are
  given durations, not timestamps.
- The schema is entirely the platform's. No framework creates or migrates
  tables in it
  ([ADR 0002](../adr/0002-conversation-persistence.md)).

## Migrations

- The schema is managed by migrations from the start: a deployment is
  upgradable in place from the first release.
- The server never migrates on its own. It refuses to start against a
  schema that is behind or ahead of the code, and names the command that
  fixes it.
- A released migration is never edited.

## Details likely to change

- The driver is `asyncpg` (Apache-2.0), imported only in `datastore`.
  `psycopg` is LGPL-3.0-only and is excluded
  ([open-source.md](open-source.md)).
- Migrations are numbered SQL files shipped in the package, applied in
  order by `robinauts db migrate`, each in a transaction, recorded in a
  `schema_migrations` table. No migration framework. Before the first
  release the files may still be rewritten.
- Attachments are `bytea`; search is `tsvector`.
- Licences as known today: FastAPI MIT, Starlette and uvicorn
  BSD-3-Clause, Pydantic MIT, `httpx` BSD-3-Clause, with `certifi`
  MPL-2.0 behind it. The gates decide, at the pinned versions.
- Tooling: Python 3.12, uv, hatchling, ruff, black, pytest,
  import-linter.
