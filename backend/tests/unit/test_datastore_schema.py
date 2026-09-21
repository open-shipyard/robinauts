# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What can be checked about the schema without a database.

That its version and the code's have not drifted apart, that its conventions
held through the last edit, that the version row is written last and never
overwritten, and that every refusal an operator can read says what to type.

What is *not* here: that it applies, that the check bites, and that the file
is really in the wheel. Those need a PostgreSQL or a build, and are in
``tests/integration/``.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from robinauts.datastore import SCHEMA_SHA256, SCHEMA_TABLES, SCHEMA_VERSION, schema_sql
from robinauts.datastore.credentials import SESSION_REFUSALS
from robinauts.domain import DB_INIT_COMMAND, SchemaError

SQL = schema_sql()

TABLES = {
    name: body
    for name, body in re.findall(
        r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SQL, flags=re.DOTALL
    )
}


def test_the_schema_file_is_readable_from_the_installed_package() -> None:
    # It is read through `importlib.resources`, not off a path beside the
    # source. That is all this proves: on an editable install the package is
    # the source tree, so whether a *wheel* carries the file is a question
    # only a wheel can answer -- tests/integration/test_wheel_contents.py.
    #
    # The licence header is spelt out nowhere here on purpose: `reuse lint`
    # reads the tree for those, and a test that quoted the tag would be one
    # more file claiming a licence for itself.
    header = SQL.splitlines()[:2]
    assert all(line.startswith("-- ") for line in header)
    assert header[0].endswith("Apache-2.0") and "Robinauts Authors" in header[1]


def test_the_tables_the_code_looks_for_are_the_tables_the_file_creates() -> None:
    # `check_schema` refuses a database that is missing one of SCHEMA_TABLES.
    # A table added to the file and not to that list would never be looked
    # for, and a half-applied schema missing it would pass.
    assert set(SCHEMA_TABLES) == TABLES.keys()


@pytest.mark.parametrize("constraint", sorted(SESSION_REFUSALS))
def test_every_constraint_the_store_answers_for_is_named_in_the_file(constraint: str) -> None:
    # The store tells a violation it has an answer for from one it does not
    # by the constraint's name. A constraint renamed here, or left for
    # PostgreSQL to name, would silently stop being translated -- and the
    # caller would get a driver error where the contract promises a refusal.
    assert f"CONSTRAINT {constraint} " in SQL


def test_the_version_in_the_file_is_the_version_in_the_code() -> None:
    # The one thing that must be changed twice, and the one thing nobody
    # remembers to change twice. An edit to schema.sql without a bump of
    # SCHEMA_VERSION would leave a server happy to run against a schema it
    # was not written for.
    recorded = re.search(r"^INSERT INTO schema_version \(version\) VALUES \((\d+)\)$", SQL, re.M)

    assert recorded is not None, "schema.sql no longer records a version the way this test reads it"
    assert int(recorded.group(1)) == SCHEMA_VERSION


def test_editing_the_schema_without_bumping_the_version_fails_here() -> None:
    # The whole guard for a schema that is edited in place. There is no
    # migration to write and therefore nothing else that would notice; this
    # pin is what turns "I changed a column and forgot" into a red build.
    # Line endings are normalised so that a checkout on Windows does not
    # fail for a reason that has nothing to do with the schema.
    text = SQL.replace("\r\n", "\n")

    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == SCHEMA_SHA256, (
        "schema.sql changed: bump SCHEMA_VERSION in datastore/schema.py and update the"
        " pinned SCHEMA_SHA256 in the same change. There are no migrations yet, so a"
        " database made from the old file is recreated, not upgraded."
    )


def test_the_version_is_written_last_and_never_overwritten() -> None:
    # Last, because the row is the claim that every table above it exists: a
    # file that stopped half way must leave no version at all. And never
    # `DO UPDATE`, because `CREATE TABLE IF NOT EXISTS` leaves an older table
    # exactly as it is -- an update here would relabel version 0's tables as
    # this version and every check afterwards would pass.
    code = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--"))
    statements = [line for line in code.splitlines() if line.strip().endswith(";")]

    assert statements[-1].strip() == "ON CONFLICT (only_row) DO NOTHING;"
    assert "DO UPDATE" not in code
    assert SQL.index("INSERT INTO schema_version") > max(
        SQL.index(f"CREATE TABLE IF NOT EXISTS {table}") for table in TABLES
    )


@pytest.mark.parametrize("table", sorted(TABLES))
def test_every_point_in_time_carries_its_zone(table: str) -> None:
    # `timestamp` without a zone is a wall clock: read as one thing by the
    # server and another by the process, and an expiry that means two things
    # is no expiry (docs/specs/backend.md).
    for line in TABLES[table].splitlines():
        column = line.strip().rstrip(",")
        assert not re.match(r"^\w+ timestamp\b(?! *with)", column), column


@pytest.mark.parametrize("table", sorted(TABLES))
def test_what_a_sweep_deletes_by_is_indexed(table: str) -> None:
    # Housekeeping runs beside everything else; a sweep that scans the whole
    # table is a sweep that holds it.
    if "expires_at " not in TABLES[table]:
        pytest.skip(f"{table} has nothing that expires")

    assert re.search(rf"^CREATE INDEX IF NOT EXISTS \w+ ON {table} \(expires_at\);$", SQL, re.M)


def test_no_default_reads_the_database_clock_for_a_decision() -> None:
    # One clock decides what has expired, and it is the application's. The
    # only `now()` in the file dates the schema itself.
    for line in SQL.splitlines():
        if "now()" in line and not line.lstrip().startswith("--"):
            assert "applied_at" in line or "schema_version" in line, line


def test_applying_by_hand_is_documented_as_one_transaction() -> None:
    # Without both flags psql keeps going after an error, which is the one
    # way to get a half-applied schema past everything else here.
    assert "ON_ERROR_STOP=1" in SQL and "--single-transaction" in SQL


# Every shape of refusal, as the operator reads it.


def test_an_empty_database_is_told_which_command_makes_a_schema() -> None:
    refused = SchemaError.missing(SCHEMA_VERSION)

    assert refused.found is None
    assert "no Robinauts schema" in str(refused)
    assert DB_INIT_COMMAND in str(refused)


def test_a_schema_of_another_version_is_told_both_versions_and_the_command() -> None:
    refused = SchemaError.mismatch(1, 2)

    assert (refused.expected, refused.found) == (1, 2)
    assert "schema version 2" in str(refused) and "needs schema version 1" in str(refused)
    assert DB_INIT_COMMAND in str(refused)


def test_tables_without_a_version_are_never_called_an_empty_database() -> None:
    # The difference that matters: an empty database is one to create a
    # schema in, and this one is not.
    refused = SchemaError.unversioned(1, ["sessions", "users"])

    assert refused.found is None
    assert "records no schema version" in str(refused)
    assert "sessions, users" in str(refused)
    assert DB_INIT_COMMAND in str(refused)


def test_a_version_that_cannot_be_read_is_an_unknown_version() -> None:
    refused = SchemaError.unreadable(1)

    assert "unknown version" in str(refused)
    assert DB_INIT_COMMAND in str(refused)


def test_a_shadowed_table_is_a_search_path_to_fix_not_a_database_to_remake() -> None:
    # Nothing is wrong with the database here, so the advice that fits every
    # other refusal is the wrong advice for this one.
    refused = SchemaError.shadowed(1, ["sessions", "users"])

    assert "sessions, users" in str(refused)
    assert "search path" in refused.advice
    assert DB_INIT_COMMAND not in str(refused)


def test_a_missing_table_under_the_right_version_names_the_table() -> None:
    refused = SchemaError.incomplete(1, {"sessions"})

    assert refused.found == 1
    assert "missing: sessions" in str(refused)
    assert DB_INIT_COMMAND in str(refused)


def test_every_refusal_says_the_command_wants_an_empty_database() -> None:
    # The sentence that keeps `robinauts db init` away from a database that
    # already has somebody's data in it.
    for refused in (
        SchemaError.missing(1),
        SchemaError.mismatch(1, 2),
        SchemaError.unversioned(1, ["users"]),
        SchemaError.unreadable(1),
        SchemaError.incomplete(1, {"users"}),
    ):
        assert "empty database only" in str(refused)
