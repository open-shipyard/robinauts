# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

from __future__ import annotations

import pytest

from robinauts.web.logs import loggable


@pytest.mark.parametrize(
    ("value", "logged"),
    [
        ("okta", "okta"),
        # A line break cannot forge a line.
        ("okta\r\nINFO user 1 signed in", "okta??INFO user 1 signed in"),
        ("a\x00b\x1b[31mc\x7f", "a?b?[31mc?"),
        ("x" * 500, "x" * 200),
    ],
)
def test_a_value_is_logged_on_one_line_cut_to_length(value: str, logged: str) -> None:
    assert loggable(value) == logged
