# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The engines' settings and storage, made from the controller's configuration."""

from __future__ import annotations

import pytest

from robinauts.agent_engines.contract.domain import ProviderKind, ToolServerAuth
from robinauts.agent_engines.contract.ports import StorageKind
from robinauts.controller.contract import domain
from robinauts.controller.contract.core import domain as core
from robinauts.worker.engine_settings import engine_settings, engine_storage

CONFIG = core.Config(
    providers={"acme": core.ProviderConfig("acme", core.ProviderKind.ANTHROPIC, "ACME_KEY")},
    models={"m": core.ModelConfig("m", "acme", "model-1")},
    tool_servers={
        "t": core.ToolServerConfig("t", "https://tools.example", "T_SECRET"),
        "c": core.ToolServerConfig(
            "c", "https://c.example", "C_KEY", core.ToolServerAuth.HEADER, header="x-api-key"
        ),
    },
    agents={"a": core.AgentConfig("a", "A", "", "m", "echo", ("t",))},
)


def test_settings_carry_the_tables_without_agents_and_answer_secrets_by_id() -> None:
    settings = engine_settings(CONFIG, {"ACME_KEY": "sk-1", "T_SECRET": "s-1"}.get)
    assert set(settings.models.providers) == {"acme"}
    assert settings.models.providers["acme"].kind is ProviderKind.ANTHROPIC
    assert set(settings.models.models) == {"m"}
    assert set(settings.models.tool_servers) == {"t", "c"}
    header = settings.models.tool_servers["c"]
    assert (header.auth, header.header) == (ToolServerAuth.HEADER, "x-api-key")
    assert settings.keys.key_for("acme") == "sk-1"
    assert settings.tool_secrets.secret_for("t") == "s-1"


def test_a_secret_the_environment_lacks_is_refused_by_name() -> None:
    settings = engine_settings(CONFIG, {}.get)
    with pytest.raises(domain.MissingSecretError, match="'acme'"):
        settings.keys.key_for("acme")
    with pytest.raises(domain.MissingSecretError, match="'t'"):
        settings.tool_secrets.secret_for("t")


POOL = object()


@pytest.mark.parametrize(
    ("storage", "kind", "options"),
    [
        (
            core.StorageConfig(core.StorageKind.LOCAL, path="/d"),
            StorageKind.LOCAL,
            {"path": "/d"},
        ),
        (
            core.StorageConfig(core.StorageKind.POSTGRES, url="x"),
            StorageKind.POSTGRES,
            {"pool": POOL},
        ),
    ],
)
def test_storage_kinds_map_to_the_engines_options(
    storage: core.StorageConfig, kind: StorageKind, options: dict[str, object]
) -> None:
    mapped = engine_storage(storage, POOL)
    assert (mapped.kind, mapped.options) == (kind, options)
