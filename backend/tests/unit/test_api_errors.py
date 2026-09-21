# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""How an error crosses HTTP, and what a 500 is careful not to say.

Two things are worth a test of their own. One: the table of statuses is
exhaustive, so that an error class added to ``domain`` without a status is a
failing test rather than a route quietly answering 500. Two: nothing a bug
knows reaches the browser -- not the message, not the type, not the traceback
-- while all of it reaches the log.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from aio import asyncio_test
from robinauts.api import (
    GENERIC_DETAIL,
    INTERNAL_ERROR,
    MAX_DETAIL_CHARS,
    SIGN_IN_DETAIL,
    STATUS_OF,
    create_api,
    public,
    status_of,
)
from robinauts.domain import (
    AuthenticationError,
    ConfigError,
    InvalidValueError,
    RobinautsError,
    SchemaError,
    SignInError,
    SignInErrorCode,
)
from webapp import PUBLIC_URL, wired

SECRET_IN_A_BUG = "a-row-nobody-outside-should-see"


def every_error() -> list[type[RobinautsError]]:
    """Every error class the platform defines, however deeply nested."""
    found: list[type[RobinautsError]] = []

    def walk(cls: type[RobinautsError]) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__module__.startswith("robinauts."):
                found.append(subclass)
                walk(subclass)

    walk(RobinautsError)
    return found


def test_every_platform_error_has_a_status_of_its_own() -> None:
    """Not "resolves to one through a base class": one written down for it.

    A class left out would answer 500 through ``RobinautsError``, which is how
    a refusal becomes an outage.
    """
    listed = set(STATUS_OF)

    assert set(every_error()) <= listed
    assert listed <= {RobinautsError, *every_error()}


def test_the_statuses_are_what_they_should_be() -> None:
    assert status_of(AuthenticationError("no")) == 401
    assert status_of(InvalidValueError("no")) == 422
    assert status_of(ConfigError(["no"])) == 500
    assert status_of(SchemaError.missing(expected=1)) == 500
    # A subclass nobody listed still resolves, through its nearest base.
    assert status_of(type("Later", (AuthenticationError,), {})("no")) == 401


class Counted(BaseModel):
    how_many: int


def leaking_app() -> FastAPI:
    """An application whose routes fail in the ways a route can."""
    app = create_api(wired().sign_in)

    @app.get("/bug", dependencies=[public()])
    async def bug() -> dict[str, str]:
        raise RuntimeError(f"the query returned {SECRET_IN_A_BUG}")

    @app.get("/ours", dependencies=[public()])
    async def ours() -> dict[str, str]:
        raise ConfigError([f"the deployment is misconfigured: {SECRET_IN_A_BUG}"])

    @app.get("/refused", dependencies=[public()])
    async def refused() -> dict[str, str]:
        raise InvalidValueError("a value nobody can work with")

    @app.get("/sign-in-failed", dependencies=[public()])
    async def sign_in_failed() -> dict[str, str]:
        raise SignInError(
            SignInErrorCode.PROVIDER_REFUSED,
            f"the provider said {SECRET_IN_A_BUG} about {SECRET_IN_A_BUG}",
        )

    @app.get("/number/{value}", dependencies=[public()])
    async def number(value: int) -> dict[str, int]:
        return {"value": value}

    @app.post("/counted", dependencies=[public()])
    async def counted(body: Counted) -> dict[str, int]:  # pragma: no cover -- always refused
        return {"how_many": body.how_many}

    return app


def quiet(app: FastAPI) -> httpx.AsyncClient:
    """A client that lets the application answer a bug rather than re-raising."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url=PUBLIC_URL,
    )


@pytest.mark.parametrize("path", ["/bug", "/ours"])
@asyncio_test
async def test_a_500_says_nothing_about_what_went_wrong(
    path: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug of ours and an error of ours both answer the same empty 500."""
    with caplog.at_level(logging.ERROR):
        async with quiet(leaking_app()) as client:
            answered = await client.get(path)

    assert answered.status_code == 500
    assert answered.json() == {"error": INTERNAL_ERROR, "detail": GENERIC_DETAIL}
    assert SECRET_IN_A_BUG not in answered.text
    assert "RuntimeError" not in answered.text and "ConfigError" not in answered.text
    assert "Traceback" not in answered.text
    # And all of it is in the log, which is where an operator reads it.
    assert SECRET_IN_A_BUG in caplog.text


@asyncio_test
async def test_a_500_still_carries_the_security_headers() -> None:
    """Even the answer Starlette builds outside our middleware carries them."""
    async with quiet(leaking_app()) as client:
        answered = await client.get("/bug")

    assert answered.headers["x-content-type-options"] == "nosniff"


@asyncio_test
async def test_a_refusal_names_its_class_and_says_why() -> None:
    async with quiet(leaking_app()) as client:
        answered = await client.get("/refused")

    assert answered.status_code == 422
    assert answered.json() == {
        "error": "InvalidValueError",
        "detail": "a value nobody can work with",
    }


@asyncio_test
async def test_an_unreadable_parameter_is_refused_in_the_same_shape() -> None:
    """FastAPI's own validation error, answered the way everything else is."""
    async with quiet(leaking_app()) as client:
        answered = await client.get("/number/not-a-number")

    assert answered.status_code == 422
    assert answered.json()["error"] == "InvalidValueError"
    assert "value" in answered.json()["detail"]


@asyncio_test
async def test_a_sign_in_failure_says_one_fixed_sentence_and_nothing_of_its_own(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ``SignInError``'s detail is written for the log: it holds a provider's
    words and the values a request carried. What crosses is the sentence the
    code stands for, which is the same closed set the sign-in page knows.
    """
    with caplog.at_level(logging.WARNING):
        async with quiet(leaking_app()) as client:
            answered = await client.get("/sign-in-failed")

    assert answered.status_code == 403
    assert answered.json() == {
        "error": "SignInError",
        "detail": SIGN_IN_DETAIL[SignInErrorCode.PROVIDER_REFUSED],
    }
    assert SECRET_IN_A_BUG not in answered.text
    assert SECRET_IN_A_BUG in caplog.text


def test_every_code_has_a_sentence_of_its_own() -> None:
    """An unlisted code would be a ``KeyError`` in a handler, which is a 500."""
    assert set(SIGN_IN_DETAIL) == set(SignInErrorCode)
    assert len(set(SIGN_IN_DETAIL.values())) == len(SignInErrorCode)


@asyncio_test
async def test_a_path_that_is_not_routed_answers_in_the_project_shape() -> None:
    async with quiet(leaking_app()) as client:
        answered = await client.get("/nowhere-at-all")

    assert answered.status_code == 404
    assert answered.json() == {"error": "NotFound", "detail": "not found"}
    assert answered.headers["x-content-type-options"] == "nosniff"


@asyncio_test
async def test_a_method_that_is_not_allowed_says_which_are() -> None:
    """The same shape, and the ``Allow`` header a client reads is kept."""
    async with quiet(leaking_app()) as client:
        answered = await client.request(
            "DELETE", "/health", headers={"content-type": "application/json"}
        )

    assert answered.status_code == 405
    assert answered.json() == {"error": "MethodNotAllowed", "detail": "method not allowed"}
    assert answered.headers["allow"] == "GET"
    assert answered.headers["referrer-policy"] == "same-origin"


@asyncio_test
async def test_a_body_that_could_not_be_read_names_the_field_and_not_the_value() -> None:
    """Pydantic's error carries the ``input`` it refused: that is what was sent.

    A password in the wrong field, a token pasted where a number goes -- the
    answer says which field and which rule, and gives the value back to
    nobody.
    """
    async with quiet(leaking_app()) as client:
        answered = await client.post("/counted", json={"how_many": SECRET_IN_A_BUG})

    assert answered.status_code == 422
    body = answered.json()
    assert body["error"] == "InvalidValueError"
    assert "how_many" in body["detail"]
    assert SECRET_IN_A_BUG not in answered.text
    assert len(body["detail"]) <= MAX_DETAIL_CHARS


@asyncio_test
async def test_a_detail_built_from_a_request_is_bounded() -> None:
    """Many wrong fields at once do not become a page of a body."""
    async with quiet(leaking_app()) as client:
        answered = await client.post(
            "/counted", json={"how_many": ["x" * 2000] * 50, "extra": "y" * 5000}
        )

    assert answered.status_code == 422
    assert len(answered.json()["detail"]) <= MAX_DETAIL_CHARS
