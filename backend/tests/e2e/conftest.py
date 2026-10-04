# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A server on the two-engine configuration of ``util.e2e``, its model server, and a browser.

``fake_model`` is what the model server answers with, and ``tools_url`` the MCP server the
``<engine>_tools`` agents use (none by default); a test module overrides either.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Page

from util import browser
from util.e2e import API_KEY, config_for
from util.fake_openai import EchoModel, FakeLocalGPTServer, FakeModel


@pytest.fixture
def fake_model() -> FakeModel:
    return EchoModel()


@pytest.fixture
def tools_url() -> str | None:
    return None


@pytest.fixture
def local_gpt(fake_model: FakeModel) -> Iterator[FakeLocalGPTServer]:
    with FakeLocalGPTServer(fake_model) as running:
        yield running


@pytest.fixture
def server(local_gpt: FakeLocalGPTServer, tools_url: str | None, tmp_path: Path) -> Iterator[str]:
    config = tmp_path / "robinauts.toml"
    config.write_text(config_for(local_gpt.base_url, tools_url))
    with browser.database(config) as url, browser.server(config, url, env=API_KEY) as running:
        yield running


@pytest.fixture
def page() -> Iterator[Page]:
    with browser.browser_page() as page:
        yield page
