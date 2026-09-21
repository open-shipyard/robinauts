# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The schema: the file that defines it, applying it, and checking it.

``schema.sql`` beside this module is the whole schema of a deployment, and
it is shipped in the wheel. Nothing here runs at start-up but
``check_schema``: the server never creates or changes the schema on its own,
a command does (``docs/specs/backend.md``), and until that command exists
(step 5 of the plan) these are the functions it will be made of.

**One schema, named once.** ``schema.sql`` creates its tables unqualified, so
they land in ``current_schema()`` -- the first schema on the connection's
``search_path`` that exists. Everything here therefore asks about *that*
schema and no other: a table of ours in the second entry of the path is not
this deployment's table, and a table of somebody else's in the second entry
is none of our business. Judging the whole path instead gets both wrong, in
both directions: a complete schema further along would make an empty one
look finished, and another application's ``users`` would make an empty one
look occupied.

**And the store must reach the same schema.** The stores run unqualified
statements too, so they resolve through the whole path, and a table earlier
on it answering to one of our names would silently take their writes.
``check_schema`` compares the two resolutions and refuses when they differ
(``SchemaError.shadowed``): the contract with the rest of the code is that
**the connection's search path resolves our table names to
``current_schema()``**, which is what a pool built with
``search_path = <the deployment's schema>`` gives, and what
``check_schema`` will not start without.

**Nothing here changes a database it did not make.** There are no migrations
until there is a production deployment, so the only safe things to do to a
database are: create the schema in an empty one, and refuse. ``create_schema``
looks before it writes -- under a lock, so that two of them cannot both
decide the database is empty -- and every refusal is a ``SchemaError`` that
says what was found and what to do. The alternative, applying the file over
whatever is there, looks idempotent and is not: ``CREATE TABLE IF NOT
EXISTS`` leaves an older table exactly as it is, so what it really does is
relabel an old schema as the current one.

**The connection is judged too, not only the database.** A search path that
names no schema, or one that answers our table names from somewhere else,
is refused with its own advice: nothing is wrong with the database, and
``robinauts db init`` would not help.

**A database is complete or it is nothing.** The version row is the last
statement of ``schema.sql``, so it is a claim that everything above it
landed; ``check_schema`` believes it only as far as checking that every
table is there, and is a table rather than a view of the same name.

``SCHEMA_VERSION`` is this build's answer to "which schema was I written
against", and ``SCHEMA_SHA256`` is what the file looked like when that
answer was last true. ``tests/unit/test_datastore_schema.py`` fails if the
file changes and the pin does not.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import resources

import asyncpg

from robinauts.domain import SchemaError

SCHEMA_VERSION = 1
"""The schema this build was written against; ``schema.sql`` says the same.

Bumped in the same change as any edit to ``schema.sql``. Until there is a
production deployment there are no migrations, so a bump means "recreate the
database", not "upgrade it" (``docs/specs/backend.md``).
"""

SCHEMA_SHA256 = "ace3881e9a411e66b14966cd808511f4e86988e7e11ac280588c6fc29ef1586f"
"""``schema.sql`` as it stood when ``SCHEMA_VERSION`` was last right for it.

A schema edited in place has no migration to forget to write, which leaves
exactly one thing to forget: the version. This pin is what remembers.
Changing the file fails ``tests/unit/test_datastore_schema.py`` until both
the version above and this hash are brought up to date, and the test says so
in as many words. Line endings are normalised to ``\\n`` before hashing, and
``.gitattributes`` keeps the file checked out that way on every platform.
"""

SCHEMA_TABLES = ("pending_logins", "schema_version", "sessions", "users")
"""Every table ``schema.sql`` creates; a test keeps this list in step with it.

What ``check_schema`` looks for. A version row with a table missing under it
is a half-applied schema, not a schema.
"""

_LOCK_SPACE = 1382508616
"""The high half of this module's advisory lock key: ours, and nobody else's.

PostgreSQL's advisory locks are one number space for the whole database,
shared with every other program connected to it. Half of a 64-bit key spent
on a constant is what keeps our lock from being somebody else's. It differs
by one from the constant in ``credentials.py`` because the low half of that
key is a ``pg_class`` OID and the low half of this one a ``pg_namespace``
OID, and the two counters are the same counter: with one space the two locks
could collide, and creating a schema would queue behind a sign-in.
"""

Executor = asyncpg.Pool | asyncpg.Connection
"""What these functions run their statements on.

A pool or a single connection: a command opening a connection for one job
has the second, a server that is already running has the first.
"""

_LOCK_SCHEMA = f"""
SELECT pg_advisory_xact_lock(
    ({_LOCK_SPACE}::bigint << 32)
    | (SELECT oid FROM pg_namespace WHERE nspname = current_schema())::bigint
)
"""
"""Hold this schema until the transaction ends.

``create_schema`` looks and then writes, and two of them against one empty
database would otherwise both find it empty and both run the file -- which
surfaces as a unique violation out of PostgreSQL's own catalogue, an error
about ``pg_type`` that says nothing to anybody. With the lock the second one
waits, finds the schema the first made, and does nothing.
"""

_TABLES_HERE = """
SELECT name,
       (
           SELECT c.oid
           FROM pg_class AS c
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
           WHERE n.nspname = current_schema()
             AND c.relname = name
             -- A table or a partitioned table. A view, a sequence or a
             -- foreign table of the right name is not this schema's table,
             -- and a schema whose `users` is a view is not one to run on.
             AND c.relkind IN ('r', 'p')
       ) AS here,
       (
           SELECT array_position(current_schemas(true), n.nspname)
                < array_position(current_schemas(true), current_schema())
           FROM pg_class AS c
           JOIN pg_namespace AS n ON n.oid = c.relnamespace
           WHERE c.oid = to_regclass(quote_ident(name))
       ) AS in_front
FROM unnest($1::text[]) AS name
"""
"""For each name: the table in ``current_schema()``, and what stands in front.

``here`` is the table ``schema.sql`` would have created and ``check_schema``
is judging. ``in_front`` is about what an unqualified statement in a store
would really hit: it is true when the name resolves to a relation in a schema
the search path reaches **before** this one, and that is the only case that
matters. A relation further along the path is harmless -- ours wins as soon
as it exists, which is exactly how a deployment lives beside another
application's ``users``. One in front wins for ever, whether or not ours is
there: before the schema is created it would be created underneath, and
after, the check would pass while every statement went somewhere else.

``current_schemas(true)`` is the path as PostgreSQL really searches it,
implicit entries included -- which is how ``pg_temp`` is caught, since a
temporary table is searched first without ever being named on the path.
"""


def schema_sql() -> str:
    """The text of ``schema.sql``, read from the installed package."""
    return resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


async def create_schema(executor: Executor) -> None:
    """Create the schema in an empty database, or raise ``SchemaError``.

    What ``robinauts db init`` does, to ``current_schema()`` and to nothing
    else. Five things can be found, and only two of them are agreeable:

    * nothing of ours -- the file is applied;
    * this very schema, whole -- nothing happens, so the command is safe to
      repeat and safe to run when you are not sure;
    * a schema of another version, our tables with no version recorded, or a
      ``schema_version`` this build cannot read -- refused, because there is
      no migration to run and the file would relabel rather than upgrade;
    * this version with a table missing -- refused too: it is a database
      somebody's ``psql`` left half way through, and finishing it would
      leave whatever else that run half did;
    * a search path that names no schema at all, or one that reaches our
      names in a schema ahead of this one -- refused before anything is
      written, because neither is a database: both are a connection to set
      up differently.

    Looking and writing happen inside one transaction, under an advisory
    lock on this schema, so that two commands at once produce one schema and
    one no-op rather than a collision inside PostgreSQL's catalogue.
    """
    await _on_a_connection(executor, _create_schema)


async def check_schema(executor: Executor) -> None:
    """Raise ``SchemaError`` unless the database is the one this build knows.

    What a server calls before it agrees to serve anything: a search path
    that names a schema, the right version recorded in it, every table under
    that version, and nothing anywhere else answering to those names. The
    error says what was found and what to do about it.
    """
    await _on_a_connection(executor, _check_schema)


async def schema_version(executor: Executor) -> int | None:
    """The version recorded in ``current_schema()``, or ``None`` if there is none.

    ``None`` covers both "no ``schema_version`` table in this schema" and
    "the table is there and empty": neither is a version, and the answer to
    both is the same command.

    A ``schema_version`` table of some other shape is **not** ``None``. It is
    a database with something in it that this build cannot read, and saying
    "no schema" about it would invite the operator to create one on top; so
    that raises ``SchemaError`` like any other unknown version.
    """
    return await _on_a_connection(executor, _schema_version)


async def _on_a_connection[T](
    executor: Executor, work: Callable[[asyncpg.Connection], Awaitable[T]]
) -> T:
    """Run ``work`` on one connection, taking one from the pool if need be.

    Every question these functions ask is about the connection that asks it
    -- ``current_schema()``, the search path, an advisory lock -- so asking
    two of them on two connections of a pool would be asking about two
    different things and believing the answers were about one.
    """
    if isinstance(executor, asyncpg.Pool):
        async with executor.acquire() as connection:
            return await work(connection)
    return await work(executor)


async def _create_schema(connection: asyncpg.Connection) -> None:
    """``create_schema`` once there is a connection to hold a lock on."""
    async with connection.transaction():
        await connection.execute(_LOCK_SCHEMA)
        tables, found = await _state(connection)
        if found is None:
            if tables.here:
                raise SchemaError.unversioned(SCHEMA_VERSION, tables.here)
            # Before the file is applied, not after: creating our tables
            # under something that already answers to their names would
            # leave a schema that passes no check and takes no writes.
            tables.check_nothing_is_in_the_way()
            await connection.execute(schema_sql())
            return
        if found != SCHEMA_VERSION:
            raise SchemaError.mismatch(SCHEMA_VERSION, found)
        tables.check()


async def _check_schema(connection: asyncpg.Connection) -> None:
    """``check_schema`` once there is one connection to ask everything on."""
    tables, found = await _state(connection)
    if found is None:
        raise (
            SchemaError.unversioned(SCHEMA_VERSION, tables.here)
            if tables.here
            else SchemaError.missing(SCHEMA_VERSION)
        )
    if found != SCHEMA_VERSION:
        raise SchemaError.mismatch(SCHEMA_VERSION, found)
    tables.check()


async def _schema_version(connection: asyncpg.Connection) -> int | None:
    """``schema_version`` on one connection."""
    _, found = await _state(connection)
    return found


async def _state(connection: asyncpg.Connection) -> tuple[_Tables, int | None]:
    """What this schema holds, and the version it records.

    The search path is checked first, because a path that names no schema
    makes every other question meaningless. Then the catalogue, and the
    version row only if the catalogue says there is a table to read it from.
    That order is not an optimisation: a statement that fails aborts the
    transaction it is in, and ``create_schema`` runs inside one -- so "try
    the select and catch the missing table" would turn the ordinary case of
    an empty database into a transaction that can do nothing else.
    """
    here = await _current_schema(connection)
    tables = _Tables(await connection.fetch(_TABLES_HERE, list(SCHEMA_TABLES)))
    if "schema_version" not in tables.here:
        return tables, None
    try:
        # Qualified with `current_schema()`, quoted by PostgreSQL's own
        # `quote_ident` rather than by us, so a `schema_version` further
        # along the search path is somebody else's business and a schema
        # named something strange is still asked about correctly.
        found = await connection.fetchval(f"SELECT version FROM {here}.schema_version")
    except asyncpg.exceptions.UndefinedColumnError as unreadable:
        # A table of that name with no `version` column: somebody else's, or
        # from a shape of ours older than this pin.
        raise SchemaError.unreadable(SCHEMA_VERSION) from unreadable
    if found is not None and not isinstance(found, int):
        raise SchemaError.unreadable(SCHEMA_VERSION)
    return tables, found


class _Tables:
    """What ``current_schema()`` holds, and where the search path goes."""

    def __init__(self, rows: list[asyncpg.Record]) -> None:
        self.here = [row["name"] for row in rows if row["here"] is not None]
        """Which of ``SCHEMA_TABLES`` are tables of this schema."""
        self.in_front = [row["name"] for row in rows if row["in_front"]]
        """Which of those names something ahead of this schema answers to.

        Whether or not ours is there as well: if it is, the statements would
        miss it, and if it is not, it would be created underneath.
        """

    def check(self) -> None:
        """Raise unless every table is here and is the one a query would hit."""
        missing = set(SCHEMA_TABLES) - set(self.here)
        if missing:
            raise SchemaError.incomplete(SCHEMA_VERSION, missing)
        self.check_nothing_is_in_the_way()

    def check_nothing_is_in_the_way(self) -> None:
        """Raise if anything ahead of this schema answers to one of our names."""
        if self.in_front:
            raise SchemaError.shadowed(SCHEMA_VERSION, self.in_front)


async def _current_schema(connection: asyncpg.Connection) -> str:
    """``current_schema()``, ready to put in front of a table name.

    Quoted by ``quote_ident`` on the server, which is the only thing that
    knows when an identifier needs quoting and how to escape what is in it.

    A search path naming nothing that exists has no ``current_schema()`` at
    all. There is then no schema to read from and none to create in either,
    and PostgreSQL would say so in its own words several statements later --
    about a table, when the trouble is the connection.
    """
    row = await connection.fetchrow(
        "SELECT quote_ident(current_schema()) AS here, current_setting('search_path') AS path"
    )
    if row["here"] is None:
        raise SchemaError.no_schema(SCHEMA_VERSION, row["path"])
    return row["here"]
