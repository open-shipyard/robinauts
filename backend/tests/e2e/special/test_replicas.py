# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Two servers on one database, and servers killed in the middle of a turn: a turn longer than
one model call's timeout, a conversation that another server takes over, and a turn nobody
opens that the sweep ends.

``ToolEchoModel`` calls the MCP server's ``nap`` with the question: "wait N" sleeps N seconds,
"hang" sleeps for ten minutes.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest
from playwright.sync_api import Page, expect

from util import stack
from util.browser import DID_NOT_FINISH, browser_page, send
from util.fake_openai import FakeLocalGPTServer, FakeModel, ToolEchoModel
from util.mcp_server import mcp_server

pytestmark = [pytest.mark.io, pytest.mark.database]

WORK = """
[work]
lease_seconds = 5
heartbeat_seconds = 1
sweep_seconds = 1
"""


async def nap(text: str) -> str:
    """The text, in capitals, after a nap."""
    if text == "hang":
        await asyncio.sleep(600)
    elif text.startswith("wait "):
        await asyncio.sleep(float(text.split()[1]))
    return text.upper()


@pytest.fixture
def fake_model() -> FakeModel:
    return ToolEchoModel("nap")


@pytest.fixture
def tools_url() -> Iterator[str]:
    with mcp_server(nap) as url:
        yield url


def new_chat(page: Page, server: str) -> None:
    page.goto(server)
    page.get_by_role("button", name="New chat").click()
    page.get_by_label("Agent").select_option("langchain_tools")


def hang(page: Page) -> str:
    """Send "hang" and wait for its tool call: the conversation's id."""
    answers = page.locator('[data-role="assistant"]')
    count = answers.count()
    send(page, "hang")
    expect(answers).to_have_count(count + 1)
    expect(answers.last.get_by_role("button", name="1 tool call")).to_be_visible()
    return conversation_id(page)


def conversation_id(page: Page) -> str:
    expect(page).to_have_url(re.compile(r"#/c/[0-9a-f-]{36}$"))
    return page.url.rsplit("/", 1)[-1]


async def ended_turn(url: str, session: str) -> tuple[str, str | None]:
    """The session's turn's state, and whether its answer was stored marked failed."""
    connection = await asyncpg.connect(url)
    try:
        state = await connection.fetchval("SELECT state FROM turns WHERE session_id = $1", session)
        failed = await connection.fetchval(
            "SELECT document->>'failed' FROM messages WHERE session_id = $1 AND role = 'assistant'",
            session,
        )
        return state, failed
    finally:
        await connection.close()


def test_replicas(local_gpt: FakeLocalGPTServer, tools_url: str, tmp_path: Path) -> None:
    config = tmp_path / "robinauts.toml"
    model_timeout = 'title = "Local GPT"\ntimeout_seconds = 2\n'
    text = stack.config_for(local_gpt.base_url, tools_url)
    config.write_text(text.replace('title = "Local GPT"\n', model_timeout, 1) + WORK)
    started: list[subprocess.Popen[bytes]] = []
    with (
        stack.database(config) as url,
        stack.server(config, url, stack.API_KEY, started) as a,
        stack.server(config, url, stack.API_KEY, started) as b,
    ):
        with browser_page() as page:
            answers = page.locator('[data-role="assistant"]')

            # 1. On A, a turn whose tool call takes 4 s finishes, past the model's 2 s timeout.
            new_chat(page, a)
            send(page, "wait 4")
            expect(answers.first).to_contain_text("The tool said: WAIT 4", timeout=15_000)

            # 2. "hang", then A is killed: on B the answer shows as failed with its tool call,
            #    and the conversation takes a new message.
            conversation = hang(page)
            started[0].kill()
            page.goto(f"{b}/#/c/{conversation}")
            expect(answers.last.get_by_text(DID_NOT_FINISH)).to_be_visible(timeout=15_000)
            expect(answers.last.get_by_role("button", name="1 tool call")).to_be_visible()
            send(page, "hello")
            # The model is told of the failed answer, and its tool call, before "hello".
            said = re.compile(r'The tool said: .*NAP\(\{"TEXT": "HANG"\}\).*HELLO', re.S)
            expect(answers.last).to_contain_text(said, timeout=15_000)

            # 3. A2 starts a turn that hangs and is killed, and nobody opens that conversation.
            with stack.server(config, url, stack.API_KEY, started) as a2:
                new_chat(page, a2)
                hanging = hang(page)
                started[-1].kill()

        # B's sweep ends it, and keeps its answer, marked failed.
        for _ in range(100):
            if asyncio.run(ended_turn(url, hanging))[0] != "running":
                break
            time.sleep(0.1)
        assert asyncio.run(ended_turn(url, hanging)) == ("interrupted", "true")
