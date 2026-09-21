# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Fitting a history into what a model will take.

Above the agent port on purpose (``docs/specs/agents.md``, ADR 0002): both
engines must behave the same, so the history an engine is given is decided
here and not inside an adapter.

**This is a placeholder, and says so.** It counts characters, because token
counting belongs to the step that knows about models and their tokenisers,
and it drops whole **turns** from the front, because summarising an older part
of a conversation is a policy of its own. What it does guarantee is the part
that a real policy will have to guarantee too: what comes back is a suffix of
the path, it is still well-formed -- it begins with a question, so no turn is
ever cut in half -- and the turn being answered is always whole in it,
whatever its size, because dropping what was just asked answers nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from robinauts.domain import InvalidValueError, Message, Role, describe


def message_chars(message: Message) -> int:
    """How big a message counts as: the characters of its text.

    Reasoning does not count: it is not sent to a vendor other than the one
    that produced it, and this version does not send it at all.
    """
    return len(message.text)


def history_chars(path: Sequence[Message]) -> int:
    """How big a history counts as."""
    return sum(message_chars(message) for message in path)


def trim_history(path: Sequence[Message], *, max_chars: int) -> tuple[Message, ...]:
    """The longest well-formed suffix of ``path`` that fits in ``max_chars``.

    ``path`` is a path from a root to a leaf
    (``robinauts.core.conversation_tree.path_to``), and a turn there is a
    question and everything the run produced under it, so a suffix beginning
    with a question is a whole number of turns and a history in its own right.
    The suffix never starts after the last question of the path: the turn
    being answered is kept entire, whatever it weighs.
    """
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars <= 0:
        raise InvalidValueError(
            f"a history is trimmed to a positive number of characters, not {describe(max_chars)}"
        )
    kept = tuple(path)
    if not kept:
        return ()
    last_question = _last_turn(kept)
    if last_question is None:
        raise InvalidValueError("a history holds the question it is answering")
    total = 0
    start = len(kept)
    for index in range(len(kept) - 1, -1, -1):
        total += message_chars(kept[index])
        if total > max_chars and index < last_question:
            break
        if kept[index].role is Role.USER:
            start = index
    return kept[min(start, last_question) :]


def _last_turn(path: Sequence[Message]) -> int | None:
    """Where the last turn of ``path`` begins: its last question."""
    for index in range(len(path) - 1, -1, -1):
        if path[index].role is Role.USER:
            return index
    return None
