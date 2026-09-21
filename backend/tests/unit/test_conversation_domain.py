# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The records of the conversation format, and what they refuse to be."""

import time
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from conversations import (
    AGENT,
    CONVERSATION,
    MODEL,
    OWNER,
    RUN,
    answer,
    conversation,
    provenance,
    question,
)
from robinauts.domain import (
    EARLIEST_YEAR,
    LATEST_YEAR,
    MAX_PART_CHARS,
    MAX_PARTS,
    MAX_TITLE_CHARS,
    SUPPORTED_PART_KINDS,
    SUPPORTED_ROLES,
    Channel,
    Conversation,
    Engine,
    InvalidValueError,
    MessagePart,
    PartKind,
    ReasoningPart,
    Role,
    TextPart,
    UnsupportedContentError,
    check_supported,
    check_supported_role,
    checked_config_id,
    checked_fragment,
    checked_parts,
    clean_text,
    describe,
    is_config_id,
    kept_parts,
)

NAIVE = datetime(2026, 9, 21, 9, 0)


# --- the ids an operator writes in the configuration ------------------------


@pytest.mark.parametrize("value", ["assistant", "a", "gpt-4o", "claude_sonnet", "a" * 40, "0"])
def test_a_config_id_is_a_lower_case_name(value: str) -> None:
    assert is_config_id(value)
    assert checked_config_id(value, "an agent's id") == value


@pytest.mark.parametrize(
    "value", ["", "Assistant", "-leading", "_leading", "a" * 41, "with space", "eh?", 7, None]
)
def test_anything_else_is_no_config_id(value: object) -> None:
    assert not is_config_id(value)
    with pytest.raises(InvalidValueError):
        checked_config_id(value, "an agent's id")


def test_the_engines_are_the_two_the_configuration_names() -> None:
    assert {engine.value for engine in Engine} == {"langgraph", "pydantic-ai"}


# --- parts ------------------------------------------------------------------


def test_a_part_carries_the_kind_it_is_stored_under() -> None:
    assert TextPart.kind is PartKind.TEXT
    assert ReasoningPart.kind is PartKind.REASONING
    assert TextPart("hello").text == "hello"
    # The encoding is core's, in one place and in both directions: a record
    # here holds and checks, and knows nothing about how it is written down.
    assert not hasattr(TextPart("hello"), "to_data")
    assert not hasattr(provenance(), "to_data")


def test_a_part_holds_bounded_text_and_nothing_else() -> None:
    assert TextPart("a" * MAX_PART_CHARS).text
    with pytest.raises(InvalidValueError):
        TextPart("a" * (MAX_PART_CHARS + 1))
    with pytest.raises(InvalidValueError):
        TextPart(7)  # type: ignore[arg-type]
    with pytest.raises(InvalidValueError):
        ReasoningPart(None)  # type: ignore[arg-type]


def test_the_bound_on_a_part_is_longer_than_a_model_can_answer() -> None:
    """A model asked for its longest answer is paid for either way.

    Sixty-four thousand output tokens is a quarter of a million characters,
    and an answer over the bound is carried in several parts by
    ``domain.text_parts``, never cut.
    """
    assert MAX_PART_CHARS >= 1_000_000
    assert MAX_PARTS * MAX_PART_CHARS >= 64_000_000


@pytest.mark.parametrize("text", ["a\x00b", "a\ud800b", "\udfff"])
def test_stored_text_is_text_a_database_and_utf_8_can_hold(text: str) -> None:
    with pytest.raises(InvalidValueError):
        TextPart(text)
    with pytest.raises(InvalidValueError):
        conversation(title=text)
    # And the repair is what the layer that meets such text applies first.
    assert TextPart(clean_text(text)).text == clean_text(text)
    clean_text(text).encode("utf-8")


def test_cleaning_joins_a_pair_that_arrived_in_two_pieces() -> None:
    """The case it exists for: a provider split one character across two
    deltas, and replacing both halves would lose a character that did
    arrive."""
    assert clean_text("\ud83d" + "\ude00") == "\U0001f600"
    assert clean_text("a" + "\ud83d" + "\ude00" + "b") == "a\U0001f600b"
    assert clean_text("\U0001f600") == "\U0001f600", "what arrived whole is untouched"


@pytest.mark.parametrize(
    ("given", "cleaned"),
    [
        ("a\x00b", "ab"),
        ("a\ud800b", "a\ufffdb"),
        ("\udfff", "\ufffd"),
        ("\ude00\ud83d", "\ufffd\ufffd"),
        ("caf\u00e9 \U0001f600", "caf\u00e9 \U0001f600"),
        ("", ""),
    ],
)
def test_cleaning_replaces_what_is_left_and_drops_what_cannot_be_stored(
    given: str, cleaned: str
) -> None:
    assert clean_text(given) == cleaned
    clean_text(given).encode("utf-8")


def test_cleaning_a_megabyte_is_linear_enough_to_be_dull() -> None:
    started = time.monotonic()
    cleaned = clean_text(("a" * 999_999) + "\ud83d\ude00")
    assert cleaned.endswith("\U0001f600")
    assert time.monotonic() - started < 1.0


def test_cleaning_takes_text() -> None:
    with pytest.raises(InvalidValueError):
        clean_text(7)  # type: ignore[arg-type]


def test_a_fragment_of_a_message_may_be_half_a_character() -> None:
    """A provider splits its answer where it likes; a delta carries it all."""
    assert checked_fragment("a\ud800", "a delta's text", 10) == "a\ud800"
    with pytest.raises(InvalidValueError):
        checked_fragment("aaa", "a delta's text", 2)


def test_a_refusal_never_repeats_what_it_refused() -> None:
    secret = "a-password-somebody-typed-in-the-wrong-box"
    for build in (
        lambda: TextPart(secret + "\x00"),
        lambda: question(parts=(secret,)),
        lambda: question(role=secret),
        lambda: conversation(title=secret + "\n" + secret),
        lambda: conversation(agent=secret),
        lambda: question(id=secret),
    ):
        with pytest.raises(InvalidValueError) as refused:
            build()
        assert secret not in str(refused.value)


def test_what_a_refusal_says_instead() -> None:
    assert describe("hello") == "text of 5 characters"
    assert describe(None) == "nothing"
    assert describe(7) == "an int"
    assert describe([1, 2]) == "a list of 2"
    assert describe(b"ab") == "2 bytes"


def test_the_format_names_every_kind_and_carries_two_of_them() -> None:
    assert {kind.value for kind in PartKind} == {
        "text",
        "image",
        "file",
        "reasoning",
        "tool_call",
        "tool_result",
    }
    assert SUPPORTED_PART_KINDS == {PartKind.TEXT, PartKind.REASONING}
    assert isinstance(TextPart(""), MessagePart)
    assert isinstance(ReasoningPart(""), MessagePart)


@pytest.mark.parametrize(
    "kind", [PartKind.IMAGE, PartKind.FILE, PartKind.TOOL_CALL, PartKind.TOOL_RESULT]
)
def test_a_kind_this_build_does_not_carry_is_refused_by_name(kind: PartKind) -> None:
    with pytest.raises(UnsupportedContentError, match=f"{kind.value}.*not supported yet"):
        check_supported(kind)


def test_the_roles_are_the_two_a_turn_has_and_the_one_tools_will_need() -> None:
    assert {role.value for role in Role} == {"user", "assistant", "tool"}
    assert SUPPORTED_ROLES == {Role.USER, Role.ASSISTANT}
    assert check_supported_role(Role.USER) is Role.USER
    with pytest.raises(UnsupportedContentError, match="tool.*not supported yet"):
        check_supported_role(Role.TOOL)


# --- provenance -------------------------------------------------------------


def test_provenance_names_the_agent_the_engine_the_model_and_the_run() -> None:
    said = provenance()
    assert (said.agent, said.engine, said.model, said.run_id) == (
        AGENT,
        Engine.PYDANTIC_AI,
        MODEL,
        RUN,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"agent": "No Such Agent"},
        {"agent": ""},
        {"model": "Sonnet 5"},
        {"engine": "pydantic-ai"},
        {"engine": None},
        {"run_id": str(RUN)},
        {"run_id": None},
    ],
)
def test_provenance_refuses_what_it_could_not_show(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidValueError):
        provenance(**changes)


# --- messages ---------------------------------------------------------------


def test_a_question_has_no_provenance_and_an_answer_must_have_one() -> None:
    assert question().provenance is None
    assert answer(question()).provenance == provenance()


def test_an_answer_without_provenance_is_refused() -> None:
    with pytest.raises(InvalidValueError, match="agent, engine, model and run"):
        answer(question(), provenance=None)


def test_a_question_with_provenance_is_refused() -> None:
    with pytest.raises(InvalidValueError, match="only an assistant message"):
        question(provenance=provenance())


def test_what_this_version_keeps_of_an_answer() -> None:
    """Reasoning is dropped rather than refused, and a message always has
    content: a model that said nothing answered with nothing, which is a
    thing a conversation should record rather than skip."""
    assert kept_parts((TextPart("Hi"), ReasoningPart("thinking"))) == (TextPart("Hi"),)
    assert kept_parts((ReasoningPart("thinking"),)) == (TextPart(""),)
    assert kept_parts((TextPart(""),)) == (TextPart(""),)
    assert kept_parts([TextPart("a"), TextPart("b")]) == (TextPart("a"), TextPart("b"))
    with pytest.raises(InvalidValueError):
        kept_parts(())
    with pytest.raises(InvalidValueError):
        kept_parts(("not a part",))


def test_an_answer_of_nothing_is_a_message_like_any_other() -> None:
    said = answer(question(), parts=kept_parts((ReasoningPart("thinking"),)))
    assert said.text == ""
    assert said.parts == (TextPart(""),)


@pytest.mark.parametrize(
    "when",
    [
        datetime(1970, 1, 1, tzinfo=timezone(timedelta(hours=14))),
        datetime(1969, 12, 31, 23, 59, tzinfo=UTC),
        datetime(9999, 1, 1, tzinfo=UTC),
        datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=5))),
    ],
)
def test_a_record_holds_no_time_that_could_not_be_written_back(when: datetime) -> None:
    """The window is on the record, not only on the encoder: a row that
    cannot be encoded is a row nothing can read back."""
    for build in (
        lambda: question(created_at=when),
        lambda: conversation(created_at=when),
        lambda: conversation(updated_at=when),
    ):
        with pytest.raises(InvalidValueError, match="once it is UTC"):
            build()


@pytest.mark.parametrize(
    "when",
    [
        datetime(EARLIEST_YEAR, 1, 1, tzinfo=UTC),
        datetime(EARLIEST_YEAR, 1, 1, 14, tzinfo=timezone(timedelta(hours=14))),
        datetime(LATEST_YEAR, 12, 31, tzinfo=UTC),
    ],
)
def test_the_ends_of_the_window_are_records_like_any_other(when: datetime) -> None:
    assert question(created_at=when).created_at == when


def test_the_rule_about_parts_is_one_rule_anything_reading_a_message_can_ask() -> None:
    assert checked_parts([TextPart("a")]) == (TextPart("a"),)
    with pytest.raises(InvalidValueError, match="at least one part"):
        checked_parts([])


def test_a_message_holds_at_least_one_part_and_at_most_the_bound() -> None:
    with pytest.raises(InvalidValueError, match="at least one part"):
        question(parts=())
    with pytest.raises(InvalidValueError, match=f"at most {MAX_PARTS} parts"):
        question(parts=tuple(TextPart("x") for _ in range(MAX_PARTS + 1)))
    assert len(question(parts=tuple(TextPart("x") for _ in range(MAX_PARTS))).parts) == MAX_PARTS


@pytest.mark.parametrize("parts", ["hello", 7, ("hello",), (None,), ({"kind": "text"},)])
def test_a_message_holds_only_the_content_the_format_carries(parts: object) -> None:
    with pytest.raises(InvalidValueError):
        question(parts=parts)


def test_parts_are_kept_as_a_tuple_whatever_they_arrived_in() -> None:
    assert question(parts=[TextPart("a"), TextPart("b")]).parts == (TextPart("a"), TextPart("b"))


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not a uuid"},
        {"conversation_id": str(CONVERSATION)},
        {"parent_id": "not a uuid"},
        {"role": "user"},
        {"role": None},
        {"channel": "web"},
        {"created_at": NAIVE},
        {"created_at": "2026-09-21T09:00:00+00:00"},
    ],
)
def test_a_message_refuses_a_field_of_the_wrong_kind(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidValueError):
        question(**changes)


def test_a_message_is_not_its_own_parent() -> None:
    message_id = uuid.uuid4()
    with pytest.raises(InvalidValueError, match="its own parent"):
        question(id=message_id, parent=message_id)


def test_a_message_of_the_tool_role_is_not_supported_yet() -> None:
    with pytest.raises(UnsupportedContentError, match="tool.*not supported yet"):
        question(role=Role.TOOL)


def test_a_messages_text_is_its_text_parts_and_not_its_reasoning() -> None:
    message = answer(
        question(), parts=(ReasoningPart("thinking"), TextPart("Hi "), TextPart("Ada"))
    )
    assert message.text == "Hi Ada"


def test_a_message_comes_from_the_web_unless_it_says_otherwise() -> None:
    assert question().channel is Channel.WEB
    assert {channel.value for channel in Channel} == {"web"}


# --- conversations ----------------------------------------------------------


def test_a_conversation_has_an_owner_an_agent_and_a_branch_to_open_on() -> None:
    leaf = uuid.uuid4()
    opened = conversation(active_leaf_id=leaf)
    assert (opened.owner_id, opened.agent, opened.active_leaf_id) == (OWNER, AGENT, leaf)
    assert conversation().active_leaf_id is None


def test_a_new_conversation_has_no_title_yet() -> None:
    assert (
        Conversation(
            id=CONVERSATION,
            owner_id=OWNER,
            agent=AGENT,
            created_at=datetime(2026, 9, 21, 9, 0, tzinfo=UTC),
            updated_at=datetime(2026, 9, 21, 9, 0, tzinfo=UTC),
        ).title
        == ""
    )


@pytest.mark.parametrize(
    "title", ["two\nlines", "a\ttab", "a\x00null", "​" + "zero width", "a" * (MAX_TITLE_CHARS + 1)]
)
def test_a_title_is_one_line_of_printable_text(title: str) -> None:
    with pytest.raises(InvalidValueError):
        conversation(title=title)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not a uuid"},
        {"owner_id": None},
        {"agent": "No Such Agent"},
        {"created_at": NAIVE},
        {"updated_at": NAIVE},
        {"active_leaf_id": "not a uuid"},
        {"title": 7},
    ],
)
def test_a_conversation_refuses_a_field_of_the_wrong_kind(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidValueError):
        conversation(**changes)


def test_the_records_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        question().role = Role.ASSISTANT  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provenance().model = "haiku"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        conversation().title = "renamed"  # type: ignore[misc]
