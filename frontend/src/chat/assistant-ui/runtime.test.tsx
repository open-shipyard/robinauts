// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { json, refusal, type Call } from "../../test/api";
import { conversation, id, message, opened } from "../../test/conversations";
import { event, streamed, streamHeaders, writable } from "../../test/stream";
import type { ChatProps } from "../index";
import type { AguiEvent } from "./agui/events";
import { asRepository, LOST_TOUCH, useChat } from "./runtime";
import {
  EMPTY,
  reduce,
  ONE_AT_A_TIME,
  ONE_AT_A_TIME_ANSWER,
  saidFor,
  STOP_DID_NOT_ARRIVE,
  type ChatAction,
  type ChatMessage,
  type ChatState,
} from "./state";

const RUN = "11111111-2222-4333-8444-555555555555";
const CONVERSATION = id(1);
const ANSWER = "aaaaaaaa-0000-4000-8000-000000000001";

// ---------------------------------------------------------------- the reducer

/** Every one of those actions, in order, from nothing. */
function after(...actions: ChatAction[]): ChatState {
  return actions.reduce(reduce, EMPTY);
}

/** One AG-UI event, as the action that carries it. */
const sent = (event: AguiEvent): ChatAction => ({ kind: "event", event });

const asked = { kind: "asked", id: "q", parentId: null, text: "why?" } as const;
const started = {
  kind: "started",
  runId: RUN,
  conversationId: CONVERSATION,
} as const;

/** What a message says, by kind of part. */
function parts(state: ChatState, messageId: string) {
  const found = state.messages.find((each) => each.id === messageId);
  return (found?.parts ?? []).map((part) => [part.kind, part.text]);
}

test("a whole turn, from the run starting to the run finishing", () => {
  const state = after(
    asked,
    started,
    sent({ type: "RUN_STARTED", threadId: CONVERSATION, runId: RUN }),
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({
      type: "TEXT_MESSAGE_CONTENT",
      messageId: ANSWER,
      delta: "Because ",
    }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "it is." }),
    sent({ type: "TEXT_MESSAGE_END", messageId: ANSWER }),
    sent({ type: "RUN_FINISHED", runId: RUN, cancelled: false }),
  );
  expect(state.messages.map((each) => [each.role, each.state])).toEqual([
    ["user", "stored"],
    ["assistant", "stored"],
  ]);
  // The deltas are one text part, in the order they arrived.
  expect(parts(state, ANSWER)).toEqual([["text", "Because it is."]]);
  expect(state.messages[1]?.parentId).toBe("q");
  expect(state.runId).toBeNull();
  expect(state.sending).toBe(false);
  expect(state.leafId).toBe(ANSWER);
  expect(state.ended).toBeNull();
});

test("thinking is collected as its own part, around what was said", () => {
  const thought = `${ANSWER}:reasoning:3`;
  const again = `${ANSWER}:reasoning:9`;
  const state = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "REASONING_MESSAGE_START", messageId: thought }),
    sent({
      type: "REASONING_MESSAGE_CONTENT",
      messageId: thought,
      delta: "so ",
    }),
    sent({
      type: "REASONING_MESSAGE_CONTENT",
      messageId: thought,
      delta: "far",
    }),
    sent({ type: "REASONING_MESSAGE_END", messageId: thought }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "One." }),
    // **A turn may think more than once**, and each stretch is a message of
    // its own on the wire, so it is a part of its own here (`api/agui.py`).
    sent({ type: "REASONING_MESSAGE_START", messageId: again }),
    sent({
      type: "REASONING_MESSAGE_CONTENT",
      messageId: again,
      delta: "more",
    }),
    sent({ type: "REASONING_MESSAGE_END", messageId: again }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: " Two." }),
    sent({ type: "TEXT_MESSAGE_END", messageId: ANSWER }),
  );
  expect(parts(state, ANSWER)).toEqual([
    ["reasoning", "so far"],
    ["text", "One."],
    ["reasoning", "more"],
    ["text", " Two."],
  ]);
  expect(state.thinking).toBeNull();
});

test("the three no-ops a re-attach relies on", () => {
  const thought = `${ANSWER}:reasoning:3`;
  const open = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "half" }),
  );

  // 1. A `*_START` for a message the client already holds open.
  const again = reduce(
    open,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
  );
  expect(again).toBe(open);
  expect(parts(again, ANSWER)).toEqual([["text", "half"]]);

  // ...and one held complete is not opened a second time either: an id
  // stands for one message.
  const stored = after(
    {
      kind: "opened",
      conversationId: CONVERSATION,
      messages: [message(ANSWER, "m1", "assistant", "whole")],
      leafId: ANSWER,
      runId: null,
      resume: null,
      endedBadly: null,
    },
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
  );
  expect(stored.messages).toHaveLength(1);

  // 2. A `*_END` for one it does not hold.
  const ending = reduce(
    open,
    sent({ type: "TEXT_MESSAGE_END", messageId: "never-seen" }),
  );
  expect(ending).toBe(open);
  expect(
    reduce(open, sent({ type: "REASONING_MESSAGE_END", messageId: thought })),
  ).toBe(open);

  // ...and a delta for a message that is complete adds nothing to it: the
  // answer is the store's now, and appending would say it twice.
  const complete = reduce(
    open,
    sent({ type: "TEXT_MESSAGE_END", messageId: ANSWER }),
  );
  expect(
    reduce(
      complete,
      sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "more" }),
    ),
  ).toBe(complete);
  expect(parts(complete, ANSWER)).toEqual([["text", "half"]]);

  // 3. The terminal event of a run it has already seen end -- which is
  //    reachable **only from a re-attach at or past the last position**: a
  //    stream of this chat's own run sets `runId` from the response's
  //    headers before any event arrives, so the first ending always lands
  //    on a run the state knows about.
  const over = reduce(
    open,
    sent({ type: "RUN_FINISHED", runId: RUN, cancelled: false }),
  );
  expect(over.runId).toBeNull();
  expect(
    reduce(over, sent({ type: "RUN_FINISHED", runId: RUN, cancelled: false })),
  ).toBe(over);
  expect(
    reduce(over, sent({ type: "RUN_ERROR", code: "failed", message: "x" })),
  ).toBe(over);
});

test("content for a message whose start went missing still arrives", () => {
  const state = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "rest" }),
  );
  expect(parts(state, ANSWER)).toEqual([["text", "rest"]]);
  expect(state.writing).toBe(ANSWER);
});

test("a run that failed says so on the answer, one sentence per code", () => {
  for (const code of ["failed", "interrupted", "quiet", "gone", "internal"]) {
    const state = after(
      asked,
      started,
      sent({
        type: "TEXT_MESSAGE_START",
        messageId: ANSWER,
        role: "assistant",
      }),
      sent({ type: "RUN_ERROR", code, message: "whatever the backend said" }),
    );
    const failed = state.messages.find((each) => each.id === ANSWER);
    expect(failed?.state).toBe("failed");
    expect(failed?.detail).toBe(saidFor(code));
    // Never the backend's own sentence, and never the run's stored error.
    expect(failed?.detail).not.toContain("whatever");
    expect(state.runId).toBeNull();
  }
  // A code this build does not know still says that something went wrong.
  expect(saidFor("something-new")).toBe("This answer did not finish.");
});

test("a run that failed before it said anything is said by the thread", () => {
  const state = after(
    asked,
    started,
    sent({ type: "RUN_ERROR", code: "failed", message: "x" }),
  );
  expect(state.ended).toBe(saidFor("failed"));
  expect(state.messages.map((each) => each.state)).toEqual(["stored"]);
});

test("a run that ends closes every message still open", () => {
  // One answer at a time is the rule and the platform keeps it, so there is
  // never more than one; a run that ended leaving a second spinning would
  // leave it spinning for ever.
  const second = "aaaaaaaa-0000-4000-8000-000000000002";
  const state = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "one" }),
    // A second announcement without the first having been completed: not
    // something the backend does, and not something to leave open either.
    sent({ type: "TEXT_MESSAGE_START", messageId: second, role: "assistant" }),
    sent({ type: "RUN_ERROR", code: "failed", message: "x" }),
  );
  expect(
    state.messages
      .filter((each) => each.role === "assistant")
      .map((each) => each.state),
  ).toEqual(["failed", "failed"]);
  expect(state.messages.every((each) => each.state !== "running")).toBe(true);
});

test("a cancellation is not a failure", () => {
  const state = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "half" }),
    sent({ type: "RUN_FINISHED", runId: RUN, cancelled: true }),
  );
  const stopped = state.messages.find((each) => each.id === ANSWER);
  expect(stopped?.state).toBe("cancelled");
  // What was produced before it stays (`docs/specs/runs.md`).
  expect(parts(state, ANSWER)).toEqual([["text", "half"]]);
  expect(state.ended).toBe("This answer was stopped before it was finished.");
});

test("opening a conversation is the whole tree, with the branch it reads on", () => {
  const first = message("m1", null, "user", "why?");
  const answer = message("m2", "m1", "assistant", "because");
  const beside = message("m3", "m1", "assistant", "or because");
  const state = after({
    kind: "opened",
    conversationId: CONVERSATION,
    messages: [first, answer, beside],
    leafId: "m3",
    runId: null,
    resume: null,
    endedBadly: null,
  });
  expect(state.messages.map((each) => each.id)).toEqual(["m1", "m2", "m3"]);
  expect(state.messages.map((each) => each.parentId)).toEqual([
    null,
    "m1",
    "m1",
  ]);
  expect(state.leafId).toBe("m3");
  // Nothing is in flight, so the next message hangs under the branch's end.
  expect(state.follows).toBe("m3");
});

test("a conversation with a run going hangs the next answer where it says", () => {
  const state = after({
    kind: "opened",
    conversationId: CONVERSATION,
    messages: [message("m1", null, "user", "why?")],
    leafId: "m1",
    runId: RUN,
    resume: { after: 4, follows: "m1" },
    endedBadly: null,
  });
  expect(state.runId).toBe(RUN);
  expect(state.follows).toBe("m1");
});

test("a refusal never leaves an answer hanging under a message it took away", () => {
  // The shape that took the interface down. A stop whose request failed used
  // to forget the run while its stream carried on writing an answer under
  // the question this chat had put on the screen; the next turn was refused
  // (409), and the refusal took *every* unsent message off -- orphaning that
  // answer, which assistant-ui refuses with an exception.
  const answering = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "half" }),
  );
  const forgotten = { ...answering, runId: null, sending: false };
  const second = reduce(forgotten, {
    kind: "asked",
    id: "unsent:second",
    parentId: ANSWER,
    text: "impatient",
  });
  const refused = reduce(second, { kind: "refused", detail: "no" });

  // The second question comes off; the first, and the answer under it, stay.
  expect(refused.messages.map((each) => each.id)).toEqual(["q", ANSWER]);
  expect(refused.messages[1]?.parentId).toBe("q");
  expect(refused.leafId).toBe(ANSWER);
  // Every parent named is a message that is there.
  for (const item of asRepository(refused.messages, refused.leafId).messages) {
    expect(
      item.parentId === null ||
        refused.messages.some((each) => each.id === item.parentId),
    ).toBe(true);
  }

  // A turn refused before anything hung under its question: that one comes
  // off, and the branch goes back to where it was.
  const only = reduce(after(asked), { kind: "refused", detail: "no" });
  expect(only.messages).toEqual([]);
  expect(only.leafId).toBeNull();

  // **A turn refused on an empty chat.** `before` saved a `follows` of
  // `null`, which is a value and not an absence: the branch goes back to
  // nothing, which is what an empty chat is.
  const first = reduce(
    reduce(EMPTY, {
      kind: "asked",
      id: "unsent:one",
      parentId: null,
      text: "hello",
    }),
    { kind: "refused", detail: "no" },
  );
  expect(first.messages).toEqual([]);
  expect(first.leafId).toBeNull();
  expect(first.follows).toBeNull();

  // And one refused in a conversation whose run had nothing to hang under,
  // where `resume.follows` was `null` too.
  const watching = after({
    kind: "opened",
    conversationId: CONVERSATION,
    messages: [],
    leafId: null,
    runId: RUN,
    resume: { after: 1, follows: null },
    endedBadly: null,
  });
  expect(watching.follows).toBeNull();
  const backAgain = reduce(
    reduce(
      { ...watching, runId: null, sending: false },
      { kind: "asked", id: "unsent:two", parentId: null, text: "hello" },
    ),
    { kind: "refused", detail: "no" },
  );
  expect(backAgain.follows).toBeNull();
  expect(backAgain.leafId).toBeNull();

  // A regeneration refused adds nothing and takes nothing away.
  const stored = after({
    kind: "opened",
    conversationId: CONVERSATION,
    messages: [message("m1", null, "user", "why?")],
    leafId: "m1",
    runId: null,
    resume: null,
    endedBadly: null,
  });
  const again = reduce(reduce(stored, { kind: "again", parentId: "m1" }), {
    kind: "refused",
    detail: "no",
  });
  expect(again.messages.map((each) => each.id)).toEqual(["m1"]);
  expect(again.leafId).toBe("m1");
});

test("the tree handed over never names a message it does not hold", () => {
  // The reducer is written not to produce either of these; what this proves
  // is that a slip is a line in the console and not the whole interface.
  const orphan: ChatMessage[] = [
    {
      id: "a",
      parentId: "gone",
      role: "assistant",
      parts: [{ kind: "text", text: "hello" }],
      state: "stored",
    },
  ];
  const said = vi.spyOn(console, "warn").mockImplementation(() => undefined);
  expect(asRepository(orphan, "a").messages).toEqual([]);
  // A head that is not there falls back to the branch that is.
  const kept: ChatMessage[] = [
    {
      id: "m1",
      parentId: null,
      role: "user",
      parts: [{ kind: "text", text: "why?" }],
      state: "stored",
    },
  ];
  expect(asRepository(kept, "nowhere").headId).toBe("m1");
  expect(asRepository([], "nowhere").headId).toBeUndefined();
  expect(said).toHaveBeenCalled();
  // **Once per shape.** The tree is rebuilt on every delta, so a slip that
  // lasts a whole answer would be a thousand identical lines.
  const already = said.mock.calls.length;
  for (let again = 0; again < 20; again += 1) {
    asRepository(orphan, "a");
    asRepository(kept, "nowhere");
  }
  expect(said.mock.calls.length).toBe(already);
  said.mockRestore();
});

test("a stream that could not be picked up again is said, not hidden", () => {
  const state = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
    sent({ type: "TEXT_MESSAGE_CONTENT", messageId: ANSWER, delta: "half" }),
    { kind: "lost", detail: "the connection went" },
  );
  expect(state.runId).toBeNull();
  expect(state.sending).toBe(false);
  expect(state.ended).toBe("the connection went");
  // **And the answer it was writing is closed.** Nothing is watching the
  // run, so nothing else will ever say that message is over.
  expect(state.messages.every((each) => each.state !== "running")).toBe(true);
  expect(state.messages.find((each) => each.id === ANSWER)?.state).toBe(
    "cancelled",
  );
});

test("an ending is never ignored while an answer is still open", () => {
  // The no-op for "a run this client has already seen end" must not swallow
  // the one event that would close a message still being written.
  const open = after(
    asked,
    started,
    sent({ type: "TEXT_MESSAGE_START", messageId: ANSWER, role: "assistant" }),
  );
  const forgotten = { ...open, runId: null };
  const over = reduce(
    forgotten,
    sent({ type: "RUN_FINISHED", runId: RUN, cancelled: false }),
  );
  expect(over.messages.find((each) => each.id === ANSWER)?.state).toBe(
    "stored",
  );
  // With nothing open it really is a no-op.
  expect(
    reduce(over, sent({ type: "RUN_FINISHED", runId: RUN, cancelled: false })),
  ).toBe(over);
});

test("opening another conversation shows nothing of the one before it", () => {
  const some = after(asked, started);
  const other = reduce(some, { kind: "opening", conversationId: id(2) });
  expect(other.messages).toEqual([]);
  expect(other.loading).toBe(true);
  // Reading the same one again keeps what is on the screen.
  const reread = reduce(
    reduce(some, { kind: "started", runId: RUN, conversationId: id(2) }),
    { kind: "opening", conversationId: id(2) },
  );
  expect(reread.messages).toHaveLength(1);
});

// -------------------------------------------------------------- the whole hook

/** A conversation with one exchange in it, and no run. */
const TREE = [
  message("m1", null, "user", "why?"),
  message("m2", "m1", "assistant", "because"),
];

function stub(answer: (call: Call) => Response | undefined) {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) => {
    const raw = init?.body;
    const call: Call = {
      url: String(input),
      method: (init?.method ?? "GET").toUpperCase(),
      body: typeof raw === "string" ? JSON.parse(raw) : undefined,
    };
    const given = answer(call);
    if (given === undefined) {
      throw new Error(`nothing answers ${call.method} ${call.url}`);
    }
    return Promise.resolve(given);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** The chat, with props a test can change. */
function chatting(props: Partial<ChatProps> = {}) {
  const started = vi.fn();
  const ended = vi.fn();
  const drawn = renderHook((given: ChatProps) => useChat(given), {
    initialProps: {
      conversationId: null,
      agentId: "helper",
      onConversationStarted: started,
      onTurnEnded: ended,
      ...props,
    } satisfies ChatProps,
  });
  return { ...drawn, started, ended };
}

/** Let everything that is already resolved run. */
const settle = () =>
  act(async () => new Promise((done) => setTimeout(done, 0)));

test("a first message begins a conversation and says which one", async () => {
  const fetch = stub((call) => {
    if (call.url === "/api/turns") {
      return streamed(
        [
          event(
            "TEXT_MESSAGE_START",
            { messageId: "m2", role: "assistant" },
            2,
          ),
          event(
            "TEXT_MESSAGE_CONTENT",
            { messageId: "m2", delta: "because" },
            3,
          ),
          event("TEXT_MESSAGE_END", { messageId: "m2" }, 4),
          event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 5),
        ],
        { headers: streamHeaders(RUN, CONVERSATION) },
      );
    }
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    return undefined;
  });
  const { result, started, ended } = chatting();
  await settle();

  await act(async () => {
    await result.current.runtime.thread.append("why?");
  });
  expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({
    agent_id: "helper",
    text: "why?",
  });
  // The id comes from the response's headers, before any event arrives.
  expect(started).toHaveBeenCalledWith(CONVERSATION);

  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
  await settle();
  // The turn is over, so the store is read again: the ids are the server's.
  expect(result.current.state.messages.map((each) => each.id)).toEqual([
    "m1",
    "m2",
  ]);
  expect(ended).toHaveBeenCalled();
});

test("a conversation with a run in flight is attached to at resume.after", async () => {
  const fetch = stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(
        opened(conversation(1), [TREE[0]!], "m1", {
          run_id: RUN,
          resume: { after: 4, follows: "m1" },
        }),
      );
    }
    if (call.url === `/api/runs/${RUN}/events`) {
      return streamed(
        [
          event(
            "TEXT_MESSAGE_START",
            { messageId: "m2", role: "assistant" },
            5,
          ),
          event("TEXT_MESSAGE_CONTENT", { messageId: "m2", delta: "be" }, 6),
        ],
        { headers: streamHeaders(RUN, CONVERSATION) },
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  const attaching = fetch.mock.calls.find(
    ([url]) => String(url) === `/api/runs/${RUN}/events`,
  );
  expect(
    (attaching?.[1]?.headers as Record<string, string>)["last-event-id"],
  ).toBe("4");
  // The message still being produced hangs where the conversation said.
  expect(result.current.state.messages[1]?.parentId).toBe("m1");
});

test("editing is a new message under the parent of the one it replaces", async () => {
  const posts: Call[] = [];
  // Three deep, so the question being edited has a parent that is not the
  // root: an edit hangs under the parent of the message it replaces.
  const deeper = [...TREE, message("m3", "m2", "user", "and then?")];
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), deeper, "m3"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      posts.push(call);
      return streamed(
        [event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 9)],
        { headers: streamHeaders(RUN, CONVERSATION) },
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(3);
  });

  // The question being replaced is `m3`, whose parent is the answer `m2`:
  // an edit hangs under the parent of the message it replaces, and that is
  // not usually the root (`docs/specs/conversations.md`).
  await act(async () => {
    result.current.runtime.thread.append({
      role: "user",
      content: [{ type: "text", text: "and at night?" }],
      parentId: "m2",
      sourceId: "m3",
    });
    await settle();
  });
  expect(posts[0]?.body).toEqual({ text: "and at night?", parent_id: "m2" });

  // The root's own edit still hangs under nothing.
  await act(async () => {
    result.current.runtime.thread.append({
      role: "user",
      content: [{ type: "text", text: "why really?" }],
      parentId: null,
      sourceId: "m1",
    });
    await settle();
  });
  expect(posts[1]?.body).toEqual({ text: "why really?", parent_id: null });
});

test("after a turn that went wrong, asking again replaces the question", async () => {
  // The answer a failed run was producing is in no conversation
  // (`docs/specs/runs.md`), so the branch ends on the question. The format
  // refuses a question under a question, and asking again is how the turn is
  // retried: the new one is a sibling of the old.
  const posts: Call[] = [];
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(
        opened(conversation(1), [TREE[0]!], "m1", {
          ended_badly: {
            run_id: RUN,
            state: "failed",
            ended_at: "2026-09-22T10:00:00Z",
          },
        }),
      );
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      posts.push(call);
      return streamed(
        [event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 9)],
        { headers: streamHeaders(RUN, CONVERSATION) },
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(1);
  });
  await act(async () => {
    result.current.runtime.thread.append("why, really?");
    await settle();
  });
  expect(posts[0]?.body).toEqual({ text: "why, really?", parent_id: null });
});

test("regenerating names the answer to produce again, and sends no message", async () => {
  const posts: Call[] = [];
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      posts.push(call);
      return streamed(
        [event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 9)],
        { headers: streamHeaders(RUN, CONVERSATION) },
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });

  await act(async () => {
    result.current.runtime.thread.startRun({ parentId: "m1", sourceId: "m2" });
    await settle();
  });
  expect(posts[0]?.body).toEqual({ regenerate: "m2" });
});

test("cancelling posts to the run and waits for the stream to say so", async () => {
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  const cancels: Call[] = [];
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    if (call.url.endsWith("/cancel")) {
      cancels.push(call);
      return json({
        id: RUN,
        state: "cancelled",
        started_at: "2026-09-22T10:00:00Z",
        ended_at: "2026-09-22T10:01:00Z",
      });
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    result.current.runtime.thread.append("and then?");
    await settle();
  });
  write(event("TEXT_MESSAGE_START", { messageId: "m4", role: "assistant" }, 2));
  write(event("TEXT_MESSAGE_CONTENT", { messageId: "m4", delta: "half" }, 3));
  await settle();
  expect(result.current.state.runId).toBe(RUN);

  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  expect(cancels[0]?.url).toBe(
    `/api/conversations/${CONVERSATION}/runs/${RUN}/cancel`,
  );
  // Still running: the run's own end is what ends it, and it comes as the
  // stream's `RUN_FINISHED` with the cancelled outcome.
  expect(result.current.state.runId).toBe(RUN);
  write(
    event(
      "RUN_FINISHED",
      { threadId: CONVERSATION, runId: RUN, outcome: { type: "cancelled" } },
      4,
    ),
  );
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("a turn a conversation that is answering refuses is said plainly", async () => {
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      return refusal(
        409,
        "RunAlreadyActiveError",
        `run ${RUN} is running in conversation ${CONVERSATION}; cancel it`,
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    result.current.runtime.thread.append("again");
    await settle();
  });
  // Not the backend's own detail, which names a run for an operator's log.
  expect(result.current.state.ended).toContain("still answering");
  expect(result.current.state.ended).not.toContain(RUN);
});

/**
 * The streams and the reads a lost connection walks through.
 *
 * `answers` is consulted in order for the calls to one url, so a route that
 * has to say one thing and then another can.
 */
function inTurn(answers: Record<string, (() => Response)[]>) {
  const at: Record<string, number> = {};
  return stub((call) => {
    const key = call.url.split("?")[0] ?? "";
    const queue = answers[key];
    if (queue === undefined) return undefined;
    const index = Math.min(at[key] ?? 0, queue.length - 1);
    at[key] = (at[key] ?? 0) + 1;
    return queue[index]?.();
  });
}

const streamOf = (...written: string[]) =>
  streamed(written, { headers: streamHeaders(RUN, CONVERSATION) });

const ANSWERING = {
  run_id: RUN,
  resume: { after: 2, follows: "m1" },
};

test("a stream that is lost reads the store and watches the run again", async () => {
  // The bug this is about: a connection that went used to fall through into a
  // reading whose answer put `run_id` back with nothing watching it, so the
  // thread said it was answering for ever.
  const fetch = inTurn({
    "/api/turns": [
      // Two events and then the connection goes: nothing said the run ended.
      () =>
        streamOf(
          event(
            "TEXT_MESSAGE_START",
            { messageId: "m2", role: "assistant" },
            2,
          ),
          event("TEXT_MESSAGE_CONTENT", { messageId: "m2", delta: "half" }, 3),
        ),
    ],
    [`/api/runs/${RUN}/events`]: [
      // The client's own tries are spent: a refusal is not one it repeats.
      () => refusal(404, "NotFoundError", "no"),
      // Read again, the run is still in flight, and this watch delivers.
      () =>
        streamOf(
          event(
            "TEXT_MESSAGE_START",
            { messageId: "m2", role: "assistant" },
            2,
          ),
          event("TEXT_MESSAGE_CONTENT", { messageId: "m2", delta: "whole" }, 3),
          event("TEXT_MESSAGE_END", { messageId: "m2" }, 4),
          event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 5),
        ),
    ],
    [`/api/conversations/${CONVERSATION}`]: [
      () => json(opened(conversation(1), [TREE[0]!], "m1", ANSWERING)),
      () => json(opened(conversation(1), TREE, "m2")),
    ],
  });
  const { result } = chatting();
  await settle();
  await act(async () => {
    await result.current.runtime.thread.append("why?");
  });
  await waitFor(() => {
    expect(result.current.state.messages.map((each) => each.id)).toEqual([
      "m1",
      "m2",
    ]);
  });
  // The answer is the store's, nothing is running, and nothing was said
  // about a connection that came back.
  expect(result.current.state.runId).toBeNull();
  expect(result.current.state.ended).toBeNull();
  expect(
    fetch.mock.calls.filter(
      ([url]) => String(url) === `/api/runs/${RUN}/events`,
    ),
  ).toHaveLength(2);
});

test("a second loss is said rather than retried for ever", async () => {
  inTurn({
    "/api/turns": [() => streamOf()],
    [`/api/runs/${RUN}/events`]: [() => refusal(404, "NotFoundError", "no")],
    [`/api/conversations/${CONVERSATION}`]: [
      () => json(opened(conversation(1), [TREE[0]!], "m1", ANSWERING)),
    ],
  });
  const { result } = chatting();
  await settle();
  await act(async () => {
    await result.current.runtime.thread.append("why?");
  });
  await waitFor(() => {
    expect(result.current.state.ended).not.toBeNull();
  });
  // In the chat's own words, not the client's.
  expect(result.current.state.ended).toBe(LOST_TOUCH);
  // **Not still answering.** The box works again, and so does the "try
  // again" on the last answer.
  expect(result.current.state.runId).toBeNull();
  expect(result.current.state.sending).toBe(false);
});

test("leaving a conversation stops a turn whose request is still in the air", async () => {
  // A stream is adopted only once its request has been answered, so between
  // the two there is a watcher-to-be; going away must stop that one too, or
  // a stream begins for a page nobody is on.
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  let arrived: (given: Response) => void = () => undefined;
  const fetch = stub((call) => {
    if (call.url.startsWith("/api/conversations/")) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    return undefined;
  });
  const { result, rerender, started, ended } = chatting({
    conversationId: CONVERSATION,
  });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  fetch.mockImplementationOnce(
    () => new Promise<Response>((done) => (arrived = done)),
  );
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });

  // "New chat" while the POST is in the air.
  await act(async () => {
    rerender({
      conversationId: null,
      agentId: "helper",
      onConversationStarted: started,
      onTurnEnded: ended,
    });
    await settle();
  });
  expect(result.current.state.messages).toHaveLength(0);

  await act(async () => {
    arrived(response);
    await settle();
  });
  // The stream that arrived late is not adopted: the empty chat is still
  // the empty chat.
  expect(result.current.state.runId).toBeNull();
  expect(result.current.state.messages).toHaveLength(0);
  write(event("TEXT_MESSAGE_START", { messageId: "m4", role: "assistant" }, 2));
  await settle();
  expect(result.current.state.messages).toHaveLength(0);
  close();
});

test("a first turn that lands after the person moved on does not take them back", async () => {
  // The POST of a first message resolves while somebody is reading another
  // conversation: the shell must not be routed to the new one, and the one
  // they opened must be read rather than skipped as "ours".
  const other = id(2);
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  let arrived: (given: Response) => void = () => undefined;
  const posts: Call[] = [];
  const fetch = stub((call) => {
    if (call.url === `/api/conversations/${other}`) {
      return json(opened(conversation(2, "Elsewhere"), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${other}/turns`) {
      posts.push(call);
      return streamOf(
        event("RUN_FINISHED", { threadId: other, runId: RUN }, 9),
      );
    }
    return undefined;
  });
  const { result, rerender, started, ended } = chatting();
  await settle();
  fetch.mockImplementationOnce(
    () => new Promise<Response>((done) => (arrived = done)),
  );
  await act(async () => {
    void result.current.runtime.thread.append("why?");
    await settle();
  });

  // Another conversation is opened while that POST is in the air.
  await act(async () => {
    rerender({
      conversationId: other,
      agentId: "helper",
      onConversationStarted: started,
      onTurnEnded: ended,
    });
    await settle();
  });
  await act(async () => {
    arrived(response);
    await settle();
  });

  // The shell is not sent anywhere, and the conversation that *was* opened
  // is the one on the screen.
  expect(started).not.toHaveBeenCalled();
  await waitFor(() => {
    expect(result.current.state.conversationId).toBe(other);
  });
  expect(result.current.state.messages.map((each) => each.id)).toEqual([
    "m1",
    "m2",
  ]);
  expect(result.current.state.runId).toBeNull();

  // And the next message goes to the conversation on the screen.
  await act(async () => {
    await result.current.runtime.thread.append("and then?");
  });
  expect(posts.map((each) => each.url)).toEqual([
    `/api/conversations/${other}/turns`,
  ]);
  write(event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 2));
  close();
});

test("a read that finds a run in flight watches it, whichever read it is", async () => {
  // Another tab began a run between this one's turn ending and its read.
  // Taking the id without watching it would leave the thread answering for
  // ever with nothing reading the answer.
  const OTHER_RUN = "22222222-3333-4444-8555-666666666666";
  const fetch = inTurn({
    [`/api/conversations/${CONVERSATION}/turns`]: [
      () =>
        streamOf(
          event(
            "TEXT_MESSAGE_START",
            { messageId: "m4", role: "assistant" },
            2,
          ),
          event("TEXT_MESSAGE_END", { messageId: "m4" }, 3),
          event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 4),
        ),
    ],
    [`/api/conversations/${CONVERSATION}`]: [
      () => json(opened(conversation(1), TREE, "m2")),
      // The read that ends the turn: somebody else is answering now.
      () =>
        json(
          opened(conversation(1), TREE, "m2", {
            run_id: OTHER_RUN,
            resume: { after: 1, follows: "m2" },
          }),
        ),
      () => json(opened(conversation(1), TREE, "m2")),
    ],
    [`/api/runs/${OTHER_RUN}/events`]: [
      () =>
        streamed(
          [
            event(
              "RUN_FINISHED",
              { threadId: CONVERSATION, runId: OTHER_RUN },
              5,
            ),
          ],
          { headers: streamHeaders(OTHER_RUN, CONVERSATION) },
        ),
    ],
  });
  const { result, ended } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    await result.current.runtime.thread.append("and then?");
  });
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
  // The run somebody else began was watched, and its end left nothing
  // answering here.
  expect(
    fetch.mock.calls.filter(
      ([url]) => String(url) === `/api/runs/${OTHER_RUN}/events`,
    ),
  ).toHaveLength(1);
  // And the panel was still told, though the turn's own watcher was stopped
  // to make room for that one.
  expect(ended).toHaveBeenCalled();
});

test("stopping before the first token leaves the box empty", async () => {
  // assistant-ui's own stop takes the trailing question out of its
  // repository and puts its text into the box, taking it back only if the
  // store has published that message again by the next macrotask.
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url.endsWith("/cancel")) return json({ id: RUN });
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  // The run exists and has said nothing yet.
  expect(result.current.state.runId).toBe(RUN);
  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  expect(result.current.runtime.thread.composer.getState().text).toBe("");
  // The question is still in the thread, not back in the box.
  expect(
    result.current.state.messages.some(
      (each) => each.role === "user" && each.parts[0]?.text === "and then?",
    ),
  ).toBe(true);
  write(
    event(
      "RUN_FINISHED",
      { threadId: CONVERSATION, runId: RUN, outcome: { type: "cancelled" } },
      2,
    ),
  );
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("a refused retry leaves the question it was retrying on the branch", async () => {
  // The branch ends on a question nobody answered, so the retry hangs under
  // that question's *parent* (`under`). A refusal must put the branch back
  // where it was and not where the refused message hung.
  inTurn({
    [`/api/conversations/${CONVERSATION}`]: [
      () =>
        json(
          opened(conversation(1), [TREE[0]!], "m1", {
            ended_badly: {
              run_id: RUN,
              state: "failed",
              ended_at: "2026-09-23T10:00:00Z",
            },
          }),
        ),
    ],
    [`/api/conversations/${CONVERSATION}/turns`]: [
      () => refusal(409, "RunAlreadyActiveError", `run ${RUN} is running`),
    ],
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(1);
  });
  await act(async () => {
    await result.current.runtime.thread.append("why, really?");
  });
  // The question that went unanswered is a message the conversation really
  // has: it is still there, and still the end of the branch.
  expect(result.current.state.messages.map((each) => each.id)).toEqual(["m1"]);
  expect(result.current.state.leafId).toBe("m1");
  expect(result.current.state.follows).toBe("m1");
});

test("a stop that does not reach the server leaves the answer alone", async () => {
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url.endsWith("/cancel")) {
      return refusal(500, "InternalError", "something went wrong");
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  write(event("TEXT_MESSAGE_START", { messageId: "m4", role: "assistant" }, 2));
  await settle();

  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  // **Nothing was cancelled**, so the run is still the run and the stream is
  // still watching it: the answer carries on arriving.
  expect(result.current.state.notice).toBe(STOP_DID_NOT_ARRIVE);
  expect(result.current.state.runId).toBe(RUN);
  write(event("TEXT_MESSAGE_CONTENT", { messageId: "m4", delta: "still" }, 3));
  await settle();
  expect(
    result.current.state.messages.find((each) => each.id === "m4")?.parts,
  ).toEqual([{ kind: "text", text: "still" }]);
  write(event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 4));
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("a box holding only whitespace is one the library restored into", async () => {
  // `restoreDraft` refuses only when the box holds something that is not all
  // whitespace, so this is a stop that *did* put the question back -- and
  // one this has to take away again, or the question is in the thread and in
  // the box at once.
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url.endsWith("/cancel")) return json({ id: RUN });
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  await act(async () => {
    result.current.runtime.thread.composer.setText("   ");
    await settle();
  });
  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  expect(result.current.runtime.thread.composer.getState().text).toBe("");
  // And the question is where it belongs: in the thread, once.
  expect(
    result.current.state.messages.filter(
      (each) => each.role === "user" && each.parts[0]?.text === "and then?",
    ),
  ).toHaveLength(1);
  write(
    event(
      "RUN_FINISHED",
      { threadId: CONVERSATION, runId: RUN, outcome: { type: "cancelled" } },
      2,
    ),
  );
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("a draft somebody had already typed is never cleared by a stop", async () => {
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url.endsWith("/cancel")) return json({ id: RUN });
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  // Something typed while the answer was on its way.
  await act(async () => {
    result.current.runtime.thread.composer.setText("a thought of my own");
    await settle();
  });
  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  expect(result.current.runtime.thread.composer.getState().text).toBe(
    "a thought of my own",
  );
  write(
    event(
      "RUN_FINISHED",
      { threadId: CONVERSATION, runId: RUN, outcome: { type: "cancelled" } },
      2,
    ),
  );
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("a turn the backend refuses takes its question back off the screen", async () => {
  // The 409 a conversation that is already answering makes: another tab
  // started a run between this one's reading and its send.
  inTurn({
    [`/api/conversations/${CONVERSATION}`]: [
      () => json(opened(conversation(1), TREE, "m2")),
    ],
    [`/api/conversations/${CONVERSATION}/turns`]: [
      () =>
        refusal(409, "RunAlreadyActiveError", `run ${RUN} is running in it`),
    ],
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    await result.current.runtime.thread.append("and then?");
  });
  expect(result.current.state.ended).toContain("still answering");
  // Not left on the screen as though it were in the conversation, and the
  // branch is back where it was.
  expect(result.current.state.messages).toHaveLength(2);
  expect(result.current.state.leafId).toBe("m2");
  expect(result.current.state.sending).toBe(false);
  expect(result.current.state.runId).toBeNull();
});

test("a second turn while one is in flight is said, not swallowed", async () => {
  // The box empties itself when it hands a message over, so a turn dropped
  // in silence is a message somebody believes they sent.
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  const fetch = stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const posted = () =>
    fetch.mock.calls.filter(
      ([url]) => String(url) === `/api/conversations/${CONVERSATION}/turns`,
    ).length;
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });

  // While the first turn's request is still in the air.
  let arrived: (given: Response) => void = () => undefined;
  fetch.mockImplementationOnce(
    () => new Promise<Response>((done) => (arrived = done)),
  );
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  await act(async () => {
    void result.current.runtime.thread.append("impatient");
    await settle();
  });
  expect(result.current.state.notice).toBe(ONE_AT_A_TIME);
  // The turn that *is* on its way keeps its question, and only it was sent.
  expect(
    result.current.state.messages.filter((each) => each.role === "user"),
  ).toHaveLength(2);
  expect(posted()).toBe(1);

  await act(async () => {
    arrived(response);
    await settle();
  });
  // **The run starting does not wipe it.** It is about what the person did,
  // not about the run, and a notice gone within milliseconds is the only
  // trace of a message that went nowhere disappearing before it is read.
  expect(result.current.state.notice).toBe(ONE_AT_A_TIME);
  write(event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 2));
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
  expect(result.current.state.notice).toBe(ONE_AT_A_TIME);

  // Their next turn is what clears it.
  await act(async () => {
    await result.current.runtime.thread.append("now then?");
  });
  expect(result.current.state.notice).toBeNull();
});

test("a second turn while one is in flight is not sent at all", async () => {
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  let posted = 0;
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      posted += 1;
      return response;
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  write(event("TEXT_MESSAGE_START", { messageId: "m4", role: "assistant" }, 2));
  await settle();
  expect(result.current.state.runId).toBe(RUN);

  // One run at a time (`docs/specs/runs.md`), and the run that is going is
  // left exactly as it is.
  await act(async () => {
    void result.current.runtime.thread.append("impatient");
    await settle();
  });
  expect(result.current.state.notice).toBe(ONE_AT_A_TIME);
  // A regeneration carries no message, so it is told so without being told
  // that a message was not sent.
  await act(async () => {
    void result.current.runtime.thread.startRun({
      parentId: "m1",
      sourceId: "m2",
    });
    await settle();
  });
  expect(result.current.state.notice).toBe(ONE_AT_A_TIME_ANSWER);
  expect(ONE_AT_A_TIME_ANSWER).not.toContain("was not sent");
  expect(posted).toBe(1);
  expect(result.current.state.runId).toBe(RUN);
  expect(result.current.state.messages.some((each) => each.id === "m4")).toBe(
    true,
  );

  write(event("TEXT_MESSAGE_CONTENT", { messageId: "m4", delta: "still" }, 3));
  await settle();
  expect(
    result.current.state.messages.find((each) => each.id === "m4")?.parts,
  ).toEqual([{ kind: "text", text: "still" }]);
  write(event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 4));
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("nothing is running until the run exists", async () => {
  // The library's own stop takes a trailing question out of the thread and
  // puts its text back into the box. Between the send and the response's
  // headers there is no run to stop, so the thread must not offer one --
  // `isRunning` is a run this chat knows the id of and nothing else.
  const { response, write, close } = writable({
    headers: streamHeaders(RUN, CONVERSATION),
  });
  const cancels: Call[] = [];
  const fetch = stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url.endsWith("/cancel")) {
      cancels.push(call);
      return json({ id: RUN, state: "cancelled" });
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`)
      return response;
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });

  // Held: the POST has been made and its headers have not arrived.
  let arrived: (given: Response) => void = () => undefined;
  fetch.mockImplementationOnce(
    () => new Promise<Response>((done) => (arrived = done)),
  );
  await act(async () => {
    void result.current.runtime.thread.append("and then?");
    await settle();
  });
  expect(result.current.state.sending).toBe(true);
  expect(result.current.state.runId).toBeNull();
  expect(result.current.runtime.thread.getState().isRunning).toBe(false);
  // And there is nothing to stop: no request goes out for one.
  await act(async () => {
    result.current.runtime.thread.cancelRun();
    await settle();
  });
  expect(cancels).toHaveLength(0);

  await act(async () => {
    arrived(response);
    await settle();
  });
  expect(result.current.state.runId).toBe(RUN);
  expect(result.current.runtime.thread.getState().isRunning).toBe(true);
  write(event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 2));
  close();
  await waitFor(() => {
    expect(result.current.state.runId).toBeNull();
  });
});

test("an edit under a question the server has never seen is not sent", async () => {
  const posts: Call[] = [];
  stub((call) => {
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(opened(conversation(1), TREE, "m2"));
    }
    if (call.url === `/api/conversations/${CONVERSATION}/turns`) {
      posts.push(call);
      return streamOf(
        event("RUN_FINISHED", { threadId: CONVERSATION, runId: RUN }, 9),
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(2);
  });
  await act(async () => {
    void result.current.runtime.thread.append({
      role: "user",
      content: [{ type: "text", text: "under nothing" }],
      parentId: "unsent:whatever",
      sourceId: "unsent:whatever",
    });
    await settle();
  });
  expect(posts).toHaveLength(0);
});

test("the tree is converted once per message, however many deltas arrive", () => {
  // A delta rebuilds the repository, and a conversation is as long as it is.
  const messages = Array.from({ length: 4 }, (_, index) => ({
    id: `m${index}`,
    parentId: index === 0 ? null : `m${index - 1}`,
    role: "user" as const,
    parts: [{ kind: "text" as const, text: "hello" }],
    state: "stored" as const,
  }));
  const first = asRepository(messages, "m3");
  const again = asRepository(messages, "m3");
  expect(again.messages.map((each) => each.message)).toEqual(
    first.messages.map((each) => each.message),
  );
  for (const [at, item] of again.messages.entries()) {
    // The same object, not an equal one: nothing was built a second time,
    // and `createdAt` did not move.
    expect(item.message).toBe(first.messages[at]?.message);
  }
  // A message the reducer touched is a new object, and only that one is
  // converted again.
  const touched = [...messages];
  touched[2] = { ...messages[2]!, parts: [{ kind: "text", text: "changed" }] };
  const third = asRepository(touched, "m3");
  expect(third.messages[1]?.message).toBe(first.messages[1]?.message);
  expect(third.messages[2]?.message).not.toBe(first.messages[2]?.message);
});

test("a conversation that is not here is one answer for two reasons", async () => {
  stub(() => refusal(404, "NotFoundError", "there is nothing here of that id"));
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.failure?.missing).toBe(true);
  });
  // And nothing is being watched behind that page.
  expect(result.current.state.runId).toBeNull();
  expect(result.current.state.sending).toBe(false);
});

test("switching branch moves the author's position on the server", async () => {
  const writes: Call[] = [];
  stub((call) => {
    if (call.method === "PUT") {
      writes.push(call);
      return json(conversation(1));
    }
    if (call.url === `/api/conversations/${CONVERSATION}`) {
      return json(
        opened(
          conversation(1),
          [...TREE, message("m3", "m1", "assistant", "or because")],
          "m2",
        ),
      );
    }
    return undefined;
  });
  const { result } = chatting({ conversationId: CONVERSATION });
  await waitFor(() => {
    expect(result.current.state.messages).toHaveLength(3);
  });
  // The tree really has two answers under the one question, which is what a
  // branch picker is.
  const answer = result.current.runtime.thread.getMessageById("m2");
  expect(answer.getState().branchCount).toBe(2);

  await act(async () => {
    answer.switchToBranch({ position: "next" });
    await settle();
  });
  expect(result.current.state.leafId).toBe("m3");
  expect(writes[0]?.url).toBe(`/api/conversations/${CONVERSATION}/leaf`);
  expect(writes[0]?.body).toEqual({ message_id: "m3" });
});

test("a read that says the same thing hands back the same messages", () => {
  // Identity is what the chat converts for assistant-ui by, so a read that
  // ends a turn must not rebuild a whole conversation over one answer.
  const stored = [
    message("m1", null, "user", "why?"),
    message("m2", "m1", "assistant", "because"),
  ];
  const first = after({
    kind: "opened",
    conversationId: CONVERSATION,
    messages: stored,
    leafId: "m2",
    runId: null,
    resume: null,
    endedBadly: null,
  });
  const again = reduce(first, {
    kind: "opened",
    conversationId: CONVERSATION,
    // The same conversation with one more answer, as a turn leaves it.
    messages: [...stored, message("m3", "m2", "user", "and then?")],
    leafId: "m3",
    runId: null,
    resume: null,
    endedBadly: null,
  });
  expect(again.messages[0]).toBe(first.messages[0]);
  expect(again.messages[1]).toBe(first.messages[1]);
  expect(again.messages[2]?.id).toBe("m3");
  // Which is what keeps the conversions, and `createdAt` with them.
  expect(asRepository(again.messages, "m3").messages[0]?.message).toBe(
    asRepository(first.messages, "m2").messages[0]?.message,
  );
  // A message the store now says something else about is rebuilt.
  const edited = reduce(first, {
    kind: "opened",
    conversationId: CONVERSATION,
    messages: [stored[0]!, message("m2", "m1", "assistant", "because of this")],
    leafId: "m2",
    runId: null,
    resume: null,
    endedBadly: null,
  });
  expect(edited.messages[0]).toBe(first.messages[0]);
  expect(edited.messages[1]).not.toBe(first.messages[1]);
});

test("handing the state over again is the same messages in a new array", () => {
  // What the runtime is given back when it has rewritten its own repository
  // -- a branch it resolved to nothing or to a message the server has never
  // seen, the message it takes out of the thread when a run is stopped. A new
  // object is "all of it, again"; the messages keep their identity, so
  // nothing is converted twice (`asRepository`).
  const some = after(asked, started);
  const back = reduce(some, { kind: "resync" });
  expect(back.messages).toEqual(some.messages);
  expect(back.messages).not.toBe(some.messages);
  expect(back.messages[0]).toBe(some.messages[0]);
  expect(asRepository(back.messages, back.leafId).messages[0]?.message).toBe(
    asRepository(some.messages, some.leafId).messages[0]?.message,
  );
});
