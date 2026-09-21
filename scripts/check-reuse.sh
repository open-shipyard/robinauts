#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# Every file in the tree has a stated licence. Further arguments are passed on
# to reuse.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$root/scripts/tool-versions.sh"
cd "$root"

uvx "reuse@$REUSE_VERSION" lint "$@"
