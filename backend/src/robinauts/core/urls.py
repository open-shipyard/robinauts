# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""URLs in one form each, so that comparing two of them means something.

An origin and an issuer are both compared exactly, by us and by the identity
provider: the redirect URI a provider registered, the ``Origin`` header of a
write, and an ID token's ``iss``. They are therefore normalised once, as the
configuration is read, and never again.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from robinauts.domain import InvalidValueError

DEFAULT_PORTS = {"http": 80, "https": 443}
"""The schemes a deployment or an issuer may use, and the port each implies."""

_NAME = re.compile(r"[a-z0-9._-]+")
"""What a host may be spelt with: an A-label domain, or an IPv4 address."""


def normalise_origin(url: str) -> str:
    """``url`` as a browser writes an ``Origin``: ``scheme://host[:port]``.

    ``InvalidValueError`` unless it is an origin and nothing more. ``http`` is
    allowed for a loopback host alone: on any other host nothing would keep
    the cookie, or the authorization code, from the network in between.
    """
    scheme, host, port, path = _split(url)
    if path not in ("", "/"):
        raise InvalidValueError(
            f"{url!r} has a path: robinauts is served at the root of its origin"
        )
    return _joined(scheme, host, port)


def normalise_issuer(url: str) -> str:
    """An issuer in one form: its path kept, without a trailing slash.

    An issuer may have a path -- Okta's authorization servers do -- so only
    the trailing slash goes, which OIDC treats as the same issuer and string
    comparison does not.
    """
    scheme, host, port, path = _split(url)
    return _joined(scheme, host, port) + path.rstrip("/")


def is_loopback(host: str) -> bool:
    """Whether ``host`` names this machine: ``localhost``, or a loopback address."""
    if not isinstance(host, str):
        return False
    host = host.strip("[]").lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _split(url: str) -> tuple[str, str, int | None, str]:
    """``url`` as scheme, host, port and path; ``InvalidValueError`` if it is not one."""
    if not isinstance(url, str):
        raise InvalidValueError(f"{url!r} is not a URL")
    text = url.strip()
    # urlsplit drops tabs and newlines wherever they are, as browsers do, so
    # ``https://exa<tab>mple.com`` would quietly become another host. A URL
    # in a configuration file holds none of that.
    if any(
        character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in text
    ):
        raise InvalidValueError(f"{url!r} holds a space or a control character")
    try:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        hostname = parts.hostname
    except ValueError:
        raise InvalidValueError(f"{url!r} is not a URL") from None
    if scheme not in DEFAULT_PORTS:
        raise InvalidValueError(f"{url!r} is not an http or https URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise InvalidValueError(f"{url!r} holds more than a scheme, host, port and path")
    # Before ``hostname``, which lower-cases: that folds U+212A, the Kelvin
    # sign, onto a plain ``k``, and ``\u212aelvin.example`` would pass for
    # ``kelvin.example``.
    if not parts.netloc.isascii():
        raise InvalidValueError(
            f"{url!r} has a host outside ASCII: write it as its A-label "
            f"(punycode, xn--...) form, which is what a certificate and a "
            f"redirect URI carry"
        )
    host = _host(url, hostname or "")
    try:
        port = parts.port
    except ValueError:
        raise InvalidValueError(f"{url!r} has a port that is not one") from None
    if port == 0:
        raise InvalidValueError(f"{url!r} has port 0, which nothing listens on")
    if scheme == "http" and not is_loopback(host):
        raise InvalidValueError(f"{url!r} is http on a host that is not loopback: use https")
    return scheme, host, port, parts.path


def _host(url: str, hostname: str) -> str:
    """The host in its one form; ``InvalidValueError`` unless it is a host at all.

    The root label's dot is silent in a name -- ``example.com.`` and
    ``example.com`` are one host -- but it is not silent to ``==``, and these
    strings are compared with ``==`` for the rest of their life. An IPv6
    literal has many spellings of one address, so it is written the way
    ``ipaddress`` compresses it. Everything else must be a name spelt with
    what a name is spelt with: a space, a control character, a backslash or a
    letter outside ASCII is not a host, whatever it may look like.
    """
    host = hostname.lower().rstrip(".")
    if not host:
        raise InvalidValueError(f"{url!r} has no host")
    if not host.isascii():
        raise InvalidValueError(
            f"{url!r} has a host outside ASCII: write it as its A-label "
            f"(punycode, xn--...) form, which is what a certificate and a "
            f"redirect URI carry"
        )
    if ":" in host:
        try:
            return ipaddress.ip_address(host).compressed
        except ValueError:
            raise InvalidValueError(f"{url!r} has a host that is not one") from None
    if not _NAME.fullmatch(host):
        raise InvalidValueError(f"{url!r} has a host that is not one")
    return host


def _joined(scheme: str, host: str, port: int | None) -> str:
    """The pieces back together, without a default port, an IPv6 host in brackets."""
    shown = f"[{host}]" if ":" in host else host
    if port is None or port == DEFAULT_PORTS[scheme]:
        return f"{scheme}://{shown}"
    return f"{scheme}://{shown}:{port}"
