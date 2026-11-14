# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The records more than one layer reads."""

from __future__ import annotations

from dataclasses import dataclass, field


class Secret:
    """A value read from the environment at start-up: held in memory, never shown.

    Its `repr` and `str` say only that it is a secret, so a secret that reaches a log line, an
    exception or an answer by mistake shows as `Secret(***)`. `reveal` is the one way to it.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Principal:
    """Who is asking: the credential a request came with, and the sources it may use.

    Results, stored queries and what is on display belong to a principal. Behind Robinauts,
    every person using an agent that names this tool server is the same principal.
    """

    id: str
    sources: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class SourceInfo:
    """A configured database, as an agent sees it: never its address or its credentials."""

    id: str
    kind: str
    description: str
    default_schema: str | None
