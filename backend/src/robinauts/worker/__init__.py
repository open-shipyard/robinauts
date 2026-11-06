# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The worker: claims queued turns through a ``TurnBroker`` and runs them on the agent engines.

A sibling of ``controller``, not a part of it. Of the controller it imports
``controller.broker.contract`` and ``controller.contract``; of the rest of Robinauts, the
engines' and the tools' contracts. ``controller.composition`` builds it, and alone imports it.
"""
