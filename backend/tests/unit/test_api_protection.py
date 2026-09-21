# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What a write has to prove, in every combination that decides it.

There is no CSRF token here (``docs/specs/sign-in.md``), so these three checks
are the whole of what keeps another site's page from writing through somebody
else's browser. They are tested as a matrix rather than as a handful of
examples, because what matters is that no combination gets through: a write
that is JSON and cross-site, one that names the right origin and the wrong
type, one with a session and no origin at all.

Two things are proven beyond the matrix: that the checks run before anything
reads the request's body, and that they run on a route that never asked for
them -- which is what "cannot be forgotten" means.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from aio import asyncio_test
from robinauts.api import (
    CROSS_SITE_DETAIL,
    MEDIA_TYPE_DETAIL,
    REPEATED_HEADER_DETAIL,
    WEBSOCKET_POLICY_VIOLATION,
    create_api,
    session_cookie,
)
from webapp import (
    JSON,
    LOOPBACK_URL,
    PUBLIC_URL,
    cookie,
    open_session,
    running,
    serving,
    wired,
)

FORM = {"content-type": "application/x-www-form-urlencoded"}
OTHER_SITE = "https://not-robinauts.example.com"


def headers(*parts: dict[str, str] | None) -> dict[str, str]:
    """The given header dictionaries, merged; ``None`` contributes nothing."""
    merged: dict[str, str] = {}
    for part in parts:
        merged.update(part or {})
    return merged


@pytest.mark.parametrize(
    ("site", "status"),
    [
        ("same-origin", 204),
        ("none", 204),
        ("NONE", 204),
        (None, 204),
        ("cross-site", 403),
        ("same-site", 403),
        # A proxy that folds two headers into one, either way round.
        ("same-origin, cross-site", 403),
        ("cross-site, same-origin", 403),
        # A value nothing here has read about, and one that is not a value.
        ("some-future-word", 403),
        ("", 403),
        ("same-origin ", 204),
    ],
)
@asyncio_test
async def test_sec_fetch_site_decides_a_write_with_no_session(
    site: str | None, status: int
) -> None:
    """A write may say ``same-origin`` or ``none``, or say nothing at all.

    ``none`` is a navigation the person typed or bookmarked, and no header at
    all is a browser too old to send one; neither says another site sent it.
    Everything else is refused, because an allow list is the only reading of
    this header that is safe: ``same-origin, cross-site`` is what a proxy
    makes of two headers, and it is neither of the two words a deny list
    would look for.
    """
    async with serving(wired().sign_in) as client:
        answered = await client.post(
            "/auth/logout",
            headers=headers(JSON, None if site is None else {"sec-fetch-site": site}),
        )

    assert answered.status_code == status


@pytest.mark.parametrize(
    ("content_type", "status"),
    [
        ("application/json", 204),
        ("application/json; charset=utf-8", 204),
        ("APPLICATION/JSON", 204),
        ("text/plain", 415),
        ("application/x-www-form-urlencoded", 415),
        ("multipart/form-data; boundary=x", 415),
        ("", 415),
    ],
)
@asyncio_test
async def test_a_write_must_be_sent_as_json(content_type: str, status: int) -> None:
    """The types a form or a plain ``fetch`` may use cannot be JSON."""
    async with serving(wired().sign_in) as client:
        answered = await client.post(
            "/auth/logout",
            headers={"content-type": content_type} if content_type else {},
        )

    assert answered.status_code == status
    if status == 415:
        assert answered.json()["error"] == "UnsupportedMediaTypeError"


@pytest.mark.parametrize(
    ("origin", "site", "status"),
    [
        (PUBLIC_URL, None, 204),
        (f"{PUBLIC_URL}/", None, 204),
        (PUBLIC_URL.upper(), None, 204),
        (OTHER_SITE, None, 403),
        ("null", None, 403),
        ("", "same-origin", 403),
        (None, "same-origin", 204),
        (None, None, 403),
        (None, "none", 403),
    ],
)
@asyncio_test
async def test_a_write_carrying_a_session_must_name_this_origin(
    origin: str | None, site: str | None, status: int
) -> None:
    """A cookie goes with whatever the browser sends, so the page must be ours.

    With no ``Origin`` header, ``Sec-Fetch-Site: same-origin`` is what stands
    in its place; anything else -- an origin that is not ours, ``null`` from a
    sandboxed frame, an empty one, a browser that says neither -- is refused.
    An empty header is a header: it names an origin that is not this one, and
    ``same-origin`` beside it does not make it ours.
    """
    deployment = wired()
    secret, _ = await open_session(deployment)

    async with serving(deployment.sign_in) as client:
        answered = await client.post(
            "/auth/logout",
            headers=headers(
                JSON,
                cookie(session_cookie(secure=True), secret),
                {"origin": origin} if origin is not None else None,
                {"sec-fetch-site": site} if site else None,
            ),
        )

    assert answered.status_code == status
    if status == 403:
        assert answered.json()["error"] == "CrossSiteRequestError"


@asyncio_test
async def test_a_write_without_a_session_needs_no_origin() -> None:
    """Nothing is being spent on the person's behalf, so there is nothing to bind."""
    async with serving(wired().sign_in) as client:
        answered = await client.post("/auth/logout", headers=JSON)

    assert answered.status_code == 204


@asyncio_test
async def test_a_loopback_deployment_checks_its_own_origin() -> None:
    deployment = wired(public_url=LOOPBACK_URL)
    secret, _ = await open_session(deployment)
    held = cookie(session_cookie(secure=False), secret)

    async with serving(deployment.sign_in, base_url=LOOPBACK_URL) as client:
        its_own = await client.post(
            "/auth/logout", headers=headers(JSON, held, {"origin": LOOPBACK_URL})
        )
        another = await client.post(
            "/auth/logout", headers=headers(JSON, held, {"origin": PUBLIC_URL})
        )

    assert (its_own.status_code, another.status_code) == (204, 403)


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
@asyncio_test
async def test_a_safe_method_proves_nothing(method: str) -> None:
    """A read changes nothing, so none of the three checks applies to it."""
    async with serving(wired().sign_in) as client:
        answered = await client.request(method, "/health", headers={"sec-fetch-site": "cross-site"})

    # OPTIONS is not routed -- nothing here answers a preflight -- but it is
    # not refused as cross-site either, which is what this is about.
    assert answered.status_code in (200, 405)


class Written(BaseModel):
    text: str


def writing_app() -> tuple[FastAPI, list[str]]:
    """An application with a route that declares a body and records being reached."""
    app = create_api(wired().sign_in)
    reached: list[str] = []

    @app.post("/write")
    async def write(body: Written) -> dict[str, str]:
        reached.append(body.text)
        return {"wrote": body.text}

    return app, reached


@asyncio_test
async def test_a_refused_write_never_reaches_the_route_or_its_body() -> None:
    """The checks are middleware, so nothing reads the body to refuse it.

    The route declares a body FastAPI would parse before it solved any
    dependency of that route, and the body sent is not JSON at all. A 415 --
    rather than a 422 about the body -- is how one tells that nothing looked.
    """
    app, reached = writing_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=PUBLIC_URL
    ) as client:
        answered = await client.post("/write", content=b"not json at all", headers=FORM)

    assert answered.status_code == 415
    assert reached == []


@asyncio_test
async def test_a_route_that_declared_nothing_is_protected_all_the_same() -> None:
    """A route added without a thought for any of this still passes the checks."""
    app, reached = writing_app()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=PUBLIC_URL
    ) as client:
        refused = await client.post(
            "/write", json={"text": "hello"}, headers={"sec-fetch-site": "cross-site"}
        )
        allowed = await client.post("/write", json={"text": "hello"})

    assert (refused.status_code, allowed.status_code) == (403, 200)
    assert reached == ["hello"]


@asyncio_test
async def test_a_deployment_with_no_sign_in_still_refuses_a_cross_site_write() -> None:
    """The first two checks hold with nobody signed in; the third has no session."""
    async with serving(None) as client:
        refused = await client.post(
            "/auth/logout", headers=headers(JSON, {"sec-fetch-site": "cross-site"})
        )
        allowed = await client.post("/auth/logout", headers=JSON)

    assert (refused.status_code, allowed.status_code) == (403, 204)


@pytest.mark.parametrize("path", ["/health", "/auth/session", "/openapi.json"])
@asyncio_test
async def test_every_answer_carries_the_security_headers(path: str) -> None:
    async with serving(wired().sign_in) as client:
        answered = await client.get(path)

    assert answered.headers["x-content-type-options"] == "nosniff"
    assert answered.headers["referrer-policy"] == "same-origin"


@asyncio_test
async def test_a_refusal_carries_them_too() -> None:
    async with serving(wired().sign_in) as client:
        refused = await client.post("/auth/logout", headers=FORM)

    assert refused.status_code == 415
    assert refused.headers["x-content-type-options"] == "nosniff"


# Requests that are not requests, and headers sent twice.


def http_scope(method: str, path: str, headers: list[tuple[bytes, bytes]]) -> dict[str, object]:
    """One HTTP scope, written out, so a test can send what a client will not.

    ``httpx`` will not send the same header twice, and that is exactly the
    request worth asking about: a proxy or a second parser between here and a
    browser may read the value this one did not.
    """
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 51234),
        "server": ("robinauts.example.com", 443),
    }


async def driven(app: Any, scope: dict[str, object], *, incoming: Any = None) -> list[Any]:
    """Drive ``app`` with that scope by hand and collect everything it sent."""
    waiting = list(incoming or [{"type": "http.request", "body": b"{}", "more_body": False}])
    sent: list[Any] = []

    async def receive() -> Any:
        return waiting.pop(0) if waiting else {"type": "http.disconnect"}

    async def send(message: Any) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


def answered(sent: list[Any]) -> tuple[int, bytes]:
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in sent if message["type"] == "http.response.body"
    )
    return start["status"], body


@pytest.mark.parametrize(
    ("name", "values"),
    [
        (b"sec-fetch-site", [b"same-origin", b"cross-site"]),
        (b"sec-fetch-site", [b"cross-site", b"same-origin"]),
        (b"content-type", [b"application/json", b"text/plain"]),
        (b"content-type", [b"text/plain", b"application/json"]),
        (b"origin", [PUBLIC_URL.encode(), OTHER_SITE.encode()]),
        (b"origin", [OTHER_SITE.encode(), PUBLIC_URL.encode()]),
    ],
)
@asyncio_test
async def test_a_deciding_header_sent_twice_is_refused(name: bytes, values: list[bytes]) -> None:
    """Whichever of the two is read, some other parser reads the other one.

    Reading the first would accept a request whose second value is
    ``cross-site``; reading the last would accept one whose first is. There is
    no reading of two that is safe, so two is not read at all.
    """
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    headers = [(b"cookie", f"__Host-robinauts_session={secret}".encode())]
    headers += [(name, value) for value in values]
    if name != b"content-type":
        headers.append((b"content-type", b"application/json"))

    status, body = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 422
    assert json.loads(body) == {
        "error": "InvalidValueError",
        "detail": REPEATED_HEADER_DETAIL,
    }


@asyncio_test
async def test_one_of_each_deciding_header_is_still_taken() -> None:
    """The check above is about two, not about one: a plain write still works."""
    app = create_api(wired().sign_in)
    headers = [(b"content-type", b"application/json"), (b"sec-fetch-site", b"same-origin")]

    status, _ = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 204


@asyncio_test
async def test_a_websocket_is_closed_before_it_is_accepted() -> None:
    """Nothing here is reachable over one, and a websocket answers no preflight.

    So it is refused by the middleware, on the handshake, whether or not a
    route exists -- and with the policy-violation code, which says it was
    refused rather than that something went wrong.
    """
    app = create_api(wired().sign_in)
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "scheme": "wss",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"cookie", b"__Host-robinauts_session=whatever")],
        "client": ("127.0.0.1", 51234),
        "server": ("robinauts.example.com", 443),
        "subprotocols": [],
    }

    sent = await driven(app, scope, incoming=[{"type": "websocket.connect"}])

    assert sent == [{"type": "websocket.close", "code": WEBSOCKET_POLICY_VIOLATION}]
    assert not any(message["type"] == "websocket.accept" for message in sent)


@asyncio_test
async def test_a_scope_of_a_kind_nothing_here_serves_is_not_served() -> None:
    app = create_api(wired().sign_in)

    sent = await driven(app, {"type": "tcp"}, incoming=[{"type": "tcp.connect"}])

    assert sent == []


@asyncio_test
async def test_the_lifespan_scope_passes_through() -> None:
    """Start-up and shutdown are not requests, and are not checked as ones."""
    app = create_api(wired().sign_in)

    async with running(app):
        assert app.state.sign_in is not None


@pytest.mark.parametrize(
    "spellings",
    [
        [(b"Sec-Fetch-Site", b"cross-site"), (b"sec-fetch-site", b"same-origin")],
        [(b"sec-fetch-site", b"same-origin"), (b"SEC-FETCH-SITE", b"cross-site")],
        [(b"Origin", OTHER_SITE.encode()), (b"origin", PUBLIC_URL.encode())],
        [(b"Content-Type", b"text/plain"), (b"content-type", b"application/json")],
    ],
)
@asyncio_test
async def test_one_header_spelt_two_ways_is_still_two_headers(
    spellings: list[tuple[bytes, bytes]],
) -> None:
    """ASGI says a server *should* lower-case header names, and does not make it so.

    A framework that looks a header up by comparing what it was given finds
    one of the two and never notices the other, which is how
    ``Sec-Fetch-Site: cross-site`` beside ``sec-fetch-site: same-origin``
    becomes an accepted cross-site write. The names are folded here, in one
    pass, so two spellings are two values of one name.
    """
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    headers = [(b"cookie", f"__Host-robinauts_session={secret}".encode()), *spellings]
    if not any(name.lower() == b"content-type" for name, _ in spellings):
        headers.append((b"content-type", b"application/json"))

    status, body = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 422
    assert json.loads(body)["detail"] == REPEATED_HEADER_DETAIL
    assert deployment.store.sessions != {}


@asyncio_test
async def test_a_session_cookie_is_found_however_the_header_is_spelt() -> None:
    """The cookie is read out of the same folded view as everything else.

    A ``Cookie:`` header the origin check did not see would be a write that
    carries a session and was never asked where it came from.
    """
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    headers = [
        (b"Cookie", f"__Host-robinauts_session={secret}".encode()),
        (b"content-type", b"application/json"),
    ]

    status, body = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 403
    assert json.loads(body)["detail"] == CROSS_SITE_DETAIL
    assert deployment.store.sessions != {}


HOSTILE_PATH = "/auth/logout/" + "\nSep 21 12:00 forged: everything is fine" + "x" * 900
HOSTILE_ORIGIN = "https://evil.example.com/\n\rSet-Cookie: x=1" + "y" * 900


@pytest.mark.parametrize(
    ("headers", "status", "detail"),
    [
        ([(b"content-type", b"text/plain")], 415, MEDIA_TYPE_DETAIL),
        (
            [(b"content-type", b"application/json"), (b"sec-fetch-site", b"cross-site")],
            403,
            CROSS_SITE_DETAIL,
        ),
    ],
)
@asyncio_test
async def test_a_refusal_repeats_nothing_the_request_carried(
    headers: list[tuple[bytes, bytes]], status: int, detail: str
) -> None:
    """The body says a fixed sentence. What it was is in the log, and nowhere else."""
    app = create_api(wired().sign_in)

    sent, body = answered(await driven(app, http_scope("POST", HOSTILE_PATH, headers)))

    assert sent == status
    assert json.loads(body) == {
        "error": "UnsupportedMediaTypeError" if status == 415 else "CrossSiteRequestError",
        "detail": detail,
    }
    assert "forged" not in body.decode()
    assert len(body) < 200


@asyncio_test
async def test_a_cookie_bearing_write_from_elsewhere_names_no_origin_back() -> None:
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    headers = [
        (b"cookie", f"__Host-robinauts_session={secret}".encode()),
        (b"content-type", b"application/json"),
        (b"origin", HOSTILE_ORIGIN.encode("latin-1")),
    ]

    status, body = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 403
    assert json.loads(body) == {"error": "CrossSiteRequestError", "detail": CROSS_SITE_DETAIL}
    assert "evil.example.com" not in body.decode()


@asyncio_test
async def test_what_is_logged_cannot_make_a_line_of_its_own(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A path arrives percent-decoded, so ``%0A`` in one is a real newline.

    Written out as it came, it would not go into a log line: it would make
    new ones, of whatever shape whoever sent it chose, in the middle of the
    record of what the deployment did.
    """
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    forging = "/auth/logout\nSep 21 12:00 WARNING nothing to see here"

    with caplog.at_level(logging.WARNING):
        await driven(
            app,
            http_scope(
                "POST",
                forging,
                [
                    (b"cookie", f"__Host-robinauts_session={secret}".encode()),
                    (b"content-type", b"application/json"),
                    (b"origin", b"https://evil.example.com"),
                ],
            ),
        )
        await driven(
            app,
            {
                "type": "websocket",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "scheme": "wss",
                "path": forging,
                "raw_path": forging.encode(),
                "query_string": b"",
                "root_path": "",
                "headers": [],
                "client": ("127.0.0.1", 51234),
                "server": ("robinauts.example.com", 443),
                "subprotocols": [],
            },
            incoming=[{"type": "websocket.connect"}],
        )

    assert caplog.records, "nothing was logged at all"
    for record in caplog.records:
        assert "\n" not in record.getMessage()
        assert "nothing to see here" in record.getMessage()  # escaped, on one line
        assert "\\n" in record.getMessage()


@asyncio_test
async def test_what_is_logged_is_bounded(caplog: pytest.LogCaptureFixture) -> None:
    """A log that can be filled a megabyte at a time is a log that loses things."""
    app = create_api(wired().sign_in)

    with caplog.at_level(logging.WARNING):
        await driven(
            app,
            http_scope("POST", "/" + "z" * 100_000, [(b"content-type", b"text/plain")]),
        )

    assert caplog.records
    for record in caplog.records:
        assert len(record.getMessage()) < 500
        assert "more" in record.getMessage()


@asyncio_test
async def test_a_folded_sec_fetch_site_does_not_get_in_by_being_neither(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One header, two values, a comma: refused, and the value in the log."""
    deployment = wired()
    secret, _ = await open_session(deployment)
    app = create_api(deployment.sign_in)
    headers = [
        (b"cookie", f"__Host-robinauts_session={secret}".encode()),
        (b"content-type", b"application/json"),
        (b"sec-fetch-site", b"same-origin, cross-site"),
    ]

    with caplog.at_level(logging.WARNING):
        status, body = answered(await driven(app, http_scope("POST", "/auth/logout", headers)))

    assert status == 403
    assert json.loads(body) == {"error": "CrossSiteRequestError", "detail": CROSS_SITE_DETAIL}
    assert deployment.store.sessions != {}
    assert "same-origin, cross-site" in caplog.text


@asyncio_test
async def test_a_websocket_that_went_away_is_not_answered() -> None:
    """A client that disconnected before the handshake gets no close message.

    Closing a connection that is already gone is a message a server has
    nowhere to put, and in some of them an error of its own.
    """
    app = create_api(wired().sign_in)
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "scheme": "wss",
        "path": "/ws",
        "raw_path": b"/ws",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 51234),
        "server": ("robinauts.example.com", 443),
        "subprotocols": [],
    }

    sent = await driven(app, scope, incoming=[{"type": "websocket.disconnect", "code": 1006}])

    assert sent == []


@asyncio_test
async def test_a_method_cannot_make_a_line_of_its_own(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The method comes off the wire like everything else in the scope."""
    app = create_api(wired().sign_in)
    forging = "POST\nSep 21 12:00 WARNING nothing to see here"

    with caplog.at_level(logging.WARNING):
        await driven(
            app,
            http_scope(forging, "/auth/logout", [(b"content-type", b"text/plain")]),
        )

    assert caplog.records
    for record in caplog.records:
        assert "\n" not in record.getMessage()
        assert "\\n" in record.getMessage()
