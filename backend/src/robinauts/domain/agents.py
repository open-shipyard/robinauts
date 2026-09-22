# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Agents are configuration: the engine that runs one, and how ids are spelt.

An agent is a name, a system prompt, a model and an engine
(``docs/specs/agents.md``); the operator writes them in the configuration and
users do not create them. What the conversation format needs of it is here:
the engine a message was produced by, and the shape of the ids an agent and a
model are referred to by. So are the records an operator's configuration is
read into -- ``AgentDefinition``, ``ModelProviderConfig``, ``ModelConfig`` and
the ``ModelsConfig`` that holds the three tables together.

**The records alone, with no reading of any file.** An adapter reads the TOML
and ``robinauts.core.parse_models_config`` decides whether it describes a
deployment, exactly as sign-in is read (``docs/layout.md``). What is here is
what every layer above needs and the rules each record keeps to.

**No key is ever in one of these.** A provider names the *environment
variable* its key is read from, which is the whole of what the configuration
carries; reading it is the adapter's, and what it read travels in a
``ProviderKeys`` (``robinauts.adapters.config_file``) that prints nothing.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlsplit

from robinauts.domain.errors import InvalidValueError
from robinauts.domain.values import checked_line, checked_text, describe

MAX_CONFIG_ID_CHARS = 40

_CONFIG_ID = re.compile(rf"[a-z0-9][a-z0-9_-]{{0,{MAX_CONFIG_ID_CHARS - 1}}}")
"""What an id the operator writes in the configuration may be spelt with.

Deliberately the same rule as a provider's id
(``robinauts.domain.sign_in.is_provider_id``), and for the same reason: these
ids are keys of a configuration table, they travel in URLs, and they are
recorded on every message an agent produced. One spelling rule means an
operator learns it once, and nothing downstream has to wonder how long an id
can be or what may be in it.
"""


def is_config_id(value: object) -> bool:
    """Whether ``value`` is spelt the way an agent's or a model's id is spelt."""
    return isinstance(value, str) and _CONFIG_ID.fullmatch(value) is not None


def checked_config_id(value: object, what: str) -> str:
    """``value`` if it is an id of that shape; ``InvalidValueError`` if not."""
    if not isinstance(value, str) or _CONFIG_ID.fullmatch(value) is None:
        raise InvalidValueError(
            f"{what} is a name: lower-case letters, digits, '-' and '_', at most "
            f"{MAX_CONFIG_ID_CHARS} of them, not {describe(value)}"
        )
    return value


class Engine(StrEnum):
    """The agent frameworks a turn can be run by (``docs/specs/agents.md``).

    A property of the agent, recorded on every message, so that a conversation
    says which engine produced which answer after the agent has been changed.
    The values are the ones the configuration is written with.
    """

    LANGGRAPH = "langgraph"
    PYDANTIC_AI = "pydantic-ai"


MAX_AGENT_TITLE_CHARS = 120
"""The longest an agent's title may be.

A conversation's title's bound (``robinauts.domain.conversation``), because
both are shown in the same kind of place -- a list, a picker, a heading -- and
one bound is one thing for an operator to learn. It is not imported from
there: that module is built on this one.
"""

MAX_SYSTEM_PROMPT_CHARS = 100_000
"""The longest a system prompt may be.

Generous, since a long prompt is a real way of writing an agent, and bounded
all the same: it is read from a file the operator wrote, sent to a provider on
every turn, and a configuration that holds a megabyte of it is a mistake
somebody should be told about at start-up rather than at the first turn.
"""


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """An agent as the operator defined it: a name, a prompt, a model, an engine.

    The record alone (``docs/specs/agents.md``). **Reading the configuration
    is not here**: an adapter reads the raw tables and ``core`` turns them into
    these, as it does for sign-in, and that is a step of its own. What is here
    is what every layer above needs -- the application to run a turn with it,
    an agent adapter to be handed it -- and the rules it keeps to.

    The system prompt is **not a message** and is never stored in a
    conversation: it is taken from the agent's configuration at every turn, so
    editing an agent takes effect at the next turn of its existing
    conversations (``docs/specs/conversations.md``).
    """

    id: str
    """How the configuration and every message produced by it name this agent."""
    title: str
    """What a person picks it by."""
    system_prompt: str
    """What the agent is told before the conversation. May be empty."""
    model: str
    """The platform's own id for the model, not the vendor's name for it."""
    engine: Engine

    def __post_init__(self) -> None:
        checked_config_id(self.id, "an agent's id")
        checked_config_id(self.model, "a model's id")
        checked_line(self.title, "an agent's title", MAX_AGENT_TITLE_CHARS)
        if not self.title.strip():
            raise InvalidValueError("an agent has a title: it is what a person picks it by")
        checked_text(self.system_prompt, "an agent's system prompt", MAX_SYSTEM_PROMPT_CHARS)
        if not isinstance(self.engine, Engine):
            raise InvalidValueError(f"an engine is an Engine, not {describe(self.engine)}")


class ProviderKind(StrEnum):
    """The kinds of model provider the configuration knows how to describe.

    The platform's own vocabulary, not a framework's: an engine translates
    these into whichever client it reaches the vendor with
    (``docs/specs/agents.md``). ``OPENAI_COMPATIBLE`` is how OpenRouter and
    any self-hosted endpoint speaking the same protocol are named, and it is
    the one kind that carries a ``base_url``.

    **Not every kind is reachable from every build.** A kind whose client does
    not pass the dependency policy is not offered until it does
    (``DEPENDENCIES.md``), which is why ``robinauts.core.parse_models_config``
    is told which kinds the deployment can build rather than assuming all of
    them.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"


MAX_ENV_NAME_CHARS = 120
"""The longest the name of an environment variable in the configuration may be.

A bound on a *name*, never on a value: what the variable holds is a key this
never sees.
"""

MAX_MODEL_NAME_CHARS = 200
"""The longest a vendor's name for a model may be, such as ``claude-sonnet-5``."""

MAX_BASE_URL_CHARS = 500
"""The longest an OpenAI-compatible endpoint's URL may be."""

DEFAULT_MODEL_TIMEOUT_SECONDS = 120.0
"""How long one call to a model may take when the configuration does not say.

Per **model call**, and therefore always shorter than the timeout on the whole
turn (``robinauts.application.DEFAULT_TURN_SECONDS``): a turn that has run out
of time is failed by the application whatever the provider is doing, and a
model call that hangs should be the engine's own failure and not that.
"""

MAX_MODEL_TIMEOUT_SECONDS = 3600.0
"""Past this a timeout is not a timeout. An hour is already far past any turn."""

MAX_OUTPUT_TOKENS = 10_000_000
"""The largest ``max_output_tokens`` a model may be configured with.

Nothing close to any model's limit; it is here so that a digit typed twice is
refused at start-up rather than paid for.
"""


_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
"""What a portable environment variable's name is spelt with (POSIX)."""


def is_env_name(value: object) -> bool:
    """Whether ``value`` is the name of an environment variable rather than a value.

    The one rule, here rather than in ``core``, because two configurations ask
    it -- a sign-in provider's client secret and a model provider's key -- and
    a rule in two places is two rules. It is also the cheapest guard there is
    against the mistake that matters: a key pasted where its variable's name
    belongs, which would put the key in the file.
    """
    return isinstance(value, str) and _ENV_NAME.fullmatch(value) is not None


LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
"""The hosts a plain-text endpoint may be on: this machine, and nowhere else.

Spelt as ``urlsplit`` reports a host -- lower case, and an IPv6 address
without the brackets it is written in -- so ``http://[::1]:8080/v1`` is this
machine and is allowed.
"""


def is_endpoint_url(value: object) -> bool:
    """Whether ``value`` is an endpoint the platform will send a key to.

    ``https://`` anywhere, ``http://`` on the loopback interface only: an
    operator's key is what travels to this URL, and a plain-text endpoint on
    another machine is a key given away. A host is required -- ``https://`` on
    its own reaches nothing -- and there is no query and no fragment, because
    a base URL is a prefix a client appends paths to and either of those would
    land in the middle of the request it builds.

    **No userinfo.** ``https://user:sk-live@gateway/v1`` is a credential
    written into the configuration file, and from there into every log line,
    error message and copy of the file that names the endpoint -- which is the
    one thing this configuration promises never to hold
    (``docs/specs/agents.md``). A provider's credential is the environment
    variable ``api_key_env`` names, and nowhere else.

    The host is taken from ``urlsplit``, which is what unbrackets an IPv6
    address, separates any userinfo and lower-cases what is left; deciding
    that by hand is how ``[::1]`` becomes a host called ``[``, and how
    ``http://localhost@evil.example/v1`` becomes "localhost". Deliberately
    narrow all the same: ``core`` has the parser that normalises what a
    browser is redirected to, and ``domain`` may not import it. What this
    refuses is what would be dangerous or would not work; what it accepts is
    handed to the client as it stands.
    """
    if not isinstance(value, str) or not value:
        return False
    if any(character.isspace() for character in value) or not value.isascii():
        return False
    if "?" in value or "#" in value:
        return False
    try:
        split = urlsplit(value)
        # `urlsplit` parses lazily: it is reading the port that raises on one
        # that is not a number, so the port is read here, inside the `try`,
        # and not left for a client to fall over later.
        _ = split.port
    except ValueError:
        return False
    if split.username is not None or split.password is not None:
        return False
    if not split.hostname:
        return False
    if split.scheme == "https":
        return True
    return split.scheme == "http" and split.hostname in LOOPBACK_HOSTS


@dataclass(frozen=True, slots=True)
class ModelProviderConfig:
    """One vendor a deployment may reach, and where its key is read from.

    ``api_key_env`` is the **name** of an environment variable, exactly as a
    sign-in provider's ``client_secret_env`` is: keys are the operator's, read
    once at start-up, never stored in the database, never logged and never
    sent to the browser (``docs/specs/agents.md``).
    """

    id: str
    """The platform's own id for this provider, which a model refers to."""
    kind: ProviderKind
    api_key_env: str
    """The name of the environment variable the key is read from."""
    base_url: str | None = None
    """Where an OpenAI-compatible endpoint lives; ``None`` for the other kinds.

    Required for ``OPENAI_COMPATIBLE`` and refused for the rest, because a
    base URL for a vendor with one endpoint is either a mistake or a way to
    send the operator's key somewhere else.
    """

    def __post_init__(self) -> None:
        checked_config_id(self.id, "a model provider's id")
        if not isinstance(self.kind, ProviderKind):
            raise InvalidValueError(
                f"a model provider's kind is a ProviderKind, not {describe(self.kind)}"
            )
        checked_line(self.api_key_env, "a model provider's api_key_env", MAX_ENV_NAME_CHARS)
        if not is_env_name(self.api_key_env):
            raise InvalidValueError(
                f"api_key_env is the NAME of an environment variable holding the key,"
                f" not {describe(self.api_key_env)}"
            )
        if self.kind is ProviderKind.OPENAI_COMPATIBLE:
            if not self.base_url:
                raise InvalidValueError(
                    "an openai-compatible provider needs its base_url: there is no"
                    " endpoint to guess"
                )
            checked_line(self.base_url, "a model provider's base_url", MAX_BASE_URL_CHARS)
            if not is_endpoint_url(self.base_url):
                # The value is not echoed: it may hold the very credential
                # this refuses, and a refusal is not a place to print one.
                raise InvalidValueError(
                    "base_url is an https:// endpoint (http:// only on the loopback"
                    " interface), with no query, no fragment and no user:password in it"
                )
        elif self.base_url is not None:
            raise InvalidValueError(
                f"only an openai-compatible provider has a base_url; {self.kind.value}"
                f" has one endpoint of its own"
            )


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """One model an agent may be pointed at: whose it is, and what it is called.

    The platform's id (``id``) and the vendor's name for it (``name``) are two
    things on purpose: an agent refers to the platform's, so that changing
    which vendor model an id means is a line of configuration and not a change
    to every agent (``docs/specs/agents.md``).
    """

    id: str
    provider: str
    """The id of the ``ModelProviderConfig`` this model is reached through."""
    name: str
    """The vendor's own name for the model, sent to the provider as it stands."""
    timeout_seconds: float = DEFAULT_MODEL_TIMEOUT_SECONDS
    """How long one call to this model may take.

    **The turn's timeout is the outer bound**, and it is not this one: the
    application fails a turn that has taken longer than ``turn_seconds``
    whatever the provider is doing (``robinauts.application.Turns``), so a
    model timeout set above it is simply never reached -- the turn ends
    first, and it ends as a turn that ran out of time rather than as a
    provider that would not answer. It is left settable past that all the
    same: the two numbers belong to different people, the bound that matters
    is enforced either way, and refusing a configuration over a number that
    can only make it stricter would be a start-up failure about nothing.
    """
    max_output_tokens: int | None = None
    """The most tokens one answer may hold; ``None`` leaves it to the engine.

    ``None`` rather than a number, because what a sensible ceiling is belongs
    to the client and moves with the vendor's models. An engine that must send
    one says what it sends.
    """

    def __post_init__(self) -> None:
        checked_config_id(self.id, "a model's id")
        checked_config_id(self.provider, "a model provider's id")
        checked_line(self.name, "a model's name", MAX_MODEL_NAME_CHARS)
        if not self.name.strip():
            raise InvalidValueError("a model has a name: what the vendor calls it")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int | float)
            or not 0 < self.timeout_seconds <= MAX_MODEL_TIMEOUT_SECONDS
        ):
            raise InvalidValueError(
                f"a model's timeout_seconds is a number of seconds over 0 and at most"
                f" {MAX_MODEL_TIMEOUT_SECONDS:g}, not {describe(self.timeout_seconds)}"
            )
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 0 < self.max_output_tokens <= MAX_OUTPUT_TOKENS
        ):
            raise InvalidValueError(
                f"a model's max_output_tokens is a whole number over 0 and at most"
                f" {MAX_OUTPUT_TOKENS}, not {describe(self.max_output_tokens)}"
            )


@dataclass(frozen=True, slots=True)
class ModelsConfig:
    """The model half of a deployment's configuration: providers, models, agents.

    Three tables that refer to one another, held together so that the thing
    handed to the composition root is whole: every agent names a model that is
    here, and every model names a provider that is here. ``core`` is what
    proves that of an operator's file; this record is what the proof produces,
    and a caller may look things up in it without wondering.

    Empty is a deployment with no agents, which is allowed and starts: the
    picker has nothing in it and ``/api/agents`` is empty
    (``docs/working-notes/poc-scope.md``).
    """

    providers: Mapping[str, ModelProviderConfig] = field(default_factory=dict)
    models: Mapping[str, ModelConfig] = field(default_factory=dict)
    agents: Mapping[str, AgentDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for where, table, wanted in (
            ("providers", self.providers, ModelProviderConfig),
            ("models", self.models, ModelConfig),
            ("agents", self.agents, AgentDefinition),
        ):
            for key, value in table.items():
                if not isinstance(value, wanted) or value.id != key:
                    raise InvalidValueError(f"the entry under {where}.{key} is not that entry")
            object.__setattr__(self, where, MappingProxyType(dict(table)))
        for model in self.models.values():
            if model.provider not in self.providers:
                raise InvalidValueError(
                    f"model {model.id!r} is reached through provider {model.provider!r},"
                    f" which is not configured"
                )
        for agent in self.agents.values():
            if agent.model not in self.models:
                raise InvalidValueError(
                    f"agent {agent.id!r} runs on model {agent.model!r}, which is not" f" configured"
                )

    def model_for(self, agent: AgentDefinition) -> ModelConfig:
        """The model that agent runs on. Whole by construction, so this cannot miss."""
        return self.models[agent.model]

    def provider_for(self, model: ModelConfig) -> ModelProviderConfig:
        """The provider that model is reached through."""
        return self.providers[model.provider]
