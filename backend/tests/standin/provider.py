# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The stand-in provider itself: ``http.server`` on a port the operating system picks.

Three endpoints, which is all OpenID Connect's authorization code flow needs
of a provider:

``GET /.well-known/openid-configuration``
    the discovery document, naming the two endpoints below.
``GET /authorize``
    records what was asked, mints a code and redirects straight back to the
    ``redirect_uri`` with it. No page, no person, no password: what is being
    tested is what the platform does with the redirect.
``POST /token``
    checks the client's authentication, the code, the ``redirect_uri`` and the
    PKCE verifier against the challenge the authorization request carried, and
    answers with an **unsigned** ID token holding the claims the test wrote.

The ID token is unsigned on purpose. The platform does not check the signature
(``docs/specs/sign-in.md``: the token comes from the token endpoint over TLS,
which OIDC Core 3.1.3.7 allows for this flow), so a stand-in that signed
anything would be testing a check that does not exist -- and would need a
crypto dependency to do it.

**Misbehaving is scripted**, because most of what an HTTP adapter has to get
right is what it does when the answer is wrong: ``Misbehaviour`` replaces the
next answer of either endpoint with a hang, a ``500``, an HTML page, a
redirect, a body past any sane bound, or an OAuth refusal.

**No fixed port and no sleeping.** The listening socket is bound to port 0, so
the operating system chooses; a held request waits on an event the test sets,
so nothing anywhere waits a guessed number of seconds for something else to be
ready.

Written fresh for this layout, from the stand-in in neorc's ``conftest.py``
(Apache-2.0, the same authors), which is an ASGI application rather than a
server; recorded in ``docs/legal/ip-clearance.md``.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, unquote_plus, urlencode

import httpx

DISCOVERY_PATH = "/.well-known/openid-configuration"
AUTHORIZE_PATH = "/authorize"
TOKEN_PATH = "/token"

HOLD_SECONDS = 30.0
"""How long a held request waits to be released before giving up.

A backstop, not a synchronisation: the test releases it, and this is only so
that a test which fails before releasing leaves no thread behind for the rest
of the run.
"""

CONNECTION_SECONDS = 30.0
"""How long a connection may be idle before its handler thread lets it go."""

CHUNK_BYTES = 8192
"""How much of a chunked body goes out at a time."""

POLL_SECONDS = 0.01
"""How often the serving thread looks to see whether it has been stopped.

``socketserver``'s own default is half a second, which every close would then
wait for: a test that opens a provider of its own -- and each one here does --
would spend more time stopping servers than running.
"""


@dataclass(frozen=True, slots=True)
class Misbehaviour:
    """How an endpoint answers instead of doing its job.

    ``times`` is how many requests it applies to; ``0`` means every request
    until it is replaced. The constructors below are the shapes worth having,
    each named after the failure it makes the adapter meet.

    Scripting one makes a fresh gate for ``hold``, so ``release()`` opens what
    was held when it was called and nothing that is scripted afterwards.
    """

    status: int = 200
    body: bytes = b""
    content_type: str = "application/json"
    location: str | None = None
    content_encoding: str | None = None
    """Declared as it is, whatever the request asked for: providers do this."""
    chunked: bool = False
    """Sent with ``Transfer-Encoding: chunked`` and no length to read ahead of."""
    content_length: int | None = None
    """A length to declare instead of the body's own; a header that lies."""
    hold: bool = False
    """Wait for ``StandInProvider.release()`` before answering at all."""
    times: int = 1

    @classmethod
    def slow(cls, *, times: int = 1) -> Misbehaviour:
        """Accept the connection and say nothing until the test releases it."""
        return cls(hold=True, body=b"{}", times=times)

    @classmethod
    def server_error(cls, status: int = 500, *, times: int = 1) -> Misbehaviour:
        """A ``5xx``, with a JSON body, so that the status alone is what decides."""
        return cls(status=status, body=b'{"error":"server_error"}', times=times)

    @classmethod
    def not_json(cls, *, times: int = 1) -> Misbehaviour:
        """``200`` and an HTML page: a captive portal, a proxy, a misrouted host."""
        return cls(
            body=b"<html><body>the provider is having a lie down</body></html>",
            content_type="text/html; charset=utf-8",
            times=times,
        )

    @classmethod
    def redirect(cls, to: str, *, status: int = 302, times: int = 1) -> Misbehaviour:
        """Point somewhere else, and see whether anybody follows."""
        return cls(status=status, body=b"", location=to, times=times)

    @classmethod
    def oversized(cls, size: int, *, chunked: bool = False, times: int = 1) -> Misbehaviour:
        """A JSON object padded past ``size`` bytes, to meet a reader's bound.

        ``chunked`` sends it with no ``Content-Length`` at all, which is the
        case a reader cannot refuse in advance and has to count its way out of.
        """
        return cls(body=json.dumps({"padding": "p" * size}).encode(), chunked=chunked, times=times)

    @classmethod
    def overstated(cls, claimed: int, *, times: int = 1) -> Misbehaviour:
        """A short body under a ``Content-Length`` that claims ``claimed`` bytes.

        A reader that believes the header refuses before reading; one that
        does not waits for bytes that never come, and the test says which.
        """
        return cls(body=b'{"padding":"p"}', content_length=claimed, times=times)

    @classmethod
    def gzip_bomb(cls, size: int, *, times: int = 1) -> Misbehaviour:
        """A small ``gzip`` body that inflates to ``size``, sent unasked.

        Half a megabyte on the wire is sixty-seven of memory once inflated, so
        a bound counted after decompression is a bound that has already been
        exceeded by the time it is looked at.
        """
        return cls(
            body=gzip.compress(b"p" * size),
            content_encoding="gzip",
            times=times,
        )

    @classmethod
    def deeply_nested(cls, depth: int, *, times: int = 1) -> Misbehaviour:
        """Well-formed JSON far past any parser's recursion limit, in a few kilobytes."""
        return cls(body=b"[" * depth + b"]" * depth, times=times)

    @classmethod
    def oauth_error(
        cls,
        error: str = "invalid_grant",
        *,
        description: str = "the code has already been used",
        status: int = 400,
        times: int = 1,
    ) -> Misbehaviour:
        """An OAuth error response (RFC 6749 5.2): reached, and saying no."""
        return cls(
            status=status,
            body=json.dumps({"error": error, "error_description": description}).encode(),
            times=times,
        )


@dataclass(frozen=True, slots=True)
class Received:
    """One request as the provider saw it, headers and all."""

    method: str
    path: str
    query: str
    headers: Mapping[str, str]
    """Lower-cased header names, so a test need not guess the client's spelling."""


class StandInProvider:
    """An OpenID Connect provider listening on loopback, for as long as it is open.

    Use it as a context manager::

        with StandInProvider() as provider:
            ...  # provider.issuer names it

    What a test writes: ``person`` (the claims the ID token carries),
    ``tamper`` (claims to override, to make a token that must be refused),
    ``discovery`` (keys added to or removed from the document -- ``None``
    removes), and the two ``*_misbehaves`` methods.

    What a test reads: ``authorized`` and ``exchanged``, every request to
    those two endpoints as it arrived; and ``received`` -- every request at
    all, headers included -- of which ``paths`` is the short form. That is how
    "the redirect was not followed" becomes a statement about what the server
    saw rather than about what the client said it did.
    """

    def __init__(
        self,
        *,
        client_id: str = "stand-in-client",
        client_secret: str = "stand-in-secret",
        host: str = "127.0.0.1",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.person: dict[str, Any] = {
            "sub": "248289761001",
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "email_verified": True,
        }
        self.tamper: dict[str, Any] = {}
        self.discovery: dict[str, Any] = {}
        self.authorized: list[dict[str, str]] = []
        self.exchanged: list[dict[str, str]] = []
        self.received: list[Received] = []
        self._misbehaviours: dict[str, tuple[Misbehaviour, threading.Event]] = {}
        self._gates: list[threading.Event] = []
        self._codes: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()
        self._server = _Server((host, 0), _Handler)
        self._server.provider = self
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            args=(POLL_SECONDS,),
            name="stand-in-provider",
            daemon=True,
        )
        self._thread.start()

    # Living.

    @property
    def issuer(self) -> str:
        """What this provider calls itself: ``http://127.0.0.1:<the port it got>``.

        Loopback ``http``, which is the one unencrypted endpoint the platform
        accepts (``core.normalise_endpoint``) and which needs no certificate
        for a test to trust.
        """
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def paths(self) -> list[str]:
        """The path of every request that arrived, in order."""
        with self._lock:
            return [request.path for request in self.received]

    def close(self) -> None:
        """Stop serving and let every thread go."""
        self.release()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=HOLD_SECONDS)

    def __enter__(self) -> StandInProvider:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # Scripting.

    def discovery_misbehaves(self, how: Misbehaviour) -> None:
        """Answer discovery with ``how`` instead of the document."""
        self._script(DISCOVERY_PATH, how)

    def token_misbehaves(self, how: Misbehaviour) -> None:
        """Answer the token endpoint with ``how`` instead of a token."""
        self._script(TOKEN_PATH, how)

    def release(self) -> None:
        """Let every request held so far answer.

        It says nothing about what is scripted next. Each scripting makes a
        gate of its own, so a provider that was released and is then told to
        be slow again really is slow again -- a single sticky flag would make
        the second test of a pair pass for the wrong reason.
        """
        with self._lock:
            gates = list(self._gates)
        for gate in gates:
            gate.set()

    def _script(self, path: str, how: Misbehaviour) -> None:
        """Put ``how`` in front of ``path``, behind a gate no earlier release opened."""
        gate = threading.Event()
        with self._lock:
            self._misbehaviours[path] = (how, gate)
            self._gates.append(gate)

    # Serving. Everything below runs on a handler thread.

    def _answer(self, request: Received, body: bytes) -> _Answer:
        """What to send for one request, misbehaviour included.

        Every piece of the request is an argument, so that two handler threads
        serving at once never read each other's: the only state shared between
        them is the records and the minted codes, and those are under a lock.
        """
        path = request.path
        gate = None
        how = None
        with self._lock:
            self.received.append(request)
            scripted = self._misbehaviours.get(path)
            if scripted is not None:
                how, gate = scripted
                if how.times == 1:
                    del self._misbehaviours[path]
                elif how.times > 1:
                    self._misbehaviours[path] = (replace(how, times=how.times - 1), gate)
        if how is not None:
            if how.hold and gate is not None:
                gate.wait(timeout=HOLD_SECONDS)
            headers = [("location", how.location)] if how.location else []
            if how.content_encoding:
                headers.append(("content-encoding", how.content_encoding))
            return _Answer(
                how.status,
                how.body,
                how.content_type,
                tuple(headers),
                chunked=how.chunked,
                content_length=how.content_length,
            )
        if path == DISCOVERY_PATH:
            return _json(200, self._document())
        if path == AUTHORIZE_PATH:
            return self._authorize(request.query)
        if path == TOKEN_PATH:
            return self._token(body, request.headers.get("authorization", ""))
        return _json(404, {"error": "not_found", "path": path})

    def _document(self) -> dict[str, Any]:
        """The discovery document, with what the test added or removed."""
        base = self.issuer
        document: dict[str, Any] = {
            "issuer": base,
            "authorization_endpoint": f"{base}{AUTHORIZE_PATH}",
            "token_endpoint": f"{base}{TOKEN_PATH}",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }
        document.update(self.discovery)
        return {key: value for key, value in document.items() if value is not None}

    def _authorize(self, query: str) -> _Answer:
        """Record the authorization request, mint a code, and send the browser back."""
        asked = _one_of_each(query)
        with self._lock:
            self.authorized.append(asked)
        redirect_uri = asked.get("redirect_uri")
        if not redirect_uri:
            return _json(400, {"error": "invalid_request", "error_description": "redirect_uri"})
        code = uuid.uuid4().hex
        with self._lock:
            self._codes[code] = asked
        back = {"code": code}
        if "state" in asked:
            back["state"] = asked["state"]
        separator = "&" if "?" in redirect_uri else "?"
        return _Answer(
            303, b"", "text/plain", (("location", f"{redirect_uri}{separator}{urlencode(back)}"),)
        )

    def _token(self, body: bytes, authorization: str) -> _Answer:
        """Check everything a token endpoint checks, then issue the ID token."""
        asked = _one_of_each(body.decode("utf-8", "replace"))
        asked["authorization"] = authorization
        with self._lock:
            self.exchanged.append(dict(asked))
        # Authenticated first, and only then is the code redeemed. A real
        # authorization server does not burn a code on behalf of a client that
        # has not proved who it is -- and a stand-in that did would turn a
        # wrong secret into a second failure nobody asked about.
        if not self._client_authenticated(asked):
            return _json(401, {"error": "invalid_client"})
        with self._lock:
            authorized = self._codes.pop(asked.get("code", ""), None)
        if authorized is None:
            # Unknown, or used already: a code is single use.
            return _json(400, {"error": "invalid_grant", "error_description": "code"})
        if asked.get("grant_type") != "authorization_code":
            return _json(400, {"error": "unsupported_grant_type"})
        if asked.get("redirect_uri") != authorized.get("redirect_uri"):
            return _json(400, {"error": "invalid_grant", "error_description": "redirect_uri"})
        if _pkce_challenge(asked.get("code_verifier", "")) != authorized.get("code_challenge"):
            return _json(400, {"error": "invalid_grant", "error_description": "code_verifier"})
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "iat": now,
            "exp": now + 300,
            "nonce": authorized.get("nonce"),
            **self.person,
            **self.tamper,
        }
        return _json(
            200,
            {
                "access_token": "stand-in-access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "id_token": unsigned_jwt(
                    {key: value for key, value in claims.items() if value is not None}
                ),
            },
        )

    def _client_authenticated(self, asked: Mapping[str, str]) -> bool:
        """Whether the client proved itself, either way OIDC allows.

        ``client_secret_basic`` undoes RFC 6749 2.3.1's form-encoding of each
        half before comparing, which is what makes a secret holding a colon,
        a space or a percent sign work.
        """
        header = asked.get("authorization", "")
        if header.startswith("Basic "):
            try:
                pair = base64.b64decode(header[len("Basic ") :], validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return False
            client_id, colon, secret = pair.partition(":")
            if not colon:
                return False
            return (unquote_plus(client_id), unquote_plus(secret)) == (
                self.client_id,
                self.client_secret,
            )
        return (asked.get("client_id"), asked.get("client_secret")) == (
            self.client_id,
            self.client_secret,
        )


@dataclass(frozen=True, slots=True)
class _Answer:
    """One HTTP response, as the handler writes it."""

    status: int
    body: bytes
    content_type: str
    headers: tuple[tuple[str, str], ...] = ()
    chunked: bool = False
    content_length: int | None = None


class _Server(ThreadingHTTPServer):
    """Threads that never hold a shutdown up, and never a port of our choosing."""

    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    provider: StandInProvider

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A client that hung up is not news; anything else still is.

        Half of what is tested here is the adapter giving up on an answer --
        a body past its bound, a request past its deadline -- and giving up
        means closing the socket mid-write. Printing a stack trace for each
        would bury the one that means something.
        """
        if isinstance(sys.exception(), ConnectionError | TimeoutError):
            return
        super().handle_error(request, client_address)


class _Handler(BaseHTTPRequestHandler):
    """HTTP/1.1, silent, and of no opinion: the provider decides what to answer."""

    protocol_version = "HTTP/1.1"
    timeout = CONNECTION_SECONDS

    def log_message(self, format: str, *args: Any) -> None:
        """Say nothing: a test's output is the test's. The signature is http.server's."""

    def do_GET(self) -> None:
        """http.server dispatches by method name, which is why this one shouts."""
        self._serve(b"")

    def do_POST(self) -> None:
        """As ``do_GET``, with the form the token endpoint was posted."""
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        self._serve(self.rfile.read(length) if length > 0 else b"")

    def _serve(self, body: bytes) -> None:
        path, _, query = self.path.partition("?")
        provider: StandInProvider = self.server.provider  # type: ignore[attr-defined]
        request = Received(
            method=self.command,
            path=path,
            query=query,
            headers={name.lower(): value for name, value in self.headers.items()},
        )
        try:
            answer = provider._answer(request, body)
        except Exception as exc:  # pragma: no cover -- a broken stand-in, not a test
            answer = _json(500, {"error": "stand_in_failed", "error_description": repr(exc)})
        self.send_response(answer.status)
        self.send_header("content-type", answer.content_type)
        if answer.chunked:
            self.send_header("transfer-encoding", "chunked")
        else:
            declared = answer.content_length
            self.send_header(
                "content-length", str(len(answer.body) if declared is None else declared)
            )
        for name, value in answer.headers:
            self.send_header(name, value)
        self.end_headers()
        self._write_body(answer)
        self.wfile.flush()

    def _write_body(self, answer: _Answer) -> None:
        """The body, in whichever framing the answer asked for."""
        if not answer.chunked:
            if answer.body:
                self.wfile.write(answer.body)
            return
        for start in range(0, len(answer.body), CHUNK_BYTES):
            piece = answer.body[start : start + CHUNK_BYTES]
            self.wfile.write(f"{len(piece):x}\r\n".encode("ascii") + piece + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


def unsigned_jwt(claims: Mapping[str, Any]) -> str:
    """A JWT carrying ``claims`` with ``alg: none`` and an empty signature."""

    def part(value: Mapping[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


async def redirect_from(url: str) -> str:
    """GET ``url`` without following it, and give back its ``Location``.

    What a browser does with an authorization URL, minus the browser: the
    end-to-end test uses it to get from ``SignIn.begin`` to the callback
    ``SignIn.complete`` is given.
    """
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        response = await client.get(url)
    location = response.headers.get("location")
    if response.status_code // 100 != 3 or not location:
        raise AssertionError(f"{url} answered {response.status_code}, not a redirect")
    return location


def _pkce_challenge(verifier: str) -> str:
    """The ``S256`` challenge of a verifier, computed here rather than imported.

    ``core.pkce_challenge`` does the same thing, and a stand-in that used it
    would agree with the platform by construction: the point of this one is to
    be a second opinion.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _one_of_each(query: str) -> dict[str, str]:
    """A query or a form as a plain mapping, keeping the first of any repeat."""
    return {name: values[0] for name, values in parse_qs(query, keep_blank_values=True).items()}


def _json(status: int, body: Mapping[str, Any]) -> _Answer:
    """A JSON answer, as every endpoint here gives."""
    return _Answer(status, json.dumps(body).encode("utf-8"), "application/json")
