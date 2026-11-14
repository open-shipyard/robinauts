# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The catalog, in process: a principal sees its own sources, in its own order."""

from __future__ import annotations

from sql_analytics.application.catalog import Catalog
from sql_analytics.contract import Principal, SourceInfo

ONE = SourceInfo(id="one", kind="duckdb", description="One.", default_schema="main")
TWO = SourceInfo(id="two", kind="sqlite", description="Two.", default_schema="main")


def test_a_principal_sees_its_sources_alone_in_the_order_it_names_them():
    catalog = Catalog([ONE, TWO])
    assert catalog.list_sources(Principal(id="p", sources=("two", "one"))) == [TWO, ONE]
    assert catalog.list_sources(Principal(id="q", sources=("one",))) == [ONE]
    assert catalog.list_sources(Principal(id="r")) == []
