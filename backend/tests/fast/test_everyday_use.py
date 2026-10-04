# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The everyday operations of ``tests/e2e/master``, step for step, over the HTTP API in process.

The configuration is the one of ``util.stack``, the store is in memory, and each engine is a
``create_autospec`` of ``AgentEngine`` injected into ``compose``. The engine answers with its
prompt and a checkpoint numbered after its call, so the checkpoint a turn is given shows what the
engine was asked to remember.
"""

from __future__ import annotations

import tomllib
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock, create_autospec

import httpx
import pytest

from aio import asyncio_test
from robinauts.agent_engines.contract.domain import Done, ProviderKind, TextDelta
from robinauts.agent_engines.contract.ports import AgentEngine
from robinauts.controller.composition import compose, configure
from robinauts.controller.contract.domain import StorageConfig, StorageKind
from robinauts.web.app import create_app
from util import stack


def mock_engine() -> MagicMock:
    engine = create_autospec(AgentEngine, instance=True)
    engine.kinds.return_value = frozenset(ProviderKind)

    async def echo(session_id: uuid.UUID, agent: Any, prompt: str, **_: Any) -> AsyncIterator[Any]:
        yield TextDelta(prompt)
        yield Done(prompt, checkpoint_id=f"cp{engine.stream.call_count}")

    engine.stream.side_effect = echo
    return engine


class Api:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def turn(self, path: str, **body: Any) -> str:
        response = await self.http.post(path, json=body)
        assert response.status_code == 200, response.text
        assert '"RUN_FINISHED"' in response.text
        return response.headers["x-robinauts-conversation-id"]

    async def start(self, agent: str, text: str) -> str:
        return await self.turn("/api/turns", agent_id=agent, text=text)

    async def opened(self, cid: str) -> dict[str, Any]:
        response = await self.http.get(f"/api/conversations/{cid}")
        assert response.status_code == 200, response.text
        return response.json()

    async def thread(self, cid: str) -> list[str]:
        """The text of each message, questions and answers in order."""
        messages = (await self.opened(cid))["messages"]
        return [p["text"] for m in messages for p in m["parts"] if p["kind"] == "text"]

    async def message(self, cid: str, index: int) -> str:
        return (await self.opened(cid))["messages"][index]["id"]

    async def history(self) -> list[str]:
        return [c["title"] for c in (await self.http.get("/api/conversations")).json()["items"]]


def echoed(*questions: str) -> list[str]:
    return [text for q in questions for text in (q, q)]


@pytest.mark.parametrize("agent", stack.AGENTS)
@asyncio_test
async def test_everyday_use(agent: str) -> None:
    engine = mock_engine()
    tables = tomllib.loads(stack.config_for("http://model.invalid/v1"))
    config, secret_for = configure(tables, dict(stack.API_KEY))
    composed = compose(
        config,
        storage=StorageConfig(StorageKind.IN_MEMORY),
        secret_for=secret_for,
        engines={name: lambda *_: engine for name in ("langchain", "pydantic-ai")},
    )
    app = create_app(
        composed.controller, credentials=composed.credentials, sign_in=None, secret_for=secret_for
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http,
    ):
        api = Api(http)

        def last_call(model: str, prompt: str, checkpoint: str | None) -> None:
            args, kwargs = engine.stream.call_args
            assert args[2] == prompt
            assert (kwargs["model"], kwargs["checkpoint_id"]) == (model, checkpoint)

        # --- Conversation A -----------------------------------------------------------------

        # 1-2. A first message on the agent: answered, and listed under its title.
        a = await api.start(agent, "alpha one")
        assert await api.thread(a) == echoed("alpha one")
        assert await api.history() == ["alpha one"]
        last_call("local_gpt", "alpha one", None)
        engine.create.assert_awaited_once_with(uuid.UUID(a))

        # 3. Two more, each from the checkpoint of the answer before it.
        await api.turn(
            f"/api/conversations/{a}/turns", text="alpha two", parent_id=await api.message(a, 1)
        )
        await api.turn(
            f"/api/conversations/{a}/turns", text="alpha three", parent_id=await api.message(a, 3)
        )
        assert await api.thread(a) == echoed("alpha one", "alpha two", "alpha three")
        last_call("local_gpt", "alpha three", "cp2")

        # 4. Edit the middle message: everything after it is cut, and it goes on from the
        #    answer before it.
        await api.turn(
            f"/api/conversations/{a}/turns", text="alpha TWO", edit=await api.message(a, 2)
        )
        assert await api.thread(a) == echoed("alpha one", "alpha TWO")
        last_call("local_gpt", "alpha TWO", "cp1")
        assert engine.stream.call_count == 4

        # 5. Regenerate the last answer: a new answer, from the same checkpoint.
        replaced = await api.message(a, 3)
        await api.turn(f"/api/conversations/{a}/turns", regenerate=replaced)
        assert await api.message(a, 3) != replaced
        assert await api.thread(a) == echoed("alpha one", "alpha TWO")
        assert engine.stream.call_count == 5
        last_call("local_gpt", "alpha TWO", "cp1")

        # --- Conversation B -----------------------------------------------------------------

        # 6. A second conversation, listed above A, starting from nothing.
        b = await api.start(agent, "beta one")
        assert await api.thread(b) == echoed("beta one")
        assert await api.history() == ["beta one", "alpha one"]
        last_call("local_gpt", "beta one", None)

        # 7. Change B's model: the next message goes to the other model, from B's checkpoint.
        moved = await http.put(f"/api/conversations/{b}/model", json={"model_id": "local_gpt_2"})
        assert moved.json()["model"] == "local_gpt_2"
        await api.turn(
            f"/api/conversations/{b}/turns",
            text="beta two",
            parent_id=await api.message(b, 1),
            model_id="local_gpt_2",
        )
        assert await api.thread(b) == echoed("beta one", "beta two")
        last_call("local_gpt_2", "beta two", "cp6")

        # --- Back to A ----------------------------------------------------------------------

        # 8. A has its edited thread and its own model.
        assert await api.thread(a) == echoed("alpha one", "alpha TWO")
        assert (await api.opened(a))["conversation"]["model"] == "local_gpt"

        # 9. A message in A goes on from the regenerated answer, to A's model.
        await api.turn(
            f"/api/conversations/{a}/turns", text="alpha four", parent_id=await api.message(a, 3)
        )
        assert await api.thread(a) == echoed("alpha one", "alpha TWO", "alpha four")
        last_call("local_gpt", "alpha four", "cp5")

        # --- Managing conversations ---------------------------------------------------------

        # 10. Delete B: it leaves the list, and the engine forgets it.
        assert (await http.delete(f"/api/conversations/{b}")).status_code == 204
        assert await api.history() == ["alpha one"]
        engine.forget.assert_awaited_once_with(uuid.UUID(b))

        # 11. Rename A.
        renamed = await http.patch(f"/api/conversations/{a}", json={"title": "Project alpha"})
        assert renamed.json()["title"] == "Project alpha"
        assert await api.history() == ["Project alpha"]

        # --- As left ------------------------------------------------------------------------

        # 12. A opens as it was left.
        opened = await api.opened(a)
        assert opened["conversation"]["title"] == "Project alpha"
        assert opened["conversation"]["model"] == "local_gpt"
        assert await api.thread(a) == echoed("alpha one", "alpha TWO", "alpha four")

        # 13. B is not found, and no turn ran beyond the eight above.
        assert (await http.get(f"/api/conversations/{b}")).status_code == 404
        assert engine.stream.call_count == 8
