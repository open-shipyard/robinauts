# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Reading the configuration: the file, the environment, and the start-up check.

Marked ``io``: it writes small files into a temporary directory and reads them
back, which is the whole point -- a reader tested against a string would not
be tested against a file that is a directory, or is not there.

The last test here reads the very example in ``docs/specs/sign-in.md`` through
both halves, ``adapters.read_toml`` and ``core.parse_sign_in_config``, because
a documented example that does not parse is a bug report waiting to be filed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from robinauts.adapters import check_client_secrets, environment, read_toml
from robinauts.core import parse_sign_in_config
from robinauts.domain import ConfigError, Matcher, ProviderConfig, SignInConfig

pytestmark = pytest.mark.io

SPEC = Path(__file__).resolve().parents[3] / "docs" / "specs" / "sign-in.md"

GOOD = """
public_url = "https://robinauts.example.com"
session_hours = 8

[providers.google]
title = "Google"
issuer = "https://accounts.google.com"
client_id = "1234.apps.googleusercontent.com"
client_secret_env = "ROBINAUTS_GOOGLE_SECRET"

[[allow]]
provider = "google"
hosted_domain = "example.com"
"""


def written(directory: Path, text: str, *, name: str = "sign-in.toml") -> Path:
    """``text`` in a file of that name, under ``directory``."""
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_good_file_comes_back_as_the_tables_it_holds(tmp_path: Path) -> None:
    data = read_toml(written(tmp_path, GOOD))

    assert data["public_url"] == "https://robinauts.example.com"
    assert data["session_hours"] == 8
    assert data["providers"]["google"]["client_secret_env"] == "ROBINAUTS_GOOGLE_SECRET"
    assert data["allow"] == [{"provider": "google", "hosted_domain": "example.com"}]


def test_the_reader_judges_nothing(tmp_path: Path) -> None:
    # Adapters read, core validates. A file full of keys nobody knows is a
    # mapping full of keys nobody knows, and `core` is what refuses it.
    data = read_toml(written(tmp_path, "nonsense = true\n[what]\never = 1\n"))

    assert data == {"nonsense": True, "what": {"ever": 1}}


def test_an_empty_file_is_an_empty_mapping(tmp_path: Path) -> None:
    assert read_toml(written(tmp_path, "")) == {}


def test_a_missing_file_names_itself(tmp_path: Path) -> None:
    path = tmp_path / "not-there.toml"

    with pytest.raises(ConfigError) as raised:
        read_toml(path)

    assert raised.value.problems and str(path) in raised.value.problems[0]


def test_a_directory_is_not_a_configuration_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as raised:
        read_toml(tmp_path)

    assert str(tmp_path) in raised.value.problems[0]


def test_a_syntax_error_names_the_file_and_the_line(tmp_path: Path) -> None:
    path = written(
        tmp_path,
        'public_url = "https://robinauts.example.com"\n'
        "session_hours = 8\n"
        "this line is not TOML\n",
    )

    with pytest.raises(ConfigError) as raised:
        read_toml(path)

    (problem,) = raised.value.problems
    assert str(path) in problem
    # tomllib puts the position in its own message, which is why the message
    # is repeated whole rather than summarised.
    assert re.search(r"line 3", problem), problem


def test_a_file_that_is_not_utf_8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "sign-in.toml"
    path.write_bytes(b'title = "\xff\xfe not utf-8"\n')

    with pytest.raises(ConfigError) as raised:
        read_toml(path)

    assert "UTF-8" in raised.value.problems[0]


def test_every_problem_is_one_config_error(tmp_path: Path) -> None:
    # A ConfigError always lists at least one problem; the reader has exactly
    # one to report, because a file either reads or it does not.
    with pytest.raises(ConfigError) as raised:
        read_toml(tmp_path / "nowhere.toml")

    assert len(raised.value.problems) == 1


# The environment, and the start-up check over it.


def test_environment_reads_a_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROBINAUTS_TEST_ONLY_SECRET", "s3cret")

    assert environment("ROBINAUTS_TEST_ONLY_SECRET") == "s3cret"


@pytest.mark.parametrize("value", [None, ""])
def test_an_unset_or_empty_variable_is_no_secret(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    # An exported but empty variable is not a configured secret: answering
    # "yes, and it is the empty string" would turn a start-up failure naming
    # the variable into a sign-in the provider refuses.
    if value is None:
        monkeypatch.delenv("ROBINAUTS_TEST_ONLY_SECRET", raising=False)
    else:
        monkeypatch.setenv("ROBINAUTS_TEST_ONLY_SECRET", value)

    assert environment("ROBINAUTS_TEST_ONLY_SECRET") is None


def provider(name: str) -> ProviderConfig:
    return ProviderConfig(
        id=name,
        title=name.title(),
        issuer=f"https://{name}.example.com",
        client_id=f"{name}-client",
        client_secret_env=f"ROBINAUTS_{name.upper()}_SECRET",
    )


def configured(*names: str) -> SignInConfig:
    return SignInConfig(
        public_url="https://robinauts.example.com",
        providers={name: provider(name) for name in names},
        allow=(),
    )


def test_the_start_up_check_passes_when_every_secret_is_there() -> None:
    held = {"ROBINAUTS_ONE_SECRET": "a", "ROBINAUTS_TWO_SECRET": "b"}

    check_client_secrets(configured("one", "two"), secret_for=held.get)


def test_the_start_up_check_names_every_missing_variable_at_once() -> None:
    # All problems at once (docs/specs/operations.md): an operator with three
    # unset variables fixes a deployment in one pass, not in three restarts.
    held = {"ROBINAUTS_TWO_SECRET": "b"}

    with pytest.raises(ConfigError) as raised:
        check_client_secrets(configured("one", "two", "three"), secret_for=held.get)

    assert len(raised.value.problems) == 2
    assert "ROBINAUTS_ONE_SECRET" in raised.value.problems[0]
    assert "ROBINAUTS_THREE_SECRET" in raised.value.problems[1]


def test_the_start_up_check_reports_the_name_and_never_a_value() -> None:
    held = {"ROBINAUTS_ONE_SECRET": "the-real-secret"}

    with pytest.raises(ConfigError) as raised:
        check_client_secrets(configured("one", "two"), secret_for=held.get)

    assert "the-real-secret" not in str(raised.value)


def test_an_empty_variable_fails_the_start_up_check() -> None:
    with pytest.raises(ConfigError):
        check_client_secrets(configured("one"), secret_for={"ROBINAUTS_ONE_SECRET": ""}.get)


def test_a_deployment_with_no_provider_has_nothing_to_check() -> None:
    check_client_secrets(configured(), secret_for=lambda name: None)


# The two halves together, on the documented example.


def spec_example() -> str:
    """The TOML block of ``docs/specs/sign-in.md``, as it is written there."""
    blocks = re.findall(r"```toml\n(.*?)```", SPEC.read_text(encoding="utf-8"), re.DOTALL)
    assert len(blocks) == 1, f"{SPEC} should hold one TOML example, not {len(blocks)}"
    return blocks[0]


def test_the_example_in_the_specification_reads_and_parses(tmp_path: Path) -> None:
    # Roles are deferred, so the [[admin]] table the spec still shows is
    # refused by `core` on purpose; the rest of the example must parse.
    text = spec_example()
    assert "[[admin]]" in text, "the spec's example no longer shows an admin table"
    without_admin = text.partition("[[admin]]")[0]

    config = parse_sign_in_config(read_toml(written(tmp_path, without_admin)))

    assert config.public_url == "https://robinauts.example.com"
    assert config.session_hours == 12
    assert sorted(config.providers) == ["google", "okta"]
    assert config.provider("okta").groups_claim == "groups"
    assert [entry.matcher for entry in config.allow] == [Matcher.HOSTED_DOMAIN, Matcher.GROUP]


def test_the_example_still_names_the_variables_rather_than_the_secrets(tmp_path: Path) -> None:
    config = parse_sign_in_config(
        read_toml(written(tmp_path, spec_example().partition("[[admin]]")[0]))
    )

    assert config.provider("google").client_secret_env == "ROBINAUTS_GOOGLE_SECRET"
    with pytest.raises(ConfigError) as raised:
        check_client_secrets(config, secret_for=lambda name: None)
    assert len(raised.value.problems) == 2
