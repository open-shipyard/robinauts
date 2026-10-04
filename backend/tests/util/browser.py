# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A real server on a config and a schema of its own, and a browser, for ``tests/ui`` and
``tests/e2e``.

Neither directory is collected by a plain run (``norecursedirs``): ``scripts/check-ui.sh``
builds the interface, installs the browser and runs them. The schema is made in the
PostgreSQL that ``ROBINAUTS_TEST_DATABASE_URL`` names and dropped afterwards.
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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import asyncpg
import pytest
from playwright.sync_api import Locator, Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
ROBINAUTS = Path(sys.executable).with_name("robinauts")


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


@contextmanager
def database(config: Path) -> Iterator[str]:
    """The URL of a new schema, with this build's tables in it, dropped afterwards."""
    given = os.environ.get("ROBINAUTS_TEST_DATABASE_URL")
    if not given:
        pytest.fail("no ROBINAUTS_TEST_DATABASE_URL: run scripts/check-ui.sh, or set it")
    schema = "robinauts_ui_" + uuid.uuid4().hex
    asyncio.run(run_statement(given, f'CREATE SCHEMA "{schema}"'))
    try:
        url = with_search_path(given, schema)
        environment = {**os.environ, "ROBINAUTS_CONFIG": str(config)}
        environment["ROBINAUTS_DATABASE_URL"] = url
        subprocess.run([str(ROBINAUTS), "db", "init"], env=environment, check=True)
        yield url
    finally:
        asyncio.run(run_statement(given, f'DROP SCHEMA "{schema}" CASCADE'))


@contextmanager
def server(config: Path, database_url: str, env: Mapping[str, str] = {}) -> Iterator[str]:
    """The URL of a server on that config, without sign-in, stopped afterwards."""
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        pytest.fail("the interface is not built: run scripts/check-ui.sh")
    port = free_port()
    environment = {**os.environ, **env, "ROBINAUTS_CONFIG": str(config)}
    environment["ROBINAUTS_DATABASE_URL"] = database_url
    command = [str(ROBINAUTS), "start", "--dev-no-sign-in", "--port", str(port)]
    with subprocess.Popen(command, env=environment) as running:
        url = f"http://127.0.0.1:{port}"
        try:
            wait_until_up(url, running)
            yield url
        finally:
            running.terminate()
            running.wait(timeout=10)


@contextmanager
def browser_page() -> Iterator[Page]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            yield browser.new_page()
        finally:
            browser.close()


def send(page: Page, message: str) -> None:
    page.get_by_label("Message input").fill(message)
    page.get_by_label("Send message").click()


def questions(page: Page) -> Locator:
    return page.locator('[data-role="user"]').get_by_role("paragraph")


def answers(page: Page) -> Locator:
    return page.locator('[data-role="assistant"]').get_by_role("paragraph")


def expect_thread(page: Page, exchanges: list[tuple[str, str]]) -> None:
    """The thread on the screen is exactly these questions, each with its answer."""
    expect(questions(page)).to_have_text([q for q, _ in exchanges])
    expect(answers(page)).to_have_text([a for _, a in exchanges])


def edit(page: Page, old: str, new: str) -> None:
    message = page.locator('[data-role="user"]').filter(has_text=old)
    message.hover()  # its actions show on hover
    message.get_by_role("button", name="Edit").click()
    page.locator(".aui-edit-composer-input").fill(new)
    page.get_by_role("button", name="Update").click()


def regenerate_last(page: Page) -> None:
    answer = page.locator('[data-role="assistant"]').last
    answer.hover()
    answer.get_by_role("button", name="Refresh").click()


def history(page: Page) -> Locator:
    """The conversations listed in the panel, newest first."""
    return page.get_by_label("Conversations").get_by_role("link")


def open_conversation(page: Page, title: str) -> None:
    history(page).filter(has_text=title).click()


def conversation_action(page: Page, title: str, action: str) -> None:
    """Open that conversation's actions and press one of them: "Rename" or "Delete"."""
    page.get_by_role("button", name=f"Actions for {title}").click()
    page.get_by_role("group", name=f"Actions for {title}").get_by_role(
        "button", name=action
    ).click()
