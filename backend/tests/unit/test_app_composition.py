# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The composition root: what it refuses at start-up, and what it opens and closes.

Two halves, and they are tested apart because they fail apart. Configuring is
where an operator's mistakes are found, and the promise is that **every one of
them is reported at once** -- a start-up that named one problem per restart
would cost as many restarts as there are mistakes. Opening is where a process
takes hold of something, and the promise is that the lifespan gives all of it
back.

No database and no environment variable here: the collaborators are handed in,
which is what ``Deployment`` takes them for.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import httpx
import pytest

from aio import asyncio_test
from fakes import FakeClock, MemoryCredentialStore, ScriptedIdentityProvider
from robinauts.adapters import HttpIdentityProvider, SecretLookup
from robinauts.app import (
    AUTH_CONFIG_VARIABLE,
    DATABASE_URL_VARIABLE,
    Deployment,
    create_app,
)
from robinauts.domain import ConfigError, InvalidValueError
from webapp import PUBLIC_URL, running

pytestmark = pytest.mark.io  # every test here writes a configuration file

DATABASE_URL = "postgresql://nobody@127.0.0.1:1/never-opened"

CONFIGURATION = """
public_url = "https://robinauts.example.com"

[providers.google]
title = "Google"
issuer = "https://accounts.google.com"
client_id = "a-client"
client_secret_env = "ROBINAUTS_GOOGLE_SECRET"

[[allow]]
provider = "google"
hosted_domain = "example.com"
"""


def written(tmp_path: Path, text: str = CONFIGURATION) -> Path:
    path = tmp_path / "sign-in.toml"
    path.write_text(text, encoding="utf-8")
    return path


def reading(variables: Mapping[str, str]) -> SecretLookup:
    """A ``SecretLookup`` over a mapping: the environment, without one.

    No test here sets a real variable: a secret in the process's environment
    is a secret in every other test's environment too.
    """
    return variables.get


def deployed(tmp_path: Path, **changes: object) -> Deployment:
    """A configured deployment over fakes, its file written for it."""
    return Deployment.configured(
        config_path=written(tmp_path),
        database_url=DATABASE_URL,
        secret_for=reading({"ROBINAUTS_GOOGLE_SECRET": "a-secret"}),
        credentials=MemoryCredentialStore(),
        clock=FakeClock(),
        **changes,  # type: ignore[arg-type]
    )


# Configuring.


def test_a_file_that_does_not_parse_is_the_whole_story(tmp_path: Path) -> None:
    """There is no configuration to check secrets against, so none are checked."""
    with pytest.raises(ConfigError) as raised:
        Deployment.configured(
            config_path=written(tmp_path, "public_url = "),
            database_url=DATABASE_URL,
            secret_for=reading({}),
            credentials=MemoryCredentialStore(),
        )

    assert len(raised.value.problems) == 1
    assert "not valid TOML" in raised.value.problems[0]


def test_every_problem_of_a_usable_configuration_is_reported_at_once(
    tmp_path: Path,
) -> None:
    """The client secret and the database, in one refusal, not two restarts.

    That is what ``docs/specs/operations.md`` asks of start-up, and the
    composition root is the only place that has both: ``core`` cannot see the
    environment and ``check_client_secrets`` cannot see the database.
    """
    with pytest.raises(ConfigError) as raised:
        Deployment.configured(
            config_path=written(tmp_path), database_url=None, secret_for=reading({})
        )

    problems = "\n".join(raised.value.problems)
    assert len(raised.value.problems) == 2
    assert "ROBINAUTS_GOOGLE_SECRET" in problems
    assert DATABASE_URL_VARIABLE in problems


def test_a_configuration_core_refuses_is_reported_with_what_else_is_wrong(
    tmp_path: Path,
) -> None:
    """Core's problems and the root's, together; the secrets are not among them.

    There is no configuration for them to be checked against -- a provider
    whose table was thrown out has no variable to look for -- so the honest
    answer is the problems that could be found, not a guess at the rest.
    """
    broken = CONFIGURATION.replace("[[allow]]", "[[nothing]]")

    with pytest.raises(ConfigError) as raised:
        Deployment.configured(
            config_path=written(tmp_path, broken),
            database_url=None,
            secret_for=reading({}),
        )

    problems = "\n".join(raised.value.problems)
    assert "nothing" in problems
    assert "no entry, so nobody could sign in" in problems
    assert DATABASE_URL_VARIABLE in problems
    assert "ROBINAUTS_GOOGLE_SECRET" not in problems


def test_the_missing_client_secret_is_named_and_never_its_value(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigError) as raised:
        Deployment.configured(
            config_path=written(tmp_path),
            database_url=DATABASE_URL,
            secret_for=reading({}),
            credentials=MemoryCredentialStore(),
        )

    assert raised.value.problems == (
        "providers.google: the client secret is read from the environment variable"
        " ROBINAUTS_GOOGLE_SECRET, which is unset or empty",
    )


def test_the_file_and_the_database_are_read_from_the_environment(
    tmp_path: Path,
) -> None:
    path = written(tmp_path)

    deployment = Deployment.configured(
        secret_for=reading(
            {
                AUTH_CONFIG_VARIABLE: str(path),
                DATABASE_URL_VARIABLE: DATABASE_URL,
                "ROBINAUTS_GOOGLE_SECRET": "a-secret",
            }
        ),
    )

    assert deployment.config.public_url == "https://robinauts.example.com"
    assert deployment.database_url == DATABASE_URL


def test_a_deployment_that_was_told_nothing_says_what_to_set() -> None:
    with pytest.raises(ConfigError) as raised:
        Deployment.configured(secret_for=reading({}))

    problems = "\n".join(raised.value.problems)
    assert AUTH_CONFIG_VARIABLE in problems
    assert DATABASE_URL_VARIABLE in problems


def test_a_store_that_was_handed_in_needs_no_database_url(tmp_path: Path) -> None:
    """What the process does not open, it does not need to be told about."""
    deployment = Deployment.configured(
        config_path=written(tmp_path),
        secret_for=reading({"ROBINAUTS_GOOGLE_SECRET": "a-secret"}),
        credentials=MemoryCredentialStore(),
    )

    assert deployment.database_url is None


# Opening and closing.


@asyncio_test
async def test_opening_wires_the_application_and_closing_lets_it_go(
    tmp_path: Path,
) -> None:
    deployment = deployed(tmp_path, provider=ScriptedIdentityProvider())

    sign_in = await deployment.open()
    opened = deployment.sign_in

    await deployment.aclose()

    assert opened is sign_in
    assert sign_in.config.public_url == "https://robinauts.example.com"
    assert deployment.sign_in is None


@asyncio_test
async def test_an_identity_provider_that_holds_a_client_is_closed(
    tmp_path: Path,
) -> None:
    """The process holds it for its life, and shutting down is when it goes."""
    adapter = HttpIdentityProvider(secret_for=reading({}), trust_env=False)
    deployment = deployed(tmp_path, provider=adapter)

    await deployment.open()
    await deployment.aclose()

    # The adapter makes its own client and `aclose` is the only way to close
    # it; a client nobody closed is a warning at shutdown and a leaked socket.
    with pytest.raises(RuntimeError):
        await adapter.discovery_document(deployment.config.provider("google"))


@asyncio_test
async def test_a_deployment_is_opened_once(tmp_path: Path) -> None:
    """A second open would leave the first pool and client unreachable and held.

    Connections for the life of the process, against a deployment that thinks
    it has one set of them. It is a mistake to say so about, not to carry out.
    """
    deployment = deployed(tmp_path, provider=ScriptedIdentityProvider())
    first = await deployment.open()

    with pytest.raises(InvalidValueError) as raised:
        await deployment.open()

    assert "opened already" in str(raised.value)
    assert deployment.sign_in is first
    await deployment.aclose()


@asyncio_test
async def test_it_is_still_opened_once_after_it_has_been_closed(tmp_path: Path) -> None:
    deployment = deployed(tmp_path, provider=ScriptedIdentityProvider())
    await deployment.open()
    await deployment.aclose()

    with pytest.raises(InvalidValueError):
        await deployment.open()


@asyncio_test
async def test_closing_one_that_was_never_opened_does_nothing(tmp_path: Path) -> None:
    deployment = deployed(tmp_path, provider=ScriptedIdentityProvider())

    await deployment.aclose()

    assert (deployment.sign_in, deployment.pool) == (None, None)


@asyncio_test
async def test_closing_twice_is_the_same_as_closing_once(tmp_path: Path) -> None:
    """Each closer is taken off the list before it is called, so there is
    nothing left for a second call to close twice -- which a lifespan that
    unwinds twice, and a test with a ``finally``, both rely on."""
    adapter = HttpIdentityProvider(secret_for=reading({}), trust_env=False)
    deployment = deployed(tmp_path, provider=adapter)

    await deployment.open()
    await deployment.aclose()
    await deployment.aclose()

    assert (deployment.sign_in, deployment.pool) == (None, None)


@asyncio_test
async def test_the_lifespan_opens_before_the_first_request_and_closes_after(
    tmp_path: Path,
) -> None:
    """The application answers nobody until the lifespan has run, and lets go after."""
    app = create_app(
        config_path=written(tmp_path),
        secret_for=reading({"ROBINAUTS_GOOGLE_SECRET": "a-secret"}),
        credentials=MemoryCredentialStore(),
        provider=ScriptedIdentityProvider(),
        clock=FakeClock(),
    )

    assert app.state.sign_in is None
    async with running(app):
        assert app.state.sign_in is not None
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=PUBLIC_URL
        ) as client:
            answered = await client.get("/auth/session")

    assert answered.json() == {
        "sign_in": True,
        "public_url": PUBLIC_URL,
        "providers": [{"id": "google", "title": "Google"}],
        "user": None,
    }
    assert app.state.sign_in is None
    assert app.state.deployment.sign_in is None


@asyncio_test
async def test_create_app_refuses_a_configuration_it_cannot_use(tmp_path: Path) -> None:
    """``robinauts start`` fails before it binds a port, not after."""
    with pytest.raises(ConfigError):
        create_app(
            config_path=written(tmp_path),
            secret_for=reading({}),
            credentials=MemoryCredentialStore(),
        )
