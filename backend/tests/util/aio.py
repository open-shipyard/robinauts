# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""Running an ``async`` test, without an asyncio plugin.

The suite has no ``pytest-asyncio``: the backend's development dependencies
are the four of ``pyproject.toml``, and a test runner is not worth a fifth.
``@asyncio_test`` turns an ``async def`` test into an ordinary one that runs it
on a fresh event loop, which is all the plugin would do here.

``functools.wraps`` keeps the signature, so pytest still sees the fixtures the
test asks for.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any


def asyncio_test[T](test: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., T]:
    """Run this ``async`` test to completion on an event loop of its own."""

    @functools.wraps(test)
    def run(*args: Any, **kwargs: Any) -> T:
        return asyncio.run(test(*args, **kwargs))

    return run
