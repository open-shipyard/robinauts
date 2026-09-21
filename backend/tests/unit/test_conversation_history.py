# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Trimming a history to a size: the placeholder policy, and what it promises."""

import pytest

from conversations import CONVERSATION, answer, question
from robinauts.core import history_chars, message_chars, tree_of, trim_history
from robinauts.domain import InvalidValueError, Message, ReasoningPart, Role, TextPart


def path(turns: int, *, chars: int = 10) -> tuple[Message, ...]:
    """``turns`` question-and-answer pairs, each message ``chars`` long."""
    messages: list[Message] = []
    for turn in range(turns):
        parent = messages[-1] if messages else None
        asked = question("q" * chars, parent=parent, seconds=turn * 2)
        messages.append(asked)
        messages.append(answer(asked, "a" * chars, seconds=turn * 2 + 1))
    return tree_of(messages, conversation_id=CONVERSATION).path_to(messages[-1].id)


def test_a_message_counts_its_text_and_not_its_reasoning() -> None:
    assert message_chars(question("hello")) == 5
    assert message_chars(answer(question(), parts=(ReasoningPart("a long thought"),))) == 0
    assert message_chars(question(parts=(TextPart("ab"), ReasoningPart("x"), TextPart("c")))) == 3
    assert history_chars(path(2, chars=10)) == 40
    assert history_chars(()) == 0


def test_a_history_that_fits_is_left_alone() -> None:
    whole = path(3)
    assert trim_history(whole, max_chars=1_000) == whole
    assert trim_history(whole, max_chars=history_chars(whole)) == whole


def test_an_empty_history_trims_to_nothing() -> None:
    assert trim_history((), max_chars=10) == ()


def test_the_oldest_turns_go_first_and_the_rest_is_a_suffix() -> None:
    whole = path(4, chars=10)
    trimmed = trim_history(whole, max_chars=45)
    assert trimmed == whole[4:]
    assert history_chars(trimmed) <= 45


def test_what_comes_back_always_begins_with_a_question() -> None:
    whole = path(4, chars=10)
    for max_chars in range(1, history_chars(whole) + 2):
        trimmed = trim_history(whole, max_chars=max_chars)
        assert trimmed[0].role is Role.USER
        assert trimmed == whole[len(whole) - len(trimmed) :]


def test_the_last_question_is_kept_whatever_its_size() -> None:
    whole = path(3, chars=100)
    assert trim_history(whole, max_chars=1) == whole[-2:]


def test_a_question_waiting_for_its_answer_is_kept_alone() -> None:
    first = question("one", seconds=0)
    said = answer(first, "1", seconds=1)
    second = question("two" * 100, parent=said, seconds=2)
    assert trim_history((first, said, second), max_chars=1) == (second,)


@pytest.mark.parametrize("max_chars", [0, -1, 1.5, True, None, "10"])
def test_a_history_is_trimmed_to_a_positive_number_of_characters(max_chars: object) -> None:
    with pytest.raises(InvalidValueError):
        trim_history(path(1), max_chars=max_chars)


def test_a_history_with_nothing_to_answer_is_refused() -> None:
    first = question(seconds=0)
    said = answer(first, seconds=1)
    with pytest.raises(InvalidValueError, match="the question it is answering"):
        trim_history((said,), max_chars=100)


def test_a_turn_of_several_messages_is_never_cut_in_half() -> None:
    """A turn is a question and everything the run produced under it."""
    first = question("q" * 10, seconds=0)
    thinking = answer(first, "a" * 10, seconds=1)
    said = answer(thinking, "b" * 10, seconds=2)
    second = question("q" * 10, parent=said, seconds=3)
    replied = answer(second, "c" * 10, seconds=4)
    whole = tree_of([first, thinking, said, second, replied], conversation_id=CONVERSATION).path_to(
        replied.id
    )
    assert trim_history(whole, max_chars=25) == whole[3:]
    assert trim_history(whole, max_chars=45) == whole[3:]
    assert trim_history(whole, max_chars=50) == whole
