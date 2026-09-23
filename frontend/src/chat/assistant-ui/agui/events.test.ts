// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { expect, test } from "vitest";

import { decode, isTerminal } from "./events";

/** That event's JSON, as `ag_ui.encoder` writes it: camel case throughout. */
const json = (body: Record<string, unknown>) => JSON.stringify(body);

test("the vocabulary the backend emits", () => {
  expect(
    decode(json({ type: "RUN_STARTED", threadId: "c", runId: "r" })),
  ).toEqual({ type: "RUN_STARTED", threadId: "c", runId: "r" });
  expect(
    decode(
      json({ type: "TEXT_MESSAGE_START", messageId: "m", role: "assistant" }),
    ),
  ).toEqual({ type: "TEXT_MESSAGE_START", messageId: "m", role: "assistant" });
  expect(
    decode(json({ type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "hi" })),
  ).toEqual({ type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "hi" });
  expect(decode(json({ type: "TEXT_MESSAGE_END", messageId: "m" }))).toEqual({
    type: "TEXT_MESSAGE_END",
    messageId: "m",
  });
  expect(
    decode(
      json({ type: "REASONING_MESSAGE_START", messageId: "m:reasoning:3" }),
    ),
  ).toEqual({ type: "REASONING_MESSAGE_START", messageId: "m:reasoning:3" });
  expect(
    decode(
      json({
        type: "REASONING_MESSAGE_CONTENT",
        messageId: "m:reasoning:3",
        delta: "so",
      }),
    ),
  ).toEqual({
    type: "REASONING_MESSAGE_CONTENT",
    messageId: "m:reasoning:3",
    delta: "so",
  });
  expect(
    decode(json({ type: "REASONING_MESSAGE_END", messageId: "m:reasoning:3" })),
  ).toEqual({ type: "REASONING_MESSAGE_END", messageId: "m:reasoning:3" });
});

test("a run that finished, and one somebody stopped", () => {
  expect(
    decode(json({ type: "RUN_FINISHED", threadId: "c", runId: "r" })),
  ).toEqual({ type: "RUN_FINISHED", runId: "r", cancelled: false });
  // **A cancellation is not a failure** (`docs/specs/wire.md`): the protocol
  // says so with an outcome on the event that says the run finished.
  expect(
    decode(
      json({
        type: "RUN_FINISHED",
        threadId: "c",
        runId: "r",
        outcome: { type: "cancelled" },
      }),
    ),
  ).toEqual({ type: "RUN_FINISHED", runId: "r", cancelled: true });
});

test("a run that ended in an error carries the code to branch on", () => {
  expect(
    decode(
      json({
        type: "RUN_ERROR",
        message: "the agent could not",
        code: "failed",
      }),
    ),
  ).toEqual({
    type: "RUN_ERROR",
    code: "failed",
    message: "the agent could not",
  });
  // AG-UI's own `code` is optional; an error without one is still an error.
  expect(decode(json({ type: "RUN_ERROR", message: "x" }))).toEqual({
    type: "RUN_ERROR",
    code: "",
    message: "x",
  });
});

test("what it does not know, it ignores", () => {
  expect(decode(json({ type: "TOOL_CALL_START", toolCallId: "t" }))).toBeNull();
  expect(decode(json({ type: "STEP_STARTED" }))).toBeNull();
  expect(decode("not json at all")).toBeNull();
  expect(decode("[1, 2]")).toBeNull();
  expect(decode("null")).toBeNull();
  expect(decode(json({ nothing: true }))).toBeNull();
});

test("a known type whose fields are wrong is ignored rather than guessed at", () => {
  expect(
    decode(json({ type: "TEXT_MESSAGE_CONTENT", messageId: "m" })),
  ).toBeNull();
  expect(decode(json({ type: "TEXT_MESSAGE_START", delta: "x" }))).toBeNull();
  expect(decode(json({ type: "RUN_STARTED", runId: "r" }))).toBeNull();
  expect(
    decode(json({ type: "TEXT_MESSAGE_CONTENT", messageId: 3, delta: "x" })),
  ).toBeNull();
});

test("the two that say a run is over, and nothing else", () => {
  expect(
    isTerminal({ type: "RUN_FINISHED", runId: "r", cancelled: false }),
  ).toBe(true);
  expect(isTerminal({ type: "RUN_ERROR", code: "failed", message: "x" })).toBe(
    true,
  );
  expect(isTerminal({ type: "TEXT_MESSAGE_END", messageId: "m" })).toBe(false);
  expect(isTerminal({ type: "RUN_STARTED", threadId: "c", runId: "r" })).toBe(
    false,
  );
});
