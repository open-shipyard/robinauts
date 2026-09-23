// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { json, refusal, stubFetch } from "../test/api";
import {
  conversation,
  id,
  madeBy,
  message,
  opened,
  RUN,
} from "../test/conversations";
import { branchOf, shownTitle, textOf, useConversation } from "./conversation";

/**
 * A tree with a branch beside the one that is open.
 *
 *     root ── answer-a ── follow-up ── answer-b   <- the leaf
 *          └─ answer-c
 *
 * `answer-c` is a regeneration of the first answer: a sibling of `answer-a`
 * under the same question (docs/specs/conversations.md, "Branches").
 */
const TREE = [
  message("root", null, "user", "What is a robin?"),
  message("answer-a", "root", "assistant", "A bird.", madeBy()),
  message("answer-c", "root", "assistant", "A small bird.", madeBy()),
  message("follow-up", "answer-a", "user", "What does it eat?"),
  message("answer-b", "follow-up", "assistant", "Worms.", madeBy()),
];

test("a branch is the leaf's ancestry, oldest first, and nothing else", () => {
  expect(branchOf(TREE, "answer-b").map((one) => one.id)).toEqual([
    "root",
    "answer-a",
    "follow-up",
    "answer-b",
  ]);
  // The other branch, from its own leaf.
  expect(branchOf(TREE, "answer-c").map((one) => one.id)).toEqual([
    "root",
    "answer-c",
  ]);
});

test("a conversation with nothing in it has no branch", () => {
  expect(branchOf([], null)).toEqual([]);
  expect(branchOf(TREE, null)).toEqual([]);
});

test("rows that are not a tree end the walk rather than hanging", () => {
  // Neither can be written by the backend; an interface that looped for ever
  // over one would be worse than one that shows a short branch.
  expect(branchOf(TREE, "nobody")).toEqual([]);
  const cycle = [
    message("a", "b", "user", "one"),
    message("b", "a", "user", "two"),
  ];
  expect(branchOf(cycle, "a").map((one) => one.id)).toEqual(["b", "a"]);
});

test("a message says its text parts, joined", () => {
  expect(textOf(message("m", null, "user", "Hello"))).toBe("Hello");
  expect(
    textOf({
      ...message("m", null, "assistant", ""),
      parts: [
        { kind: "text", text: "A long " },
        { kind: "text", text: "answer." },
      ],
    }),
  ).toBe("A long answer.");
});

test("a conversation nobody named is shown as Untitled", () => {
  expect(shownTitle("Named")).toBe("Named");
  expect(shownTitle("")).toBe("Untitled");
  expect(shownTitle("   ")).toBe("Untitled");
});

test("opening a conversation gives its branch and what its run is doing", async () => {
  stubFetch(() =>
    json(
      opened(conversation(1, "First"), TREE, "answer-b", {
        run_id: RUN,
        resume: { after: 12, follows: "answer-b" },
      }),
    ),
  );
  const { result } = renderHook(() => useConversation(id(1)));
  expect(result.current.state.status).toBe("loading");

  await waitFor(() => {
    expect(result.current.state.status).toBe("loaded");
  });
  const { state } = result.current;
  if (state.status !== "loaded") throw new Error("it did not load");
  expect(state.conversation.title).toBe("First");
  expect(state.branch.map((one) => one.id)).toEqual([
    "root",
    "answer-a",
    "follow-up",
    "answer-b",
  ]);
  expect(state.runId).toBe(RUN);
  expect(state.resume).toEqual({ after: 12, follows: "answer-b" });
  expect(state.endedBadly).toBeNull();
});

test("a conversation that is not there is one answer, not two", async () => {
  // A conversation of somebody else's and one that never existed answer
  // identically (docs/specs/conversations.md).
  stubFetch(() =>
    refusal(404, "NotFoundError", "there is nothing here of that id"),
  );
  const { result } = renderHook(() => useConversation(id(2)));
  await waitFor(() => {
    expect(result.current.state.status).toBe("failed");
  });
  const { state } = result.current;
  if (state.status !== "failed") throw new Error("it did not fail");
  expect(state.missing).toBe(true);
  expect(state.detail).toBe("there is nothing here of that id");
});

test("any other refusal is a failure that is not a missing conversation", async () => {
  stubFetch(() =>
    refusal(500, "InternalError", "the request could not be served"),
  );
  const { result } = renderHook(() => useConversation(id(3)));
  await waitFor(() => {
    expect(result.current.state.status).toBe("failed");
  });
  const { state } = result.current;
  if (state.status !== "failed") throw new Error("it did not fail");
  expect(state.missing).toBe(false);
});

test("asking for another conversation does not show the one before it", async () => {
  const bodies = new Map([
    [id(1), opened(conversation(1, "First"), TREE, "answer-b")],
    [id(2), opened(conversation(2, "Second"), [], null)],
  ]);
  stubFetch((call) => {
    const wanted = call.url.slice("/api/conversations/".length);
    return json(bodies.get(wanted));
  });

  const { result, rerender } = renderHook(
    ({ which }: { which: string }) => useConversation(which),
    { initialProps: { which: id(1) } },
  );
  await waitFor(() => {
    expect(result.current.state.status).toBe("loaded");
  });

  rerender({ which: id(2) });
  // Not the first conversation for a frame, and not the second before it
  // has arrived: nothing.
  expect(result.current.state.status).toBe("loading");
  await waitFor(() => {
    expect(result.current.state.status).toBe("loaded");
  });
  const { state } = result.current;
  if (state.status !== "loaded") throw new Error("it did not load");
  expect(state.conversation.title).toBe("Second");
});

test("reloading keeps what is on the screen while it asks again", async () => {
  let title = "First";
  const fetch = stubFetch(() =>
    json(opened(conversation(1, title), TREE, "answer-b")),
  );
  const { result } = renderHook(() => useConversation(id(1)));
  await waitFor(() => {
    expect(result.current.state.status).toBe("loaded");
  });

  title = "Renamed";
  result.current.reload();
  // Still the conversation that is up, rather than a blank "Loading…".
  expect(result.current.state.status).toBe("loaded");
  await waitFor(() => {
    const { state } = result.current;
    expect(state.status === "loaded" && state.conversation.title).toBe(
      "Renamed",
    );
  });
  expect(fetch.mock.calls).toHaveLength(2);
});

test("a read that was dropped does not publish what arrived after it", async () => {
  // The body of an abandoned read arrives all the same -- `fetch` resolved
  // before the abort -- and publishing it would put a conversation back on
  // the screen that nothing asked for.
  let stale: ((answer: Response) => void) | null = null;
  const fetch = vi.fn<typeof globalThis.fetch>(() => {
    if (stale === null) {
      return new Promise<Response>((settle) => {
        stale = settle;
      });
    }
    return Promise.resolve(
      json(opened(conversation(1, "The newer read"), [], null)),
    );
  });
  vi.stubGlobal("fetch", fetch);

  const { result } = renderHook(() => useConversation(id(1)));
  await act(async () => {
    // Asking again drops the read in the air.
    result.current.reload();
    await Promise.resolve();
  });
  await waitFor(() => {
    expect(result.current.state.status).toBe("loaded");
  });

  await act(async () => {
    stale?.(
      json(opened(conversation(1, "The dropped read"), TREE, "answer-b")),
    );
    await Promise.resolve();
  });

  const { state } = result.current;
  if (state.status !== "loaded") throw new Error("it did not load");
  expect(state.conversation.title).toBe("The newer read");
  expect(state.branch).toEqual([]);
});
