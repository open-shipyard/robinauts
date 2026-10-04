# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A controller on the echo engine and the in-memory store, for the controller's own tests."""

from __future__ import annotations

from robinauts.agent_engines.contract.ports import AgentEngine
from robinauts.controller.composition import compose
from robinauts.controller.contract.domain import (
    AgentConfig,
    Config,
    ModelConfig,
    ProviderConfig,
    ProviderKind,
    StorageConfig,
    StorageKind,
    TurnStarted,
    User,
)
from robinauts.controller.contract.ports import Controller

CONFIG = Config(
    providers={"echo": ProviderConfig("echo", ProviderKind.ANTHROPIC, "ECHO_API_KEY")},
    models={"echo": ModelConfig("echo", provider="echo", name="echo", title="Echo")},
    agents={
        "echo": AgentConfig("echo", title="Echo", system_prompt="", model="echo", engine="echo")
    },
)


async def opened(engine: AgentEngine | None = None) -> Controller:
    """Opened on the echo engine, or on that engine in its place."""
    engines = None if engine is None else {"echo": lambda *_: engine}
    controller = compose(
        CONFIG, storage=StorageConfig(StorageKind.IN_MEMORY), secret_for={}.get, engines=engines
    ).controller
    await controller.open()
    return controller


async def settled(controller: Controller, user: User, started: TurnStarted) -> None:
    """Wait for the turn to end, as a watcher would."""
    async for _ in controller.watch_turn(user, started.session_id, started.turn_id):
        pass
