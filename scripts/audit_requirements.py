#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Deal an exported lockfile out into requirement files an auditor can read.

A lockfile may pin one package at two versions, each behind its own
environment marker. The markers have to go -- evaluated against whichever
machine is running, they would hide most of the locked set from the audit --
and once they are gone, the two pins cannot share a requirements file.

So the pins are dealt into as many conflict-free files as it takes, usually
one. Prints how many were written. Used by `scripts/check-audit.sh`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def canonical_name(name: str) -> str:
    """The PEP 503 form of a package name."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def pins(export: str) -> list[tuple[str, str]]:
    """Every `name==version` of an export, without its markers or comments."""
    found = []
    for line in export.splitlines():
        line = re.sub(r" *;.*$", "", line.split("#")[0]).strip()
        if "==" in line:
            name, _, version = line.partition("==")
            found.append((canonical_name(name), version.strip()))
    return found


def deal(pinned: list[tuple[str, str]]) -> list[dict[str, str]]:
    """The smallest run of groups in which no package appears twice."""
    groups: list[dict[str, str]] = []
    for name, version in pinned:
        for group in groups:
            if group.get(name) == version:
                break  # already in this group, and nothing to add
            if name not in group:
                group[name] = version
                break
        else:
            groups.append({name: version})
    return groups


def main(argv: list[str]) -> int:
    export, work = Path(argv[1]), Path(argv[2])
    groups = deal(pins(export.read_text(encoding="utf-8")))
    for number, group in enumerate(groups, start=1):
        (work / f"requirements-{number}.txt").write_text(
            "".join(f"{name}=={version}\n" for name, version in sorted(group.items())),
            encoding="utf-8",
        )
    print(len(groups))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
