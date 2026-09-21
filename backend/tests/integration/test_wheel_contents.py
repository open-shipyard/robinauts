# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What the built wheel actually carries.

``schema.sql`` is the one file in this package that is not Python, and the
one a packaging default could quietly leave behind. Reading it through
``importlib.resources`` proves nothing about that: a development checkout is
an editable install, where the package *is* the source tree and the file is
always there. So this builds a wheel and looks inside it.

Marked ``io``: it runs a build, into a temporary directory that is thrown
away, and needs no database. It takes a couple of seconds. It skips, with
the reason, on a machine with no ``uv`` on the path.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from robinauts.datastore import schema_sql

pytestmark = pytest.mark.io

BACKEND = Path(__file__).resolve().parents[2]
SHIPPED = "robinauts/datastore/schema.sql"


def left_behind(*, before: bool, after: bool) -> bool:
    """Whether the build added a ``dist/`` that was not there before it.

    A developer who ran ``uv build`` by hand already has one, and that is not
    this test's business: the question is what *this* build left, not what
    the tree looked like to begin with.
    """
    return after and not before


@pytest.fixture(scope="module")
def dist_before() -> bool:
    """Whether ``backend/dist`` was there **before** anything was built.

    The `wheel` fixture below asks for it, which is what makes this run
    first: read after the build, it would be the same value as the one the
    test compares it against, and the comparison would always hold.
    """
    return (BACKEND / "dist").exists()


@pytest.fixture(scope="module")
def wheel(dist_before: bool) -> Iterator[Path]:
    """A freshly built wheel, in a directory removed when the module is done.

    Built with ``--wheel`` alone: the source distribution would double the
    time and this is a question about the wheel.
    """
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("no uv on the path to build a wheel with")
    with tempfile.TemporaryDirectory(prefix="robinauts-wheel-") as out:
        built = subprocess.run(
            [uv, "build", "--wheel", "--out-dir", out],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            check=False,
        )
        assert built.returncode == 0, built.stdout + built.stderr
        wheels = list(Path(out).glob("*.whl"))
        assert len(wheels) == 1, f"expected one wheel, got {wheels}"
        yield wheels[0]


def test_the_schema_definition_is_in_the_wheel(wheel: Path) -> None:
    # Without it an installed Robinauts could not create its own database,
    # and nothing would say so until somebody ran the command on a new
    # deployment.
    with zipfile.ZipFile(wheel) as built:
        assert SHIPPED in built.namelist()


def test_the_schema_in_the_wheel_is_the_schema_the_code_reads(wheel: Path) -> None:
    # A wheel carrying a *different* schema.sql would be worse than one
    # carrying none: the version check would pass and the tables would not
    # match. Newlines are normalised on both sides, because the question is
    # what the file says and not how this checkout spells the end of a line.
    with zipfile.ZipFile(wheel) as built:
        shipped = built.read(SHIPPED).decode("utf-8").replace("\r\n", "\n")

    assert shipped == schema_sql().replace("\r\n", "\n")


def test_the_build_left_nothing_new_in_the_tree(wheel: Path, dist_before: bool) -> None:
    # `uv build` writes to backend/dist/ unless it is told otherwise, and a
    # dist/ left behind is a directory `reuse lint` then reads. What is
    # asserted is that *this* build added none: a dist/ that was already
    # there is somebody's own, and failing over it would be this test
    # complaining about a tree it did not touch.
    assert wheel.parent != BACKEND / "dist"
    assert not left_behind(before=dist_before, after=(BACKEND / "dist").exists())


@pytest.mark.parametrize(
    ("before", "after", "left"),
    [(False, True, True), (False, False, False), (True, True, False), (True, False, False)],
)
def test_only_a_dist_this_build_made_counts_as_left_behind(
    before: bool, after: bool, left: bool
) -> None:
    # The one case that must fail the test above is the one where the build
    # made the directory: `uv build` without `--out-dir` would do exactly
    # that, and `reuse lint` would then read whatever it put there.
    assert left_behind(before=before, after=after) is left
