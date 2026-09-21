# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Signing in to the interface, and out: the ``/auth`` routes.

::

    GET  /auth/session             whether sign-in is on, with whom, and who is in
    GET  /auth/login/{provider}    begin: a redirect to the provider
    GET  /auth/callback/{provider} the redirect URI registered with the provider
    POST /auth/logout              end the session

All four are public: a person with no session reaches every one of them, and
``/auth/session`` in particular is **never a 401** -- "nobody is signed in" is
an answer, not a refusal, and it is the answer the interface starts from.
Sign-out is a write, so it takes a write's checks
(``robinauts.api.protection``), origin included: no other site may sign a
person out.

The two middle routes are browser navigations rather than calls, so they are
out of the OpenAPI document: nothing generates a client for them, and what
they answer is a ``Location`` header.

**A sign-in that fails says one word.** Whatever went wrong -- a state that
does not match, a provider that refused the code, an allow list that does not
have the person -- the browser is sent to the sign-in page with one of the
fixed codes of ``docs/specs/sign-in.md``, and the detail, which may repeat
what a provider said, goes to the log. The codes are a closed set that the
interface knows; the provider's words are for whoever runs the deployment.

The design is neorc's, written again for this layout; recorded in
``docs/legal/ip-clearance.md``.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from robinauts.api.access import CurrentUser, public, signing_in
from robinauts.api.cookies import clear_cookie, login_cookie, session_cookie, set_cookie
from robinauts.api.errors import error_body
from robinauts.api.logs import shown
from robinauts.api.schemas import (
    ErrorResponse,
    ProviderSummary,
    SessionResponse,
    UserSummary,
)
from robinauts.application import SignIn
from robinauts.domain import SignInError, UnknownProviderError, is_provider_id

_log = logging.getLogger(__name__)

NO_STORE = "no-store"
"""Every answer here carries a cookie, a redirect or who is signed in."""

UI_PATH = "/ui/"
"""Where the interface is served; a sign-in ends by landing in it."""

SIGN_IN_PAGE = f"{UI_PATH}#/sign-in?error="
"""The hash route the interface shows in place of every page, and its code."""

NO_SIGN_IN = "this deployment has no sign-in configuration"

MISSHAPEN_PROVIDER = "the provider named in the path is not spelt as a provider id"
"""What is logged and redirected for when the id could not be one at all.

Never the id itself: that is a path parameter, which is to say whatever was in
the link somebody followed. It goes in the log through
``robinauts.api.logs.shown`` and into no answer at all.
"""

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.get("/session", dependencies=[public()])
async def read_session(request: Request, response: Response, user: CurrentUser) -> SessionResponse:
    """Whether sign-in is configured, the providers, and who is signed in.

    The interface asks this first and on every reload. It answers 200 to
    everybody: an expired cookie and no cookie at all are both ``user: null``.
    """
    response.headers["cache-control"] = NO_STORE
    sign_in = signing_in(request)
    if sign_in is None:
        return SessionResponse(sign_in=False)
    return SessionResponse(
        sign_in=True,
        public_url=sign_in.config.public_url,
        providers=[
            ProviderSummary(id=provider.id, title=provider.title)
            for provider in sign_in.config.providers.values()
        ],
        user=None if user is None else UserSummary.of(user),
    )


# A browser navigation, not a call: out of the schema.
@auth_router.get("/login/{provider}", include_in_schema=False, dependencies=[public()])
async def begin_sign_in(request: Request, provider: str, return_to: str | None = None) -> Response:
    """Begin a sign-in: a pending sign-in, the state in a cookie, a redirect.

    ``return_to`` is where in the interface the person was. It is whatever was
    in the link they followed, so the application checks it
    (``core.safe_return_to``) before it is stored and again before it is used;
    nothing here trusts it.
    """
    sign_in = _configured(request)
    misshapen = _misshapen(sign_in, provider)
    if misshapen is not None:
        return misshapen
    try:
        begun = await sign_in.begin(provider, return_to=return_to)
    except SignInError as exc:
        return _failed(sign_in, exc)
    response = _navigation(begun.authorization_url)
    set_cookie(
        response,
        login_cookie(secure=sign_in.config.secure),
        begun.state,
        seconds=sign_in.pending_login_life.total_seconds(),
        secure=sign_in.config.secure,
    )
    return response


@auth_router.get("/callback/{provider}", include_in_schema=False, dependencies=[public()])
async def finish_sign_in(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Response:
    """Finish the sign-in the provider sent the browser back from.

    The ``state`` in the query must be the one in the cookie; everything after
    that -- taking the pending sign-in, exchanging the code, checking the
    claims, asking the allow list -- is the application's, and every refusal it
    raises ends at the sign-in page.
    """
    sign_in = _configured(request)
    secure = sign_in.config.secure
    misshapen = _misshapen(sign_in, provider)
    if misshapen is not None:
        return misshapen
    try:
        opened = await sign_in.complete(
            provider,
            state=state,
            cookie_state=request.cookies.get(login_cookie(secure=secure)),
            code=code,
            error=error,
        )
    except SignInError as exc:
        return _failed(sign_in, exc)
    except Exception as exc:
        # However this broke, the sign-in is over. A state cookie left in the
        # browser would be offered to the next callback that arrives, which is
        # a sign-in somebody else began waiting to be finished by this one.
        # ``CancelledError`` is a ``BaseException`` and is not caught: a
        # dropped request is not a sign-in that failed.
        _log.exception("the callback of a sign-in raised %s", type(exc).__name__)
        broken = JSONResponse(error_body(exc, 500), status_code=500)
        broken.headers["cache-control"] = NO_STORE
        clear_cookie(broken, login_cookie(secure=secure), secure=secure)
        return broken
    # The name and the subject come out of an ID token, which is to say from
    # outside: escaped, like everything else that did.
    _log.info(
        "%s signed in with %s",
        shown(opened.user.email or opened.user.subject),
        shown(opened.user.provider),
    )
    response = _navigation(_landing(sign_in.config.public_url, opened.return_to))
    clear_cookie(response, login_cookie(secure=secure), secure=secure)
    set_cookie(
        response,
        session_cookie(secure=secure),
        opened.secret,
        seconds=sign_in.session_life.total_seconds(),
        secure=secure,
    )
    return response


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[public()],
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorResponse},
    },
)
async def sign_out(request: Request) -> Response:
    """End the session, if there is one, and clear its cookie.

    Idempotent: signing out twice, or without ever having signed in, is 204
    both times. The cookie is cleared either way, so a browser holding one
    that no longer names a session stops sending it.
    """
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["cache-control"] = NO_STORE
    sign_in = signing_in(request)
    if sign_in is None:
        return response
    secure = sign_in.config.secure
    name = session_cookie(secure=secure)
    secret = request.cookies.get(name)
    if secret:
        await sign_in.sign_out(secret)
    clear_cookie(response, name, secure=secure)
    return response


def _configured(request: Request) -> SignIn:
    """The deployment's sign-in; 404 when it has none to offer.

    There is no sign-in page to send anybody to when there is no sign-in, so
    this one is a refusal rather than a redirect.
    """
    sign_in = signing_in(request)
    if sign_in is None:
        raise UnknownProviderError(f"a sign-in route was asked for, and {NO_SIGN_IN}")
    return sign_in


def _misshapen(sign_in: SignIn, provider: str) -> Response | None:
    """The sign-in page, if the id in the path could not be a provider id at all.

    The id is checked for **shape** before anything else looks at it
    (``domain.is_provider_id``), because it arrives as a path parameter and is
    therefore as long as, and spelt with whatever, the link that carried it
    liked. Unchecked it would reach a message, and a message reaches a log; a
    log line built out of a request is a log line somebody else can write.

    These two are navigations, so the answer is the one every other failed
    sign-in gets -- the sign-in page, ``unknown_provider``, the login cookie
    cleared -- rather than a JSON refusal a browser would show as a blank
    page. Whether a well-formed id names a provider that exists is the
    configuration's question, asked after this.
    """
    if is_provider_id(provider):
        return None
    _log.warning("a sign-in route was asked for %s, which is not a provider id", shown(provider))
    return _failed(sign_in, UnknownProviderError(MISSHAPEN_PROVIDER))


def _navigation(url: str) -> Response:
    """A 303 to ``url``, which is never to be kept by anything in between."""
    response = RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)
    response.headers["cache-control"] = NO_STORE
    return response


def _failed(sign_in: SignIn, exc: SignInError) -> Response:
    """Send the browser to the sign-in page with the code, and log the rest.

    The login cookie goes: whatever the sign-in was, it is over, and a state
    cookie left behind would be offered to the next callback that arrives.
    """
    _log.warning("sign-in failed, %s: %s", exc.code.value, shown(exc.detail))
    secure = sign_in.config.secure
    response = _navigation(f"{sign_in.config.public_url}{SIGN_IN_PAGE}{quote(exc.code.value)}")
    clear_cookie(response, login_cookie(secure=secure), secure=secure)
    return response


def _landing(public_url: str, return_to: str) -> str:
    """Where a finished sign-in lands: the interface, at the route asked for.

    ``return_to`` is a path of this origin that the application has checked
    twice (``core.safe_return_to``). The interface routes on the hash
    (``docs/specs/frontend.md``), so what is carried over is the hash and
    nothing else: a target that names no route -- ``/``, which is the default
    -- lands on the interface's own first page.
    """
    _, marker, route = return_to.partition("#")
    return f"{public_url}{UI_PATH}{marker}{route}"
