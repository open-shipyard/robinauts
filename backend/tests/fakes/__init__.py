# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""In-memory implementations of every port, for the tests of the application.

They are the ports' own abstract base classes, implemented
(``docs/layout.md``, "Conventions"): a fake that drifted from a port would
fail to instantiate. The credential store and the conversation store pass
the same contract suites as the real ones will (``tests/contracts/``).
"""

from fakes.clock import START, FakeClock
from fakes.conversations import MemoryConversationStore
from fakes.credentials import MemoryCredentialStore
from fakes.identity_provider import Answer, ScriptedIdentityProvider, discovery_for
from fakes.ids import CountingIdSource
from fakes.secrets import LENGTH, CountingSecretSource, StuntedSecretSource

__all__ = [
    "LENGTH",
    "START",
    "Answer",
    "CountingIdSource",
    "CountingSecretSource",
    "FakeClock",
    "MemoryConversationStore",
    "MemoryCredentialStore",
    "ScriptedIdentityProvider",
    "StuntedSecretSource",
    "discovery_for",
]
