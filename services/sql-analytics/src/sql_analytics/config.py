# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors
"""The configuration file: read whole at start-up, checked, and refused with every reason.

An unknown key, a missing key, a value of the wrong type, a source of a kind this version
cannot reach, a principal naming an unknown source, an environment variable that is not set:
each stops the start, and the message names the key and says why. Secrets are named by the
environment variable that holds them (`*_env`), read once here, and kept as `Secret`.

It imports the contract alone.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sql_analytics.contract import Principal, Secret, SourceInfo

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
MIN_TOKEN_LENGTH = 16

# Each kind this version can reach: the keys of its own beyond the common ones, which of them
# are required, and its default schema. The connectors themselves come with milestone M1
# (DuckDB, SQLite) and M3 (PostgreSQL); until then a source is listed, not connected.
KINDS: dict[str, dict[str, Any]] = {
    "duckdb": {"keys": {"path": str}, "required": {"path"}, "schema": "main"},
    "sqlite": {"keys": {"path": str}, "required": {"path"}, "schema": "main"},
    "postgres": {"keys": {"dsn_env": str}, "required": {"dsn_env"}, "schema": "public"},
}
# The kinds the plan names whose extra this version does not declare yet, because their
# dependency trees do not pass the licence gate today (README.md).
NOT_YET = ("snowflake", "bigquery", "spark")
SOURCE_KEYS: dict[str, type] = {
    "kind": str,
    "description": str,
    "schema": str,
    "timeout_seconds": int,
    "max_rows": int,
}


class ConfigError(ValueError):
    """The file cannot be used. `problems` holds one sentence per reason."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class ServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_hosts: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoreConfig:
    path: str
    metadata: str = "sqlite"
    dsn: Secret | None = None


@dataclass(frozen=True)
class ResultsConfig:
    max_rows: int = 100_000
    model_chars: int = 8_000
    page_rows: int = 200
    page_bytes: int = 1_000_000
    ttl_hours: int = 24


@dataclass(frozen=True)
class PrincipalConfig:
    id: str
    token: Secret
    sources: tuple[str, ...]

    def principal(self) -> Principal:
        return Principal(id=self.id, sources=self.sources)


@dataclass(frozen=True)
class SourceConfig:
    id: str
    kind: str
    description: str
    schema: str
    timeout_seconds: int = 30
    max_rows: int | None = None
    settings: Mapping[str, Any] = field(default_factory=dict)
    secrets: Mapping[str, Secret] = field(default_factory=dict)

    def info(self) -> SourceInfo:
        return SourceInfo(
            id=self.id, kind=self.kind, description=self.description, default_schema=self.schema
        )


@dataclass(frozen=True)
class Config:
    server: ServerConfig
    store: StoreConfig
    results: ResultsConfig
    principals: tuple[PrincipalConfig, ...]
    sources: tuple[SourceConfig, ...]


class _Reader:
    """Collects every problem instead of stopping at the first, so one run says them all."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self.environ = environ
        self.problems: list[str] = []

    def table(self, value: object, where: str) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        self.problems.append(f"{where} must be a table")
        return {}

    def keys(self, table: Mapping[str, Any], allowed: Mapping[str, type], where: str) -> None:
        for key in table:
            if key not in allowed:
                self.problems.append(f"{where}.{key} is not a key this version knows")
                continue
            expected = allowed[key]
            value = table[key]
            # A TOML boolean is a Python int; it is not a number here.
            wrong = isinstance(value, bool) and expected is not bool
            if wrong or not isinstance(value, expected):
                self.problems.append(f"{where}.{key} must be {_type_name(expected)}")

    def value(self, table: Mapping[str, Any], key: str, kind: type, default: Any) -> Any:
        """The value when it has the right type (`keys` has already said when it has not)."""
        value = table.get(key, default)
        if isinstance(value, bool) and kind is not bool:
            return default
        return value if isinstance(value, kind) else default

    def positive(self, table: Mapping[str, Any], key: str, default: int | None, where: str) -> Any:
        value = self.value(table, key, int, default)
        if value is not None and value <= 0:
            self.problems.append(f"{where}.{key} must be greater than 0")
            return default
        return value

    def required(self, table: Mapping[str, Any], keys: set[str], where: str) -> None:
        for key in sorted(keys - set(table)):
            self.problems.append(f"{where}.{key} is required")

    def secret(self, table: Mapping[str, Any], key: str, where: str) -> Secret | None:
        name = self.value(table, key, str, None)
        if name is None:
            return None
        if not name:
            self.problems.append(f"{where}.{key} must name an environment variable")
            return None
        value = self.environ.get(name, "")
        if not value:
            self.problems.append(f"{where}.{key} names {name}, which is not set")
            return None
        return Secret(value)


def _type_name(kind: type) -> str:
    return {str: "a string", int: "an integer", list: "a list", dict: "a table"}.get(
        kind, kind.__name__
    )


def _strings(reader: _Reader, value: object, where: str) -> tuple[str, ...]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    reader.problems.append(f"{where} must be a list of strings")
    return ()


def _server(reader: _Reader, table: dict[str, Any]) -> ServerConfig:
    reader.keys(table, {"host": str, "port": int, "allowed_hosts": list}, "server")
    port = reader.value(table, "port", int, DEFAULT_PORT)
    if not 0 < port < 65536:
        reader.problems.append("server.port must be between 1 and 65535")
        port = DEFAULT_PORT
    allowed = table.get("allowed_hosts", [])
    return ServerConfig(
        host=reader.value(table, "host", str, DEFAULT_HOST),
        port=port,
        allowed_hosts=(
            _strings(reader, allowed, "server.allowed_hosts") if isinstance(allowed, list) else ()
        ),
    )


def _store(reader: _Reader, table: dict[str, Any]) -> StoreConfig:
    reader.keys(table, {"metadata": str, "path": str, "dsn_env": str}, "store")
    reader.required(table, {"path"}, "store")
    metadata = reader.value(table, "metadata", str, "sqlite")
    dsn = None
    if metadata == "sqlite":
        if "dsn_env" in table:
            reader.problems.append('store.dsn_env is for metadata = "postgres" alone')
    elif metadata == "postgres":
        reader.required(table, {"dsn_env"}, "store")
        dsn = reader.secret(table, "dsn_env", "store")
    else:
        reader.problems.append('store.metadata must be "sqlite" or "postgres"')
    path = reader.value(table, "path", str, "")
    if "path" in table and not path:
        reader.problems.append("store.path must not be empty")
    return StoreConfig(path=path, metadata=metadata, dsn=dsn)


def _results(reader: _Reader, table: dict[str, Any]) -> ResultsConfig:
    defaults = ResultsConfig()
    names = ("max_rows", "model_chars", "page_rows", "page_bytes", "ttl_hours")
    reader.keys(table, dict.fromkeys(names, int), "results")
    values = {
        name: reader.positive(table, name, getattr(defaults, name), "results") for name in names
    }
    return ResultsConfig(**values)


def _source(reader: _Reader, id: str, table: dict[str, Any]) -> SourceConfig | None:
    where = f"sources.{id}"
    kind = table.get("kind")
    if not isinstance(kind, str):
        reader.problems.append(f"{where}.kind is required, and must be a string")
        return None
    if kind in NOT_YET:
        reader.problems.append(
            f"{where}.kind: {kind!r} is not available in this version; its extra is not "
            "declared yet (see the README)"
        )
        return None
    if kind not in KINDS:
        known = ", ".join(sorted(KINDS))
        reader.problems.append(f"{where}.kind: {kind!r} is not a kind of source ({known})")
        return None
    spec = KINDS[kind]
    reader.keys(table, {**SOURCE_KEYS, **spec["keys"]}, where)
    reader.required(table, {"description", *spec["required"]}, where)
    settings: dict[str, Any] = {}
    secrets: dict[str, Secret] = {}
    for key in spec["keys"]:
        if key not in table:
            continue
        if key.endswith("_env"):
            secret = reader.secret(table, key, where)
            if secret is not None:
                secrets[key.removesuffix("_env")] = secret
        else:
            settings[key] = reader.value(table, key, spec["keys"][key], None)
    return SourceConfig(
        id=id,
        kind=kind,
        description=reader.value(table, "description", str, ""),
        schema=reader.value(table, "schema", str, spec["schema"]),
        timeout_seconds=reader.positive(table, "timeout_seconds", 30, where),
        max_rows=reader.positive(table, "max_rows", None, where),
        settings=settings,
        secrets=secrets,
    )


def _principal(
    reader: _Reader, id: str, table: dict[str, Any], sources: set[str]
) -> PrincipalConfig | None:
    where = f"principals.{id}"
    reader.keys(table, {"token_env": str, "sources": list}, where)
    reader.required(table, {"token_env", "sources"}, where)
    listed = table.get("sources", [])
    named = _strings(reader, listed, f"{where}.sources") if isinstance(listed, list) else ()
    for source in named:
        if source not in sources:
            reader.problems.append(f"{where}.sources names {source!r}, which is not a source")
    if len(set(named)) != len(named):
        reader.problems.append(f"{where}.sources names a source twice")
    token = reader.secret(table, "token_env", where)
    if token is not None and len(token.reveal()) < MIN_TOKEN_LENGTH:
        reader.problems.append(
            f"{where}.token_env holds a token shorter than {MIN_TOKEN_LENGTH} characters"
        )
        token = None
    if token is None:
        return None
    return PrincipalConfig(id=id, token=token, sources=tuple(dict.fromkeys(named)))


def parse(text: str, environ: Mapping[str, str]) -> Config:
    """The configuration in `text`, with its secrets read from `environ`; or ConfigError."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError([f"the file is not valid TOML: {error}"]) from None
    reader = _Reader(environ)
    known = {"server", "store", "results", "principals", "sources"}
    for key in document:
        if key not in known:
            reader.problems.append(f"{key} is not a key this version knows")
    for key in ("store", "principals", "sources"):
        if key not in document:
            reader.problems.append(f"[{key}] is required")

    server = _server(reader, reader.table(document.get("server", {}), "server"))
    store = _store(reader, reader.table(document.get("store", {}), "store"))
    results = _results(reader, reader.table(document.get("results", {}), "results"))

    sources: list[SourceConfig] = []
    source_tables = reader.table(document.get("sources", {}), "sources")
    for id, table in source_tables.items():
        source = _source(reader, id, reader.table(table, f"sources.{id}"))
        if source is not None:
            sources.append(source)

    principals: list[PrincipalConfig] = []
    principal_tables = reader.table(document.get("principals", {}), "principals")
    if "principals" in document and not principal_tables:
        reader.problems.append("principals must name at least one principal")
    for id, table in principal_tables.items():
        principal = _principal(
            reader, id, reader.table(table, f"principals.{id}"), set(source_tables)
        )
        if principal is not None:
            principals.append(principal)
    # Compared once, here, so that a token always maps to one principal.
    tokens = [principal.token.reveal() for principal in principals]
    if len(set(tokens)) != len(tokens):
        reader.problems.append("two principals hold the same token")

    if reader.problems:
        raise ConfigError(reader.problems)
    return Config(
        server=server,
        store=store,
        results=results,
        principals=tuple(principals),
        sources=tuple(sources),
    )


def load(path: Path, environ: Mapping[str, str]) -> Config:
    """The configuration in the file at `path`; or ConfigError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError([f"cannot read {path}: {error.strerror or error}"]) from None
    except UnicodeDecodeError:
        raise ConfigError([f"cannot read {path}: it is not UTF-8"]) from None
    return parse(text, environ)
