# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The tree: which parents are legal, what a branch is, where to open."""

import time
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import FrozenInstanceError, replace

import pytest

from conversations import CONVERSATION, OTHER_CONVERSATION, answer, conversation, question
from robinauts.core import (
    ConversationTree,
    check_parent,
    check_tree,
    may_follow,
    tree_of,
    tree_of_stored,
)
from robinauts.domain import (
    InvalidMessageTreeError,
    InvalidValueError,
    Message,
    MessageNotFoundError,
    Role,
    StoredDataError,
)


def exchange() -> tuple[Message, Message, Message, Message]:
    """Two turns: a question, its answer, a second question, its answer."""
    first = question("one", seconds=0)
    said = answer(first, "1", seconds=1)
    second = question("two", parent=said, seconds=2)
    replied = answer(second, "2", seconds=3)
    return first, said, second, replied


def once(messages: Iterable[Message]) -> Iterator[Message]:
    """The messages as a generator: readable once, and no more than once."""
    return iter(list(messages))


def tree(messages: Iterable[Message], **changes: object) -> ConversationTree:
    """The tree of a conversation's messages, checked."""
    fields: dict[str, object] = {"conversation_id": CONVERSATION}
    fields.update(changes)
    return tree_of(messages, **fields)  # type: ignore[arg-type]


# --- what may follow what ---------------------------------------------------


@pytest.mark.parametrize(
    ("role", "parent_role", "allowed"),
    [
        # A conversation begins with a question, and only with a question.
        (Role.USER, None, True),
        (Role.ASSISTANT, None, False),
        (Role.TOOL, None, False),
        # A question follows an answer, and nothing else.
        (Role.USER, Role.ASSISTANT, True),
        (Role.USER, Role.USER, False),
        (Role.USER, Role.TOOL, False),
        # A turn is a chain: an answer follows the question, another answer,
        # or the result of a tool it called.
        (Role.ASSISTANT, Role.USER, True),
        (Role.ASSISTANT, Role.ASSISTANT, True),
        (Role.ASSISTANT, Role.TOOL, True),
        # A tool message follows the answer that called it.
        (Role.TOOL, Role.ASSISTANT, True),
        (Role.TOOL, Role.USER, False),
        (Role.TOOL, Role.TOOL, False),
    ],
)
def test_the_whole_rule_of_the_shape_of_a_conversation(
    role: Role, parent_role: Role | None, allowed: bool
) -> None:
    assert may_follow(role, parent_role) is allowed


def test_the_rule_is_asked_with_roles_and_not_with_something_else() -> None:
    with pytest.raises(InvalidMessageTreeError):
        may_follow("user", None)
    with pytest.raises(InvalidMessageTreeError):
        may_follow(Role.USER, "assistant")
    with pytest.raises(InvalidMessageTreeError):
        check_parent(Role.USER, "a message")


def test_check_parent_applies_the_rule_to_a_message() -> None:
    first, said, _, _ = exchange()
    assert check_parent(Role.USER, None) is None
    assert check_parent(Role.USER, said) is None
    assert check_parent(Role.ASSISTANT, first) is None
    assert check_parent(Role.ASSISTANT, said) is None
    with pytest.raises(InvalidMessageTreeError, match="does not follow"):
        check_parent(Role.ASSISTANT, None)
    with pytest.raises(InvalidMessageTreeError, match="does not follow"):
        check_parent(Role.USER, first)


# --- what a collection of messages must be ----------------------------------


def test_a_conversation_nobody_has_written_in_yet_passes() -> None:
    empty = tree([])
    assert empty.messages == ()
    assert empty.leaves() == ()
    assert empty.default_leaf(conversation()) is None
    assert check_tree([], conversation_id=CONVERSATION) == ()


def test_a_well_formed_conversation_passes_and_comes_back_in_order() -> None:
    first, said, second, replied = exchange()
    assert tree([replied, first, second, said]).messages == (first, said, second, replied)
    assert check_tree([replied, first, second, said], conversation_id=CONVERSATION) == (
        first,
        said,
        second,
        replied,
    )


def test_a_turn_may_produce_several_messages() -> None:
    first = question("one", seconds=0)
    said = answer(first, "thinking out loud", seconds=1)
    also = answer(said, "and the answer", seconds=2)
    second = question("two", parent=also, seconds=3)
    built = tree([first, said, also, second])
    assert built.messages == (first, said, also, second)
    assert built.path_to(second.id) == (first, said, also, second)


def test_two_messages_of_the_same_id_are_refused() -> None:
    first = question()
    with pytest.raises(InvalidMessageTreeError, match="share the id"):
        tree([first, replace(first, parts=first.parts)])


def test_something_that_is_not_a_message_is_refused() -> None:
    with pytest.raises(InvalidMessageTreeError):
        tree(["a message"])


def test_a_parent_that_is_not_here_is_refused() -> None:
    with pytest.raises(InvalidMessageTreeError, match="no parent here"):
        tree([answer(uuid.uuid4())])


def test_messages_of_two_conversations_are_refused() -> None:
    with pytest.raises(InvalidMessageTreeError, match="do not belong"):
        tree([question(), question(conversation_id=OTHER_CONVERSATION, seconds=1)])


def test_a_parent_in_another_conversation_is_an_orphan() -> None:
    elsewhere = question(conversation_id=OTHER_CONVERSATION)
    with pytest.raises(InvalidMessageTreeError):
        tree([answer(elsewhere)], conversation_id=OTHER_CONVERSATION)


def test_the_conversation_is_said_and_never_inferred() -> None:
    """A caller that passed the wrong messages is refused, not answered."""
    first = question(conversation_id=OTHER_CONVERSATION)
    with pytest.raises(InvalidMessageTreeError, match="do not belong"):
        tree([first])
    assert tree([first], conversation_id=OTHER_CONVERSATION).messages == (first,)
    with pytest.raises(TypeError):
        tree_of([first])  # type: ignore[call-arg]
    with pytest.raises(InvalidValueError, match="is a UUID"):
        tree([first], conversation_id="not a uuid")


def test_a_cycle_is_refused() -> None:
    first = question("one", seconds=0)
    said = answer(first, seconds=1)
    with pytest.raises(InvalidMessageTreeError, match="its own ancestor"):
        tree([replace(first, parent_id=said.id), said])


def test_a_question_may_stand_at_the_root_and_so_may_a_second_one() -> None:
    first = question("one", seconds=0)
    edited = question("one, better", seconds=1)
    assert len(tree([first, edited]).messages) == 2


def test_a_long_branch_is_walked_once_per_message() -> None:
    messages = deep(200)
    built = tree(messages)
    assert len(built.messages) == len(messages)
    assert len(built.path_to(messages[-1].id)) == len(messages)


def test_the_messages_are_read_once_whatever_they_arrive_in() -> None:
    first, said, second, replied = exchange()
    messages = [first, said, second, replied]
    assert tree(once(messages)).messages == tuple(messages)
    assert tree_of_stored(once(messages), conversation_id=CONVERSATION).messages == tuple(messages)
    assert check_tree(once(messages), conversation_id=CONVERSATION) == tuple(messages)


def test_the_order_is_by_time_and_then_by_id() -> None:
    same = [question("a", seconds=0), question("b", seconds=0), question("c", seconds=0)]
    assert tree(same).messages == tuple(sorted(same, key=lambda message: message.id.bytes))


# --- one door for rows ------------------------------------------------------


def test_rows_are_checked_once_at_the_one_door_they_come_through() -> None:
    """The read path: what comes out of the database is ours to get right,
    and it is said once rather than at every question afterwards."""
    first = question("one", seconds=0)
    said = answer(first, seconds=1)
    cycle = [replace(first, parent_id=said.id), said]
    for broken in ([answer(uuid.uuid4())], ["not a message"], cycle):
        with pytest.raises(StoredDataError) as refused:
            tree_of_stored(broken, conversation_id=CONVERSATION)
        assert refused.value.__cause__ is not None
    with pytest.raises(StoredDataError):
        tree_of_stored([question(conversation_id=OTHER_CONVERSATION)], conversation_id=CONVERSATION)


def test_afterwards_a_question_can_only_fail_for_the_requests_reasons() -> None:
    """A checked tree answers; the one way it refuses is an id nobody has."""
    first, said, second, replied = exchange()
    built = tree_of_stored([first, said, second, replied], conversation_id=CONVERSATION)
    assert built.conversation_id == CONVERSATION
    assert built.messages == (first, said, second, replied)
    assert built.path_to(replied.id) == (first, said, second, replied)
    assert built.default_leaf(conversation()) == replied
    assert built.branches_along(replied.id)[-1].message == replied
    assert built.branches_of(said.id).message == said
    assert built.turn_start(replied.id) == second
    assert built.parent_for_regenerate(replied.id) == second.id
    assert built.parent_for_edit(second.id) == said.id
    assert built.siblings_of(replied.id) == (replied,)
    assert built.children_of(first.id) == (said,)
    assert built.leaves() == (replied,)
    assert built.message_at(said.id) == said
    assert built.check_attachment(parent_id=replied.id, role=Role.USER) is None

    nobodys = uuid.uuid4()
    for ask in (
        built.path_to,
        built.branches_along,
        built.branches_of,
        built.turn_start,
        built.parent_for_regenerate,
        built.parent_for_edit,
        built.siblings_of,
        built.message_at,
    ):
        with pytest.raises(MessageNotFoundError):
            ask(nobodys)
    with pytest.raises(MessageNotFoundError):
        built.check_attachment(parent_id=nobodys, role=Role.USER)
    assert built.default_leaf(conversation(active_leaf_id=nobodys)) == replied


def test_a_tree_of_one_conversation_is_not_asked_about_another() -> None:
    first, said, _, _ = exchange()
    built = tree_of_stored([first, said], conversation_id=CONVERSATION)
    with pytest.raises(InvalidMessageTreeError):
        built.default_leaf(conversation(id=OTHER_CONVERSATION))


def test_a_tree_cannot_be_rewritten_from_outside() -> None:
    """Documented immutable, and immutable in fact. There is no index to
    hand in either: a tree is made of its messages, and everything else about
    it is computed from them."""
    first, said, _, _ = exchange()
    built = tree([first, said])
    with pytest.raises(TypeError):
        built.at[said.id] = first  # type: ignore[index]
    with pytest.raises(TypeError):
        built.below[said.id] = (first,)  # type: ignore[index]
    with pytest.raises(TypeError):
        built.among[said.id] = 7  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        built.messages = ()  # type: ignore[misc]


def test_an_unchecked_tree_cannot_be_built_at_all() -> None:
    """The constructor is the check: there is no other way to have one."""
    first = question("one", seconds=0)
    said = answer(first, seconds=1)
    looped = replace(first, parent_id=said.id)
    with pytest.raises(InvalidMessageTreeError, match="its own ancestor"):
        ConversationTree((looped, said), conversation_id=CONVERSATION)
    with pytest.raises(InvalidMessageTreeError, match="no parent here"):
        ConversationTree((said,), conversation_id=CONVERSATION)


def test_a_walk_still_ends_if_a_tree_is_doctored_afterwards() -> None:
    """Defence in depth behind the constructor: nothing reaches these."""
    first = question("one", seconds=0)
    said = answer(first, seconds=1)
    built = tree([first, said])
    looped = replace(first, parent_id=said.id)
    object.__setattr__(built, "at", {looped.id: looped, said.id: said})
    object.__setattr__(built, "below", {looped.id: (said,), said.id: (looped,)})
    with pytest.raises(InvalidMessageTreeError, match="does not end"):
        built.path_to(said.id)
    with pytest.raises(InvalidMessageTreeError, match="walks in circles"):
        built.default_leaf(conversation(active_leaf_id=said.id))


# --- paths, children, siblings, leaves --------------------------------------


def test_a_path_runs_from_a_root_down_to_the_leaf() -> None:
    first, said, second, replied = exchange()
    built = tree([said, replied, first, second])
    assert built.path_to(replied.id) == (first, said, second, replied)
    assert built.path_to(first.id) == (first,)


def test_a_path_to_a_message_of_another_branch_is_that_branch_alone() -> None:
    first, said, second, replied = exchange()
    other = question("two, differently", parent=said, seconds=4)
    assert tree([first, said, second, replied, other]).path_to(other.id) == (first, said, other)


def test_children_are_the_branches_under_a_message_oldest_first() -> None:
    first, said, second, replied = exchange()
    again = answer(second, "2, again", seconds=4)
    built = tree([first, said, second, replied, again])
    assert built.children_of(second.id) == (replied, again)
    assert built.children_of(replied.id) == ()
    assert built.children_of(None) == (first,)


def test_siblings_are_the_branches_a_message_is_one_of_itself_included() -> None:
    first, said, second, replied = exchange()
    again = answer(second, "2, again", seconds=4)
    built = tree([first, said, second, replied, again])
    assert built.siblings_of(replied.id) == (replied, again)
    assert built.siblings_of(again.id) == (replied, again)
    assert built.siblings_of(first.id) == (first,)


def test_leaves_are_the_ends_of_the_branches() -> None:
    first, said, second, replied = exchange()
    other = question("two, differently", parent=said, seconds=4)
    assert tree([first, said, second, replied, other]).leaves() == (replied, other)


# --- the branches beside a path ---------------------------------------------


def test_a_path_comes_with_the_branches_beside_each_message() -> None:
    """What the interface draws: "2 of 3", and what it moves between."""
    first, said, second, replied = exchange()
    again = answer(second, "2, again", seconds=4)
    edited = question("two, better", parent=said, seconds=5)
    built = tree([first, said, second, replied, again, edited])

    along = built.branches_along(again.id)
    assert tuple(branch.message for branch in along) == (first, said, second, again)
    assert [branch.at for branch in along] == [0, 0, 0, 1]
    assert [branch.how_many for branch in along] == [1, 1, 2, 2]
    assert along[2].siblings == (second.id, edited.id)
    assert along[3].siblings == (replied.id, again.id)
    assert built.branches_of(edited.id).at == 1


# --- turns ------------------------------------------------------------------


def test_the_turn_a_message_belongs_to_is_found_from_anywhere_inside_it() -> None:
    first = question("one", seconds=0)
    said = answer(first, "thinking", seconds=1)
    also = answer(said, "answering", seconds=2)
    built = tree([first, said, also])
    assert built.turn_start(also.id) == first
    assert built.turn_start(said.id) == first
    assert built.turn_start(first.id) == first


# --- editing and regenerating -----------------------------------------------


def test_an_edit_attaches_beside_the_question_it_edits() -> None:
    first, said, second, replied = exchange()
    messages = [first, said, second, replied]
    built = tree(messages)
    assert built.parent_for_edit(second.id) == said.id
    assert built.parent_for_edit(first.id) is None
    edited = question("two, better", parent=said.id, seconds=4)
    assert tree([*messages, edited]).siblings_of(second.id) == (second, edited)


def test_a_regeneration_attaches_under_the_question_of_the_whole_turn() -> None:
    first, said, second, replied = exchange()
    messages = [first, said, second, replied]
    assert tree(messages).parent_for_regenerate(replied.id) == second.id
    again = answer(second, "2, again", seconds=4)
    assert tree([*messages, again]).path_to(again.id) == (first, said, second, again)


def test_regenerating_a_turn_of_several_messages_goes_back_to_its_question() -> None:
    """Not under whatever the old answer followed: the turn is replaced."""
    first = question("one", seconds=0)
    said = answer(first, "thinking", seconds=1)
    also = answer(said, "answering", seconds=2)
    messages = [first, said, also]
    assert tree(messages).parent_for_regenerate(also.id) == first.id
    again = answer(first, "answering again", seconds=3)
    built = tree([*messages, again])
    assert built.path_to(again.id) == (first, again)
    assert built.siblings_of(said.id) == (said, again)


def test_only_a_question_is_edited_and_only_an_answer_regenerated() -> None:
    first, said, _, _ = exchange()
    built = tree([first, said])
    with pytest.raises(InvalidMessageTreeError, match="only a question is edited"):
        built.parent_for_edit(said.id)
    with pytest.raises(InvalidMessageTreeError, match="only an answer is regenerated"):
        built.parent_for_regenerate(first.id)
    with pytest.raises(MessageNotFoundError):
        built.parent_for_edit(uuid.uuid4())


def test_where_a_new_message_may_attach() -> None:
    first, said, _, _ = exchange()
    built = tree([first, said])
    assert built.check_attachment(parent_id=None, role=Role.USER) is None
    assert built.check_attachment(parent_id=said.id, role=Role.USER) is None
    assert built.check_attachment(parent_id=first.id, role=Role.ASSISTANT) is None
    assert built.check_attachment(parent_id=said.id, role=Role.ASSISTANT) is None
    with pytest.raises(InvalidMessageTreeError):
        built.check_attachment(parent_id=first.id, role=Role.USER)
    with pytest.raises(InvalidMessageTreeError):
        built.check_attachment(parent_id=None, role=Role.ASSISTANT)
    with pytest.raises(MessageNotFoundError):
        built.check_attachment(parent_id=uuid.uuid4(), role=Role.USER)


def test_a_new_message_may_not_hang_under_another_conversations_message() -> None:
    """These are one conversation's messages: somebody else's is not here."""
    first, said, _, _ = exchange()
    elsewhere = question("theirs", conversation_id=OTHER_CONVERSATION)
    with pytest.raises(MessageNotFoundError):
        tree([first, said]).check_attachment(parent_id=elsewhere.id, role=Role.ASSISTANT)


# --- the branch a conversation opens on -------------------------------------


def test_a_conversation_opens_where_its_author_was_last() -> None:
    first, said, second, replied = exchange()
    other = question("two, differently", parent=said, seconds=4)
    built = tree([first, said, second, replied, other])
    assert built.default_leaf(conversation(active_leaf_id=replied.id)) == replied
    assert built.default_leaf(conversation(active_leaf_id=other.id)) == other


def test_an_author_on_a_message_that_has_since_been_answered_opens_on_the_answer() -> None:
    first, said, second, replied = exchange()
    built = tree([first, said, second, replied])
    assert built.default_leaf(conversation(active_leaf_id=first.id)) == replied


def test_the_branch_it_opens_on_is_the_one_whose_last_message_is_newest() -> None:
    """Not the one whose first message is: a branch begun early and continued
    yesterday is where its author is, whatever was started after it."""
    first = question("one", seconds=0)
    old = answer(first, "the old branch", seconds=1)
    new = answer(first, "the new branch", seconds=2)
    continued = question("carrying on the old one", parent=old, seconds=10)
    built = tree([first, old, new, continued])
    assert built.default_leaf(conversation(active_leaf_id=first.id)) == continued
    assert built.default_leaf(conversation()) == continued


def test_a_conversation_with_no_active_leaf_opens_on_the_newest_branch() -> None:
    first, said, second, replied = exchange()
    other = question("two, differently", parent=said, seconds=4)
    built = tree([first, said, second, replied, other])
    assert built.default_leaf(conversation()) == other
    assert built.default_leaf(conversation(active_leaf_id=uuid.uuid4())) == other


def test_an_author_on_a_leaf_stays_on_it() -> None:
    first, said, _, _ = exchange()
    assert tree([first, said]).default_leaf(conversation(active_leaf_id=said.id)) == said


# --- a conversation somebody has used --------------------------------------


def wide(children: int) -> tuple[Message, list[Message]]:
    """One question, answered ``children`` times: what regenerating leaves."""
    asked = question("one", seconds=0)
    return asked, [answer(asked, f"{step}", seconds=step + 1) for step in range(children)]


def deep(steps: int) -> list[Message]:
    """One branch, ``steps`` messages long."""
    messages = [question("one", seconds=0)]
    for step in range(1, steps):
        previous = messages[-1]
        messages.append(
            answer(previous, "said", seconds=step)
            if previous.role is Role.USER
            else question("more", parent=previous, seconds=step)
        )
    return messages


def test_a_conversation_of_ten_thousand_messages_is_read_once_not_once_each() -> None:
    """A guard against a quadratic walk, not a benchmark.

    Ten thousand answers under one question is what regenerating leaves
    behind, and a function that looked for a message's siblings -- or for
    where it falls among them -- by walking the whole conversation would take
    seconds to open it.
    """
    asked, said = wide(10_000)
    messages = [asked, *said]
    chain = deep(10_000)
    opened = conversation(active_leaf_id=asked.id)

    started = time.monotonic()
    wide_tree = tree_of_stored(messages, conversation_id=CONVERSATION)
    deep_tree = tree_of_stored(chain, conversation_id=CONVERSATION)
    assert len(wide_tree.messages) == 10_001
    assert len(wide_tree.children_of(asked.id)) == 10_000
    assert len(wide_tree.siblings_of(said[-1].id)) == 10_000
    assert len(wide_tree.leaves()) == 10_000
    assert wide_tree.default_leaf(opened) == said[-1]
    # The path through the last of ten thousand siblings: its branches are
    # the whole of that fan, and finding where it falls among them must not
    # be a walk of them.
    along = wide_tree.branches_along(said[-1].id)
    assert along[-1].at == 9_999
    assert along[-1].how_many == 10_000
    assert len(deep_tree.path_to(chain[-1].id)) == 10_000
    assert len(deep_tree.branches_along(chain[-1].id)) == 10_000
    assert deep_tree.turn_start(chain[-1].id) == chain[-2]
    spent = time.monotonic() - started

    assert spent < 5.0, f"ten walks of ten thousand messages took {spent:.1f}s"
