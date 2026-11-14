# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""Which principal an `Authorization` header names."""

from __future__ import annotations

import pytest

from sql_analytics.adapters.http.auth import Authenticator
from sql_analytics.contract import Principal, Secret

A = Principal(id="a", sources=("demo",))
B = Principal(id="b")
AUTHENTICATOR = Authenticator([(Secret("a" * 16), A), (Secret("b" * 16), B)])


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer " + "a" * 16, A),
        ("bearer " + "b" * 16, B),
        ("Bearer   " + "a" * 16 + " ", A),
        (None, None),
        ("", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("Basic " + "a" * 16, None),
        ("a" * 16, None),
        ("Bearer " + "a" * 15, None),
        ("Bearer " + "a" * 17, None),
        ("Bearer " + "c" * 16, None),
    ],
)
def test_a_header_names_the_principal_whose_token_it_carries(header, expected):
    assert AUTHENTICATOR.authenticate(header) == expected
