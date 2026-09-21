# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The committed OpenAPI document, kept in step with the routes.

``backend/openapi.json`` is a snapshot (``docs/specs/backend.md``): the
interface's typed client is generated from it, so a change to the wire has to
be visible in a diff rather than only in a running server. This fails when the
file and the code disagree, and says what to run.

It compares the file's **text**, not only the document it parses to, because
the file is read by people and by a generator: two files that mean the same
thing and are written differently are still a diff nobody asked for.
"""

from __future__ import annotations

import json
from pathlib import Path

from robinauts.api import openapi_document

SNAPSHOT = Path(__file__).resolve().parents[2] / "openapi.json"

REGENERATE = "scripts/update-openapi.sh"


def written(document: dict[str, object]) -> str:
    """The snapshot's one spelling: two-space indent, keys in order, newline.

    The same spelling ``scripts/update-openapi.sh`` writes. If the two ever
    part company, this test is what says so.
    """
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def test_the_snapshot_is_what_the_code_describes() -> None:
    assert SNAPSHOT.exists(), f"{SNAPSHOT} is missing; run {REGENERATE}"

    assert SNAPSHOT.read_text(encoding="utf-8") == written(
        openapi_document()
    ), f"the routes and {SNAPSHOT.name} disagree; run {REGENERATE} and read the diff"


def test_the_snapshot_describes_the_routes_a_client_is_generated_for() -> None:
    """The browser navigations are out; everything a client calls is in."""
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert sorted(document["paths"]) == ["/auth/logout", "/auth/session", "/health"]
    assert "/auth/login/{provider}" not in document["paths"]
    assert "/auth/callback/{provider}" not in document["paths"]


def test_the_snapshot_names_no_host() -> None:
    """It describes the routes, not a deployment.

    A ``servers`` entry would bake somebody's public URL into a committed
    file, and into every client generated from it.
    """
    document = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    assert "servers" not in document
    assert document["info"]["version"] == "0"
