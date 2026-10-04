# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""A local HTTP server speaking OpenAI's Chat Completions, answering from a model a test injects.

The server is the protocol; the model is a plain class with one method, ``reply``,
so a test picks the behaviour by picking the model:
``FakeLocalGPTServer(EchoModel())``.
"""

from util.fake_openai.echo_model import EchoModel, PoisonEchoModel
from util.fake_openai.server import FakeLocalGPTServer, FakeModel

__all__ = ["EchoModel", "FakeLocalGPTServer", "FakeModel", "PoisonEchoModel"]
