# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The service, started as its command and spoken to over HTTP, as a host would."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

TOKEN_A = "token-of-principal-a"
TOKEN_B = "token-of-principal-b"
TOOLS = {"list_sources"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _config(folder: Path, port: int) -> Path:
    path = folder / "sql-analytics.toml"
    path.write_text(
        f"""
[server]
port = {port}
allowed_hosts = ["sql.internal.example"]

[store]
path = "{folder / "store"}"

[principals.a]
token_env = "TEST_TOKEN_A"
sources = ["lite", "demo"]

[principals.b]
token_env = "TEST_TOKEN_B"
sources = ["warehouse"]

[sources.demo]
kind = "duckdb"
description = "The demo data."
path = "{folder / "demo.duckdb"}"

[sources.lite]
kind = "sqlite"
description = "A small SQLite file."
path = "{folder / "lite.db"}"

[sources.warehouse]
kind = "postgres"
description = "The warehouse."
dsn_env = "TEST_WAREHOUSE_DSN"
schema = "analytics"
""",
        encoding="utf-8",
    )
    return path


ENVIRONMENT = {
    "TEST_TOKEN_A": TOKEN_A,
    "TEST_TOKEN_B": TOKEN_B,
    "TEST_WAREHOUSE_DSN": "postgresql://reader:hunter2-secret@db.internal/warehouse",
}


def _command(*arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "sql_analytics", *arguments],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=60,
    )


class Client:
    """Just enough of an MCP client: JSON-RPC over POST with a bearer token."""

    def __init__(self, http: httpx.Client, url: str, token: str | None) -> None:
        self.url = url
        self.http = http
        self.headers = {"Accept": "application/json, text/event-stream"}
        if token is not None:
            self.headers["Authorization"] = f"Bearer {token}"
        self.next_id = 1

    def post(self, message: dict, **headers: str) -> httpx.Response:
        return self.http.post(self.url, json=message, headers={**self.headers, **headers})

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        response = self.post(message)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["id"] == self.next_id
        return body

    def call(self, name: str, arguments: dict | None = None) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})["result"]


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    port = _free_port()
    config = _config(tmp_path_factory.mktemp("service"), port)
    process = subprocess.Popen(
        [sys.executable, "-m", "sql_analytics", "serve", "--config", str(config)],
        env={**os.environ, **ENVIRONMENT},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            break
        except OSError:
            if process.poll() is not None or time.monotonic() > deadline:
                process.kill()
                pytest.fail(f"the service did not start: {process.stderr.read().decode()}")
            time.sleep(0.1)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=10)
        log = process.stderr.read().decode()
        process.stderr.close()
        # Nothing the service wrote names a token or a database secret.
        for secret in ENVIRONMENT.values():
            assert secret not in log


@pytest.fixture(scope="module")
def http():
    with httpx.Client(timeout=10) as client:
        yield client


def _client(service: str, http: httpx.Client, token: str | None) -> Client:
    client = Client(http, f"{service}/mcp", token)
    initialized = client.request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    )
    assert initialized["result"]["serverInfo"]["name"] == "sql-analytics"
    assert "list_sources" in initialized["result"]["instructions"]
    return client


def test_healthz_answers_without_a_token(service):
    response = httpx.get(f"{service}/healthz")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


@pytest.mark.parametrize("token", [None, "wrong-token-of-sixteen", TOKEN_A[:-1]])
def test_mcp_refuses_a_request_without_a_known_token(service, http, token):
    client = Client(http, f"{service}/mcp", token)
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    response = client.post(message)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": "a valid bearer token is required"}


@pytest.mark.parametrize("path", ["/healthz", "/mcp"])
def test_a_host_that_is_not_allowed_is_refused_on_every_path(service, path):
    response = httpx.post(
        f"{service}{path}",
        headers={"Host": "attacker.example", "Authorization": f"Bearer {TOKEN_A}"},
    )
    assert response.status_code == 400


def test_an_allowed_host_is_let_through(service):
    response = httpx.get(f"{service}/healthz", headers={"Host": "sql.internal.example:443"})
    assert response.status_code == 200


def test_tools_list_names_list_sources_for_the_model(service, http):
    tools = {
        tool["name"]: tool
        for tool in _client(service, http, TOKEN_A).request("tools/list")["result"]["tools"]
    }
    assert set(tools) == TOOLS
    tool = tools["list_sources"]
    assert tool["_meta"]["ui"] == {"visibility": ["model"]}
    assert "resourceUri" not in tool["_meta"]["ui"]
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["inputSchema"].get("required", []) == []
    assert set(tool["outputSchema"]["properties"]) == {"sources"}


def test_each_principal_lists_its_own_sources_alone(service, http):
    a = _client(service, http, TOKEN_A).call("list_sources")
    assert a["isError"] is False
    assert a["structuredContent"] == {
        "sources": [
            {
                "id": "lite",
                "kind": "sqlite",
                "description": "A small SQLite file.",
                "default_schema": "main",
            },
            {
                "id": "demo",
                "kind": "duckdb",
                "description": "The demo data.",
                "default_schema": "main",
            },
        ]
    }
    assert a["content"][0]["text"] == (
        "2 source(s):\n"
        "- lite (sqlite, default schema main): A small SQLite file.\n"
        "- demo (duckdb, default schema main): The demo data."
    )
    b = _client(service, http, TOKEN_B).call("list_sources")
    assert [source["id"] for source in b["structuredContent"]["sources"]] == ["warehouse"]
    # A source's address and credentials are never part of an answer.
    for answer in (a, b):
        text = str(answer)
        for fragment in ("path", ".db", ".duckdb"):
            assert fragment not in text
        for secret in ENVIRONMENT.values():
            assert secret not in text


def test_check_says_the_configuration_can_be_used(tmp_path):
    config = _config(tmp_path, _free_port())
    result = _command("check", "--config", str(config), env=ENVIRONMENT)
    assert result.returncode == 0, result.stderr
    assert "2 principal(s), 3 source(s)" in result.stdout


def test_a_configuration_that_cannot_be_used_stops_the_start(tmp_path):
    config = _config(tmp_path, _free_port())
    environment = {**ENVIRONMENT, "TEST_TOKEN_B": "", "TEST_WAREHOUSE_DSN": ""}
    for command in ("check", "serve"):
        result = _command(command, "--config", str(config), env=environment)
        assert result.returncode == 2
        assert "principals.b.token_env names TEST_TOKEN_B, which is not set" in result.stderr
        assert "sources.warehouse.dsn_env names TEST_WAREHOUSE_DSN" in result.stderr
        assert TOKEN_A not in result.stderr + result.stdout
