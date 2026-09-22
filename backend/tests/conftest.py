# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Test-wide settings, and the one thing a run must prove about itself.

The suite imports the gate scripts from `scripts/`, which is a directory of
programs rather than a package. Compiled bytecode dropped there carries no
licence header, and `reuse lint` reads whatever is in the tree, so nothing
here writes any -- however pytest was started, and not only through
`scripts/check-tests.sh`.

With one exception it cannot reach: this file's own bytecode, which pytest
imports before the line below runs. `scripts/check-tests.sh` sets
`PYTHONDONTWRITEBYTECODE` for that one.

The hooks at the bottom answer "did the database tests actually run". A
build that sets `ROBINAUTS_REQUIRE_POSTGRES` is saying it will not accept a
green run in which they did not, and the variable being set proves only that
somebody meant them to: `-m "not io"` sets it and skips every one of them.
So the tests marked `database` are counted as they run, and a run that
required a database and counted none is failed at the end, saying so. The
decision itself is in `postgres.py`, where it can be tested without a
session to fake.

It speaks only about a run that got as far as running tests. A session that
was interrupted, that could not be configured, that only collected, or that
fell over inside pytest has something else to say for itself, and an answer
about the database on top of that would be noise at best and a wrong
diagnosis at worst.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

sys.dont_write_bytecode = True

VENDOR_LOGGERS = ("anthropic", "anthropic._base_client", "httpx2", "httpcore2")
"""The loggers an agent engine pins when it is built, whichever engine it is.

Named here rather than imported from either adapter: this file is loaded for
every test in the suite, and importing an adapter would make the whole suite
import an agent framework. The adapters' own tests assert that their
``QUIET_CLIENT_LOGGERS`` is this list, so the two cannot drift apart.
"""


@pytest.fixture(autouse=True)
def vendor_logger_levels() -> Iterator[None]:
    """Put those loggers back where each test found them.

    Their levels are **process-wide**, and building an engine moves them --
    which is the point of ``quiet_client_logging`` and is therefore something
    every module that builds one leaves behind it. Here rather than in four
    modules, because "which tests build an engine" is not a list anybody should
    have to keep: a test that left one at ``CRITICAL`` would be an environment
    the next test could not see the end of, and one that left it at ``DEBUG``
    would hide an engine that forgot to pin it.
    """
    was = [(name, logging.getLogger(name).level) for name in VENDOR_LOGGERS]
    try:
        yield
    finally:
        for name, level in was:
            logging.getLogger(name).setLevel(level)


_DATABASE_TESTS_RUN = 0
"""How many tests marked `database` reached their call phase.

Passed or failed, both count: the question is whether the database was
exercised, not whether it liked what it was asked. A skipped test never gets
here, which is the whole point.
"""

_SPEAKS_FOR_ITSELF = frozenset({pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED})
"""The outcomes that mean "the suite ran": everything else is about the run.

Interrupted, no tests collected, usage error, internal error -- each of those
already says what went wrong, and none of them is evidence about a database.
"""


def pytest_runtest_call(item: Any) -> None:
    """Count a database test the moment it really starts running."""
    global _DATABASE_TESTS_RUN
    if item.get_closest_marker("database") is not None:
        _DATABASE_TESTS_RUN += 1


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail a run that was told to prove the database and did not."""
    # Imported here rather than at the top: this file is loaded before the
    # `pythonpath` of pyproject.toml puts `tests/` on the path.
    from postgres import REQUIRE_POSTGRES, database_required, database_tests_missing

    if session.config.option.collectonly or exitstatus not in _SPEAKS_FOR_ITSELF:
        return
    problem = database_tests_missing(
        required=database_required(REQUIRE_POSTGRES),
        ran=_DATABASE_TESTS_RUN,
        narrowed=_was_narrowed(session.config),
        distributed=_was_distributed(session.config),
    )
    if problem is None:
        return
    print(f"\nERROR: {problem}.", file=sys.stderr)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _was_narrowed(config: Any) -> bool:
    """Whether this run asked for a subset of the suite.

    A marker expression, a keyword expression, or arguments naming something
    other than the configured `testpaths`. Such a run says nothing about the
    tests it did not select, so it cannot be the run that proves them.
    """
    if config.option.markexpr or config.option.keyword:
        return True
    return list(config.args) != list(config.getini("testpaths"))


def _was_distributed(config: Any) -> bool:
    """Whether this run is split across processes.

    `pytest-xdist` is not a dependency and this does not make it one: the
    counter above lives in one process, so under xdist it would read zero
    however many database tests ran, and a confident wrong answer is worse
    than none. Asked three ways because a worker, the controller and a run
    that merely passed `-n` each show it differently.
    """
    return bool(
        os.environ.get("PYTEST_XDIST_WORKER")
        or hasattr(config, "workerinput")
        or getattr(config.option, "numprocesses", None)
    )
