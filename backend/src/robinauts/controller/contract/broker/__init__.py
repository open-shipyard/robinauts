# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The turn broker's contract: what a worker is written against, and all it sees of the
controller beside the controller's own records. The port, the records that cross it, and how a
message and an event are written as the documents that cross it. It imports nothing of the
controller but ``controller.contract.domain``, which never imports it."""
