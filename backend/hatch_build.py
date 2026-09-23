# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""What a wheel must carry that is not under ``backend/``.

The deliverable is **one wheel** holding the backend, the schema and the built
interface (``docs/specs/frontend.md``): ``pip install`` plus a PostgreSQL is a
whole deployment. Two of those three live outside this directory, so hatchling
is told about them here.

**The interface**: ``frontend/dist`` becomes ``robinauts/ui/``, which is a
force-include -- added by the build hook rather than declared in
``pyproject.toml``, because a declared one is looked for whichever kind of
build it is, and an **editable** install has no built frontend by design.

**The licence files** cannot be declared, and that is what the two plugins below
are for. ``LICENSE`` and ``NOTICE`` are the repository's, at its root, and
``THIRD_PARTY_LICENSES.txt`` is written into ``frontend/dist`` by the frontend
build; all three belong in the wheel's ``license-files``
(``docs/oss-checklist.md``, "Releases"), and PEP 639's globs are relative to the
project directory -- a pattern climbing out of it is written into the metadata
as it was spelt, which is not a path a wheel may hold. So they are **staged**
beside ``pyproject.toml`` while the wheel is built, and taken away again.

**Two plugins, because of when each thing is decided.** Hatchling reads and
caches ``license-files`` before it runs a single build hook, so staging from a
build hook would stage them for a list that had already been settled -- and an
empty one. The metadata hook runs first, which is where the staging is; the
build hook runs after it, which is where the refusal is, because only the build
knows whether it is building a real wheel.

**And it refuses.** A missing ``frontend/dist``, a ``dist`` with no
``index.html``, or one with no ``THIRD_PARTY_LICENSES.txt`` stops the build.
Without that, a wheel built where the frontend had not been built would install,
start, and serve "the interface is not built" to every visitor -- and one built
from a ``dist`` whose notices had been lost would redistribute other people's
code without the attribution their licences ask for
(``docs/specs/open-source.md``). The second of those is caught by nothing else
at all, and the first is caught late and obscurely, by a packaging error about
an include; this says what to do instead.

**Editable installs are exempt**, and only they. ``uv sync`` builds one for
every checkout, CI's included, and a development checkout has no built frontend
by design -- the files are never committed, the interface is developed against
Vite's own server, and an installed package that carries none answers the page
that says so (``robinauts.api.ui``). The exemption is on the build *version*
hatchling asks for, so nothing a caller passes can turn it on for a real wheel.

**The sdist is not the deliverable**, and is made honest rather than clever.
It is a copy of ``backend/`` and carries no interface, because the interface is
not in ``backend/``; a wheel built *from* an unpacked sdist therefore cannot
carry one either, and is refused with a sentence that says where a wheel comes
from instead (``scripts/build-wheel.sh``). Nothing else is left out of it. Its
licence files are this project's own two and never the bundle's notices, which
belong to the wheel that carries the bundle -- and which would otherwise make
the sdist's metadata depend on whether somebody had run ``npm run build``
first. The build hook is registered for the sdist target as well, for one
reason: the metadata hook stages licence files for **every** build, and
``finalize`` is what takes them away again.

**A build is a thing this directory does once at a time.** The staged copies
are real files beside ``pyproject.toml``, so two builds of this project running
at once in the same checkout would share them -- and the first to finish would
take them out from under the second. Build one at a time, or in checkouts of
their own; ``scripts/build-wheel.sh`` and CI both do the former.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.metadata.plugin.interface import MetadataHookInterface

BACKEND = Path(__file__).resolve().parent
"""Where ``pyproject.toml`` is, and where the licence files are staged."""

REPOSITORY = BACKEND.parent

FRONTEND = REPOSITORY / "frontend"
"""Beside ``backend/`` in the repository, and **nowhere at all** in an sdist."""

FRONTEND_BUILD = FRONTEND / "dist"
"""What ``npm run build`` writes, and what the wheel's ``robinauts/ui/`` is."""

PKG_INFO = "PKG-INFO"
"""Beside the ``pyproject.toml`` of every source distribution, and of no checkout.

The one marker that cannot be faked by where an sdist happens to be unpacked
(``in_a_checkout``). Hatchling reads it in the same place and for the same
reason.
"""

INDEX = "index.html"
"""The one page the interface is (``robinauts.api.ui.INDEX``)."""

NOTICES = "THIRD_PARTY_LICENSES.txt"
"""Every notice the bundle's own dependencies ask for, written by the build."""

UI_IN_THE_WHEEL = "robinauts/ui"
"""Where the built interface lands inside the package (``robinauts.api.ui``)."""

OURS: tuple[tuple[Path, str], ...] = (
    (REPOSITORY / "LICENSE", "LICENSE"),
    (REPOSITORY / "NOTICE", "NOTICE"),
)
"""This project's own terms, which every distribution of it carries."""

THEIRS: tuple[tuple[Path, str], ...] = ((FRONTEND_BUILD / NOTICES, NOTICES),)
"""The notices of everything inside the JavaScript bundle.

**The wheel's alone.** They are the terms of code the *bundle* carries, and an
sdist carries no bundle: putting them in one would distribute somebody else's
notice beside none of their code, and would make the sdist's metadata depend
on whether the checkout that built it happened to have run ``npm run build``.
"""

STAGED: tuple[tuple[Path, str], ...] = OURS + THEIRS
"""Each licence file this can stage: where it is, and what it is staged as.

The staged name is what the metadata hook puts in ``license-files``, and so is
the name the distribution holds it under. Which of them are staged is
``stage``'s decision, and it depends on what is being built.
"""

REQUIRED = (FRONTEND_BUILD / INDEX, FRONTEND_BUILD / NOTICES, *(source for source, _ in STAGED))
"""Every file a wheel may not be built without, checked one at a time."""

EDITABLE = "editable"
"""The build hatchling calls an editable install, and the one this passes over."""

WHEEL = "wheel"
"""The one target that carries the interface, and the one that refuses."""

DOT = "."
"""A file whose name begins with this is not part of the interface. See ``carried``."""

LICENSE_FILES = "license-files"
"""The metadata field this fills in; ``project.dynamic`` lists it for that."""

NOT_BUILT = (
    "the frontend has not been built: {missing} is not there. A wheel carries the"
    " built interface and its notices (docs/specs/frontend.md), so run"
    " `npm ci && npm run build` in frontend/ -- or scripts/build-wheel.sh, which does"
    " both -- before building one. Nothing was written and nothing was left behind."
)
"""Why a wheel was refused, naming the file that was looked for."""

FROM_AN_SDIST = (
    "this is a wheel being built from the source distribution, which carries no"
    " frontend: the interface is not under backend/, so it is not in an sdist of"
    " backend/ either. A wheel is built from the checkout, with the frontend built"
    " -- `scripts/build-wheel.sh <directory>` does both -- and the sdist is not the"
    " deliverable (docs/specs/frontend.md). Nothing was written and nothing was left"
    " behind."
)
"""Why that wheel was refused, which is a different thing to go and do.

Told apart by ``PKG-INFO`` (``in_a_checkout``), which is in every source
distribution and in no checkout -- and **not** by where the directory happens
to be, because an sdist unpacked inside the repository has the repository's
``frontend/`` beside it and none of it is its own.
"""


def in_a_checkout() -> bool:
    """Whether this is the repository and not an unpacked source distribution.

    **What decides whether anything here may write beside ``pyproject.toml``.**
    In the repository, ``LICENSE`` and ``NOTICE`` next to it are copies this
    made and are this to remove; in an unpacked sdist they are files the
    distribution *carries*, and clearing them would take a licence out of
    somebody's copy of the project.

    Told apart by ``PKG-INFO``, which every source distribution carries beside
    its ``pyproject.toml`` and which no checkout has -- hatchling reads the
    same marker for the same reason. **Not** by ``frontend/`` being there: an
    sdist unpacked anywhere inside the repository has one beside it, and would
    be read as the repository it is sitting in -- its licence files deleted,
    and a wheel built for it out of the outer checkout's bundle.
    """
    return not (BACKEND / PKG_INFO).is_file()


def building_the_sdist() -> bool:
    """Whether this process is building the source distribution.

    Hatchling tells a **metadata** hook nothing about the target -- it is given
    the project root and its own configuration and no more -- and this is the
    one thing here that has to know. The two PEP 517 entry points import
    different builders (``hatchling.build.build_sdist`` imports
    ``hatchling.builders.sdist``, ``build_wheel`` imports
    ``hatchling.builders.wheel``), and the metadata is settled inside the
    builder that was imported, so the modules a build has loaded say which one
    it is.

    It is an inference about somebody else's package, so it is **pinned by
    tests on both sides**: the sdist's ``PKG-INFO`` must list exactly this
    project's own two licence files, and the wheel's ``METADATA`` all three
    (``tests/integration/test_wheel_contents.py``). A hatchling that stopped
    behaving this way fails there rather than shipping a wrong notice.
    """
    loaded = sys.modules
    return "hatchling.builders.sdist" in loaded and "hatchling.builders.wheel" not in loaded


def stage() -> list[str]:
    """Copy the licence files beside ``pyproject.toml``; the names, for the metadata.

    An **sdist** gets this project's own two and never the bundle's notices
    (``THEIRS``), so that its metadata says the same thing in every checkout.
    Everything else -- the wheel, and the editable install ``uv sync`` builds
    -- gets whatever is there.

    Best effort past that, and deliberately so: an editable install is built in
    every checkout, CI's included, and a metadata hook that refused where
    ``frontend/dist`` does not exist would stop ``uv sync`` in all of them.
    What may not be **built** without them is the build hook's decision, below,
    which knows which kind of build this is.

    Whatever a build that failed part way left behind goes first: ``finalize``
    does not run when a build raises, and a stale copy of a licence file is
    worse than none, because nothing would look at it again.

    Nothing at all outside a checkout (``in_a_checkout``): there is nothing to
    copy from, and the files of that name are the distribution's own.
    """
    clear()
    if not in_a_checkout():
        return []
    wanted = OURS if building_the_sdist() else STAGED
    staged = []
    for source, name in wanted:
        if source.is_file():
            shutil.copyfile(source, BACKEND / name)
            staged.append(name)
    return staged


def clear() -> None:
    """Take the staged licence files out of the source tree.

    **Only in a checkout.** In an unpacked source distribution the files of
    those names are ones the distribution carries, and removing them would take
    a licence out of somebody's copy of this project -- which a wheel built
    from an sdist would otherwise do on its way to being refused.

    ``missing_ok``: the usual case is that there is nothing to remove.
    """
    if not in_a_checkout():
        return
    for _, name in STAGED:
        (BACKEND / name).unlink(missing_ok=True)


def carried() -> dict[str, str]:
    """Every built file that goes into the wheel, by where it lands in it.

    File by file rather than "this whole directory", for one reason: a
    directory a build writes into is a directory other things write into too,
    and a **dotfile** -- an editor's swap file, a ``.DS_Store``, a ``.env``
    somebody left beside the bundle -- would otherwise be packaged and served
    to anybody who asked for it (``robinauts.api.ui.hidden`` refuses to serve
    one; this refuses to ship one). Nothing else is left out: what the build
    wrote is what the interface is.
    """
    return {
        str(found): f"{UI_IN_THE_WHEEL}/{found.relative_to(FRONTEND_BUILD).as_posix()}"
        for found in sorted(FRONTEND_BUILD.rglob("*"))
        if found.is_file()
        and not any(part.startswith(DOT) for part in found.relative_to(FRONTEND_BUILD).parts)
    }


class RobinautsMetadataHook(MetadataHookInterface):  # type: ignore[type-arg]
    """Stage the licence files, and name them, before the metadata is settled."""

    PLUGIN_NAME = "custom"

    def update(self, metadata: dict[str, Any]) -> None:
        """Fill in ``project.license-files``, which is dynamic for this reason."""
        metadata[LICENSE_FILES] = stage()


class RobinautsBuildHook(BuildHookInterface):  # type: ignore[type-arg]
    """Put the built interface in the wheel, or refuse to build one.

    Registered for the **sdist** target as well, where it adds and refuses
    nothing: the metadata hook stages the licence files for every build, and
    ``finalize`` below is what takes them away again. Without that, building an
    sdist would leave three copies beside ``pyproject.toml``.
    """

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Before anything is written into the archive.

        A refusal clears the staged licence files on the way out. ``finalize``
        does not run when a build raises, and this is the one failure that is
        **expected** -- somebody builds a wheel in a checkout they have not
        built the frontend in -- so leaving three copies of somebody's licence
        beside ``pyproject.toml`` every time would be leaving them there.
        """
        if self.target_name != WHEEL or version == EDITABLE:
            return
        try:
            # The distribution first, the directory second: an sdist unpacked
            # inside the repository has a ``frontend/`` beside it and is still
            # an sdist, and the bundle in it is not its own.
            if not in_a_checkout() or not FRONTEND.is_dir():
                raise FileNotFoundError(FROM_AN_SDIST)
            for missing in REQUIRED:
                if not missing.is_file():
                    raise FileNotFoundError(NOT_BUILT.format(missing=missing))
        except FileNotFoundError:
            clear()
            raise
        build_data["force_include"].update(carried())

    def finalize(self, version: str, build_data: dict[str, Any], artifact: str) -> None:
        """After the archive is written: the staged files were for it alone."""
        clear()

    def clean(self, versions: list[str]) -> None:
        """``hatch clean``, and anything else asking for a tidy tree."""
        clear()
