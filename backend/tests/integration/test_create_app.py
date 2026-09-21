# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The whole deployment, wired by ``create_app``, against a real PostgreSQL.

Everything at once and nothing faked but the operator: the configuration file
on disk, the pool on the test database, ``check_schema``, the real HTTP
adapter, and a real OpenID Connect provider on loopback. A person signs in and
out through the routes, and their user and session are rows.

The other half is the refusal: a database with no schema of ours must stop the
server from starting, and say what to run (``docs/specs/backend.md``). The
lifespan is where that happens, so the lifespan is what is driven here.

Each test works in a schema of its own, named in the connection string the way
a deployment would name one.

Marked ``io`` and ``database``; skipped, with the reason, without
``ROBINAUTS_TEST_DATABASE_URL``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest

from aio import asyncio_test
from postgres import DATABASE_URL, TemporarySchema, requires_postgres
from robinauts.app import create_app
from robinauts.datastore import SCHEMA_VERSION, create_schema
from robinauts.domain import DB_INIT_COMMAND, SchemaError
from standin import StandInProvider, redirect_from
from webapp import running

pytestmark = requires_postgres

PUBLIC_URL = "https://robinauts.example.com"
SECRET_VARIABLE = "ROBINAUTS_STAND_IN_SECRET"

CONFIGURATION = """
public_url = "{public_url}"
session_hours = 1

[providers.standin]
title = "The stand-in"
issuer = "{issuer}"
client_id = "{client_id}"
client_secret_env = "{secret_variable}"

[[allow]]
provider = "standin"
email = "ada@example.com"
"""


@pytest.fixture
def stand_in() -> Iterator[StandInProvider]:
    with StandInProvider() as provider:
        yield provider


def written(tmp_path: Path, stand_in: StandInProvider) -> Path:
    path = tmp_path / "sign-in.toml"
    path.write_text(
        CONFIGURATION.format(
            public_url=PUBLIC_URL,
            issuer=stand_in.issuer,
            client_id=stand_in.client_id,
            secret_variable=SECRET_VARIABLE,
        ),
        encoding="utf-8",
    )
    return path


def in_schema(name: str) -> str:
    """The test database's URL, with the search path a deployment would set.

    A deployment that keeps the platform's tables under a schema of its own
    says so in the connection string, and the server obeys it: this is that,
    and it is what lets every test here have a schema to itself.
    """
    assert DATABASE_URL is not None
    separator = "&" if "?" in DATABASE_URL else "?"
    return f"{DATABASE_URL}{separator}options=-csearch_path%3D{name}"


@asynccontextmanager
async def schema(*, applied: bool = True) -> AsyncIterator[TemporarySchema]:
    """A schema of this test's own, with or without ``schema.sql`` in it."""
    temporary = TemporarySchema(min_size=1, max_size=1)
    await temporary.open()
    try:
        if applied:
            await create_schema(temporary.pool)
        yield temporary
    finally:
        await temporary.close()


@asyncio_test
async def test_a_person_signs_in_and_out_of_a_real_deployment(
    tmp_path: Path, stand_in: StandInProvider
) -> None:
    async with schema() as temporary:
        app = create_app(
            config_path=written(tmp_path, stand_in),
            database_url=in_schema(temporary.name),
            secret_for={SECRET_VARIABLE: stand_in.client_secret}.get,
        )

        async with running(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=PUBLIC_URL,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                begun = await client.get("/auth/login/standin", params={"return_to": "/#/chat/1"})
                back = await redirect_from(begun.headers["location"])
                landed = await client.get(f"/auth/callback/standin?{urlsplit(back).query}")
                signed_in = await client.get("/auth/session")
                out = await client.post(
                    "/auth/logout",
                    headers={"content-type": "application/json", "origin": PUBLIC_URL},
                )
                after = await client.get("/auth/session")
            users = await temporary.pool.fetchval("SELECT count(*) FROM users")
            sessions = await temporary.pool.fetchval("SELECT count(*) FROM sessions")

        closed = app.state.deployment.pool

    assert landed.headers["location"] == f"{PUBLIC_URL}/ui/#/chat/1"
    assert signed_in.json()["user"]["email"] == "ada@example.com"
    assert signed_in.json()["providers"] == [{"id": "standin", "title": "The stand-in"}]
    assert out.status_code == 204
    assert after.json()["user"] is None
    assert (users, sessions) == (1, 0)
    # The lifespan gave back what it took: no pool, no sign-in, nothing held.
    assert closed is None
    assert app.state.sign_in is None
    assert app.state.deployment.sign_in is None


@asyncio_test
async def test_the_server_refuses_to_start_against_a_database_with_no_schema(
    tmp_path: Path, stand_in: StandInProvider
) -> None:
    """And says what to run, and that it works on an empty database only."""
    async with schema(applied=False) as temporary:
        app = create_app(
            config_path=written(tmp_path, stand_in),
            database_url=in_schema(temporary.name),
            secret_for={SECRET_VARIABLE: stand_in.client_secret}.get,
        )

        with pytest.raises(SchemaError) as raised:
            async with running(app):  # pragma: no cover -- start-up fails
                pass

        # The pool it opened to find out is closed all the same.
        assert app.state.deployment.pool is None

    assert "no Robinauts schema" in str(raised.value)
    assert DB_INIT_COMMAND in str(raised.value)
    assert f"schema version {SCHEMA_VERSION}" in str(raised.value)
    assert app.state.sign_in is None


@asyncio_test
async def test_the_pool_is_opened_only_when_the_lifespan_runs(
    tmp_path: Path, stand_in: StandInProvider
) -> None:
    """``create_app`` reads and validates; it opens nothing.

    So a misconfigured deployment fails before it touches a database, and a
    process that is only being asked for its application does not connect.
    """
    async with schema() as temporary:
        app = create_app(
            config_path=written(tmp_path, stand_in),
            database_url=in_schema(temporary.name),
            secret_for={SECRET_VARIABLE: stand_in.client_secret}.get,
        )

        assert app.state.deployment.pool is None

        async with running(app):
            opened = app.state.deployment.pool
            assert not opened.is_closing()

    assert opened.is_closing()
