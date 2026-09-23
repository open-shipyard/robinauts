// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * Our state, given to assistant-ui to render.
 *
 * `useExternalStoreRuntime` is the runtime for a host that owns its own
 * messages: the library renders and calls back, and every message, every
 * branch and every byte of a stream is ours (`./state.ts`). None of
 * assistant-ui's own persistence is used -- no `assistant-cloud`, no thread
 * list -- because the conversation lives in our database and nowhere else
 * (ADR 0001).
 *
 * **What the adapter really offers, having read it** (`@assistant-ui/react`
 * 0.15.19, `ExternalStoreAdapter`):
 *
 * - `messages` is a flat list which the runtime relinks into a chain, so the
 *   branches beside the one being read would exist only once the runtime had
 *   been shown them. `messageRepository` is the other way in and is the one
 *   used here: an `ExportedMessageRepository` is **every message with its
 *   parent, and a head**, which is the shape our API already answers in, so
 *   the branch picker has the whole tree from the first render.
 * - `switchToBranch` is offered when `setMessages` is there, and the list a
 *   switch hands back is not what decides our branch -- the server keeps the
 *   author's position (`PUT /api/conversations/{id}/leaf`). So `setMessages`
 *   is present and does nothing, and the switch is heard through
 *   `unstable_onBranchChange`, which fires on a branch picker's click and on
 *   nothing else.
 * - `onNew`, `onEdit`, `onReload` and `onCancel` are the four the vendored
 *   Thread's composer and action bar reach: send, edit, regenerate, stop.
 *   Each is one of the wire's turns (`docs/specs/wire.md`).
 * - `isRunning` is ours to say, and while it is true with no assistant
 *   message at the end of the branch the runtime draws a placeholder of its
 *   own -- which is the "working" dot between a question and its first word.
 */
import {
  fromThreadMessageLike,
  useExternalStoreRuntime,
  type AppendMessage,
  type AssistantRuntime,
  type ExportedMessageRepository,
  type ExternalStoreAdapter,
  type MessageStatus,
  type ThreadComposerRuntime,
  type ThreadMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { useEffect, useMemo, useReducer, useState } from "react";

import { ApiError, detailOf, request } from "../../api/client";
import { cancelRun } from "../../conversation/conversation";
import type { ChatProps } from "../index";
import {
  attach,
  startNewConversation,
  startTurn,
  type Attached,
} from "./agui/client";
import {
  EMPTY,
  ENDED_BADLY,
  isUnsent,
  ONE_AT_A_TIME,
  ONE_AT_A_TIME_ANSWER,
  reduce,
  STOP_DID_NOT_ARRIVE,
  under,
  UNSENT,
  type ChatAction,
  type ChatMessage,
  type ChatState,
} from "./state";

/** What is said when there is nobody to talk to. */
export const NO_AGENT =
  "This deployment has no agent configured, so there is nobody to send this to.";

/** What a second turn in a conversation that is already answering is told. */
export const STILL_ANSWERING =
  "This conversation is still answering. Stop that answer before sending another.";

/**
 * What is said when the answer could not be followed to its end.
 *
 * One sentence for every way a **watch** ends badly -- a connection nobody
 * could pick up again, a run that is no longer there, a stream that sent
 * something we do not read -- because what a person can do about them is the
 * same thing, and none of the details is about them. What the *turn* itself
 * was refused with is said as the backend said it (`said`).
 */
export const LOST_TOUCH =
  "The connection to this answer was lost. Opening the conversation again shows what was stored.";

/**
 * The sentence for a refusal, in the chat's own words where it has any.
 *
 * A 409 is the one refusal a person causes by doing something reasonable, and
 * the backend's own detail for it names a run and a conversation by id, for
 * an operator's log (`api/errors.py`). Everything else is the backend's
 * sentence, which is already written for a reader.
 */
function said(failure: unknown): string {
  if (failure instanceof ApiError && failure.status === 409) {
    return STILL_ANSWERING;
  }
  return detailOf(failure);
}

/** What the component below gets back. */
export interface Chatting {
  state: ChatState;
  runtime: AssistantRuntime;
}

export function useChat(props: ChatProps): Chatting {
  const [state, dispatch] = useReducer(reduce, EMPTY);

  // Made once, and what it holds is its own: `dispatch` never changes, and
  // everything a turn reads while it runs -- the props, the state, the
  // stream being watched -- is written into it by the effect below. A turn
  // is begun from a click and finishes minutes later, so it has to read
  // whatever is current then rather than what was current when it was made.
  // They also call one another: a turn ends in a reading, and a reading of a
  // conversation with a run going attaches to it.
  const [turns] = useState(() => turnsOf(dispatch, props));
  useEffect(() => {
    turns.now(props, state);
  });

  // Which conversation is on the screen. Reading one is one call
  // (`docs/specs/conversations.md`), and leaving one abandons it.
  const conversationId = props.conversationId;
  useEffect(() => {
    // A conversation this chat created itself is already on the screen, and
    // reading it again would put "Loading…" over an answer that is arriving.
    if (conversationId !== null && turns.began(conversationId)) return;
    turns.stop();
    if (conversationId === null) {
      dispatch({ kind: "cleared" });
      return;
    }
    const dropped = new AbortController();
    dispatch({ kind: "opening", conversationId });
    void turns.read(conversationId, dropped.signal);
    return () => {
      dropped.abort();
    };
  }, [conversationId, turns]);

  // Going away stops watching: the stream is a view of the run, and closing
  // it changes nothing about the run (`docs/specs/runs.md`).
  useEffect(() => {
    return () => {
      turns.stop();
    };
  }, [turns]);

  // The runtime re-imports what it is given when the object is not the one it
  // was given last, so this is what decides how often it does.
  const repository = useMemo(
    () => asRepository(state.messages, state.leafId),
    [state.messages, state.leafId],
  );

  const adapter: ExternalStoreAdapter = useMemo(
    () => ({
      messageRepository: repository,
      // **A run, and not a turn that has been asked for.** Between the send
      // and the response's headers there is nothing to stop: the library's
      // own `cancelRun` would take the question back out of the thread and
      // put its text into the box, and the server would answer it anyway.
      // While `sending`, `onNew` refuses instead (see `turnsOf`).
      isRunning: state.runId !== null,
      isLoading: state.loading,
      // There is nothing to send a first message to when the deployment has
      // no agent; the box still takes what is typed into it.
      isSendDisabled: state.conversationId === null && props.agentId === null,
      // **What the runtime rewrote, handed straight back.** It is present at
      // all because branch switching is offered only when it is; what it does
      // is refuse the rewrite, because the conversation is the server's. It
      // is not a no-op, though: the runtime rewrites its own repository
      // first, so leaving this empty would leave the two disagreeing -- and
      // a head it has dropped and we still name is an exception thrown from
      // inside the library on the next render. Handing ours over again puts
      // it back in step (`state.ts`, `resync`).
      setMessages: () => {
        dispatch({ kind: "resync" });
      },
      unstable_onBranchChange: turns.onBranchChange,
      onNew: turns.onNew,
      onEdit: turns.onEdit,
      onReload: turns.onReload,
      onCancel: turns.onCancel,
    }),
    [
      repository,
      state.runId,
      state.loading,
      state.conversationId,
      props.agentId,
      turns,
    ],
  );

  const runtime = useExternalStoreRuntime(adapter);

  // **The box.** Two things the library leaves it saying the wrong thing
  // about a message that never became a turn; what they are and why is in
  // `turnsOf`, beside `wanted`. This runs after every render, which is after
  // the library's own work in the same event, and it never overwrites
  // anything the person has typed since.
  useEffect(() => {
    turns.reaches(() => runtime.thread.composer);
  }, [turns, runtime]);
  useEffect(() => {
    const wanted = turns.saying();
    if (wanted === null) return;
    const box = runtime.thread.composer;
    const held = box.getState().text;
    if (wanted.kind === "put") {
      if (held === "") box.setText(wanted.text);
      return;
    }
    // **The library's own rule, not a stricter one.** `restoreDraft` refuses
    // only when the box holds something that is not all whitespace, so a box
    // holding two spaces is one it restored into -- and one this must clear,
    // or the question sits in the thread and in the box at once.
    if (wanted.was.trim() === "" && held === wanted.text) box.setText("");
  });

  return { state, runtime };
}

/**
 * Everything the chat does to the API, made once.
 *
 * A closure rather than a set of hooks: what these read is plainly the four
 * values below, which the component keeps current, and nothing a render
 * happened to leave behind.
 */
function turnsOf(dispatch: (action: ChatAction) => void, first: ChatProps) {
  let props = first;
  let state = EMPTY;
  /** The stream being watched; aborted when another starts or this goes away. */
  let watching: AbortController | null = null;
  /**
   * The turns whose request is still in the air.
   *
   * A stream is adopted only once its request has been answered (`follow`),
   * so between the two there is a watcher-to-be that `watching` does not name
   * -- and leaving a conversation while one is in the air must stop it too,
   * or a stream would begin for a page nobody is on.
   */
  const starting = new Set<AbortController>();
  /** A conversation this chat created itself, which the shell then routes to. */
  let ours: string | null = null;
  /**
   * What the box must be made to say, once, after the next render.
   *
   * Two things the library leaves it saying the wrong thing, and both are
   * about a message that never became a turn:
   *
   * - **take**: pressing stop before an answer has begun makes the library
   *   take the trailing question out of its own repository and restore its
   *   text into the composer, on the assumption that a host which keeps no
   *   unanswered question would want it back to edit. Ours is not that host:
   *   the backend stored that question when the turn began, so it stays in
   *   the conversation, and a box holding a copy of a message on the screen
   *   is a message somebody sends twice. The library takes its own draft
   *   back only when it can see that the store still holds the message, and
   *   here it cannot -- what it moved is the end of the branch, the one case
   *   it reads as "the host has not removed it yet".
   * - **put**: the box empties itself when it hands a message over, so a
   *   turn refused here for being a second one leaves nothing behind at all.
   *   The text goes back, and a notice says why (`ONE_AT_A_TIME`).
   *
   * `was` is what the box held **before** the stop: a draft somebody had
   * already typed is theirs and is never cleared.
   */
  type Wanted =
    { kind: "take"; text: string; was: string } | { kind: "put"; text: string };
  let wanted: Wanted | null = null;

  /** How the box is reached, once there is a runtime to reach it with. */
  let box: (() => ThreadComposerRuntime) | null = null;
  function reaches(reach: () => ThreadComposerRuntime): void {
    box = reach;
  }

  /** What the box must be made to say, once. */
  function saying(): Wanted | null {
    const held = wanted;
    wanted = null;
    return held;
  }

  /** What a turn begun from now on reads. Written after every render. */
  function now(current: ChatProps, held: ChatState): void {
    props = current;
    state = held;
  }

  /**
   * Whether a turn is already on its way, and so no second one may be.
   *
   * **One run at a time** (`docs/specs/runs.md`), and the backend says so
   * with a 409. Refusing here as well is not belt and braces: it is what
   * keeps at most one question on the screen that the server has not been
   * told about, so a turn that *is* refused can be taken back off it without
   * having to work out which of several it was.
   *
   * The Thread does not offer either -- the box shows stop while a run is
   * going, and the action bar hides itself -- so this is reachable only by
   * driving the runtime, or by being very quick between a send and its
   * answer's headers.
   */
  function busy(): boolean {
    return state.runId !== null || state.sending;
  }

  /**
   * Say that the turn was not sent, because the box has already cleared it.
   *
   * assistant-ui empties the composer when it hands a message over, so a turn
   * dropped in silence is a message somebody believes they sent
   * (`ONE_AT_A_TIME`). `told` changes nothing else: the turn that *is* on its
   * way keeps its question, its run and its stream.
   */
  function told(text: string): void {
    dispatch({ kind: "told", detail: ONE_AT_A_TIME });
    // The box cleared itself when it handed this over, so without this the
    // message is gone and the notice is all there is.
    if (text !== "") wanted = { kind: "put", text };
  }

  /**
   * Whether reading that conversation would put "Loading…" over it.
   *
   * True only for one this chat **created and is still showing**. Both
   * halves matter: `ours` alone would skip the read for a conversation this
   * chat created and then left, and the state alone cannot tell "already
   * shown" from "about to be read".
   */
  function began(conversationId: string): boolean {
    return conversationId === ours && state.conversationId === conversationId;
  }

  /** Stop watching, and forget the conversation this chat began. */
  function stop(): void {
    ours = null;
    watching?.abort();
    watching = null;
    for (const beginning of starting) beginning.abort();
    starting.clear();
  }

  /**
   * Read that conversation and show what the server says it is.
   *
   * **A read that finds a run in flight watches it**, whichever read it is.
   * Opening a conversation is the obvious one (`docs/specs/runs.md`), and the
   * read that ends a turn is the one that matters: another tab may have begun
   * a run in the meantime, and taking its id without watching it would leave
   * this thread answering for ever with nothing reading the answer.
   */
  async function read(
    conversationId: string,
    signal: AbortSignal,
    afterLoss = false,
  ): Promise<void> {
    let opened;
    try {
      opened = await request("get", "/api/conversations/{conversation_id}", {
        path: { conversation_id: conversationId },
        signal,
      });
    } catch (failure) {
      if (signal.aborted) return;
      dispatch({
        kind: "unopened",
        detail: said(failure),
        missing: failure instanceof ApiError && failure.status === 404,
      });
      return;
    }
    if (signal.aborted) return;
    dispatch({
      kind: "opened",
      conversationId,
      messages: opened.messages,
      leafId: opened.leaf_id,
      runId: opened.run_id,
      resume: opened.resume,
      endedBadly:
        opened.ended_badly === null
          ? null
          : (ENDED_BADLY.get(opened.ended_badly.state) ?? null),
    });
    // Every complete message has just been loaded, so attaching at
    // `resume.after` replays exactly the one still being produced and none
    // that is already on the screen.
    const runId = opened.run_id;
    const resume = opened.resume;
    if (runId !== null && resume !== null) {
      void follow(
        (watched) => attach(runId, resume.after, { signal: watched }),
        {
          watch: true,
          afterLoss,
        },
      );
    }
  }

  /**
   * Open a stream and read it to its end, then read the conversation again.
   *
   * The promise is resolved once the **stream is open**, not once the run has
   * finished: what a caller waits for is whether the turn was accepted, and a
   * refusal is a status that comes before the stream (`docs/specs/wire.md`).
   * The answer then arrives event by event.
   *
   * `watch` tells the two callers apart, and what it decides is what a
   * refusal means. A **turn** somebody asked for that is refused leaves the
   * run alone -- a conversation that is already answering refuses a second
   * turn (409) while the first is still going. A **watch** that is refused is
   * nobody watching the run at all, which is a different thing to say and
   * must not leave the thread waiting for an answer nothing is reading.
   */
  function follow(
    start: (signal: AbortSignal) => Promise<Attached>,
    { watch = false, afterLoss = false } = {},
  ): Promise<void> {
    const control = new AbortController();
    starting.add(control);
    return start(control.signal).then(
      (attached) => {
        starting.delete(control);
        // This page went away while the request was in the air.
        if (control.signal.aborted) return;
        // **The one being watched is let go of here and not before.** A turn
        // a conversation that is already answering refuses (409) must leave
        // the first run's stream alone; stopping it to make room for a turn
        // that never began would lose the answer that is arriving.
        watching?.abort();
        watching = control;
        dispatch({
          kind: "started",
          runId: attached.runId,
          conversationId: attached.conversationId,
        });
        void consume(attached, control, afterLoss);
      },
      (failure: unknown) => {
        starting.delete(control);
        if (control.signal.aborted) return;
        dispatch(
          watch
            ? { kind: "lost", detail: LOST_TOUCH }
            : { kind: "refused", detail: said(failure) },
        );
      },
    );
  }

  async function consume(
    attached: Attached,
    control: AbortController,
    afterLoss: boolean,
  ): Promise<void> {
    let lost: string | null = null;
    try {
      for await (const { event } of attached.events) {
        if (control.signal.aborted) return;
        dispatch({ kind: "event", event });
      }
    } catch {
      if (control.signal.aborted) return;
      lost = LOST_TOUCH;
    }
    if (control.signal.aborted) return;

    if (lost !== null) {
      // **The connection went and the run did not have to.** A client that
      // missed deltas reloads the conversation, which is what the store is
      // for (`docs/specs/wire.md`), and a run that is still in flight there
      // is one to watch again -- with the client's budget of tries reset,
      // since a link that has come back is not the link that went.
      //
      // Once. A second loss is one to tell about rather than to keep
      // retrying, and the reading below leaves `isRunning` false, so the box
      // and the answer's "try again" are usable.
      if (!afterLoss) {
        await read(attached.conversationId, control.signal, true);
        return;
      }
      dispatch({ kind: "lost", detail: lost });
      return;
    }

    // A turn writes to the conversation, and a write is what the panel's list
    // is asked for again after (`src/history/history.ts`). **Before** the
    // read below: that read may find another run in flight and watch it,
    // which stops this watcher -- and the list still has to be asked for.
    props.onTurnEnded?.();
    // The turn is over and **the store is the truth**: the ids are the
    // server's, the answer carries its provenance, and the branch is the one
    // its author is on.
    await read(attached.conversationId, control.signal);
  }

  async function onNew(message: AppendMessage): Promise<void> {
    const text = wrote(message);
    if (text === "") return;
    if (busy()) return told(text);
    // Not the end of the branch where that is a question nobody answered:
    // sending again is how a turn that went wrong is retried (`under`).
    const parentId = under(state, message.parentId ?? state.leafId);
    dispatch({ kind: "asked", id: unsent(), parentId, text });
    const conversationId = state.conversationId;
    if (conversationId !== null) {
      await follow((signal) =>
        startTurn(conversationId, { text, parentId }, { signal }),
      );
      return;
    }
    const agentId = props.agentId;
    if (agentId === null) {
      dispatch({ kind: "lost", detail: NO_AGENT });
      return;
    }
    await follow(async (signal) => {
      const attached = await startNewConversation(agentId, text, { signal });
      // **Only if this page is still the empty chat.** Somebody who opened
      // another conversation while the request was in the air is not to be
      // taken to this one instead, and claiming it as ours would stop the
      // conversation they *did* open from being read at all. The
      // conversation exists either way; the panel's next refresh lists it.
      if (signal.aborted) return attached;
      // The interface has one to be on now: a route to go to and a row for
      // the panel. What to do about it is the application's
      // (`src/chat/index.ts`).
      ours = attached.conversationId;
      props.onConversationStarted(attached.conversationId);
      return attached;
    });
  }

  async function onEdit(message: AppendMessage): Promise<void> {
    const text = wrote(message);
    const conversationId = state.conversationId;
    if (text === "" || conversationId === null) return;
    // **An edit is a new message under the parent of the one it replaces**
    // (`docs/specs/conversations.md`): nothing is overwritten, and what the
    // tree gains is a branch beside the old one.
    const parentId = message.parentId;
    // A parent the server has never been told about: the question being
    // edited is itself one this chat put on the screen a moment ago and the
    // conversation has not been read since. The backend would answer 404 for
    // it. The Thread hides the edit button while a run is going, so this is
    // reachable only by driving the runtime directly.
    if (isUnsent(parentId)) return;
    if (busy()) return told(text);
    dispatch({ kind: "asked", id: unsent(), parentId, text });
    await follow((signal) =>
      startTurn(conversationId, { text, parentId }, { signal }),
    );
  }

  async function onReload(
    parentId: string | null,
    config: { sourceId: string | null },
  ): Promise<void> {
    const conversationId = state.conversationId;
    const regenerate = config.sourceId;
    if (conversationId === null || regenerate === null) return;
    // Nothing was typed for a regeneration, so there is nothing to put back
    // and nothing that was not sent.
    if (busy()) {
      dispatch({ kind: "told", detail: ONE_AT_A_TIME_ANSWER });
      return;
    }
    // A regeneration carries no new message: it answers the question that
    // turn already had (`docs/specs/conversations.md`).
    dispatch({ kind: "again", parentId });
    await follow((signal) =>
      startTurn(conversationId, { regenerate }, { signal }),
    );
  }

  async function onCancel(): Promise<void> {
    // **Both of these before anything is awaited.** assistant-ui's own
    // `cancelRun` calls this and then, in the same turn of the loop, takes
    // the trailing question out of its repository and puts its text into the
    // box. The `resync` is what puts its repository back -- ours still holds
    // that message, because the backend stored it when the turn began -- and
    // `restored` is what `useChat` clears the box with. A dispatch after an
    // `await` would be too late for either.
    dispatch({ kind: "resync" });
    const { conversationId, runId } = state;
    const tail = state.messages.find((each) => each.id === state.leafId);
    wanted =
      tail !== undefined && tail.role === "user"
        ? {
            kind: "take",
            text: tail.parts.map((part) => part.text).join(""),
            // Read **now**, before the library touches it: a draft somebody
            // had already typed is not one to clear.
            was: box?.().getState().text ?? "",
          }
        : null;
    // Nothing to stop. The Thread offers stopping only while `isRunning`,
    // which is a run this chat knows the id of, so this is a guard and not a
    // state: there is no request that would say "stop whatever is going".
    if (conversationId === null || runId === null) return;
    try {
      await cancelRun(conversationId, runId);
    } catch {
      // **Nothing about the run changed**, and the stream watching it is
      // still watching: the request failed, so nothing was cancelled and the
      // answer carries on arriving. Forgetting the run here would leave it
      // writing into a thread that thinks nothing is happening -- and would
      // leave an answer hanging under a question a later refusal could take
      // off the screen.
      dispatch({ kind: "told", detail: STOP_DID_NOT_ARRIVE });
      return;
    }
    // Nothing else: a cancellation is not a failure, and the stream this is
    // already watching ends with `RUN_FINISHED` and AG-UI's `cancelled`
    // outcome (`docs/specs/wire.md`).
  }

  function onBranchChange({ headId }: { headId: string | null }): void {
    if (headId === null || isUnsent(headId)) {
      // A head this state cannot mean: nothing, or a message the server has
      // never been told about. The runtime has moved its own repository
      // there all the same, so the two now disagree -- and what puts them
      // back in step is handing the whole state over again, which is a new
      // object and a `resetHead` on the branch this really reads.
      dispatch({ kind: "resync" });
      return;
    }
    dispatch({ kind: "branch", leafId: headId });
    const conversationId = state.conversationId;
    if (conversationId === null) return;
    // Where its author is reading is the conversation's and not this tab's,
    // and moving there writes nothing else: it deliberately does not date the
    // conversation (`docs/specs/conversations.md`).
    void request("put", "/api/conversations/{conversation_id}/leaf", {
      path: { conversation_id: conversationId },
      body: { message_id: headId },
    }).then(undefined, () => {
      // The branch on the screen is the branch being read either way; a
      // position the server did not keep is not worth a sentence.
    });
  }

  return {
    now,
    began,
    stop,
    reaches,
    saying,
    read,
    onNew,
    onEdit,
    onReload,
    onCancel,
    onBranchChange,
  };
}

/** An id for a message the server has not been told about yet. */
function unsent(): string {
  return `${UNSENT}${crypto.randomUUID()}`;
}

/** What was typed, as one string. */
function wrote(message: AppendMessage): string {
  return message.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

/**
 * Every message of ours, converted once.
 *
 * **A delta rebuilds the repository**, and a conversation is as long as it
 * is: without this, a hundred deltas into a turn of a hundred-message
 * conversation is ten thousand conversions of messages that have not changed
 * since they were read. The reducer builds a new object only for a message it
 * touches, so object identity is exactly "this message has changed", and a
 * `WeakMap` keyed on it is a cache nothing has to invalidate -- an entry goes
 * when the message it is of does.
 *
 * Giving assistant-ui converted messages rather than `ThreadMessageLike`s is
 * also what makes `createdAt` stop moving: `fromThreadMessageLike` stamps
 * `new Date()` on anything without one, so the same message converted twice
 * was two different messages.
 */
const converted = new WeakMap<ChatMessage, ThreadMessage>();

/**
 * The whole tree, with the branch it is read on, as the runtime takes it.
 *
 * **Nothing goes out of here naming a message that is not in it.** The
 * library throws on a parent it has not been given and on a head it does not
 * hold, and an exception from inside a render is the whole interface gone --
 * over a message, which is the thing this is least entitled to lose. The
 * reducer is written not to produce either (`state.ts`), so what this drops
 * is a slip: it is said once to the console and the conversation carries on.
 */
export function asRepository(
  messages: readonly ChatMessage[],
  leafId: string | null,
): ExportedMessageRepository {
  const known = new Set<string>();
  const items = [];
  for (const message of messages) {
    if (message.parentId !== null && !known.has(message.parentId)) {
      complain(
        `dropping ${message.id}: its parent ${message.parentId} is not here`,
      );
      continue;
    }
    known.add(message.id);
    items.push({ message: stored(message), parentId: message.parentId });
  }
  const last = items[items.length - 1]?.message.id ?? null;
  const headId = leafId !== null && known.has(leafId) ? leafId : last;
  if (leafId !== null && headId !== leafId) {
    complain(`the branch ends on ${leafId}, which is not here`);
  }
  return {
    messages: items,
    // Left out rather than given as `null`, which would mean "no branch at
    // all"; left out, the runtime reads the last message as the head.
    ...(headId === null ? {} : { headId }),
  };
}

/** The shapes already complained about; every render would say them again. */
const complained = new Set<string>();

/**
 * Say that a message named something that is not there.
 *
 * **It firing is a bug of ours** -- the reducer is written never to produce
 * either shape (`state.ts`) -- and nothing a person can do anything about,
 * so it goes to the console and not on to the screen, and it is not thrown,
 * because the conversation on the screen is worth more than the certainty.
 * A warning rather than a debug line for the same reason: whoever is looking
 * at the console should see it.
 *
 * Once per shape. The tree is rebuilt on every delta, so a slip that lasts a
 * whole answer would otherwise be a thousand identical lines and the one
 * before it scrolled away.
 */
function complain(what: string): void {
  if (complained.has(what)) return;
  complained.add(what);
  console.warn(`[robinauts] the chat's tree is not a tree: ${what}`);
}

/** That message as assistant-ui holds one, converted at most once. */
function stored(message: ChatMessage): ThreadMessage {
  const held = converted.get(message);
  if (held !== undefined) return held;
  const made = fromThreadMessageLike(
    asThreadMessage(message),
    message.id,
    // The fallback status, for a message that carries none. Ours all do --
    // an assistant message is given one below and a user message may not have
    // one at all -- so this is never what is used.
    { type: "complete", reason: "unknown" },
  );
  converted.set(message, made);
  return made;
}

/** One message of ours, as assistant-ui takes one. */
export function asThreadMessage(message: ChatMessage): ThreadMessageLike {
  const content = message.parts.map((part) =>
    part.kind === "reasoning"
      ? ({ type: "reasoning", text: part.text } as const)
      : ({ type: "text", text: part.text } as const),
  );
  if (message.role === "user") {
    return {
      id: message.id,
      role: "user",
      content: content.filter((part) => part.type === "text"),
    };
  }
  return {
    id: message.id,
    role: "assistant",
    content,
    status: asStatus(message),
  };
}

/** How a message of ours stands, in assistant-ui's words. */
function asStatus(message: ChatMessage): MessageStatus {
  switch (message.state) {
    case "running":
      return { type: "running" };
    case "cancelled":
      return { type: "incomplete", reason: "cancelled" };
    case "failed":
      // What the Thread shows under the message, and the one place a sentence
      // about a run that went wrong is drawn by the library rather than by us.
      return {
        type: "incomplete",
        reason: "error",
        error: message.detail ?? "",
      };
    case "stored":
      return { type: "complete", reason: "stop" };
  }
}
