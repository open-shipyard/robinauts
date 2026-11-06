# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The turn broker over HTTP: what a worker in a process of its own and the server that
spawned it send each other (``wire``). The server serves it (``web/worker_api.py``) and the
worker calls it (``worker/http_turn_broker.py``)."""
