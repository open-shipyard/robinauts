# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""How a platform error crosses HTTP: one status per class, one body shape.

Every ``RobinautsError`` answers with the status its class is listed under and
a body naming the class::

    {"error": "AuthenticationError", "detail": "sign in at /ui/"}

The class name is what a client branches on -- several classes share a status,
and "403" does not say whether to sign in again or to give up -- so it is sent
rather than left to be guessed from the status. Starlette's own refusals, a
404 and a 405, are put in the same shape, so that a client has one kind of
error body to understand and not two.

**One answer for everything that is not there.** A conversation that does not
exist, a message that does not, a run that does not, and one that exists and
belongs to somebody else all answer the *same* body -- ``NotFoundError`` and
one fixed sentence -- with the same status and the same headers. The
difference between "no such id" and "not yours" is the whole of what an
attacker wants from an id, and a body that named the class would hand it over
while the status hid it. Which of them it really was goes to the log.

**A body never repeats what the request carried.** Three rules, and each of
them exists because something once did:

- **nothing that answers 5xx says why.** A 500 is a mistake of ours, and its
  message is written for an operator: it may hold a query, a row, the name of
  a variable. The browser is told that the request could not be served, and
  the whole of it goes to the log -- **with the chain of causes and the frames
  of the innermost one**, because an error of ours often says only what kind
  of thing went wrong, and because a reader that turns anything it meets into
  one sentence turns a bug of ours into it too (``chain``, ``where``). The
  same for an exception that is not ours at all, which is the ordinary way a
  bug becomes a response;
- **a sign-in failure says one fixed sentence per code.** A ``SignInError``'s
  own ``detail`` is written for the log: it repeats a provider's words and the
  values a request carried. The routes answer these with a redirect and never
  reach here, and one that does is still not going to reflect its input back;
- **a request that could not be read names the field and the rule**, never
  the value. Pydantic's error carries the ``input`` it refused, which is the
  very thing somebody submitted.

The status table is exhaustive on purpose, and a test says so: a new error
class in ``robinauts.domain`` that nobody gave a status to fails the suite
rather than quietly answering 500.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from robinauts.api.logs import shown
from robinauts.domain import (
    AuthenticationError,
    ConfigError,
    ConversationNotFoundError,
    CrossSiteRequestError,
    IllegalTransitionError,
    InvalidIdTokenError,
    InvalidMessageTreeError,
    InvalidValueError,
    MessageNotFoundError,
    NotAllowedError,
    NotFoundError,
    NotTheOwnerError,
    ProviderUnavailableError,
    RobinautsError,
    RunAlreadyActiveError,
    RunNotFoundError,
    SchemaError,
    SignInError,
    SignInErrorCode,
    StoredDataError,
    UnknownProviderError,
    UnsupportedContentError,
    UnsupportedFormatError,
    UnsupportedMediaTypeError,
)

_log = logging.getLogger(__name__)

GENERIC_DETAIL = "the request could not be served"
"""What a 5xx tells the browser. Everything else about it is in the log."""

INTERNAL_ERROR = "InternalError"
"""The ``error`` of a body that names no class, because none would be true."""

NOT_FOUND_ERROR = "NotFoundError"
"""The one class name everything that is not there answers with."""

NOT_FOUND_DETAIL = "there is nothing here of that id"
"""The one sentence it answers with. It says nothing about whose it is."""

UNREADABLE_DETAIL = "the request could not be read"
"""What a request nobody could parse is told, when there is nothing safe to add."""

MAX_DETAIL_CHARS = 300
"""How long a detail built out of a request may be. It is a sentence, not a dump."""

_LOGGED = 600
"""How much of one of our own messages a log line carries.

Longer than what comes from a request (``logs.MAX_SHOWN``): these are written
here, for an operator, and a configuration error lists every problem it found.
Bounded all the same, because some of them are built out of a request.
"""

MAX_REPORTED_FIELDS = 5
"""How many fields a "could not be read" answer names before it stops."""

MAX_CAUSES = 5
"""How far down a chain of causes a log line follows before it stops."""

MAX_FRAMES = 15
"""How many frames of the innermost cause a log line carries.

The last ones, which are the ones nearest what went wrong. Enough to find the
line; not a page of stack for every refusal.
"""

SIGN_IN_DETAIL: Mapping[SignInErrorCode, str] = {
    SignInErrorCode.EXPIRED: "the sign-in took too long, or was already used",
    SignInErrorCode.STATE_MISMATCH: "the sign-in did not begin in this browser",
    SignInErrorCode.NOT_ALLOWED: "this account may not sign in to this deployment",
    SignInErrorCode.UNKNOWN_PROVIDER: "there is no such sign-in provider",
    SignInErrorCode.BUSY: "too many sign-ins are in progress; try again shortly",
    SignInErrorCode.PROVIDER_UNAVAILABLE: "the sign-in provider could not be reached",
    SignInErrorCode.PROVIDER_REFUSED: "the sign-in provider refused the sign-in",
    SignInErrorCode.INVALID_ID_TOKEN: "the sign-in provider's answer was not for this sign-in",
}
"""One fixed sentence per code, which is all a browser is ever told.

The same closed set the sign-in page knows (``docs/specs/sign-in.md``), said
in words instead of as a query parameter. Nothing here is built out of a
request or out of what a provider said.
"""

STATUS_OF: dict[type[RobinautsError], int] = {
    RobinautsError: 500,
    # What was sent cannot be taken as it is.
    InvalidValueError: 422,
    UnsupportedMediaTypeError: 415,
    # Who is asking is not known, or is not let in.
    AuthenticationError: 401,
    CrossSiteRequestError: 403,
    # A sign-in that did not complete. The auth routes answer these with a
    # redirect to the sign-in page and never reach this table; it is here so
    # that one escaping from anywhere else is still a refusal rather than a
    # 500, and so that the table stays exhaustive.
    SignInError: 403,
    NotAllowedError: 403,
    InvalidIdTokenError: 403,
    UnknownProviderError: 404,
    ProviderUnavailableError: 502,
    # Content of a kind the format names and this build does not carry: the
    # request asked for something that is not there yet, not something wrong.
    UnsupportedContentError: 422,
    InvalidMessageTreeError: 422,
    # A conversation nobody may see and one that never existed answer the
    # same body, not merely the same status (see `error_body`), so that an id
    # cannot be probed for existence.
    NotFoundError: 404,
    ConversationNotFoundError: 404,
    MessageNotFoundError: 404,
    RunNotFoundError: 404,
    NotTheOwnerError: 404,
    # The conversation is busy answering, or the run has moved on: the state
    # of something else is what refuses, and trying again may well work.
    RunAlreadyActiveError: 409,
    IllegalTransitionError: 409,
    # Start-up, not a request: a deployment in this state does not serve.
    ConfigError: 500,
    SchemaError: 500,
    # Our own rows, unreadable by this build. Nothing the request did, so the
    # browser is told nothing and the whole of it goes to the log.
    UnsupportedFormatError: 500,
    StoredDataError: 500,
}
"""The status each platform error answers with; every class of the hierarchy."""


def status_of(exc: RobinautsError) -> int:
    """The status for ``exc``: its class's, or its nearest listed base class's."""
    for cls in type(exc).__mro__:
        if issubclass(cls, RobinautsError) and cls in STATUS_OF:
            return STATUS_OF[cls]
    raise AssertionError("unreachable: RobinautsError itself has a status")


def error_body(exc: BaseException, status: int) -> dict[str, Any]:
    """The JSON body an error crosses as, with nothing in it that came from outside."""
    if status >= 500:
        return {"error": INTERNAL_ERROR, "detail": GENERIC_DETAIL}
    if isinstance(exc, NotFoundError | NotTheOwnerError):
        # Identical in every byte, on purpose: see this module's docstring.
        return {"error": NOT_FOUND_ERROR, "detail": NOT_FOUND_DETAIL}
    if isinstance(exc, SignInError):
        return {"error": type(exc).__name__, "detail": SIGN_IN_DETAIL[exc.code]}
    return {"error": type(exc).__name__, "detail": str(exc)}


def chain(exc: BaseException, *, most: int = _LOGGED) -> str:
    """``exc`` and what raised it, each escaped and bounded, in one line.

    An error of ours often says only what kind of thing went wrong -- "a
    stored message cannot be read by this build" is the whole of it, on
    purpose, because the browser must learn nothing from it. Which message,
    and what exactly was wrong with it, is in the error it was raised **from**,
    and without that an operator is told that something is broken and nothing
    about what. So the chain is followed and written out.

    Escaped and bounded like anything else a log line carries
    (``robinauts.api.logs``): the deepest cause is frequently the one built
    out of a row, and a row is as much somebody's text as a request is.
    """
    said = []
    seen: BaseException | None = exc
    while seen is not None and len(said) < MAX_CAUSES:
        said.append(f"{type(seen).__name__}: {shown(seen, most=most)}")
        seen = seen.__cause__ or seen.__context__
    return " <- ".join(said)


def where(exc: BaseException, *, most: int = MAX_FRAMES) -> str:
    """Where the innermost cause was raised: ``file:line in function``.

    A 5xx of ours says nothing to the browser and often little to the log
    either -- "a stored message cannot be read by this build" is a sentence
    about a kind of thing, and ``reading_stored`` gives that same sentence to
    a bug in our own reader. Without the frames there is nothing to look at.

    **Only the frames**, and only their three fields: no source lines, no
    locals, and not the exception's own message, which ``chain`` carries and
    escapes. A file name and a function name are the interpreter's, not
    anybody's input, and they go through ``shown`` all the same, so that
    nothing here can end a log line or start one.
    """
    innermost: BaseException = exc
    seen = 0
    while (innermost.__cause__ or innermost.__context__) and seen < MAX_CAUSES:
        innermost = innermost.__cause__ or innermost.__context__  # type: ignore[assignment]
        seen += 1
    frames = traceback.extract_tb(innermost.__traceback__)[-most:]
    return shown(
        " < ".join(f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames),
        most=_LOGGED,
    )


def refusal(exc: RobinautsError) -> JSONResponse:
    """The response one of our errors becomes.

    Used by the handlers below and by the request protection, which runs as
    middleware -- outside the reach of an exception handler -- and so has to
    build its refusal rather than raise it.

    A 401 carries no ``WWW-Authenticate``: the browser must not be offered its
    own sign-in dialogue, since signing in here is a page of ours.

    Where the body says less than the exception does, the difference goes to
    the log; otherwise nobody would ever see what really happened.
    """
    status = status_of(exc)
    body = error_body(exc, status)
    if status >= 500:
        # The whole chain: see `chain`. A 5xx of ours says nothing to the
        # browser, so if what it was raised from does not reach the log,
        # nothing anywhere says which row or which version was the trouble.
        _log.error("%s | at %s", chain(exc), where(exc))
    elif body["detail"] != str(exc):
        _log.warning("%s", chain(exc))
    return JSONResponse(body, status_code=status)


def http_error_name(status: int) -> str:
    """The ``error`` a Starlette refusal is named by: ``NotFound``, ``MethodNotAllowed``."""
    try:
        return HTTPStatus(status).phrase.replace(" ", "").replace("-", "")
    except ValueError:
        return INTERNAL_ERROR if status >= 500 else "HttpError"


def http_error_detail(status: int) -> str:
    """Its ``detail``: the status's own phrase, and nothing of the request."""
    try:
        return HTTPStatus(status).phrase.lower()
    except ValueError:
        return GENERIC_DETAIL if status >= 500 else UNREADABLE_DETAIL


def unreadable_detail(exc: RequestValidationError) -> str:
    """Which fields could not be read, and why -- never with what.

    Pydantic's error carries the ``input`` it refused, which is exactly the
    value somebody submitted: a password in the wrong field, a token pasted
    where a number goes. What is said here is where the problem is and which
    rule it broke, bounded, because both are ours and neither is theirs.
    """
    said = []
    for problem in exc.errors()[:MAX_REPORTED_FIELDS]:
        where = ".".join(str(piece)[:40] for piece in problem.get("loc", ()))
        message = str(problem.get("msg", "invalid"))
        said.append(f"{where}: {message}" if where else message)
    return "; ".join(said)[:MAX_DETAIL_CHARS] or UNREADABLE_DETAIL


def install_handlers(app: FastAPI, *, headers: Mapping[str, str] | None = None) -> None:
    """Teach ``app`` to answer every exception in the one shape above.

    ``headers`` go on the last of the four, and only there. The others answer
    from inside the middleware stack, so whatever is put on every response is
    put on theirs as well; an unhandled exception is turned into a response by
    Starlette's outermost middleware, beyond the reach of ours, and would
    otherwise be the one answer of the deployment carrying none.
    """

    @app.exception_handler(RobinautsError)
    async def _platform_error(request: Request, exc: RobinautsError) -> JSONResponse:
        return refusal(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """A path that is not routed, a method that is not allowed, and the rest.

        Starlette answers these itself, in a shape of its own
        (``{"detail": ...}``). They are the two answers a client is most
        likely to meet after a typo, so they are put in the project's shape
        like everything else. The headers are kept: a 405 carries ``Allow``,
        and a client reads it.
        """
        if exc.status_code >= 500:
            _log.error(
                "%s %s answered %s: %s",
                shown(request.method, most=16),
                shown(request.url.path),
                exc.status_code,
                shown(exc.detail),
            )
        body = {
            "error": http_error_name(exc.status_code),
            "detail": http_error_detail(exc.status_code),
        }
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _unreadable_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        """A parameter or a body FastAPI could not read.

        Answered in the same shape as every other refusal, naming the fields
        and the rules they broke and none of the values.
        """
        return refusal(InvalidValueError(unreadable_detail(exc)))

    @app.exception_handler(Exception)
    async def _unknown_error(request: Request, exc: Exception) -> JSONResponse:
        """Anything else: a bug. The browser learns nothing from it.

        Starlette re-raises whatever this handler was given after it has been
        turned into a response, so an ASGI server still logs it; the line here
        is what ties it to the request it came from.
        """
        _log.exception(
            "%s %s raised %s",
            shown(request.method, most=16),
            shown(request.url.path),
            type(exc).__name__,
        )
        return JSONResponse(error_body(exc, 500), status_code=500, headers=dict(headers or {}))
