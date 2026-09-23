#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The deliverable, end to end: build the wheel, look inside it, install it into
# a virtual environment that has nothing else in it, and run the command.
#
# What it is for is the half that no unit test can reach -- that what a person
# gets from `pip install` is a working Robinauts with its interface and the
# licences of everything it carries (docs/specs/operations.md,
# docs/oss-checklist.md). Everything it builds goes into a temporary directory
# that is removed however this ends, so the checkout is left exactly as it was.
#
# One optional argument: a directory to leave the wheel in, for a caller that
# wants to keep it (CI's `wheel` job uploads it as an artifact).
set -eu

if [ "$#" -gt 1 ]; then
    printf 'usage: %s [directory-to-keep-the-wheel-in]\n' "$0" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

work=$(mktemp -d)
# INT and TERM as well as EXIT: an interrupted check must not leave a wheel and
# a whole virtual environment behind in /tmp.
trap 'rm -rf "$work"' EXIT
trap 'rm -rf "$work"; exit 130' INT
trap 'rm -rf "$work"; exit 143' TERM

if [ "$#" -eq 1 ]; then
    mkdir -p "$1"
    into=$(CDPATH= cd -- "$1" && pwd)
else
    into="$work/dist"
fi

wheel=$("$root/scripts/build-wheel.sh" "$into")
printf 'built %s (%s bytes)\n' "$wheel" "$(wc -c <"$wheel")"

# A virtual environment with nothing in it, so that what answers below can only
# have come out of the wheel.
uv venv "$work/venv" >&2
python="$work/venv/bin/python"
uv pip install --python "$python" "$wheel" >&2

"$python" - "$wheel" <<'PYTHON'
"""Everything a release carries, named one at a time."""

import re
import sys
import zipfile

PACKAGE = "robinauts"
WANTED = (
    f"{PACKAGE}/ui/index.html",
    f"{PACKAGE}/datastore/schema.sql",
)
UI = f"{PACKAGE}/ui/"
ASSETS = f"{UI}assets/"
LICENCES = ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt")
# The same rule the server caches by (robinauts.api.ui.HASHED), asked of what
# the build really emitted: a year of `immutable` is honest only while every
# asset's name carries a digest of its contents.
HASHED = re.compile(r"-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")

with zipfile.ZipFile(sys.argv[1]) as built:
    names = built.namelist()
    tops = {name.split("/", 1)[0] for name in names}
    found = sorted(name for name in tops if name.endswith(".dist-info"))
    if len(found) != 1:
        print(
            f"a wheel holds exactly one .dist-info directory and this one holds"
            f" {len(found)}: {found}. That is a broken archive rather than a missing"
            f" file, so nothing else here was checked.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    (metadata_directory,) = found
    metadata = built.read(f"{metadata_directory}/METADATA").decode("utf-8")

missing = [name for name in WANTED if name not in names]
assets = [name for name in names if name.startswith(ASSETS)]
if not assets:
    missing.append(f"{ASSETS}*")

wrong = [name for name in assets if not HASHED.search(name)]
wrong += [
    name
    for name in names
    if name.startswith(UI) and any(part.startswith(".") for part in name.split("/"))
]
# In the wheel *and* listed in its metadata: the second is the half that is
# usually missed (docs/oss-checklist.md, "Releases").
missing.extend(
    f"{metadata_directory}/licenses/{name}"
    for name in LICENCES
    if f"{metadata_directory}/licenses/{name}" not in names
)
missing.extend(f"License-File: {name}" for name in LICENCES if f"License-File: {name}" not in metadata)

if missing:
    print("the wheel is missing:", file=sys.stderr)
    for name in missing:
        print(f"  {name}", file=sys.stderr)
    raise SystemExit(1)

if wrong:
    print(
        "the wheel carries interface files it should not: an asset whose name holds no"
        " digest of its contents (which the server would cache for a year), or a file"
        " whose name begins with a dot (which is not part of the interface):",
        file=sys.stderr,
    )
    for name in wrong:
        print(f"  {name}", file=sys.stderr)
    raise SystemExit(1)

print(
    f"the wheel carries {len(names)} files: the interface ({len(assets)} hashed assets),"
    f" the schema and every licence file"
)
PYTHON

# The console script, out of the installed wheel and nothing else: it says
# which build this is and which schema it wants, and it needs no database to.
"$work/venv/bin/robinauts" --help >/dev/null
"$work/venv/bin/robinauts" version

printf 'the wheel installs and answers.\n'
