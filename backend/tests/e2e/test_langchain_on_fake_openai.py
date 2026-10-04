# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A message typed in the browser goes through the LangChain engine to an OpenAI-compatible
server and back, and the answer is kept in PostgreSQL.

The server is ``FakeLocalGPTServer`` on this machine, answering with ``EchoModel``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from util import browser
from util.fake_openai import EchoModel, FakeLocalGPTServer

pytestmark = [pytest.mark.io, pytest.mark.database]

PROMPT = "Hello there, robinaut."
SYSTEM_PROMPT = "You are a robinaut."

CONFIG = """
[model_providers.local_gpt]
kind = "openai-compatible"
base_url = "{base_url}"
api_key_env = "LOCAL_GPT_KEY"

[models.local_gpt]
provider = "local_gpt"
name = "fake-gpt"
title = "Local GPT"

[agents.assistant]
title = "Assistant"
system_prompt = "{system_prompt}"
model = "local_gpt"
engine = "langchain"
"""


@pytest.fixture
def local_gpt() -> Iterator[FakeLocalGPTServer]:
    with FakeLocalGPTServer(EchoModel()) as running:
        yield running


@pytest.fixture
def server(local_gpt: FakeLocalGPTServer, tmp_path: Path) -> Iterator[str]:
    config = tmp_path / "robinauts.toml"
    config.write_text(CONFIG.format(base_url=local_gpt.base_url, system_prompt=SYSTEM_PROMPT))
    with (
        browser.database(config) as url,
        browser.server(config, url, env={"LOCAL_GPT_KEY": "not-a-real-key"}) as running,
    ):
        yield running


@pytest.fixture
def page() -> Iterator[Page]:
    with browser.browser_page() as page:
        yield page


def test_a_message_is_answered_by_the_fake_gpt_and_kept(
    server: str, page: Page, local_gpt: FakeLocalGPTServer
) -> None:
    page.goto(server)
    page.get_by_role("button", name="New chat").click()
    expect(page.get_by_label("Agent")).to_have_value("assistant")

    browser.send(page, PROMPT)
    question = page.locator('[data-role="user"]').get_by_role("paragraph")
    answer = page.locator('[data-role="assistant"]').get_by_role("paragraph")
    expect(answer).to_have_text(PROMPT)

    page.reload()
    expect(question).to_have_text(PROMPT)
    expect(answer).to_have_text(PROMPT)

    [request] = local_gpt.received
    assert request["model"] == "fake-gpt"
    assert request["stream"] is True
    assert [(m["role"], m["content"]) for m in request["messages"]] == [
        ("system", SYSTEM_PROMPT),
        ("user", PROMPT),
    ]
