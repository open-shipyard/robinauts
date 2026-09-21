# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What every write must prove before anything reads it, and what every answer carries.

There is no CSRF token (``docs/specs/sign-in.md``, "Request protection").
Three checks stand in its place, on every request whose method is not
``GET``, ``HEAD`` or ``OPTIONS``:

1. **It came from this site.** ``Sec-Fetch-Site`` is set by the browser and
   cannot be set by a page. A write may carry ``same-origin``, or ``none``
   (a navigation the person typed or bookmarked), or no such header at all --
   a browser too old to send one, which check 3 is what covers for a request
   carrying a session. **Everything else is refused**, and that is an allow
   list rather than a list of the two values that mean another site:
   ``same-site`` is a sibling subdomain, which is not us either; and a value
   nobody here has heard of, or two values a proxy folded into one header
   with a comma, is not a statement anybody can act on. Reading the known-bad
   values instead would let ``same-origin, cross-site`` through as neither.
2. **It is JSON.** A form, and the few types a page may ``fetch`` without a
   preflight, cannot be ``application/json``; asking for that type makes the
   browser ask us first, and nothing here answers a preflight. This holds for
   every write, session or none.
3. **A cookie-authenticated write names its origin.** A cookie goes with
   whatever the browser sends, so a write that carries one must come from a
   page of the public URL: ``Origin`` equal to it, or -- for a browser that
   sends no ``Origin`` -- ``Sec-Fetch-Site: same-origin``.

Before any of the three: **each of those headers may appear once**, whatever
it is spelt like. A header sent twice is answered by the first value here and
by the second somewhere else, and "somewhere else" is a proxy, a cache or a
second parser -- which is how ``Sec-Fetch-Site: same-origin`` followed by
``Sec-Fetch-Site: cross-site`` becomes an accepted cross-site write. There is
no reading of two that is safe, so two is refused.

The names are lower-cased **here**, in one pass over the scope's own list, and
the cookies are read out of that same pass. ASGI says a server should hand
header names over in lower case and does not make it so, and the framework's
own header lookup compares what it was given: with a server that passes the
names through, ``Sec-Fetch-Site: cross-site`` beside
``sec-fetch-site: same-origin`` is two headers to us and one to it, and the
one it finds is whichever came first. Reading them once, by a name we folded
ourselves, is what makes "sent twice" mean sent twice.

**A refusal says a fixed sentence.** What was wrong with the request is the
request, and a body that repeated it would be reflecting whatever somebody
sent back at whoever they sent it through. The particulars -- the path, the
origin, which header -- go to the log, escaped and bounded
(``robinauts.api.logs``).

**It is middleware, not a dependency.** FastAPI reads a route's declared body
before it solves that route's dependencies, so a dependency would check the
request after the body was parsed; and a route added later could be written
without it. Here there is nothing to forget: every request to the application
passes through, whatever routes exist.

That also means it is outside the exception handlers, which live further in,
so it builds its refusal (``errors.refusal``) rather than raising it.

**What it does with a connection that is not a request.** A ``lifespan`` scope
is start-up and shutdown and passes through -- there is no request to check.
Everything else is **refused**, not passed on: the platform streams over
server-sent events (``docs/specs/wire.md``) and has no websocket route, and a
websocket is the one kind of connection that carries cookies and answers no
preflight, so a handler reachable over one would be reachable from any page on
the web. A websocket is closed with a policy-violation code before it is
accepted; a scope of a kind nothing here knows is not served at all.

``SecurityHeaders`` is the other half: what every HTTP answer carries whether
it succeeded or not. ``nosniff`` so that a JSON body is never read as a
script, and ``Referrer-Policy: same-origin`` so that a path of ours -- which
may name a conversation -- is not sent to whatever a person clicks through to.
It leaves every other kind of scope exactly as it found it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from starlette.datastructures import MutableHeaders
from starlette.requests import cookie_parser
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from robinauts.api.cookies import session_cookie
from robinauts.api.errors import refusal
from robinauts.api.logs import shown
from robinauts.domain import (
    CrossSiteRequestError,
    InvalidValueError,
    RobinautsError,
    SignInConfig,
    UnsupportedMediaTypeError,
)

_log = logging.getLogger(__name__)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
"""Methods that change nothing, and so have nothing to prove."""

SITE_ACCEPTED = frozenset({"same-origin", "none"})
"""The only ``Sec-Fetch-Site`` values a write may carry.

An allow list, not a deny list. ``cross-site`` and ``same-site`` are the two
that plainly mean another site's page, and they are not the only two strings
that are not ``same-origin``: a proxy that folds two headers into one sends
``same-origin, cross-site``, and a browser released next year may send a word
nothing here has read about. Neither says this request came from us.
"""

JSON_MEDIA_TYPE = "application/json"

DECIDING_HEADERS = ("sec-fetch-site", "content-type", "origin")
"""The headers a write is judged by; each may be sent once or not at all."""

COOKIE_HEADER = "cookie"
"""Read in the same pass, so that a session is found by the same folded names."""

CROSS_SITE_DETAIL = "a write must come from a page of this deployment"
MEDIA_TYPE_DETAIL = f"a write must be sent as {JSON_MEDIA_TYPE}"
REPEATED_HEADER_DETAIL = "a write may carry each of the headers it is judged by only once"
"""What a refusal says. Fixed sentences: a body repeats nothing that was sent."""

WEBSOCKET_POLICY_VIOLATION = 1008
"""The close code for a connection refused on principle rather than on error."""

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "same-origin"),
)
"""Carried by every answer; a route may still set one of them to something else."""


@dataclass(frozen=True, slots=True)
class Refusal:
    """A request that may not be taken: what is sent back, and what is written down."""

    error: RobinautsError
    """What crosses: one of the fixed sentences above, and no request in it."""
    because: str
    """What the log says: the particulars, already escaped and bounded."""


def request_headers(scope: Scope) -> dict[str, list[str]]:
    """The headers this judges a write by, read once and folded here.

    Every value of each, in the order they arrived, under a name this
    lower-cased itself -- so that two spellings of one header are two values
    of one name rather than two headers nobody compared.
    """
    found: dict[str, list[str]] = {name: [] for name in (*DECIDING_HEADERS, COOKIE_HEADER)}
    for raw_name, raw_value in scope.get("headers", ()):
        name = raw_name.decode("latin-1").strip().lower()
        if name in found:
            found[name].append(raw_value.decode("latin-1"))
    return found


def refused(scope: Scope, config: SignInConfig | None) -> Refusal | None:
    """Why this request may not be taken, or ``None`` if it may.

    ``config`` is the deployment's sign-in configuration, and ``None`` when
    none is configured: then no request carries a session of ours, and check 3
    has nothing to compare with. Checks 1 and 2 hold either way -- with nobody
    signed in there is no credential at all between another site's page and
    this API, which is the case that needs them most.

    Cross-site is answered before the media type: a request another site's
    page sent is refused for what it is, whatever it happens to carry.
    """
    method = str(scope.get("method", ""))
    if method in SAFE_METHODS:
        return None
    # The method is compared with a fixed set above and is escaped here: it
    # comes out of the scope, which is to say off the wire, and a log line is
    # a line until something in it is a newline.
    where = f"{shown(method, most=16)} {shown(scope.get('path', ''))}"
    sent = request_headers(scope)
    for name in DECIDING_HEADERS:
        if len(sent[name]) > 1:
            return Refusal(
                InvalidValueError(REPEATED_HEADER_DETAIL),
                f"{where} carries {len(sent[name])} {name} headers",
            )
    # Sent-and-empty is not the same as not sent: an empty header is a header
    # that says nothing, and a write that says nothing about where it came
    # from is refused wherever it does say something unreadable.
    site_sent = bool(sent["sec-fetch-site"])
    site = sent["sec-fetch-site"][0].strip().lower() if site_sent else ""
    if site_sent and site not in SITE_ACCEPTED:
        return Refusal(
            CrossSiteRequestError(CROSS_SITE_DETAIL),
            f"{where} carries sec-fetch-site {shown(site)}, which is not"
            f" {' or '.join(sorted(SITE_ACCEPTED))}",
        )
    media_type = ""
    if sent["content-type"]:
        media_type = sent["content-type"][0].partition(";")[0].strip().lower()
    if media_type != JSON_MEDIA_TYPE:
        return Refusal(
            UnsupportedMediaTypeError(MEDIA_TYPE_DETAIL),
            f"{where} was sent as {shown(media_type)}, not {JSON_MEDIA_TYPE}",
        )
    if config is None or not _session_held(sent, config):
        return None
    origin = sent["origin"][0] if sent["origin"] else None
    if origin is not None:
        # ``isascii`` before ``lower``: outside ASCII, case folding is not a
        # matter of thirty-two -- U+212A, the Kelvin sign, folds onto a plain
        # ``k`` -- and an origin is written in ASCII or is not one of ours.
        named = origin.strip().removesuffix("/")
        if named.isascii() and named.lower() == config.public_url:
            return None
    elif site == "same-origin":
        return None
    return Refusal(
        CrossSiteRequestError(CROSS_SITE_DETAIL),
        f"{where} with a session named origin"
        f" {shown(origin) if origin is not None else '<none>'},"
        f" not {config.public_url}",
    )


def _session_held(sent: dict[str, list[str]], config: SignInConfig) -> bool:
    """Whether the request carries this deployment's session cookie.

    Out of the same folded view as the rest: a ``Cookie:`` header found by one
    spelling and a ``cookie:`` header found by another would be a write that
    carries a session and is not checked for one.
    """
    name = session_cookie(secure=config.secure)
    return any(cookie_parser(header).get(name) for header in sent[COOKIE_HEADER])


class RequestProtection:
    """The checks, in front of the whole application, and nothing else served.

    Pure ASGI rather than ``BaseHTTPMiddleware``: it reads the request's
    headers and cookies out of the scope and never touches ``receive``, so a
    refused request is answered without a byte of its body being read.

    What it needs of the deployment -- the public URL and whether the cookie
    is ``Secure`` -- is read from the application's state at each request, not
    captured when the middleware is built: the composition root opens its
    collaborators in the ASGI lifespan, which runs after this object exists.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind == "lifespan":
            # Start-up and shutdown: no request, nothing to check.
            await self.app(scope, receive, send)
            return
        if kind == "websocket":
            await self._closed(scope, receive, send)
            return
        if kind != "http":
            _log.warning(
                "refusing an ASGI scope of type %s, which nothing here serves", shown(kind)
            )
            return
        sign_in = getattr(scope["app"].state, "sign_in", None)
        problem = refused(scope, None if sign_in is None else sign_in.config)
        if problem is None:
            await self.app(scope, receive, send)
            return
        _log.warning("refused: %s", problem.because)
        await refusal(problem.error)(scope, receive, send)

    async def _closed(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Close a websocket without accepting it, and without reaching a route.

        The handshake is answered before anything of ours sees it: nothing
        here is meant to be reachable over a websocket, and a websocket
        carries the session cookie and is not held back by any preflight.
        """
        _log.warning("refusing a websocket connection to %s", shown(scope.get("path", "")))
        # The handshake is answered only once it has been made. A client that
        # went away first sends ``websocket.disconnect``, and closing a
        # connection that is already gone is a message a server has nowhere to
        # put -- in some of them, an error of its own.
        first = await receive()
        if first.get("type") != "websocket.connect":
            return
        await send({"type": "websocket.close", "code": WEBSOCKET_POLICY_VIOLATION})


class SecurityHeaders:
    """Add ``SECURITY_HEADERS`` to every HTTP answer that does not set them itself."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, with_headers)
