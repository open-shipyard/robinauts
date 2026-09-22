# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Both real engines, each over a model a test writes the answer for.

What the two swap tests share (``tests/unit/test_engine_swap.py`` and the
configuration swap in ``tests/integration/test_create_app.py``). Each engine's
own module scripts its own framework's model in its own terms; here they are
scripted **together**, and each records the same normalised view of what it was
told -- ``(role, text)`` pairs and the system prompt beside them -- so that a
test can ask both engines the same question about the history they received.

Nothing here reaches a provider: what is replaced is the one seam each adapter
has for its vendor (``chat_model_for``, ``model_for``), and the adapters, the
application and the store are the deployment's own.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from pydantic_ai import ModelRequest
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, FunctionModel

from conversations import AGENT, MODEL, agent_definition
from robinauts.adapters import ProviderKeys
from robinauts.adapters.agents.langgraph import LangGraphAgent
from robinauts.adapters.agents.pydantic_ai import PydanticAIAgent
from robinauts.domain import (
    Engine,
    ModelConfig,
    ModelProviderConfig,
    ModelsConfig,
    ProviderKind,
    Role,
)
from robinauts.ports import Agent

PROVIDER = "anthropic"
KEY_VARIABLE = "ROBINAUTS_ANTHROPIC_KEY"
KEY = "not-a-real-key"
"""What the engines are handed. Nothing here spends it, or could."""

MODELS = ModelsConfig(
    providers={
        PROVIDER: ModelProviderConfig(
            id=PROVIDER, kind=ProviderKind.ANTHROPIC, api_key_env=KEY_VARIABLE
        )
    },
    models={MODEL: ModelConfig(id=MODEL, provider=PROVIDER, name="claude-sonnet-5")},
    agents={AGENT: agent_definition()},
)
"""One provider and one model, which both engines reach by the same id.

An agent's engine can be swapped only if its model exists under both
(``docs/specs/agents.md``); this is that, as a deployment writes it.
"""

Heard = tuple[tuple[str, str], ...]
"""One call's history as (role, text) pairs: what a model was really told."""

_ROLE_OF = {"human": Role.USER.value, "ai": Role.ASSISTANT.value}
"""LangChain's names for the two roles, as the platform spells them."""


class ScriptedChat(BaseChatModel):
    """The LangGraph half: a chat model that streams what the test wrote.

    A real ``BaseChatModel`` with a real ``_astream``, so the engine's graph,
    its streaming and its releasing are exercised as they would be against a
    provider.
    """

    said: str = ""
    heard: list[Heard] = []
    """Every call's history, normalised: what this engine handed the model."""
    instructions: list[str] = []
    """Every call's system prompt, which is not one of the messages."""

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover -- never asked
        raise NotImplementedError("this model only streams")

    async def _astream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.instructions.append(
            "".join(str(message.content) for message in messages if message.type == "system")
        )
        self.heard.append(
            tuple(
                (_ROLE_OF[message.type], str(message.content))
                for message in messages
                if message.type != "system"
            )
        )
        yield ChatGenerationChunk(message=AIMessageChunk(content=self.said))


class ScriptedStream:
    """The Pydantic AI half: a model that streams what the test wrote.

    A real ``FunctionModel``, for the same reason, recording the same
    normalised view of the history so that the two engines can be asked one
    question about it.
    """

    def __init__(self, said: str, *, thinking: str = "") -> None:
        self.said = said
        self.thinking = thinking
        self.heard: list[Heard] = []
        self.instructions: list[str] = []
        self.model = FunctionModel(stream_function=self._stream, model_name="scripted")

    async def _stream(self, messages: list[Any], info: AgentInfo) -> AsyncIterator[Any]:
        self.instructions.append(info.instructions or "")
        self.heard.append(
            tuple(
                (
                    Role.USER.value if isinstance(message, ModelRequest) else Role.ASSISTANT.value,
                    "".join(getattr(part, "content", "") for part in message.parts),
                )
                for message in messages
            )
        )
        if self.thinking:
            yield {0: DeltaThinkingPart(content=self.thinking)}
        yield self.said


@dataclass(frozen=True, slots=True)
class Scripts:
    """The two models one conversation is answered by, one per engine.

    Held together so that a test reads what **both** were told without knowing
    which engine ran which turn.
    """

    langgraph: ScriptedChat
    pydantic_ai: ScriptedStream


def scripts(said: str, *, thinking: str = "") -> Scripts:
    """Both models, saying the same words, one of them thinking first.

    The same answer under either engine on purpose: a test that compared what
    was stored would otherwise be told the two apart by their text rather than
    by the one field that is allowed to differ.
    """
    return Scripts(
        langgraph=ScriptedChat(said=said),
        pydantic_ai=ScriptedStream(said, thinking=thinking),
    )


def both_engines(said: Scripts) -> dict[Engine, Agent]:
    """Both real engines, wired as a deployment wires them, over those models."""
    keys = ProviderKeys({PROVIDER: KEY})
    return {
        Engine.LANGGRAPH: LangGraphAgent(
            MODELS, keys, chat_model_for=lambda *_: said.langgraph  # noqa: ARG005
        ),
        Engine.PYDANTIC_AI: PydanticAIAgent(
            MODELS, keys, model_for=lambda *_: said.pydantic_ai.model  # noqa: ARG005
        ),
    }
