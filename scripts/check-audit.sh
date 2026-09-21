#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# Known vulnerabilities in the whole locked set, runtime and development
# alike. Takes no arguments: what it does with pip-audit's output is not
# something a caller can change and still be checking anything.
set -eu

if [ "$#" -ne 0 ]; then
    printf '%s takes no arguments (got: %s)\n' "$0" "$*" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root/scripts/tool-versions.sh"
cd "$root/backend"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT INT TERM

# The export is a command of its own, not the left-hand side of a pipeline:
# there, a failure -- a stale lock, say -- would leave an empty file behind
# and everything after it would cheerfully audit nothing.
uv export --locked --all-groups --no-emit-project --no-annotate --no-hashes \
    --format requirements.txt >"$work/export.txt"

# Markers are stripped on purpose. Left in, pip-audit evaluates them against
# the runner and quietly audits nothing for, say, a Windows-only package: the
# locked set is what we ship and test with, not what this machine installs.
# What a marker was keeping apart, though, can be two versions of one package,
# which no single requirements file may hold. They are dealt out into as many
# files as it takes, and each file is audited in its turn.
groups=$(python3 "$root/scripts/audit_requirements.py" "$work/export.txt" "$work")

# --disable-pip keeps pip out of it; with pip in the loop, a package that
# happens to be in pip-audit's own environment is skipped, and quietly.
status=0
number=1
while [ "$number" -le "$groups" ]; do
    set +e
    uvx "pip-audit@$PIP_AUDIT_VERSION" --strict --disable-pip --no-deps \
        --format json --requirement "$work/requirements-$number.txt" \
        >"$work/report-$number.json"
    outcome=$?
    set -e
    [ "$outcome" -eq 0 ] || status=$outcome
    number=$((number + 1))
done

# Neither pip-audit's exit code nor --strict says whether every pinned package
# was looked at, so that is checked here: the reports together have to name
# exactly the set that was asked about, version by version.
python3 - "$work" "$groups" "$status" <<'PY'
import json
import re
import sys
from pathlib import Path

work, groups, status = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).strip().lower()


pinned = set()
for number in range(1, groups + 1):
    for line in (work / f"requirements-{number}.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line:
            name, _, version = line.partition("==")
            pinned.add((canonical(name), version.strip()))

# An audit of nothing passes everything, so it is not an audit.
if not pinned:
    print("the export of the locked set pinned no package at all; nothing was audited.")
    raise SystemExit(1)

entries = []
try:
    for number in range(1, groups + 1):
        report = json.loads((work / f"report-{number}.json").read_text(encoding="utf-8"))
        entries.extend(report["dependencies"])
except (OSError, ValueError, KeyError):
    print(f"pip-audit produced no report to read (it exited {status}).")
    raise SystemExit(1) from None

# An entry pip-audit skipped carries a reason instead of a version. It is not
# a package that was looked at, and it is not one to pass over in silence.
skipped = [entry for entry in entries if entry.get("skip_reason") or "version" not in entry]
if skipped:
    print(f"pip-audit skipped {len(skipped)} of the {len(pinned)} packages the lock pins:")
    for entry in skipped:
        reason = entry.get("skip_reason") or "no reason given"
        print(f"  {entry.get('name', 'an unnamed package')}: {reason}")
    raise SystemExit(1)

audited = {(canonical(entry["name"]), entry["version"]) for entry in entries}

if audited != pinned:
    missing = sorted(pinned - audited)
    extra = sorted(audited - pinned)
    print(f"pip-audit audited {len(audited)} of the {len(pinned)} packages the lock pins.")
    for label, pairs in (("not audited", missing), ("not locked", extra)):
        if pairs:
            print(f"  {label}: {', '.join(f'{name} {version}' for name, version in pairs)}")
    raise SystemExit(1)

vulnerable = [entry for entry in entries if entry.get("vulns")]
for entry in vulnerable:
    for vulnerability in entry["vulns"]:
        fixed = ", ".join(vulnerability.get("fix_versions") or []) or "no fix released"
        print(f"{entry['name']} {entry['version']}: {vulnerability['id']} (fix: {fixed})")

if vulnerable:
    print(f"\n{len(vulnerable)} of {len(pinned)} locked packages have known vulnerabilities.")
    raise SystemExit(1)
if status != 0:
    # --strict, or something else pip-audit is unhappy about; whatever it is,
    # it said so above and it is not for this script to overrule.
    print(f"\npip-audit named no vulnerability but exited {status}; read what it printed.")
    raise SystemExit(1)
print(f"All {len(pinned)} locked packages audited; no known vulnerabilities.")
PY
