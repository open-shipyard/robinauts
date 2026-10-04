# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The configuration ``tests/e2e`` runs the server on: one agent per engine, both on models
served by ``FakeLocalGPTServer``, and what a request to it should carry.

Given an MCP server, it also has one agent per engine with that server's tools,
``<engine>_tools``.
"""

from __future__ import annotations

from typing import Any

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

[models.local_gpt_2]
provider = "local_gpt"
name = "fake-gpt-2"
title = "Local GPT 2"

[agents.langchain]
title = "LangChain"
system_prompt = "{system_prompt}"
model = "local_gpt"
engine = "langchain"

[agents.pydantic_ai]
title = "Pydantic AI"
system_prompt = "{system_prompt}"
model = "local_gpt"
engine = "pydantic-ai"
"""

TOOLS_CONFIG = """
[tool_servers.tools]
url = "{tools_url}"
auth = "none"

[agents.langchain_tools]
title = "LangChain with tools"
system_prompt = "{system_prompt}"
model = "local_gpt"
engine = "langchain"
tools = ["tools"]

[agents.pydantic_ai_tools]
title = "Pydantic AI with tools"
system_prompt = "{system_prompt}"
model = "local_gpt"
engine = "pydantic-ai"
tools = ["tools"]
"""

API_KEY = {"LOCAL_GPT_KEY": "not-a-real-key"}


def config_for(base_url: str, tools_url: str | None = None) -> str:
    config = CONFIG.format(base_url=base_url, system_prompt=SYSTEM_PROMPT)
    if tools_url is not None:
        config += TOOLS_CONFIG.format(tools_url=tools_url, system_prompt=SYSTEM_PROMPT)
    return config


def sent(request: dict[str, Any]) -> list[tuple[str, str]]:
    """The conversation a request carried, as ``(role, text)``, its system prompt checked."""
    system, *rest = request["messages"]
    assert (system["role"], system["content"]) == ("system", SYSTEM_PROMPT)
    return [(m["role"], m["content"]) for m in rest]
