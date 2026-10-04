# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The platform of ``util.stack`` over HTTP: ``tests/e2e`` without the browser.

One model server, one ``robinauts`` server and one schema for the whole run, so a test keeps
to conversations it opened itself: the listing holds every other test's too. ``fake_model``
is what the model server answers each test with, and a test module overrides it; ``local_gpt``
is the model server, holding only that test's requests. The ``<engine>_tools`` agents call
``shout`` on a real MCP server.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from util import stack
from util.fake_openai import EchoModel, FakeLocalGPTServer, FakeModel
from util.mcp_server import mcp_server


def shout(text: str) -> str:
    """The text, in capitals."""
    return text.upper()


@pytest.fixture(scope="session")
def model_server() -> Iterator[FakeLocalGPTServer]:
    with FakeLocalGPTServer(EchoModel()) as running:
        yield running


@pytest.fixture(scope="session")
def tools_url() -> Iterator[str]:
    with mcp_server(shout) as url:
        yield url


@pytest.fixture(scope="session")
def server(
    model_server: FakeLocalGPTServer, tools_url: str, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    config = tmp_path_factory.mktemp("api") / "robinauts.toml"
    config.write_text(stack.config_for(model_server.base_url, tools_url))
    with (
        stack.database(config) as url,
        stack.server(config, url, env=stack.API_KEY) as running,
    ):
        yield running


@pytest.fixture
def fake_model() -> FakeModel:
    return EchoModel()


@pytest.fixture
def local_gpt(model_server: FakeLocalGPTServer, fake_model: FakeModel) -> FakeLocalGPTServer:
    model_server.model = fake_model
    model_server.received.clear()
    return model_server


@pytest.fixture
def api(server: str, local_gpt: FakeLocalGPTServer) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=server, timeout=30.0) as client:
        yield client
