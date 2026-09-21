# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Reading the configuration: the file, and the environment the secrets are in.

**Adapters read, core validates** (``docs/layout.md``). Everything here hands
back raw data or raises: ``read_toml`` returns whatever tables were in the
file, and ``robinauts.core.parse_sign_in_config`` -- which this may not import
-- is what decides whether they describe a deployment. The composition root
calls the two in turn.

Reading is where a file can be missing, unreadable or misspelt, and each of
those is a ``ConfigError`` naming the file, because an operator reading a
start-up failure has a path to look at and nothing else. TOML puts the line
and the column of a syntax error in its own message, so the message is
repeated whole.

``environment`` and ``check_client_secrets`` are the other half. A secret is
never in the file: a provider names the environment variable its client secret
is read from (``docs/specs/operations.md``), and this is the layer that may
touch the environment. The check exists so that a deployment with three
providers and three unset variables is told about all three at once, at
start-up, rather than one at a time as people try to sign in.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from robinauts.domain import ConfigError, SignInConfig

SecretLookup = Callable[[str], str | None]
"""How a secret is asked for: given a variable's name, its value or ``None``.

A callable rather than a direct read of ``os.environ``, so that a test scripts
what the environment holds without setting a real variable -- and so that a
later deployment may take its secrets from somewhere else entirely without
anything above this line changing.
"""


def read_toml(path: str | os.PathLike[str]) -> Mapping[str, Any]:
    """The tables in the TOML file at ``path``, unexamined.

    ``ConfigError`` when the file cannot be read or is not TOML, naming the
    path in every case and the line in a syntax error. Nothing else is judged
    here: an empty file is an empty mapping, and unknown keys, missing values
    and everything else are ``core``'s to refuse.
    """
    where = _named(path)
    try:
        with open(path, "rb") as file:
            return tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        # tomllib's message already ends in "(at line L, column C)", which is
        # the whole reason it is repeated rather than summarised.
        raise ConfigError([f"{where}: not valid TOML: {exc}"]) from exc
    except OSError as exc:
        raise ConfigError([f"{where}: {exc.strerror or type(exc).__name__}"]) from exc
    except UnicodeDecodeError as exc:
        # TOML is UTF-8 by definition; a file that is not is not a TOML file.
        raise ConfigError([f"{where}: not valid UTF-8, which TOML must be: {exc.reason}"]) from exc


def environment(name: str) -> str | None:
    """The value of the environment variable ``name``; ``None`` if it has none.

    An empty variable counts as unset. A deployment that exports
    ``ROBINAUTS_GOOGLE_SECRET=`` has not configured a secret, and answering
    "yes, it is there, and it is the empty string" would turn a start-up
    failure that names the variable into a sign-in that the provider refuses.
    """
    return os.environ.get(name) or None


def check_client_secrets(config: SignInConfig, *, secret_for: SecretLookup = environment) -> None:
    """Refuse to start when a provider's client secret is not in the environment.

    Every provider is looked at and **every** missing variable is reported at
    once, in one ``ConfigError`` -- never one restart per variable. Only the
    variable's **name** is in the message; its value is a secret and its
    absence is the whole of what is being reported.

    That is all this promises: every missing *variable*, together. It is not
    "every problem a deployment has, together", which is what
    ``docs/specs/operations.md`` asks of start-up, because this cannot see the
    others -- the file did not parse, a table is malformed, a model provider's
    key is missing. Putting those in one list is the composition root's job,
    and it is the one place that has them all. What it has to do: a file that
    does not parse stops there, since there is no configuration to check
    secrets against; but once ``core`` has accepted one, the problems from
    here belong in the same ``ConfigError`` as every other start-up problem it
    can gather, rather than in a second failure after the first is fixed.

    It takes a ``SignInConfig`` -- a domain record that ``core`` has already
    made -- rather than the raw tables, so that this reads the environment and
    judges nothing else.
    """
    problems = [
        f"providers.{provider.id}: the client secret is read from the environment"
        f" variable {provider.client_secret_env}, which is unset or empty"
        for provider in config.providers.values()
        if not secret_for(provider.client_secret_env)
    ]
    if problems:
        raise ConfigError(problems)


def _named(path: str | os.PathLike[str]) -> str:
    """The path as a message names it: the text of it, however it was given."""
    try:
        return str(Path(path))
    except TypeError:  # pragma: no cover -- a caller passing something else
        return repr(path)
