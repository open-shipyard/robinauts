# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The one way text from a request is written to a log.

A log is a file of lines, and a line ends at a newline. A path, a header, an
id in a path parameter, a provider's error message: each of them is whatever
somebody sent, and a server writes them percent-decoded, so ``%0A`` in a path
arrives as a real newline. Written out as they are, they do not go **into** a
line -- they make new ones, of whatever shape whoever sent them chose, in the
middle of the record of what the deployment did.

So every log call in ``robinauts.api`` that carries text from a request puts
it through ``shown``:

- **escaped**, with ``ascii()``, which quotes the text and writes every
  control character, every newline and everything outside ASCII as an escape.
  Nothing that comes out of it can end a line or start one;
- **bounded**, because the length is the sender's choice too, and a log that
  can be filled a megabyte at a time is a log that can be made to lose what
  came before.

The body of a response is the other half of the same rule, and it is stricter:
it repeats nothing from the request at all (``robinauts.api.errors``). This is
for the log, where the particulars are the point.
"""

from __future__ import annotations

MAX_SHOWN = 120
"""How much of a value from outside a log line repeats.

Enough to recognise a path or an origin; far too little to bury the line
before it. What is dropped is counted, so a line never quietly says less than
it means to.
"""


def shown(value: object, *, most: int = MAX_SHOWN) -> str:
    """``value`` as a log line may carry it: quoted, escaped and bounded.

    The clipping happens **before** the escaping, so the bound is on the text
    that arrived rather than on its spelling; an escape is up to six
    characters, so what comes out is longer than ``most`` and still bounded by
    it. What was dropped is counted rather than left to be guessed at.
    """
    text = value if isinstance(value, str) else str(value)
    clipped = text[:most]
    escaped = ascii(clipped)
    if len(clipped) == len(text):
        return escaped
    return f"{escaped}+{len(text) - len(clipped)} more"
