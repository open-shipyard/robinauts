# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
#
# The versions of the tools that are pinned by hand: uv, which CI installs,
# and the isolated tools the checks run with `uvx`. None of them is in
# backend/uv.lock and Dependabot sees none of them, so this file is the one
# place they are bumped -- read the release notes, run the checks, and say so
# in the pull request. DEPENDENCIES.md explains why the `uvx` tools stay
# outside the lock.
#
# Sourced by the check scripts; it defines variables and runs nothing.

# uv itself, which CI installs; locally you use whatever you have. Read into
# the workflow's environment before setup-uv runs, so the version CI builds
# with is written down once, here.
UV_VERSION=0.12.6

# reuse lint: every file in the tree states its licence.
REUSE_VERSION=6.2.0

# pip-audit: known vulnerabilities in the locked set.
PIP_AUDIT_VERSION=2.10.1
