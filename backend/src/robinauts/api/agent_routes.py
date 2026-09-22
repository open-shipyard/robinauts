# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The agents a conversation can be started with: ``GET /api/agents``.

Its own module and its own router, because it is its own subject: the
conversation routes are about one person's conversations, and this is about
what the **deployment** is configured with -- the same list for everybody
signed in, holding no conversation, no run and nothing of anybody's
(``docs/specs/agents.md``).

Signed in all the same. The list says which agents an operator runs and on
which engine, which is not something a deployment tells the world.

**It may also answer 405 and 500**, described once as the document's
``default`` answer, and it does not serve HEAD -- both for the reasons
``robinauts.api.conversation_routes`` gives.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from robinauts.api.access import signed_in, turning
from robinauts.api.refusals import LISTING_AGENTS
from robinauts.api.schemas import AgentListResponse, AgentSummary

agent_router = APIRouter(prefix="/api", tags=["agents"])


@agent_router.get("/agents", dependencies=[signed_in()], responses=LISTING_AGENTS)
async def list_agents(request: Request) -> AgentListResponse:
    """The agents this deployment is configured with, for the picker.

    The id to start a conversation with, the title to show, and the engine it
    runs on. **Not the system prompt**, which is the operator's and is not a
    message, and nothing about a vendor or a key (``docs/specs/agents.md``).

    Declared rather than injected: the list is the deployment's and is the
    same for everybody signed in, so the route needs the declaration and not
    the person.

    They are fixed at start-up in this version: the configuration is read once
    by the composition root, so an agent added or removed shows here after a
    restart.
    """
    return AgentListResponse(
        items=[AgentSummary.of(definition) for definition in turning(request).agents]
    )
