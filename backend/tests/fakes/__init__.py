# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""In-memory implementations of every port, for the tests of the application.

They are the ports' own abstract base classes, implemented
(``docs/layout.md``, "Conventions"): a fake that drifted from a port would
fail to instantiate. The credential store passes the same contract suite as
the real one (``tests/contracts/credential_store.py``).
"""

from fakes.clock import START, FakeClock
from fakes.credentials import MemoryCredentialStore
from fakes.identity_provider import Answer, ScriptedIdentityProvider, discovery_for
from fakes.secrets import LENGTH, CountingSecretSource, StuntedSecretSource

__all__ = [
    "LENGTH",
    "START",
    "Answer",
    "CountingSecretSource",
    "FakeClock",
    "MemoryCredentialStore",
    "ScriptedIdentityProvider",
    "StuntedSecretSource",
    "discovery_for",
]
