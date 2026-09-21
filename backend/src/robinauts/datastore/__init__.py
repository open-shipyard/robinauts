# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Owned state: the store ports over the deployment's one PostgreSQL.

The only place in the package that imports the database driver, and the only
place that knows any SQL (``docs/layout.md``; an import-linter contract in
``backend/pyproject.toml`` keeps ``asyncpg`` here). It depends on
``robinauts.ports`` and ``robinauts.domain`` and on nothing else inside the
package: it implements the ports and returns domain objects, and decides
nothing that the application decides.

There is no ORM. The SQL is hand-written and the schema is ours
(``docs/specs/backend.md``, ADR 0002): ``schema.sql`` beside this module is
the whole of it, one definition edited in place, applied by a command and
never by the server.

So far: ``PostgresCredentialStore``. The conversation, run and usage stores
join it, over the same pool and the same file.
"""

from robinauts.datastore.credentials import PostgresCredentialStore
from robinauts.datastore.pool import MAX_POOL_SIZE, MIN_POOL_SIZE, open_pool
from robinauts.datastore.schema import (
    SCHEMA_SHA256,
    SCHEMA_TABLES,
    SCHEMA_VERSION,
    check_schema,
    create_schema,
    schema_sql,
    schema_version,
)

__all__ = [
    "MAX_POOL_SIZE",
    "MIN_POOL_SIZE",
    "SCHEMA_SHA256",
    "SCHEMA_TABLES",
    "SCHEMA_VERSION",
    "PostgresCredentialStore",
    "check_schema",
    "create_schema",
    "open_pool",
    "schema_sql",
    "schema_version",
]
