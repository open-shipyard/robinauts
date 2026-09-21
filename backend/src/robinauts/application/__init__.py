# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Control flow and business rules: what the platform does, in order.

Depends on ``ports``, ``core`` and ``domain`` (``docs/layout.md``). It is
handed every port implementation and constructs none.

What it keeps in the process is only what ``docs/layout.md`` allows it to: a
``SignIn`` holds the discovery documents it has checked and the one fetch of
each that is in flight, the reading of the monotonic clock at which it last
swept expired rows, and a count of the sweeps that failed. A cache, a
scheduling hint and a diagnostic. Losing any of them costs one fetch, one
extra sweep, or a number nobody read; nothing a sign-in is decided by is in
them, and a second process may disagree about all three without a single
answer changing.

The rules the flow applies are ``core``'s, and so is everything in it that is
input and output alone: the allow list, the claims, the URLs, what a secret
must be, and the authorization request itself.
"""

from robinauts.application.conversations import (
    DEFAULT_PAGE,
    Conversations,
    OpenedConversation,
    owner_of,
)
from robinauts.application.local import LocalAccess
from robinauts.application.sign_in import (
    PENDING_LOGIN_LIFE,
    SWEEP_SECONDS,
    BegunSignIn,
    OpenedSession,
    ProviderEndpoints,
    SignIn,
)
from robinauts.application.turns import (
    DEFAULT_HISTORY_CHARS,
    DEFAULT_TURN_SECONDS,
    NO_ANSWER,
    TIMED_OUT,
    UNFINISHED_ANSWER,
    StartedTurn,
    Turns,
)

__all__ = [
    "DEFAULT_HISTORY_CHARS",
    "DEFAULT_PAGE",
    "DEFAULT_TURN_SECONDS",
    "NO_ANSWER",
    "PENDING_LOGIN_LIFE",
    "SWEEP_SECONDS",
    "TIMED_OUT",
    "UNFINISHED_ANSWER",
    "BegunSignIn",
    "Conversations",
    "LocalAccess",
    "OpenedConversation",
    "OpenedSession",
    "ProviderEndpoints",
    "SignIn",
    "StartedTurn",
    "Turns",
    "owner_of",
]
