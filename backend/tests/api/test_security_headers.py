# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The security headers on the interface, the API and their refusals."""

from __future__ import annotations

import httpx

from robinauts.web.headers import SECURITY_HEADERS
from util.controller_db import requires_postgres

pytestmark = requires_postgres


def test_every_answer_carries_the_security_headers(api: httpx.Client) -> None:
    answers = {
        "page": api.get("/ui/"),
        "missing file": api.get("/ui/assets/nothing.js"),
        "write to the interface": api.post("/ui/"),
        "api": api.get("/api/conversations"),
        "refused": api.get("/api/conversations", headers={"host": "evil.example"}),
        "refused page": api.get("/ui/", headers={"host": "evil.example"}),
    }
    statuses = {name: answer.status_code for name, answer in answers.items()}
    assert statuses == {
        "page": 200,
        "missing file": 404,
        "write to the interface": 405,
        "api": 200,
        "refused": 403,
        "refused page": 403,
    }
    for name, answer in answers.items():
        for header, value in SECURITY_HEADERS:
            assert answer.headers.get_list(header) == [value], (name, header)
    assert "frame-ancestors 'none'" in answers["page"].headers["content-security-policy"]
