# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""``POST .../chat/completions`` on a loopback port, streamed or not, answered by a ``FakeModel``.

Bound to port 0, so the operating system picks the port; ``base_url`` is what a
provider's ``base_url`` should be set to. Every request body is kept in
``received``, in order.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Protocol

COMPLETION_ID = "chatcmpl-fake"


class FakeModel(Protocol):
    def reply(self, messages: list[dict[str, Any]]) -> str:
        """The answer's text, given the request's ``messages`` as the client sent them."""
        ...


class FakeLocalGPTServer:
    def __init__(self, model: FakeModel) -> None:
        self.model = model
        self.received: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._http = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(self))
        self._thread = threading.Thread(target=self._http.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._http.server_address[:2]
        return f"http://{host}:{port}/v1"

    def start(self) -> FakeLocalGPTServer:
        self._thread.start()
        return self

    def stop(self) -> None:
        self._http.shutdown()
        self._http.server_close()
        self._thread.join()

    def __enter__(self) -> FakeLocalGPTServer:
        return self.start()

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()

    def answer(self, request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """The text the model replies with, and the request's model name echoed back."""
        with self._lock:
            self.received.append(request)
        return self.model.reply(request["messages"]), request.get("model", "fake-gpt")


def _chunk(model: str, delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {
        "id": COMPLETION_ID,
        "object": "chat.completion.chunk",
        "created": 1,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _usage(text: str) -> dict[str, int]:
    completion = len(text.split())
    return {"prompt_tokens": 1, "completion_tokens": completion, "total_tokens": 1 + completion}


def _handler_for(server: FakeLocalGPTServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if not self.path.endswith("/chat/completions"):
                self._send_json(404, {"error": {"message": f"no route {self.path}"}})
                return
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text, model = server.answer(request)
            if request.get("stream"):
                self._stream(request, text, model)
            else:
                self._send_json(200, self._completion(text, model))

        def _completion(self, text: str, model: str) -> dict[str, Any]:
            return {
                "id": COMPLETION_ID,
                "object": "chat.completion",
                "created": 1,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": _usage(text),
            }

        def _stream(self, request: dict[str, Any], text: str, model: str) -> None:
            # One chunk per word, each keeping the whitespace after it, so they join back exactly.
            pieces = re.findall(r"\s*\S+\s*|\s+", text)
            chunks = [
                _chunk(model, {"role": "assistant", "content": ""}),
                *(_chunk(model, {"content": piece}) for piece in pieces),
                _chunk(model, {}, "stop"),
            ]
            if (request.get("stream_options") or {}).get("include_usage"):
                chunks.append({**_chunk(model, {}), "choices": [], "usage": _usage(text)})
            body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
            self._send(200, "text/event-stream", body.encode())

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            self._send(status, "application/json", json.dumps(payload).encode())

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler
