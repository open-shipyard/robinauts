# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The configuration ``tests/e2e`` runs the server on: one agent per engine, both on models
served by ``FakeLocalGPTServer``, and what a request to it should carry."""

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

API_KEY = {"LOCAL_GPT_KEY": "not-a-real-key"}


def config_for(base_url: str) -> str:
    return CONFIG.format(base_url=base_url, system_prompt=SYSTEM_PROMPT)


def sent(request: dict[str, Any]) -> list[tuple[str, str]]:
    """The conversation a request carried, as ``(role, text)``, its system prompt checked."""
    system, *rest = request["messages"]
    assert (system["role"], system["content"]) == ("system", SYSTEM_PROMPT)
    return [(m["role"], m["content"]) for m in rest]
