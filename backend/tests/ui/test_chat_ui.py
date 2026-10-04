# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The interface in a real browser, over a real server on the echo engine and PostgreSQL.

``tests/ui`` is not collected by a plain run (``norecursedirs``): ``scripts/check-ui.sh`` builds
the interface, installs the browser and runs it. The server stores in the PostgreSQL that
``ROBINAUTS_TEST_DATABASE_URL`` names, in a schema of its own that is dropped afterwards, and
the echo engine calls no model, so nothing here needs a key.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest
from playwright.sync_api import Page, expect, sync_playwright

pytestmark = [pytest.mark.io, pytest.mark.database]

ROOT = Path(__file__).resolve().parents[3]
ECHO_CONFIG = ROOT / "examples" / "echo.toml"
ROBINAUTS = Path(sys.executable).with_name("robinauts")

# What the interface says of an answer that failed (frontend/src/chat/assistant-ui/state.ts).
DID_NOT_FINISH = "This answer did not finish: something went wrong while it was being produced."


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_up(url: str, server: subprocess.Popen[bytes]) -> None:
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError(f"the server exited with {server.returncode}")
        try:
            with urllib.request.urlopen(url + "/auth/session"):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"nothing answered on {url}")


def with_search_path(url: str, schema: str) -> str:
    """``url`` with every connection made from it working in ``schema``."""
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query) + [("search_path", schema)]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


async def run_statement(url: str, statement: str) -> None:
    connection = await asyncpg.connect(url)
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


@pytest.fixture
def database() -> Iterator[str]:
    """The URL of a new schema, with this build's tables in it, dropped when the test ends."""
    given = os.environ.get("ROBINAUTS_TEST_DATABASE_URL")
    if not given:
        pytest.fail("no ROBINAUTS_TEST_DATABASE_URL: run scripts/check-ui.sh, or set it")
    schema = "robinauts_ui_" + uuid.uuid4().hex
    asyncio.run(run_statement(given, f'CREATE SCHEMA "{schema}"'))
    try:
        url = with_search_path(given, schema)
        environment = {**os.environ, "ROBINAUTS_CONFIG": str(ECHO_CONFIG)}
        environment["ROBINAUTS_DATABASE_URL"] = url
        subprocess.run([str(ROBINAUTS), "db", "init"], env=environment, check=True)
        yield url
    finally:
        asyncio.run(run_statement(given, f'DROP SCHEMA "{schema}" CASCADE'))


@pytest.fixture
def server(database: str) -> Iterator[str]:
    """The URL of a server on the echo agent, stopped when the test ends."""
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        pytest.fail("the interface is not built: run scripts/check-ui.sh")
    port = free_port()
    environment = {**os.environ, "ROBINAUTS_CONFIG": str(ECHO_CONFIG)}
    environment["ROBINAUTS_DATABASE_URL"] = database
    command = [str(ROBINAUTS), "start", "--dev-no-sign-in", "--port", str(port)]
    with subprocess.Popen(command, env=environment) as running:
        url = f"http://127.0.0.1:{port}"
        try:
            wait_until_up(url, running)
            yield url
        finally:
            running.terminate()
            running.wait(timeout=10)


@pytest.fixture
def page() -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            yield browser.new_page()
        finally:
            browser.close()


def test_a_conversation_with_echo_answers_keeps_and_edits(server: str, page: Page) -> None:
    page.goto(server)
    page.get_by_role("button", name="New chat").click()
    expect(page.get_by_label("Agent")).to_have_value("echo")

    page.get_by_label("Message input").fill("hello")
    page.get_by_label("Send message").click()
    answer = page.locator('[data-role="assistant"]')
    expect(answer).to_contain_text("The tool said: hello")

    # Read back from the database: the reloaded page opens the conversation from the server.
    page.reload()
    expect(answer).to_contain_text("The tool said: hello")

    page.locator('[data-role="user"]').hover()  # its actions show on hover
    page.get_by_role("button", name="Edit").click()
    page.locator(".aui-edit-composer-input").fill("hi")
    page.get_by_role("button", name="Update").click()
    expect(answer).to_contain_text("The tool said: hi")
    expect(page.locator('[data-role="user"]')).to_contain_text("hi")
    expect(page.locator('[data-role="user"]')).not_to_contain_text("hello")


def test_a_failed_answer_says_so_in_its_place_and_keeps_saying_it(server: str, page: Page) -> None:
    page.goto(server)
    page.get_by_role("button", name="New chat").click()
    expect(page.get_by_label("Agent")).to_have_value("echo")

    page.get_by_label("Message input").fill("poison")  # echo ends this turn badly
    page.get_by_label("Send message").click()
    answers = page.locator('[data-role="assistant"]')
    failed = answers.first.get_by_text(DID_NOT_FINISH)
    expect(failed).to_be_visible()
    expect(page.get_by_text(DID_NOT_FINISH)).to_have_count(1)

    page.reload()
    expect(page.locator('[data-role="user"]')).to_contain_text("poison")
    expect(failed).to_be_visible()
    expect(page.get_by_text(DID_NOT_FINISH)).to_have_count(1)

    # Retry is the reload button of a failed answer: a fresh answer to the same question,
    # which echo fails again for "poison".
    first_try = answers.first.get_attribute("data-message-id")
    answers.first.hover()
    page.get_by_role("button", name="Refresh").click()
    expect(answers.first).not_to_have_attribute("data-message-id", first_try or "")
    expect(answers).to_have_count(1)
    expect(failed).to_be_visible()
    expect(page.get_by_text(DID_NOT_FINISH)).to_have_count(1)
    # A retry, not a regeneration: the model was told about the failure.
    conversation = page.url.split("#/c/")[1]
    opened = page.request.get(f"{server}/api/conversations/{conversation}").json()
    assert "pressed the retry button" in opened["messages"][-1]["parts"][0]["arguments"]["text"]

    # A reply goes under the failed answer, which stays, and still says it failed. Echo says
    # back what the model was told: the failed exchange, then the new message.
    page.get_by_label("Message input").fill("hello")
    page.get_by_label("Send message").click()
    expect(answers).to_have_count(2)
    expect(answers.last).to_contain_text("Message: poison")
    expect(answers.last).to_contain_text("The user's new message: hello")
    expect(failed).to_be_visible()

    page.reload()
    expect(answers.last).to_contain_text("The user's new message: hello")
    expect(failed).to_be_visible()
    expect(page.get_by_text(DID_NOT_FINISH)).to_have_count(1)
