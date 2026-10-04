# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

from __future__ import annotations

import pytest

from robinauts.controller.core.titles import ELLIPSIS, MAX_TITLE_CHARS, title_from_text

FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f466"


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("What is a robinaut?", "What is a robinaut?"),
        ("", ""),
        ("  \n\t\n", ""),
        ("  spaces  around  ", "spaces around"),
        ("\n\nfirst line\nsecond line", "first line"),
        ("hard\x00to\x07show", "hard to show"),
        ("café 中文 \U0001f600", "café 中文 \U0001f600"),
        ("a" * MAX_TITLE_CHARS, "a" * MAX_TITLE_CHARS),
        # A long word is cut at the limit; an emoji sequence is kept whole or not at all.
        ("a" * 500, "a" * (MAX_TITLE_CHARS - 1) + ELLIPSIS),
        ("x" * (MAX_TITLE_CHARS - 4) + FAMILY, "x" * (MAX_TITLE_CHARS - 4) + ELLIPSIS),
        # Nothing left after the cut is no title; only the beginning of a huge text is read.
        ("\u200d" * (MAX_TITLE_CHARS * 3), ""),
        ("\n" + "the title\n" + "y" * 64_000_000, "the title"),
    ],
)
def test_the_title_is_the_first_line_with_anything_on_it(text: str, title: str) -> None:
    assert title_from_text(text) == title


def test_a_long_title_is_cut_at_a_word_boundary() -> None:
    title = title_from_text("word " * 100)
    assert len(title) <= MAX_TITLE_CHARS
    assert title.endswith("word" + ELLIPSIS)


def test_a_cut_keeps_accents_with_their_letters() -> None:
    title = title_from_text("é" * MAX_TITLE_CHARS)
    assert title[: -len(ELLIPSIS)].endswith("é")
