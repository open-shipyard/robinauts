# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The security headers on the interface, the API and their refusals."""

from __future__ import annotations

from pathlib import Path

import httpx

from robinauts.controller.composition import compose
from robinauts.controller.contract.domain import Config, StorageConfig, StorageKind
from robinauts.web.app import create_app
from robinauts.web.headers import SECURITY_HEADERS
from util.aio import asyncio_test


@asyncio_test
async def test_every_answer_carries_the_security_headers(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>Robinauts</title>")
    composed = compose(Config(), storage=StorageConfig(StorageKind.IN_MEMORY), secret_for={}.get)
    app = create_app(composed, sign_in=None, secret_for={}.get, ui_dir=tmp_path)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as http:
            answers = {
                "page": await http.get("/ui/"),
                "missing file": await http.get("/ui/assets/nothing.js"),
                "write to the interface": await http.post("/ui/"),
                "api": await http.get("/api/conversations"),
                "refused": await http.get("/api/conversations", headers={"host": "evil.example"}),
                "refused page": await http.get("/ui/", headers={"host": "evil.example"}),
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
