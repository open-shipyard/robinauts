# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The configuration file: what is read from it, and every reason it is refused."""

from __future__ import annotations

import pytest

from sql_analytics.config import ConfigError, load, parse
from sql_analytics.contract import Principal, SourceInfo

TOKEN = "t" * 16
ENVIRON = {"TOKEN_A": TOKEN, "TOKEN_B": "u" * 16, "PG_DSN": "postgresql://reader@db/x"}

MINIMAL = """
[store]
path = "/var/lib/sql-analytics"

[principals.a]
token_env = "TOKEN_A"
sources = ["demo"]

[sources.demo]
kind = "duckdb"
description = "The demo data."
path = "/var/lib/sql-analytics/demo.duckdb"
"""


def test_a_minimal_file_takes_the_defaults():
    config = parse(MINIMAL, ENVIRON)
    assert (config.server.host, config.server.port, config.server.allowed_hosts) == (
        "127.0.0.1",
        8770,
        (),
    )
    assert (config.store.path, config.store.metadata, config.store.dsn) == (
        "/var/lib/sql-analytics",
        "sqlite",
        None,
    )
    assert config.results.max_rows == 100_000
    assert config.results.model_chars == 8_000
    [principal] = config.principals
    assert principal.principal() == Principal(id="a", sources=("demo",))
    assert principal.token.reveal() == TOKEN
    [source] = config.sources
    assert source.info() == SourceInfo(
        id="demo", kind="duckdb", description="The demo data.", default_schema="main"
    )
    assert source.settings == {"path": "/var/lib/sql-analytics/demo.duckdb"}
    assert source.timeout_seconds == 30


def test_a_full_file_is_read_whole():
    config = parse(
        """
[server]
host = "0.0.0.0"
port = 9000
allowed_hosts = ["sql.internal.example"]

[store]
metadata = "postgres"
path = "/srv/sql"
dsn_env = "PG_DSN"

[results]
max_rows = 10
model_chars = 20
page_rows = 30
page_bytes = 40
ttl_hours = 50

[principals.a]
token_env = "TOKEN_A"
sources = ["pg", "lite"]

[principals.b]
token_env = "TOKEN_B"
sources = []

[sources.pg]
kind = "postgres"
description = "PostgreSQL."
dsn_env = "PG_DSN"
schema = "realworld"
timeout_seconds = 5
max_rows = 7

[sources.lite]
kind = "sqlite"
description = "SQLite."
path = "/srv/lite.db"
""",
        ENVIRON,
    )
    assert config.server.allowed_hosts == ("sql.internal.example",)
    assert config.store.dsn is not None
    assert config.store.dsn.reveal() == ENVIRON["PG_DSN"]
    assert [config.results.max_rows, config.results.ttl_hours] == [10, 50]
    assert [p.principal() for p in config.principals] == [
        Principal(id="a", sources=("pg", "lite")),
        Principal(id="b", sources=()),
    ]
    pg, lite = config.sources
    assert pg.info().default_schema == "realworld"
    assert (pg.timeout_seconds, pg.max_rows, pg.settings) == (5, 7, {})
    assert pg.secrets["dsn"].reveal() == ENVIRON["PG_DSN"]
    assert lite.info().default_schema == "main"


def test_a_secret_never_shows():
    config = parse(MINIMAL, ENVIRON)
    token = config.principals[0].token
    assert TOKEN not in repr(config)
    assert TOKEN not in f"{token} {token!r}"
    assert token != config.principals[0].token.__class__(TOKEN)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda t: t + "\n[extra]\n", "extra is not a key this version knows"),
        (lambda t: t.replace("[store]", "[server]\nprt = 1\n[store]"), "server.prt is not a key"),
        (lambda t: t.replace("[store]", "[server]\nport = 0\n[store]"), "server.port must be"),
        (lambda t: t.replace("[store]", '[server]\nport = "x"\n[store]'), "an integer"),
        (lambda t: t.replace("[store]", "[server]\nport = true\n[store]"), "an integer"),
        (
            lambda t: t.replace("[store]", "[server]\nallowed_hosts = [1]\n[store]"),
            "server.allowed_hosts must be a list of strings",
        ),
        (lambda t: t.replace('path = "/var/lib/sql-analytics"\n', ""), "store.path is required"),
        (lambda t: t.replace('path = "/var/lib/sql-analytics"\n', 'path = ""\n'), "empty"),
        (
            lambda t: t.replace("[store]", '[store]\nmetadata = "redis"'),
            'store.metadata must be "sqlite" or "postgres"',
        ),
        (
            lambda t: t.replace("[store]", '[store]\nmetadata = "postgres"'),
            "store.dsn_env is required",
        ),
        (
            lambda t: t.replace("[store]", '[store]\ndsn_env = "PG_DSN"'),
            'store.dsn_env is for metadata = "postgres" alone',
        ),
        (lambda t: t + "\n[results]\npage_rows = -1\n", "results.page_rows must be greater"),
        (lambda t: t.replace("[principals.a]", "[principals.b]\n[principals.a]"), "token_env"),
        (lambda t: t.replace('"TOKEN_A"', '"NOT_SET"'), "names NOT_SET, which is not set"),
        (lambda t: t.replace('"TOKEN_A"', '""'), "must name an environment variable"),
        (lambda t: t.replace('"TOKEN_A"', '"SHORT"'), "shorter than 16 characters"),
        (lambda t: t.replace('["demo"]', '["demo", "other"]'), "'other', which is not a source"),
        (lambda t: t.replace('["demo"]', '["demo", "demo"]'), "names a source twice"),
        (lambda t: t.replace('["demo"]', '"demo"'), "principals.a.sources must be a list"),
        (
            lambda t: t + '\n[principals.b]\ntoken_env = "TOKEN_C"\nsources = []\n',
            "two principals hold the same token",
        ),
        (lambda t: t.replace('kind = "duckdb"', 'kind = "oracle"'), "is not a kind of source"),
        (lambda t: t.replace('kind = "duckdb"', 'kind = "snowflake"'), "not available in this"),
        (lambda t: t.replace('kind = "duckdb"\n', ""), "sources.demo.kind is required"),
        (lambda t: t.replace('description = "The demo data."\n', ""), "description is required"),
        (lambda t: t.replace('path = "/var/lib/sql-analytics/demo.duckdb"', ""), "demo.path is"),
        (lambda t: t + 'dsn_env = "PG_DSN"\n', "sources.demo.dsn_env is not a key"),
        (lambda t: t + "timeout_seconds = 0\n", "sources.demo.timeout_seconds must be greater"),
        (lambda t: t.replace("[sources.demo]\n", "[sources]\ndemo = 1\n[sources.x]\n"), "table"),
        (lambda t: t.replace("[principals.a]", "[principals.x]\n[nope.a]"), "nope is not"),
        (lambda t: t + "\n= nonsense\n", "the file is not valid TOML"),
    ],
)
def test_a_file_that_cannot_be_used_is_refused_with_the_reason(change, problem):
    environ = {**ENVIRON, "TOKEN_C": TOKEN, "SHORT": "short"}
    with pytest.raises(ConfigError) as refused:
        parse(change(MINIMAL), environ)
    assert any(problem in line for line in refused.value.problems), refused.value.problems


@pytest.mark.parametrize("section", ["store", "principals", "sources"])
def test_each_required_section_is_named_when_missing(section):
    with pytest.raises(ConfigError) as refused:
        parse("", ENVIRON)
    assert f"[{section}] is required" in refused.value.problems


def test_every_problem_is_said_at_once():
    text = MINIMAL.replace('"TOKEN_A"', '"NOT_SET"').replace('kind = "duckdb"', 'kind = "oracle"')
    with pytest.raises(ConfigError) as refused:
        parse(text, ENVIRON)
    assert len(refused.value.problems) == 2


def test_a_file_that_cannot_be_read_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load(tmp_path / "missing.toml", ENVIRON)
    (tmp_path / "latin.toml").write_bytes(b"\xff")
    with pytest.raises(ConfigError, match="not UTF-8"):
        load(tmp_path / "latin.toml", ENVIRON)
