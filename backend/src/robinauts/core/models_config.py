# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Checking the model configuration, from raw tables into domain records.

The other half of the file ``core.sign_in_config`` reads, and written the same
way and for the same reasons: an adapter parses the TOML and hands the tables
here, so that reading a file and judging what is in it stay apart and this can
be tested with a dict. **Unknown keys are errors**, because a misspelt key
that was ignored would be a rule the operator believes is in force; **every
problem is reported at once**, so that a deployment is fixed in one pass.

    [model_providers.anthropic]
    kind = "anthropic"
    api_key_env = "ROBINAUTS_ANTHROPIC_KEY"

    [models.sonnet]
    provider = "anthropic"
    name = "claude-sonnet-5"
    timeout_seconds = 120
    max_output_tokens = 8192

    [agents.assistant]
    title = "Assistant"
    model = "sonnet"
    engine = "langgraph"
    system_prompt = "Play fair."

``model_providers`` and not ``providers``: the latter is already the identity
providers people sign in with, and the two live in one file
(``docs/specs/agents.md``).

``base_url`` belongs to the kinds that name a **protocol** rather than a vendor
(``domain.KINDS_WITH_BASE_URL``): it is required there, because there is no
endpoint to guess, and refused everywhere else, because a vendor's endpoint is
the engine's own constant and a second answer to "where is it" would be a way
to send the operator's key somewhere else.

**No key is in the file.** A provider names the environment variable its key
is read from; reading it belongs to ``robinauts.adapters.config_file``, which
is the layer that may touch the environment, and which reports every unset
variable at once in the same way.

**What this deployment can build is told to it, not assumed.** ``engines`` is
the set of engines wired in the composition root and ``kinds`` the set of
provider kinds it has a client for -- a package that fails the dependency
policy is a provider the build does not offer (``DEPENDENCIES.md``). ``core``
cannot know either, and an agent pointed at something that was never built
would otherwise be a deployment that starts and fails at the first turn, so
both are refused here, among every other problem.

**No agents at all is a configuration**, not a mistake: a file with no
``[agents]`` table describes a deployment that starts with none and serves an
empty picker (``docs/working-notes/poc-scope.md``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from robinauts.core.sign_in_config import TOP_LEVEL_KEYS
from robinauts.domain import (
    KINDS_WITH_BASE_URL,
    MAX_AGENT_TITLE_CHARS,
    MAX_BASE_URL_CHARS,
    MAX_CONFIG_ID_CHARS,
    MAX_ENV_NAME_CHARS,
    MAX_MODEL_NAME_CHARS,
    MAX_MODEL_TIMEOUT_SECONDS,
    MAX_OUTPUT_TOKENS,
    MAX_SYSTEM_PROMPT_CHARS,
    AgentDefinition,
    ConfigError,
    Engine,
    InvalidValueError,
    ModelConfig,
    ModelProviderConfig,
    ModelsConfig,
    ProviderKind,
    is_config_id,
    is_endpoint_url,
    is_env_name,
)

MODEL_PROVIDER_KEYS = frozenset({"kind", "api_key_env", "base_url"})
MODEL_ENTRY_KEYS = frozenset({"provider", "name", "timeout_seconds", "max_output_tokens"})
AGENT_KEYS = frozenset({"title", "model", "engine", "system_prompt"})

_KINDS = {kind.value: kind for kind in ProviderKind}
_ENGINES = {engine.value: engine for engine in Engine}

ALL_ENGINES: frozenset[Engine] = frozenset(Engine)
"""Every engine there is, which is what a test of these rules alone assumes."""

ALL_KINDS: frozenset[ProviderKind] = frozenset(ProviderKind)
"""Every provider kind there is; a deployment passes what it can build."""


def parse_models_config(
    data: Mapping[str, Any],
    *,
    engines: frozenset[Engine] = ALL_ENGINES,
    kinds: frozenset[ProviderKind] = ALL_KINDS,
) -> ModelsConfig:
    """The model configuration these tables describe.

    Raises ``ConfigError`` whose ``problems`` names every fault found, each
    saying where it is and what was expected. ``engines`` and ``kinds`` are
    what the deployment can build; anything else is refused here rather than
    at the first turn.
    """
    problems: list[str] = []
    # "Unknown" means unknown to both halves of the file: the sign-in tables
    # are somebody else's business and are not mistakes. ``admin`` is refused
    # by the sign-in parser, and refusing it twice would be one mistake
    # reported as two.
    _unknown(data, TOP_LEVEL_KEYS | {"admin"}, "", problems)

    # The **declared** tables, not the built records, are what a reference is
    # checked against below. A provider with a mistake in it is still a
    # provider the operator declared, and reporting every model that names it
    # -- and every agent that names those models -- would bury the one mistake
    # under the cascade it caused. It is the sign-in parser's rule for
    # ``[[allow]]``, for the same reason.
    declared_providers = _table(data, "model_providers", problems)
    declared_models = _table(data, "models", problems)

    providers: dict[str, ModelProviderConfig] = {}
    for provider_id, table in declared_providers.items():
        provider = _provider(provider_id, table, kinds, problems)
        if provider is not None:
            providers[provider.id] = provider

    models: dict[str, ModelConfig] = {}
    for model_id, table in declared_models.items():
        model = _model(model_id, table, declared_providers, problems)
        if model is not None:
            models[model.id] = model

    agents: dict[str, AgentDefinition] = {}
    for agent_id, table in _table(data, "agents", problems).items():
        agent = _agent(agent_id, table, declared_models, engines, problems)
        if agent is not None:
            agents[agent.id] = agent

    if problems:
        raise ConfigError(problems)
    return ModelsConfig(providers=providers, models=models, agents=agents)


def _table(data: Mapping[str, Any], key: str, problems: list[str]) -> Mapping[str, Any]:
    """The table under ``key``, or an empty one, saying so if it is not a table."""
    raw = data.get(key, {})
    if not isinstance(raw, Mapping):
        problems.append(f"{key}: a table of entries by id")
        return {}
    return raw


def _provider(
    provider_id: object,
    table: object,
    kinds: frozenset[ProviderKind],
    problems: list[str],
) -> ModelProviderConfig | None:
    where = f"model_providers.{provider_id}"
    if not is_config_id(provider_id):
        problems.append(
            f"{where}: an id is up to {MAX_CONFIG_ID_CHARS} lower-case letters, digits," f" _ and -"
        )
        return None
    if not isinstance(table, Mapping):
        problems.append(f"{where}: a table")
        return None
    before = len(problems)
    _unknown(table, MODEL_PROVIDER_KEYS, where, problems)

    kind = None
    raw_kind = _string(table, "kind", where, problems)
    if raw_kind:
        kind = _KINDS.get(raw_kind)
        if kind is None:
            problems.append(f"{where}.kind: one of {_named(_KINDS)}, not {raw_kind!r}")
        elif kind not in kinds:
            # A client that does not pass the dependency policy is a provider
            # this build does not offer (``DEPENDENCIES.md``). Said at
            # start-up, with what can be used instead, rather than found out
            # by a person waiting for an answer.
            problems.append(
                f"{where}.kind: this build cannot reach {raw_kind!r} providers;"
                f" it was built with {_named(kinds)}"
            )
            kind = None

    api_key_env = _string(table, "api_key_env", where, problems, limit=MAX_ENV_NAME_CHARS)
    if api_key_env and not is_env_name(api_key_env):
        problems.append(
            f"{where}.api_key_env: the NAME of an environment variable holding the key,"
            f" not the key itself"
        )
        api_key_env = ""

    base_url = None
    if "base_url" in table:
        base_url = _string(table, "base_url", where, problems, limit=MAX_BASE_URL_CHARS) or None
        if base_url is None:
            pass
        elif kind is not None and kind not in KINDS_WITH_BASE_URL:
            problems.append(
                f"{where}.base_url: only these kinds have one:"
                f" {_named(KINDS_WITH_BASE_URL)}; {kind.value} has one endpoint of"
                f" its own"
            )
            base_url = None
        elif not is_endpoint_url(base_url):
            problems.append(
                f"{where}.base_url: an https:// endpoint (http:// on the loopback"
                f" interface only), with no query, no fragment and no user:password"
                f" in it -- a provider's credential is the variable api_key_env"
                f" names and is never in this file"
            )
            base_url = None
    elif kind is not None and kind in KINDS_WITH_BASE_URL:
        problems.append(
            f"{where}.base_url: a provider of kind {kind.value} needs one; there is"
            f" no endpoint to guess"
        )

    if len(problems) > before or kind is None:
        return None
    return _built(
        where,
        problems,
        ModelProviderConfig,
        id=provider_id,
        kind=kind,
        api_key_env=api_key_env,
        base_url=base_url,
    )


def _model(
    model_id: object,
    table: object,
    declared: Mapping[str, Any],
    problems: list[str],
) -> ModelConfig | None:
    where = f"models.{model_id}"
    if not is_config_id(model_id):
        problems.append(
            f"{where}: an id is up to {MAX_CONFIG_ID_CHARS} lower-case letters, digits," f" _ and -"
        )
        return None
    if not isinstance(table, Mapping):
        problems.append(f"{where}: a table")
        return None
    before = len(problems)
    _unknown(table, MODEL_ENTRY_KEYS, where, problems)

    provider_id = _string(table, "provider", where, problems)
    if provider_id and provider_id not in declared:
        problems.append(f"{where}.provider: {provider_id!r} is not one of [model_providers]")
    name = _string(table, "name", where, problems, limit=MAX_MODEL_NAME_CHARS)

    given: dict[str, Any] = {}
    seconds = _seconds(table, where, problems)
    if seconds is not None:
        given["timeout_seconds"] = seconds
    tokens = _tokens(table, where, problems)
    if tokens is not None:
        given["max_output_tokens"] = tokens

    if len(problems) > before:
        return None
    return _built(
        where, problems, ModelConfig, id=model_id, provider=provider_id, name=name, **given
    )


def _agent(
    agent_id: object,
    table: object,
    declared: Mapping[str, Any],
    engines: frozenset[Engine],
    problems: list[str],
) -> AgentDefinition | None:
    where = f"agents.{agent_id}"
    if not is_config_id(agent_id):
        problems.append(
            f"{where}: an id is up to {MAX_CONFIG_ID_CHARS} lower-case letters, digits," f" _ and -"
        )
        return None
    if not isinstance(table, Mapping):
        problems.append(f"{where}: a table")
        return None
    before = len(problems)
    _unknown(table, AGENT_KEYS, where, problems)

    title = _string(
        table, "title", where, problems, default=str(agent_id), limit=MAX_AGENT_TITLE_CHARS
    )
    model_id = _string(table, "model", where, problems)
    if model_id and model_id not in declared:
        problems.append(f"{where}.model: {model_id!r} is not one of [models]")

    engine = None
    raw_engine = _string(table, "engine", where, problems)
    if raw_engine:
        engine = _ENGINES.get(raw_engine)
        if engine is None:
            problems.append(f"{where}.engine: one of {_named(_ENGINES)}, not {raw_engine!r}")
        elif engine not in engines:
            problems.append(
                f"{where}.engine: the {raw_engine} engine is not wired in this"
                f" deployment; set engine to one of"
                f" {_named(engines)}"
            )
            engine = None

    system_prompt = ""
    if "system_prompt" in table:
        raw = table["system_prompt"]
        if not isinstance(raw, str):
            problems.append(f"{where}.system_prompt: text, or no system_prompt at all")
        elif len(raw) > MAX_SYSTEM_PROMPT_CHARS:
            problems.append(f"{where}.system_prompt: at most {MAX_SYSTEM_PROMPT_CHARS} characters")
        else:
            system_prompt = raw

    if len(problems) > before or engine is None:
        return None
    return _built(
        where,
        problems,
        AgentDefinition,
        id=agent_id,
        title=title,
        system_prompt=system_prompt,
        model=model_id,
        engine=engine,
    )


def _seconds(table: Mapping[str, Any], where: str, problems: list[str]) -> float | None:
    """``timeout_seconds``, or ``None`` to leave the record's own default."""
    if "timeout_seconds" not in table:
        return None
    seconds = table["timeout_seconds"]
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, int | float)
        or not math.isfinite(seconds)
        or not 0 < seconds <= MAX_MODEL_TIMEOUT_SECONDS
    ):
        problems.append(
            f"{where}.timeout_seconds: a number of seconds over 0 and at most"
            f" {MAX_MODEL_TIMEOUT_SECONDS:g}, not {seconds!r}"
        )
        return None
    return float(seconds)


def _tokens(table: Mapping[str, Any], where: str, problems: list[str]) -> int | None:
    """``max_output_tokens``, or ``None`` to leave it to the engine."""
    if "max_output_tokens" not in table:
        return None
    tokens = table["max_output_tokens"]
    if (
        isinstance(tokens, bool)
        or not isinstance(tokens, int)
        or not 0 < tokens <= MAX_OUTPUT_TOKENS
    ):
        problems.append(
            f"{where}.max_output_tokens: a whole number of tokens over 0 and at most"
            f" {MAX_OUTPUT_TOKENS}, not {tokens!r}"
        )
        return None
    return tokens


def _built(where: str, problems: list[str], record: Any, **fields: Any) -> Any:
    """Build the record, turning the last word of the rules into a problem.

    **The record is the rule, not this.** What is checked above is checked so
    that the operator is told where the mistake is and what was expected; the
    record refuses the same things in its own words, and anything it refuses
    that this let through -- a title spelt over two lines, say -- belongs in
    the same list as every other problem rather than escaping start-up as a
    different kind of error.
    """
    try:
        return record(**fields)
    except InvalidValueError as exc:
        problems.append(f"{where}: {exc}")
        return None


def _named(values: Any) -> str:
    """The names of what is allowed, in order, for a message that lists them."""
    return ", ".join(sorted(str(value) for value in values)) or "none"


def _unknown(
    table: Mapping[str, Any], known: frozenset[str] | set[str], where: str, problems: list[str]
) -> None:
    for key in table:
        if key not in known:
            prefix = f"{where}: " if where else ""
            problems.append(f"{prefix}unknown key {key!r}")


def _string(
    table: Mapping[str, Any],
    key: str,
    where: str,
    problems: list[str],
    *,
    default: str | None = None,
    limit: int | None = None,
) -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or not value:
        problems.append(f"{where}.{key}: missing, or not a non-empty string")
        return ""
    if limit is not None and len(value) > limit:
        problems.append(f"{where}.{key}: at most {limit} characters")
        return ""
    return value
