# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Test-wide settings.

The suite imports the gate scripts from `scripts/`, which is a directory of
programs rather than a package. Compiled bytecode dropped there carries no
licence header, and `reuse lint` reads whatever is in the tree, so nothing
here writes any -- however pytest was started, and not only through
`scripts/check-tests.sh`.

With one exception it cannot reach: this file's own bytecode, which pytest
imports before the line below runs. `scripts/check-tests.sh` sets
`PYTHONDONTWRITEBYTECODE` for that one.
"""

import sys

sys.dont_write_bytecode = True
