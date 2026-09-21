# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Enforce the dependency matrix from docs/layout.md with import-linter."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_import_contracts() -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "lint-imports")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
