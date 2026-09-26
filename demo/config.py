#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The demo's configuration file, written from its template and then read back.

``demo/start.sh`` knows what the deployment is -- which provider, which key
variable, which model -- and ``demo/robinauts.toml.in`` is the shape of it.
This puts the one into the other.

**Why this is not three lines of ``sed``.** The model name is the one value
here that a person types (``ROBINAUTS_DEMO_MODEL``), and ``sed`` would read a
``&``, a ``|`` or a backslash in it as part of its own replacement language: a
value that broke out of the string it was being written into would be a
configuration that says something nobody asked for -- another provider, another
endpoint -- and the platform would start on it without complaint, since it
would be perfectly valid TOML. So the substitution is literal
(``str.replace``), what cannot be written into a TOML string is refused before
anything is written, and the finished file is **parsed back** and every
substituted value compared with what was asked for. A file that does not say
what this was told to say is not left on disk.

It uses the standard library alone (``tomllib``), so it runs under any
interpreter the demo has and needs no environment of its own.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

PLACEHOLDERS = ("@PROVIDER_ID@", "@PROVIDER_KIND@", "@KEY_VARIABLE@", "@MODEL_NAME@")
"""Every name the template holds besides ``@BASE_URL@``, which is a whole line.

Listed so that a template that grew a placeholder nobody fills is caught here,
where it is one message, rather than reaching the parser as a literal ``@`` in
a model name.
"""

BASE_URL = "@BASE_URL@"
"""The template's line for it. A provider kind that has no ``base_url`` is not
a provider with an empty one: the line goes altogether, because ``base_url =
""`` is a start-up refusal and ``base_url`` at all is one for the ``anthropic``
kind (``docs/specs/agents.md``)."""

MODEL = "demo"
"""The id of the one model the template declares, looked for when reading back."""

FORBIDDEN = '"\\'
"""What a value may not hold, because a TOML basic string would not survive it.

Refused rather than escaped: everything written here is an id, a variable name,
a URL or a vendor's name for a model, and not one of them has any business
holding a quote or a backslash. Refusing says which value was wrong; escaping
would quietly accept a model name that cannot be one.
"""


def check(value: str, what: str) -> str:
    """``value`` if it can be written into a TOML string as it stands."""
    if not value:
        raise SystemExit(f"{what} is empty")
    if any(character in FORBIDDEN for character in value):
        raise SystemExit(f"{what} may not hold a quote or a backslash: {value!r}")
    if any(character in value for character in "\n\r\t") or not value.isprintable():
        raise SystemExit(f"{what} is one line of printable text: {value!r}")
    return value


def filled(template: str, values: dict[str, str], base_url: str) -> str:
    """The template with every placeholder replaced, literally.

    ``@BASE_URL@`` is the exception, being a whole line: it becomes the
    assignment when there is an endpoint to write, and the line is dropped when
    there is not.
    """
    lines = []
    for line in template.splitlines(keepends=True):
        if line.strip() == BASE_URL:
            if not base_url:
                continue
            line = line.replace(BASE_URL, f'base_url = "{base_url}"')
        lines.append(line)
    text = "".join(lines)
    for placeholder in PLACEHOLDERS:
        text = text.replace(placeholder, values[placeholder])
    left = [name for name in (*PLACEHOLDERS, BASE_URL) if name in text]
    if left:
        raise SystemExit(f"{', '.join(left)} left in the finished configuration")
    return text


def written(text: str, values: dict[str, str], base_url: str) -> None:
    """Refuse the file unless, read back, it says what it was told to say."""
    tables = tomllib.loads(text)
    provider_id = values["@PROVIDER_ID@"]
    provider = tables["model_providers"][provider_id]
    model = tables["models"][MODEL]
    said = {
        "kind": (provider["kind"], values["@PROVIDER_KIND@"]),
        "api_key_env": (provider["api_key_env"], values["@KEY_VARIABLE@"]),
        "model name": (model["name"], values["@MODEL_NAME@"]),
        "provider": (model["provider"], provider_id),
        "base_url": (provider.get("base_url", ""), base_url),
    }
    wrong = [
        f"{what}: {found!r}, not {wanted!r}"
        for what, (found, wanted) in said.items()
        if found != wanted
    ]
    if wrong:
        raise SystemExit(
            "the configuration does not say what it was told to say: " + "; ".join(wrong)
        )
    if not tables.get("agents"):
        raise SystemExit("the configuration declares no agents")


def main(argv: list[str] | None = None) -> int:
    """Write the configuration. Exits 2 for anything it was asked wrongly."""
    parser = argparse.ArgumentParser(
        prog="demo/config.py", description="the demo's configuration, from its template"
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider-id", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--key-variable", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument(
        "--base-url", default="", help="the endpoint, for a kind that names a protocol"
    )
    arguments = parser.parse_args(argv)

    values = {
        "@PROVIDER_ID@": check(arguments.provider_id, "the provider's id"),
        "@PROVIDER_KIND@": check(arguments.kind, "the provider's kind"),
        "@KEY_VARIABLE@": check(arguments.key_variable, "the key's variable"),
        "@MODEL_NAME@": check(arguments.model_name, "the model's name"),
    }
    base_url = check(arguments.base_url, "the base_url") if arguments.base_url else ""

    text = filled(arguments.template.read_text(encoding="utf-8"), values, base_url)
    written(text, values, base_url)
    arguments.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SystemExit, OSError, tomllib.TOMLDecodeError) as refused:
        # Exit 2 with one line, as demo/start.sh's own refusals do; a code of
        # its own, and never a traceback, for something an operator set.
        if isinstance(refused, SystemExit) and refused.code in (0, None):
            raise
        print(refused, file=sys.stderr)
        raise SystemExit(2) from None
