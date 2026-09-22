# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Reading a stream the way a browser does: the SSE parser, and a driver.

Two things, and the second exists because of a limit in the first tool a test
would reach for. ``httpx``'s ASGI transport **runs the application to its end**
before it answers: every byte of the response is collected and handed over at
once. That is fine for a stream that finishes -- a turn whose engine the test
lets run to the end -- and it is no use at all for what a stream is *for*:
receiving one event while the run goes on, and going away in the middle.

So ``streaming`` drives the ASGI application itself, as a server does: it
sends the request, it hands each body chunk to the test as it is written, and
``close`` sends ``http.disconnect``, which is exactly what a server sends when
the client's socket goes. Nothing here knows anything about the routes; it is
the protocol, and about forty lines of it.

The parser is deliberately literal about the format: an ``id:``, an ``event:``
and the ``data:`` lines of one block, and a block that is only a comment
(``: keep-alive``) kept as one, because a heartbeat is a thing a test asks
about.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

BLOCK = "\n\n"
"""What separates one server-sent event from the next."""


@dataclass(frozen=True, slots=True)
class Sent:
    """One block of a stream: an event, or a comment on its own."""

    data: str = ""
    name: str | None = None
    """The ``event:`` field, which is the AG-UI type here."""
    id: str | None = None
    """The ``id:`` field, which is the event's position in its run."""
    comment: str | None = None
    """What a block that carried nothing but a comment said."""

    @property
    def body(self) -> dict[str, Any]:
        """The event's JSON, as the client would read it."""
        read = json.loads(self.data)
        assert isinstance(read, dict)
        return read

    @property
    def type(self) -> str:
        """The AG-UI type the body names; what a test reads at a glance."""
        return str(self.body["type"])


def parse(text: str) -> list[Sent]:
    """Every block of that stream, in order, comments included."""
    blocks = []
    for block in text.split(BLOCK):
        if not block.strip("\n"):
            continue
        blocks.append(_block(block))
    return blocks


def events(text: str) -> list[Sent]:
    """The blocks that carry an event; the heartbeats left out."""
    return [block for block in parse(text) if block.comment is None]


def beats(text: str) -> list[str]:
    """What the comment blocks of that stream said."""
    return [block.comment for block in parse(text) if block.comment is not None]


def _block(block: str) -> Sent:
    """One block, field by field. Unknown fields are ignored, as a client does."""
    data: list[str] = []
    name: str | None = None
    identifier: str | None = None
    comment: str | None = None
    for line in block.split("\n"):
        if not line:
            continue
        if line.startswith(":"):
            comment = line[1:].strip()
            continue
        field_name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field_name == "data":
            data.append(value)
        elif field_name == "event":
            name = value
        elif field_name == "id":
            identifier = value
    return Sent(
        data="\n".join(data),
        name=name,
        id=identifier,
        comment=comment if not data else None,
    )


@dataclass
class Streamed:
    """One request being served, and what it has written so far."""

    status: int
    headers: Mapping[str, str]
    _chunks: asyncio.Queue[bytes | None]
    _served: asyncio.Task[None]
    _gone: asyncio.Event
    _read: str = ""
    _over: bool = False
    _blocks: list[Sent] = field(default_factory=list)

    async def next_block(self) -> Sent:
        """The next event or comment the stream writes.

        ``AssertionError`` if the response ends first, which is what a test
        waiting for something that is never coming should be told.
        """
        while not self._blocks:
            assert not self._over, f"the stream ended; it had said {self._read!r}"
            await self._more()
        return self._blocks.pop(0)

    async def upto(self, name: str) -> list[Sent]:
        """Everything up to and including the first event of that AG-UI type."""
        seen = []
        while True:
            block = await self.next_block()
            seen.append(block)
            if block.comment is None and block.type == name:
                return seen

    async def rest(self) -> list[Sent]:
        """Everything the stream writes from here until it ends."""
        while not self._over:
            await self._more()
        kept, self._blocks = self._blocks, []
        return kept

    async def close(self) -> None:
        """Go away in the middle, as a closed tab does.

        ``http.disconnect`` is what a server sends when the client's connection
        is gone, and what Starlette's streaming response listens for.
        """
        self._gone.set()
        await self._served

    async def _more(self) -> None:
        """Wait for the next chunk and put whatever blocks are now whole in reach."""
        chunk = await self._chunks.get()
        if chunk is None:
            self._over = True
            await self._served
            return
        self._read += chunk.decode()
        whole, _, rest = self._read.rpartition(BLOCK)
        if whole:
            self._blocks.extend(parse(whole + BLOCK))
            self._read = rest


@asynccontextmanager
async def streaming(
    app: Any,
    method: str,
    path: str,
    *,
    headers: Mapping[str, str],
    query: str = "",
    body: bytes = b"",
) -> AsyncIterator[Streamed]:
    """Drive that ASGI application for one request, reading it as it is written.

    The scope is the one a server builds; ``scope["app"]`` is Starlette's own
    doing, so the request protection finds the deployment's state where it
    expects to. The request's body is sent in one message, as a small JSON body
    arrives in one.

    Leaving the block closes the connection if the test has not, and waits for
    the application to let go -- so nothing is left running into the next test.
    """
    loop = asyncio.get_running_loop()
    chunks: asyncio.Queue[bytes | None] = asyncio.Queue()
    started: asyncio.Future[tuple[int, dict[str, str]]] = loop.create_future()
    gone = asyncio.Event()
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            started.set_result(
                (
                    message["status"],
                    {
                        name.decode("latin-1").lower(): value.decode("latin-1")
                        for name, value in message.get("headers", ())
                    },
                )
            )
        elif message["type"] == "http.response.body":
            await chunks.put(message.get("body", b""))
            if not message.get("more_body", False):
                await chunks.put(None)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers.items()
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("robinauts.example.com", 443),
    }
    served = loop.create_task(app(scope, receive, send))
    try:
        # An application that raised before it answered would otherwise leave
        # this waiting for a response that is never coming; whatever it raised
        # is what a test should be shown.
        await asyncio.wait((started, served), return_when=asyncio.FIRST_COMPLETED)
        if not started.done():
            await served
            raise AssertionError("the application returned without answering")
        status, answered = await started
        yield Streamed(status=status, headers=answered, _chunks=chunks, _served=served, _gone=gone)
    finally:
        gone.set()
        await served
