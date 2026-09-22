# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The LangGraph engine: the contract suite, the mapping, and what it never does.

The engine is run for real -- its graph compiled, its stream consumed, its
``finally`` exercised -- over a chat model the test scripts. No network, no
key: what is replaced is the one seam the adapter has for it
(``LangGraphAgent(chat_model_for=...)``), and everything else is the code a
deployment runs.

Four subjects:

- the **contract** both engines are held to (``contracts/agents.py``), run
  here over the real engine for the first time;
- the **mapping**: what the model is given, and what its chunks become. A
  turn of this engine holds one answer and always streams -- a graph with one
  node calls the model once, and the framework hands the answer over in pieces
  however the provider sent it -- which is what the two declarations on the
  contract subclass say;
- the **client**: that a model's configuration reaches Anthropic's client as
  the key, the timeout, the retries and the ceiling it describes, asserted on
  the constructed object because constructing one reaches nothing;
- **nothing phones home**: with the environment asking loudly for tracing, a
  turn attaches no tracer and this process has never built a LangSmith client.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import anthropic
import langsmith
import langsmith._internal._context
import langsmith.run_trees
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tracers import langchain as tracer_module
from langchain_core.tracers.context import _tracing_v2_is_enabled

from aio import asyncio_test
from contracts.agents import AgentContract, Ending, Script
from conversations import agent_definition, answer, question
from robinauts.adapters import ProviderKeys
from robinauts.adapters.agents.langgraph import (
    ANTHROPIC_ENDPOINT,
    ANTHROPIC_KEY_HEADER,
    CLIENT_VARIABLES_REMOVED,
    DEFAULT_ANTHROPIC_OUTPUT_TOKENS,
    MAX_RETRIES,
    TRACING_VARIABLES_REMOVED,
    LangGraphAgent,
    chat_model,
)
from robinauts.domain import (
    AgentDefinition,
    AnswerCompleted,
    AnswerReasoningDelta,
    AnswerStarted,
    AnswerTextDelta,
    Engine,
    EngineEvent,
    Message,
    ModelConfig,
    ModelProviderConfig,
    ModelsConfig,
    ProviderKind,
    ReasoningPart,
    Role,
    TextPart,
    UnsupportedContentError,
)
from robinauts.ports import Agent

PROVIDER = "anthropic"
MODEL = "sonnet"
AGENT = "assistant"
KEY = "not-a-real-key"
"""What the tests hand the engine. Nothing here reaches a provider."""

SYSTEM_PROMPT = "Play fair."

PIECES = 3
"""How many deltas a streamed answer is scripted to arrive in."""

ANTHROPIC_PROVIDER = ModelProviderConfig(
    id=PROVIDER, kind=ProviderKind.ANTHROPIC, api_key_env="ROBINAUTS_ANTHROPIC_KEY"
)


def models(**changes: Any) -> ModelsConfig:
    """A configuration with one provider, one model and one agent on LangGraph."""
    model = ModelConfig(id=MODEL, provider=PROVIDER, name="claude-sonnet-5", **changes)
    return ModelsConfig(
        providers={PROVIDER: ANTHROPIC_PROVIDER},
        models={MODEL: model},
        agents={AGENT: definition()},
    )


def definition() -> AgentDefinition:
    return agent_definition(
        id=AGENT, model=MODEL, engine=Engine.LANGGRAPH, system_prompt=SYSTEM_PROMPT
    )


def keys() -> ProviderKeys:
    return ProviderKeys({PROVIDER: KEY})


class ScriptedChatModel(BaseChatModel):
    """A chat model a test writes the chunks for, and can stop or break.

    A real ``BaseChatModel`` with a real ``_astream``, so the engine's graph,
    its streaming and its releasing are exercised as they would be against a
    provider -- and so that a cancellation reaches an ``await`` the way it
    would reach a socket. ``open_streams`` is what "the engine released what
    it held" looks like from underneath: the ``finally`` of this generator is
    reached only when the stream is closed.
    """

    chunks: list[Any] = []
    """What ``_astream`` yields, one ``AIMessageChunk`` content each."""
    error: Any = None
    """Raised after the chunks, which is how a provider fails mid-answer."""
    gate: Any = None
    """Awaited after the chunks: a turn that hangs, for the cancellation test."""
    provider_metadata: dict[str, Any] = {}
    """What the chunks carry as ``response_metadata``; Anthropic names itself."""
    seen: list[list[BaseMessage]] = []
    """Every call's messages, exactly as the graph handed them over."""
    open_streams: int = 0

    model_config = {"arbitrary_types_allowed": True}

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        """The whole answer at once: what a model that does not stream does."""
        self.seen.append(list(messages))
        whole = AIMessageChunk(content="", response_metadata=dict(self.provider_metadata))
        for content in self.chunks:
            whole = whole + AIMessageChunk(
                content=content, response_metadata=dict(self.provider_metadata)
            )
        return ChatResult(generations=[ChatGeneration(message=whole)])

    async def _astream(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.seen.append(list(messages))
        self.open_streams += 1
        try:
            for content in self.chunks:
                chunk = ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=content, response_metadata=dict(self.provider_metadata)
                    )
                )
                if run_manager is not None:
                    await run_manager.on_llm_new_token(chunk.text, chunk=chunk)
                yield chunk
            if self.error is not None:
                raise self.error
            if self.gate is not None:
                await self.gate.wait()
        finally:
            self.open_streams -= 1


def in_pieces(text: str, pieces: int = PIECES) -> list[str]:
    """``text`` cut into that many pieces, the way a provider sends one."""
    size = max(1, -(-len(text) // pieces))
    return [text[start : start + size] for start in range(0, len(text), size)]


def scripted(script: Script) -> ScriptedChatModel:
    """The chat model one turn of that script needs.

    A turn of this engine is one call to the model, so it is the script's
    first answer that is scripted; ``answers_per_turn`` below is what keeps
    the suite from asking for a second.
    """
    said = script.answers[0].text if script.answers else ""
    streams = not script.answers or script.answers[0].streamed
    return ScriptedChatModel(
        chunks=in_pieces(said) if said else [],
        disable_streaming=not streams,
        error=RuntimeError("the provider said no") if script.ending is Ending.FAIL else None,
        gate=asyncio.Event() if script.ending is Ending.HANG else None,
    )


class TestLangGraphAgent(AgentContract):
    """The real engine, held to everything the port promises."""

    answers_per_turn = 1
    """A graph with one node calls the model once, so a turn holds one answer."""

    can_answer_without_streaming = False
    """LangGraph hands the answer over in pieces even when the model sent one."""

    def new_agent(self, script: Script) -> Agent:
        self.model = scripted(script)
        return LangGraphAgent(
            models(), keys(), chat_model_for=lambda *_: self.model  # noqa: ARG005
        )

    def held(self, agent: Agent) -> int:
        assert isinstance(agent, LangGraphAgent)
        # Both halves: the engine's own graph stream, and the model's stream
        # inside it. A turn that let go of the first and not the second would
        # still be holding a response open.
        return agent.held + self.model.open_streams

    def definition(self) -> AgentDefinition:
        return definition()


# --- what the model is given ------------------------------------------------


async def turn_of(
    agent: LangGraphAgent, history: Sequence[Message], *, definition_: AgentDefinition | None = None
) -> list[EngineEvent]:
    """Every event of one turn, run to its end."""
    seen: list[EngineEvent] = []
    events = agent.run_turn(definition_ or definition(), history)
    async for event in events:
        seen.append(event)
    return seen


def engine(model: ScriptedChatModel, **changes: Any) -> LangGraphAgent:
    return LangGraphAgent(
        models(**changes), keys(), chat_model_for=lambda *_: model  # noqa: ARG005
    )


@asyncio_test
async def test_the_system_prompt_comes_first_and_is_not_a_message() -> None:
    model = ScriptedChatModel(chunks=["Someone who plays fair."])
    asked = question("What is a robinaut?")

    await turn_of(engine(model), (asked,))

    (given,) = model.seen
    assert [(type(message).__name__, message.content) for message in given] == [
        ("SystemMessage", SYSTEM_PROMPT),
        ("HumanMessage", "What is a robinaut?"),
    ]


@asyncio_test
async def test_an_agent_with_no_system_prompt_sends_none() -> None:
    # An empty system message is not the same as none, and some providers
    # refuse it.
    model = ScriptedChatModel(chunks=["Hello."])
    agent = LangGraphAgent(models(), keys(), chat_model_for=lambda *_: model)  # noqa: ARG005

    await turn_of(
        agent,
        (question(),),
        definition_=agent_definition(
            id=AGENT, model=MODEL, engine=Engine.LANGGRAPH, system_prompt=""
        ),
    )

    (given,) = model.seen
    assert [type(message).__name__ for message in given] == ["HumanMessage"]


@asyncio_test
async def test_the_history_keeps_its_roles_and_carries_no_reasoning() -> None:
    model = ScriptedChatModel(chunks=["Again."])
    asked = question("What is a robinaut?")
    replied = answer(
        asked,
        parts=(ReasoningPart("thinking about it"), TextPart("Someone who plays fair.")),
    )
    again = question("And a robin?", parent=replied)

    await turn_of(engine(model), (asked, replied, again))

    (given,) = model.seen
    assert [(type(message).__name__, message.content) for message in given] == [
        ("SystemMessage", SYSTEM_PROMPT),
        ("HumanMessage", "What is a robinaut?"),
        # The thinking of the previous turn is not sent back: this version
        # keeps none of it, and what is stored holds none either.
        ("AIMessage", "Someone who plays fair."),
        ("HumanMessage", "And a robin?"),
    ]
    assert all(message.role is not Role.TOOL for message in (asked, replied, again))


# --- what the model's chunks become -----------------------------------------


@asyncio_test
async def test_thinking_is_streamed_as_reasoning_and_kept_out_of_the_answer() -> None:
    # Anthropic's own content blocks, as they arrive from the client: a
    # thinking block, then text. langchain-core normalises the first to a
    # standard `reasoning` block, which is what the engine reads.
    model = ScriptedChatModel(
        chunks=[
            [{"type": "thinking", "thinking": "let me think", "index": 0}],
            [{"type": "text", "text": "Someone who ", "index": 1}],
            [{"type": "text", "text": "plays fair.", "index": 1}],
        ],
        provider_metadata={"model_provider": "anthropic"},
    )

    seen = await turn_of(engine(model), (question(),))

    assert isinstance(seen[0], AnswerStarted)
    assert [event.text for event in seen if isinstance(event, AnswerReasoningDelta)] == [
        "let me think"
    ]
    assert [event.text for event in seen if isinstance(event, AnswerTextDelta)] == [
        "Someone who ",
        "plays fair.",
    ]
    completed = seen[-1]
    assert isinstance(completed, AnswerCompleted)
    # The thinking is shown as it arrives and is in none of the parts: what
    # `domain.kept_parts` would drop anyway must not be inside the text.
    assert completed.parts == (TextPart("Someone who plays fair."),)


@asyncio_test
async def test_an_answer_with_nothing_in_it_is_announced_and_completed_empty() -> None:
    # A model that streamed chunks holding no text and no thinking -- an empty
    # piece, or a kind of block this version does not carry. A message has
    # content, so "the agent answered with nothing" is recorded as one empty
    # part rather than as a turn that produced no answer.
    seen = await turn_of(engine(ScriptedChatModel(chunks=[""])), (question(),))

    assert seen == [AnswerStarted(), AnswerCompleted(parts=(TextPart(""),))]


@asyncio_test
async def test_a_character_split_across_two_chunks_is_put_back_together() -> None:
    # A provider splits where it likes; what is stored has to be storable.
    whole = "\N{ROCKET}"
    above = ord(whole) - 0x10000
    high, low = chr(0xD800 + (above >> 10)), chr(0xDC00 + (above & 0x3FF))
    model = ScriptedChatModel(chunks=[high, low])

    seen = await turn_of(engine(model), (question(),))

    assert seen[-1] == AnswerCompleted(parts=(TextPart(whole),))


@asyncio_test
async def test_a_model_that_does_not_stream_still_arrives_as_one_delta() -> None:
    """The "not streamed" shape, as this engine really produces it.

    The contract suite says an engine need not stream, and declares that this
    one always does (``can_answer_without_streaming = False``); what that
    means in practice is this. The model hands the whole answer over at once,
    LangGraph passes it on as a single message chunk, and the turn is
    announced, one delta, completed -- with exactly what was streamed, which
    is the promise that still holds.
    """
    whole = "All of it at once."
    model = ScriptedChatModel(chunks=[whole], disable_streaming=True)

    seen = await turn_of(engine(model), (question(),))

    assert [type(event) for event in seen] == [AnswerStarted, AnswerTextDelta, AnswerCompleted]
    assert [event.text for event in seen if isinstance(event, AnswerTextDelta)] == [whole]
    assert seen[-1] == AnswerCompleted(parts=(TextPart(whole),))


@asyncio_test
async def test_a_message_of_the_tool_role_is_never_sent_to_a_model() -> None:
    """The second of two refusals, and the one the engine owes.

    ``domain.Message`` already refuses the ``tool`` role, so one cannot be
    built or stored and the message below has to be forced into existence.
    The engine checks anyway: it is the line that turns a history into what a
    model is told, and the failure it would otherwise have is silent -- a
    tool result sent as though the agent had said it. The day tool results
    are carried, this is the line that has to learn what they look like, and
    a line that would have guessed is worse than one that refuses.
    """
    model = ScriptedChatModel(chunks=["Never asked."])
    from_a_tool = question("the weather is fine")
    object.__setattr__(from_a_tool, "role", Role.TOOL)

    with pytest.raises(UnsupportedContentError) as raised:
        await turn_of(engine(model), (from_a_tool,))

    assert "tool" in str(raised.value)
    assert model.seen == []


@asyncio_test
async def test_a_model_that_asks_to_use_a_tool_fails_the_turn() -> None:
    # This version has no tools: every block after the call would belong to an
    # answer that cannot be produced, so finishing the turn with whatever text
    # came with it would store half an answer that looks whole. An engine
    # reports that by raising.
    model = ScriptedChatModel(
        chunks=[
            [{"type": "text", "text": "Let me look it up. ", "index": 0}],
            [{"type": "tool_call", "name": "search", "args": {}, "id": "t1", "index": 1}],
        ],
        provider_metadata={"model_provider": "anthropic"},
    )
    agent = engine(model)

    with pytest.raises(UnsupportedContentError) as raised:
        await turn_of(agent, (question(),))

    assert "tool" in str(raised.value)
    assert (agent.held, model.open_streams) == (0, 0)


@asyncio_test
async def test_anthropics_own_spelling_of_a_tool_call_fails_the_turn_too() -> None:
    # Without the metadata langchain-core normalises by, the vendor's own
    # block arrives as it was sent; it means the same thing and is refused.
    model = ScriptedChatModel(
        chunks=[[{"type": "tool_use", "name": "search", "input": {}, "id": "t1", "index": 0}]]
    )

    with pytest.raises(UnsupportedContentError):
        await turn_of(engine(model), (question(),))


@asyncio_test
async def test_the_engine_holds_nothing_after_a_turn_that_ended() -> None:
    model = ScriptedChatModel(chunks=["Done."])
    agent = engine(model)

    await turn_of(agent, (question(),))

    assert (agent.held, model.open_streams) == (0, 0)


# --- the client the configuration describes ---------------------------------


def test_anthropic_is_built_with_the_key_timeout_retries_and_ceiling() -> None:
    model = ModelConfig(
        id=MODEL,
        provider=PROVIDER,
        name="claude-sonnet-5",
        timeout_seconds=17.0,
        max_output_tokens=1234,
    )

    built = chat_model(model, ANTHROPIC_PROVIDER, KEY)

    assert isinstance(built, ChatAnthropic)
    assert built.model == "claude-sonnet-5"
    assert built.anthropic_api_key is not None
    assert built.anthropic_api_key.get_secret_value() == KEY
    assert built.default_request_timeout == 17.0
    assert built.max_retries == MAX_RETRIES
    assert built.max_tokens == 1234


def test_a_model_with_no_ceiling_gets_the_engine_s_own() -> None:
    # Anthropic's API requires one on every request, so the engine sends one.
    built = chat_model(ModelConfig(id=MODEL, provider=PROVIDER, name="c"), ANTHROPIC_PROVIDER, KEY)

    assert isinstance(built, ChatAnthropic)
    assert built.max_tokens == DEFAULT_ANTHROPIC_OUTPUT_TOKENS


def test_the_key_is_not_in_what_the_keys_print() -> None:
    printed = repr(keys())

    assert KEY not in printed
    assert PROVIDER in printed


REDIRECTING_VARIABLES = {
    # Both are read by ChatAnthropic, and the second by the SDK underneath it,
    # when no base URL is passed: one of them inherited from a shell, a unit
    # file or a container image would send every turn -- and the key -- to
    # whatever host it named.
    "ANTHROPIC_API_URL": "https://evil.example.test",
    "ANTHROPIC_BASE_URL": "https://evil.example.test",
    # Read by ChatAnthropic when no key is passed.
    "ANTHROPIC_API_KEY": "sk-somebody-elses-key",
    # A proxy only this one client would obey. An operator's proxy is
    # HTTPS_PROXY, which is how everything else in this process is proxied.
    "ANTHROPIC_PROXY": "http://evil.example.test:3128",
}
"""An environment doing everything it can to redirect a turn and its key."""


def test_the_endpoint_and_the_key_come_from_the_configuration_and_never_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in REDIRECTING_VARIABLES.items():
        monkeypatch.setenv(name, value)

    built = chat_model(
        ModelConfig(id=MODEL, provider=PROVIDER, name="claude-sonnet-5"), ANTHROPIC_PROVIDER, KEY
    )

    assert isinstance(built, ChatAnthropic)
    assert built.anthropic_api_url == ANTHROPIC_ENDPOINT
    assert built.anthropic_api_key is not None
    assert built.anthropic_api_key.get_secret_value() == KEY
    assert built.anthropic_proxy is None
    # And the client underneath it, which has env fallbacks of its own.
    assert str(built._async_client.base_url).rstrip("/") == ANTHROPIC_ENDPOINT
    assert str(built._client.base_url).rstrip("/") == ANTHROPIC_ENDPOINT
    assert built._async_client.api_key == KEY


# --- nothing phones home ----------------------------------------------------


TRACING_VARIABLES = {
    "LANGSMITH_TRACING": "true",
    "LANGCHAIN_TRACING_V2": "true",
    "LANGSMITH_API_KEY": "not-a-real-key",
    "LANGCHAIN_API_KEY": "not-a-real-key",
    # The version 1 tracer's variables. langchain-core does not ignore them:
    # with either set and v2 tracing off -- which is what this adapter makes
    # sure of -- it raises, so a process that inherited one would fail every
    # turn. They are what `force_tracing_off` takes out of the environment.
    "LANGCHAIN_TRACING": "true",
    "LANGCHAIN_HANDLER": "langchain",
}
"""An environment doing everything it can to turn hosted tracing on."""


@pytest.fixture
def asking_to_trace(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every variable langsmith reads, set, and read afresh -- then forgotten.

    ``langsmith.utils.get_env_var`` caches, so a variable set after something
    has already asked for it would not be seen at all and a test that proved
    nothing would pass. The cache is cleared **again on the way out**, because
    a cached "true" that outlived the test would be an environment later tests
    could not see the end of.

    What ``force_tracing_off`` sets is **process-wide on purpose** and is put
    back here too: a test that left langsmith's global switch and context var
    where it found them is a test that says nothing about the next one, and
    one that left them turned off would hide a later engine that forgot to
    turn them off itself. Both are private to langsmith and are reached as
    such, which is the honest cost of checking a process-wide promise.
    """
    context = langsmith._internal._context
    was_global = context._GLOBAL_TRACING_ENABLED
    was_context = context._TRACING_ENABLED.get()
    for name, value in TRACING_VARIABLES.items():
        monkeypatch.setenv(name, value)
    langsmith.utils.get_env_var.cache_clear()
    try:
        yield
    finally:
        monkeypatch.undo()
        langsmith.utils.get_env_var.cache_clear()
        context._GLOBAL_TRACING_ENABLED = was_global
        context._TRACING_ENABLED.set(was_context)


@pytest.fixture(scope="module", autouse=True)
def no_client_at_the_end() -> Iterator[None]:
    """Nothing in this module builds a LangSmith client, first call or last.

    Asserted **after** every test of the module as well as by the test of its
    own below: the global is created on first use and kept, so the claim is
    about the whole run and not about the moment one test happened to look.
    """
    yield
    assert langsmith.run_trees._CLIENT is None


class _NeverBuilt:
    """Anything that tries to reach LangSmith. Building one fails the test."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("the engine reached LangSmith")


@asyncio_test
async def test_a_turn_attaches_no_tracer_however_loudly_the_environment_asks(
    monkeypatch: pytest.MonkeyPatch, asking_to_trace: None
) -> None:
    # `_configure` swallows a tracer that will not build, so a tracer that
    # refuses to exist is not enough on its own: the predicate langchain-core
    # decides by is what is asserted, and the stand-in is what would catch a
    # tracer attached some other way.
    monkeypatch.setattr(tracer_module, "LangChainTracer", _NeverBuilt)
    model = ScriptedChatModel(chunks=["Quietly."])

    seen = await turn_of(engine(model), (question(),))

    assert [event for event in seen if isinstance(event, AnswerTextDelta)]
    assert _tracing_v2_is_enabled() is False


def test_the_engine_turns_tracing_off_the_moment_it_is_built(
    asking_to_trace: None,
) -> None:
    LangGraphAgent(models(), keys(), chat_model_for=lambda *_: ScriptedChatModel())  # noqa: ARG005

    assert _tracing_v2_is_enabled() is False


def test_turning_tracing_off_takes_the_version_1_variables_out_of_the_environment(
    asking_to_trace: None,
) -> None:
    # Turning tracing off must not be a way of breaking a deployment:
    # langchain-core raises on every call when one of these is set and v2
    # tracing is off, which is exactly the state this adapter puts it in.
    LangGraphAgent(models(), keys(), chat_model_for=lambda *_: ScriptedChatModel())  # noqa: ARG005

    assert all(name not in os.environ for name in TRACING_VARIABLES_REMOVED)


def test_no_langsmith_client_has_been_built_in_this_process() -> None:
    """Importing the engine, building one and running turns opens no client.

    The global below is the only client langchain-core's tracer would use, and
    it is created on first use and kept. It being ``None`` after this module's
    import and every turn above is the whole claim: nothing here has talked to
    LangSmith, and nothing could have without building it.
    """
    assert langsmith.run_trees._CLIENT is None


CUSTOM_HEADERS = "ANTHROPIC_CUSTOM_HEADERS"
"""The one client variable an argument cannot override: headers are merged."""


def test_the_key_header_is_the_configured_key_whatever_the_environment_injects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The SDK merges this variable into the headers the caller passed, so one
    # line of it would replace the key header outright and a turn would be
    # spent on somebody else's key. The caller's header wins, and the engine
    # is a caller.
    monkeypatch.setenv(CUSTOM_HEADERS, f"{ANTHROPIC_KEY_HEADER}: sk-somebody-elses-key")

    built = chat_model(
        ModelConfig(id=MODEL, provider=PROVIDER, name="claude-sonnet-5"), ANTHROPIC_PROVIDER, KEY
    )

    assert isinstance(built, ChatAnthropic)
    sent = _headers_of(built)
    assert [value for name, value in sent if name.lower() == ANTHROPIC_KEY_HEADER] == [KEY]


def test_building_the_engine_takes_the_header_variable_out_of_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The other half: an argument cannot say "and nothing else", so the
    # variable itself goes when the engine is built at start-up.
    monkeypatch.setenv(CUSTOM_HEADERS, "anthropic-beta: nobody-configured-this")

    LangGraphAgent(models(), keys(), chat_model_for=lambda *_: ScriptedChatModel())  # noqa: ARG005

    assert all(name not in os.environ for name in CLIENT_VARIABLES_REMOVED)


def _headers_of(built: ChatAnthropic) -> list[tuple[str, str]]:
    """The headers the client would really send, built without sending one."""
    client = built._async_client
    request = client._build_request(
        anthropic._models.FinalRequestOptions.construct(
            method="post", url="/v1/messages", json_data={}
        )
    )
    return list(request.headers.multi_items())
