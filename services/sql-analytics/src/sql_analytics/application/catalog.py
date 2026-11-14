# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The catalog: which sources a principal may use. Schemas, tables and columns come with the
connectors."""

from __future__ import annotations

from collections.abc import Iterable

from sql_analytics.contract import Principal, SourceInfo


class Catalog:
    def __init__(self, sources: Iterable[SourceInfo]) -> None:
        self._sources = {source.id: source for source in sources}

    def list_sources(self, principal: Principal) -> list[SourceInfo]:
        """The principal's sources, in the order its configuration names them."""
        return [self._sources[id] for id in principal.sources if id in self._sources]
