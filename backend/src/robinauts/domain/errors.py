# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Every error the platform raises, rooted at ``RobinautsError``.

A sign-in failure carries one of the fixed codes of
``docs/specs/sign-in.md``: the browser is told the code and nothing else,
while ``detail`` says what really happened and goes to the log.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class RobinautsError(Exception):
    """The root of the platform's error hierarchy."""


class InvalidValueError(RobinautsError, ValueError):
    """A value that no part of the platform can work with."""


class ConfigError(RobinautsError):
    """Configuration that cannot be used; ``problems`` lists every one found.

    The operator gets the whole list at once, as ``docs/specs/operations.md``
    asks: a start-up that fixed one problem at a time would take as many
    restarts as there are mistakes.
    """

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems: tuple[str, ...] = tuple(problems)
        if not self.problems:
            raise InvalidValueError("a ConfigError lists at least one problem")
        super().__init__("invalid configuration:\n" + "\n".join(self.problems))


DB_INIT_COMMAND = "robinauts db init"
"""The command that creates the schema. The server never creates it itself.

Named here because ``SchemaError`` is what an operator reads when the
database is not the one this build was written against, and an error that
says what is wrong without saying what to type is half an error.
"""


class SchemaError(RobinautsError):
    """The database is not the one this build was written against.

    Every way that can be true ends in the same two refusals -- the schema is
    not created, and the server does not start -- because a server that ran
    against a schema it does not know would write rows nothing can read back
    (``docs/specs/backend.md``). What differs is only what the operator is
    told they are looking at, so the shapes are the constructors below and
    the advice is one sentence, written once.

    Until there is a production deployment there are no migrations: a
    database of any other version is **made again**, not upgraded, and the
    command that creates the schema works on an empty database only. Saying
    that in every message is deliberate -- the alternative is an operator
    running the command on the database that already has their data in it.
    """

    ADVICE = (
        f"`{DB_INIT_COMMAND}` creates the schema, and until there are migrations it works"
        " on an empty database only: a database of any other version is made again"
    )

    def __init__(
        self,
        problem: str,
        *,
        expected: int,
        found: int | None = None,
        advice: str | None = None,
    ) -> None:
        self.problem = problem
        """What is wrong, without the advice: one clause, for a log line."""
        self.expected = expected
        self.found = found
        """The version in the database, or ``None`` if it has no usable one."""
        self.advice = advice or self.ADVICE
        """What to do. Recreating the database, unless something else fixes it."""
        super().__init__(f"{problem}; this build needs schema version {expected}. {self.advice}")

    @classmethod
    def missing(cls, expected: int) -> SchemaError:
        """There is nothing of ours in this database at all."""
        return cls("the database has no Robinauts schema", expected=expected)

    @classmethod
    def no_schema(cls, expected: int, path: str) -> SchemaError:
        """The connection's search path names nothing that exists.

        Then there is no schema to look in and none to create in either: an
        unqualified ``CREATE TABLE`` has nowhere to go. The command cannot
        help, so it is not the thing to suggest.
        """
        return cls(
            f"the connection's search path ({path}) names no schema that exists",
            expected=expected,
            advice=(
                "create the schema in the database, or point the search path at one that"
                " is there"
            ),
        )

    @classmethod
    def mismatch(cls, expected: int, found: int) -> SchemaError:
        """There is a schema, of a version this build was not written for."""
        return cls(f"the database is at schema version {found}", expected=expected, found=found)

    @classmethod
    def unversioned(cls, expected: int, tables: Iterable[str]) -> SchemaError:
        """Our tables are there and no version is recorded.

        A database somebody made by hand, or one whose creation stopped half
        way. Either way there is no telling what shape those tables are in,
        so it is not a database to add the rest of a schema to.
        """
        return cls(
            "the database holds Robinauts tables"
            f" ({', '.join(sorted(tables))}) but records no schema version",
            expected=expected,
        )

    @classmethod
    def unreadable(cls, expected: int) -> SchemaError:
        """There is a ``schema_version`` table, and it is not ours.

        Another shape, another meaning, or another project's: a version that
        cannot be read is a version that cannot be trusted, and guessing it
        is how a server ends up writing into somebody else's tables.
        """
        return cls(
            "the database has a schema_version table this build cannot read,"
            " so the schema in it is of an unknown version",
            expected=expected,
        )

    @classmethod
    def shadowed(cls, expected: int, tables: Iterable[str]) -> SchemaError:
        """The schema is right, and it is not the one the queries would reach.

        PostgreSQL resolves an unqualified table name through ``search_path``,
        and the schema checked is the one the definition was created in. If
        something earlier on the path answers to the same name, the two part
        company: the check passes, and every statement afterwards goes
        somewhere else. It is a configuration to correct, not a database.
        """
        return cls(
            "the search path reaches other tables by these names before the schema's own"
            f" ({', '.join(sorted(tables))}), so the queries would not go where the"
            " schema is",
            expected=expected,
            found=expected,
            # Not a database to make again: nothing is wrong with it.
            advice=(
                "set the connection's search path so that the schema holding the Robinauts"
                " tables is the first one on it"
            ),
        )

    @classmethod
    def incomplete(cls, expected: int, missing: Iterable[str]) -> SchemaError:
        """The version is right and the schema is not all there."""
        return cls(
            f"the database records schema version {expected} but does not have"
            f" every table this build expects (missing: {', '.join(sorted(missing))})",
            expected=expected,
            found=expected,
        )


class SignInErrorCode(StrEnum):
    """What the sign-in page is told when a sign-in does not complete.

    The set is fixed and public: it reaches the browser as a query parameter,
    so a code names a kind of failure and never the provider's own words.
    """

    EXPIRED = "expired"
    """The sign-in took longer than a pending sign-in lives, or was replayed."""
    STATE_MISMATCH = "state_mismatch"
    """The callback's ``state`` is not one this deployment handed out."""
    NOT_ALLOWED = "not_allowed"
    """The provider says who they are; the allow list does not have them."""
    UNKNOWN_PROVIDER = "unknown_provider"
    """No provider of that id is configured."""
    BUSY = "busy"
    """Too many sign-ins are already in progress."""
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    """The provider could not be reached, or answered nothing usable."""
    PROVIDER_REFUSED = "provider_refused"
    """The provider refused the sign-in, or the authorization code."""
    INVALID_ID_TOKEN = "invalid_id_token"
    """The ID token is not one for this sign-in."""


class SignInError(RobinautsError):
    """A sign-in that cannot complete.

    ``code`` is what the browser is told; ``detail`` is for the log alone and
    may hold what a provider said.
    """

    def __init__(self, code: SignInErrorCode, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}")


class NotAllowedError(SignInError):
    """The provider authenticated someone the allow list does not accept."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.NOT_ALLOWED, detail)


class UnknownProviderError(SignInError):
    """A sign-in was asked for with a provider id that is not configured."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.UNKNOWN_PROVIDER, detail)


class InvalidIdTokenError(SignInError):
    """An ID token whose claims do not belong to this sign-in."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.INVALID_ID_TOKEN, detail)


class ProviderUnavailableError(SignInError):
    """The provider could not be reached, or answered something unusable."""

    def __init__(self, detail: str) -> None:
        super().__init__(SignInErrorCode.PROVIDER_UNAVAILABLE, detail)
