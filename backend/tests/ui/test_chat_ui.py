# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The interface in a real browser, over a real server on the echo engine and PostgreSQL.

The echo engine calls no model, so nothing here needs a key; ``browser`` runs the server.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page, expect

from util import browser

pytestmark = [pytest.mark.io, pytest.mark.database]

ECHO_CONFIG = browser.ROOT / "examples" / "echo.toml"

# What the interface says of an answer that failed (frontend/src/chat/assistant-ui/state.ts).
DID_NOT_FINISH = "This answer did not finish: something went wrong while it was being produced."


@pytest.fixture
def server() -> Iterator[str]:
    """The URL of a server on the echo agent, stopped when the test ends."""
    with browser.database(ECHO_CONFIG) as url, browser.server(ECHO_CONFIG, url) as running:
        yield running


@pytest.fixture
def page() -> Iterator[Page]:
    with browser.browser_page() as page:
        yield page


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
