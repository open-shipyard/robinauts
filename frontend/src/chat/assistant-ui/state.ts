// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * What the chat holds, and the one function that changes it.
 *
 * A reducer, and nothing else: no `fetch`, no timers, no React. What arrives
 * -- a conversation read from the API, an AG-UI event, a message somebody
 * typed -- is an action, and what comes out is the next state. That is what
 * makes the interesting half of the chat a thing a test can drive one event
 * at a time (`./runtime.test.tsx`), and it is where the rules of
 * `docs/specs/wire.md` about a stream that begins in the middle are written
 * down once.
 *
 * **The store is the truth and this is a view of it.** What is held here is
 * the conversation as it was last read, plus the message the run in flight is
 * producing -- which is in no conversation until it is complete
 * (`docs/specs/runs.md`). When a turn ends, the conversation is read again
 * and what the server says replaces all of it: real ids, the provenance of
 * the answer, the branch its author is on. Nothing here is ever the only copy
 * of anything.
 *
 * **The whole tree, not one branch.** Every message the conversation has is
 * kept, each with its parent, because that is what a branch picker is
 * (`docs/specs/conversations.md`); which branch is being read is `leafId`.
 */
import type { Message } from "../../conversation/conversation";
import type { AguiEvent } from "./agui/events";

/**
 * What a message of ours that the server has never seen is called.
 *
 * A send puts the question on the screen before the turn has been accepted,
 * and until the conversation is read again that message has an id no route
 * would answer for. The prefix is how everything that would put an id into a
 * request -- moving the author's branch, hanging a message under one -- tells
 * the two apart. No id the backend issues holds a colon (they are uuids).
 */
export const UNSENT = "unsent:";

/** Whether that is a message the server has never been told about. */
export function isUnsent(id: string | null): boolean {
  return id !== null && id.startsWith(UNSENT);
}

/** A piece of what a message says: what it said, or what it thought. */
export interface ChatPart {
  kind: "text" | "reasoning";
  /**
   * The id of a stretch of thinking, which is how the event that ends it
   * finds it. A stretch has one because a turn may think more than once and
   * each one is a message of its own on the wire (`api/agui.py`).
   */
  id?: string;
  text: string;
}

/** How a message stands. */
export type ChatMessageState = "stored" | "running" | "cancelled" | "failed";

/** One message, as the chat holds one. */
export interface ChatMessage {
  id: string;
  parentId: string | null;
  role: "user" | "assistant";
  parts: ChatPart[];
  state: ChatMessageState;
  /** The sentence to show on a message whose run failed. */
  detail?: string;
}

/** The whole of it. */
export interface ChatState {
  /** Which conversation this is of; `null` on an empty chat. */
  conversationId: string | null;
  /** The one call that opens a conversation has not answered yet. */
  loading: boolean;
  /** Why it could not be opened, and whether that was a 404. */
  failure: { detail: string; missing: boolean } | null;
  /** Every message of the tree, and the one being produced. */
  messages: ChatMessage[];
  /** The end of the branch being read. */
  leafId: string | null;
  /** The run in flight. */
  runId: string | null;
  /**
   * A turn has been asked for and its run is not known yet.
   *
   * `runId` alone would leave the moment between the send and the response's
   * headers looking idle, which is the moment a person is most likely to
   * press send again.
   */
  sending: boolean;
  /** What the next message the run announces hangs under. */
  follows: string | null;
  /** The assistant message the stream is writing, if one is open. */
  writing: string | null;
  /** The stretch of thinking that is open, if one is. */
  thinking: string | null;
  /** What to say about the last run when it did not end well. */
  ended: string | null;
  /**
   * Something said to the person, which only the person clears.
   *
   * Apart from `ended`, which is about a run and goes when the next one
   * starts. A notice is about **what they just did** -- a message that was
   * not sent, a stop that did not reach the server -- and a run starting
   * milliseconds later must not wipe it, or the only trace of a message that
   * went nowhere disappears before it can be read. What clears it is the
   * next turn they successfully ask for, or leaving the conversation.
   */
  notice: string | null;
  /**
   * The turn on its way: what it added, and where the branch was before it.
   *
   * A turn the server refuses is one that never happened, so what it put on
   * the screen comes off and the branch goes back -- and **neither is a
   * guess**. The message to take off is the one that turn added and no other
   * (another may be on the screen from a turn that is still going), and the
   * branch goes back to where it was, which is not the refused question's
   * parent: a retry of a turn that went wrong hangs under the *parent* of
   * the question nobody answered (`under`), so restoring to that parent
   * would take that question off the branch as well.
   */
  before: {
    asked: string | null;
    leafId: string | null;
    follows: string | null;
  } | null;
}

export const EMPTY: ChatState = {
  conversationId: null,
  loading: false,
  failure: null,
  messages: [],
  leafId: null,
  runId: null,
  sending: false,
  follows: null,
  writing: null,
  thinking: null,
  ended: null,
  notice: null,
  before: null,
};

/**
 * How a run that ended badly is said, one fixed sentence per state.
 *
 * A `Map` rather than an object, as the sign-in errors are and for the same
 * reason: the states are the API's closed set today, and a build that met one
 * it did not know must say that something went wrong rather than render
 * whatever an object inherited under that name.
 */
export const ENDED_BADLY = new Map<string, string>([
  ["cancelled", "This answer was stopped before it was finished."],
  [
    "failed",
    "This answer did not finish: something went wrong while it was being produced.",
  ],
  [
    "interrupted",
    "This answer was interrupted when the server stopped. Sending the message again is how it is retried.",
  ],
]);

/**
 * The same, for the `code` of an AG-UI `RUN_ERROR` (`docs/specs/wire.md`).
 *
 * The event carries a sentence of the backend's as well, and this is used
 * instead of it: what the backend sends is written for a reader of a stock
 * AG-UI client, and the two states it shares with `ENDED_BADLY` should read
 * the same here whether they arrived in a stream or in a reload.
 */
export const RUN_ERRORS = new Map<string, string>([
  ["failed", ENDED_BADLY.get("failed") ?? ""],
  ["interrupted", ENDED_BADLY.get("interrupted") ?? ""],
  [
    "quiet",
    "This answer stopped saying anything and was given up on. Sending the message again is how it is retried.",
  ],
  [
    "gone",
    "This answer is no longer there. Open the conversation again to see what is.",
  ],
  ["internal", "Something went wrong while this answer was being produced."],
]);

const ENDED_SOMEHOW = "This answer did not finish.";

/**
 * What a second turn asked for while one is on its way is told.
 *
 * **One run at a time** (`docs/specs/runs.md`). It says that the message was
 * not sent, because the box has already cleared it: assistant-ui empties the
 * composer when it hands a message over, and a turn that went nowhere with a
 * box that went empty would be a message somebody thinks they sent.
 */
export const ONE_AT_A_TIME =
  "This conversation is already answering, and it takes one turn at a time. That message was not sent.";

/**
 * The same, for asking for an answer again.
 *
 * Without the last sentence: a regeneration carries no message
 * (`docs/specs/conversations.md`), so there is nothing that was not sent and
 * nothing to put back into the box.
 */
export const ONE_AT_A_TIME_ANSWER =
  "This conversation is already answering, and it takes one turn at a time.";

/**
 * What a stop that did not reach the server is told.
 *
 * **The run is not affected by it**, and neither is the stream watching it:
 * the request failed, so nothing was cancelled, and the answer carries on
 * arriving. Saying that the connection to the answer was lost would be
 * exactly backwards.
 */
export const STOP_DID_NOT_ARRIVE =
  "The stop did not reach the server, so the answer is still arriving.";

/** That code's sentence, and one for a code this build does not know. */
export function saidFor(code: string): string {
  return RUN_ERRORS.get(code) ?? ENDED_SOMEHOW;
}

/**
 * What a new question hangs under, given where the branch ends.
 *
 * Usually the end itself. **Unless the end is a question nobody answered** --
 * which is what a run that failed, was cancelled or was interrupted leaves
 * behind, since the answer it was producing is in no conversation
 * (`docs/specs/runs.md`) -- and then it is that question's own parent. Two
 * reasons, and they are the same reason: the format refuses a message of
 * role `user` under another (`InvalidMessageTreeError`,
 * `docs/specs/conversations.md`), and **asking again is how such a turn is
 * retried**. What the tree gains is a sibling of the question that went
 * unanswered, which is a branch beside it rather than a message lost.
 */
export function under(state: ChatState, at: string | null): string | null {
  const tail = state.messages.find((message) => message.id === at);
  return tail !== undefined && tail.role === "user" ? tail.parentId : at;
}

/** Everything that can change the chat. */
export type ChatAction =
  /** An empty chat: nothing opened, nothing being read. */
  | { kind: "cleared" }
  /** That conversation is being read. */
  | { kind: "opening"; conversationId: string }
  /** It was read: this is what the server says it is. */
  | {
      kind: "opened";
      conversationId: string;
      messages: readonly Message[];
      leafId: string | null;
      runId: string | null;
      /** Where the run in flight is to be attached after, and under what. */
      resume: { after: number; follows: string | null } | null;
      /** How the last run ended, when it ended badly. */
      endedBadly: string | null;
    }
  /** It could not be read. */
  | { kind: "unopened"; detail: string; missing: boolean }
  /** Somebody sent a message: it is on the screen before the server has it. */
  | { kind: "asked"; id: string; parentId: string | null; text: string }
  /** An answer is to be produced again, under the parent of the old one. */
  | { kind: "again"; parentId: string | null }
  /** The stream is open: this is the run it is of. */
  | { kind: "started"; runId: string; conversationId: string }
  /** One event of that run. */
  | { kind: "event"; event: AguiEvent }
  /** The stream could not be picked up again: nothing is watching the run. */
  | { kind: "lost"; detail: string }
  /** Something to say, and nothing else about the conversation changes. */
  | { kind: "told"; detail: string }
  /**
   * The turn was refused before it began, so nothing about the run changed.
   *
   * Told apart from `lost` because a conversation that is already answering
   * refuses a second turn (409) **while the first is still going**: forgetting
   * the run it is watching over a turn it never started would leave the answer
   * arriving into a thread that thinks nothing is happening.
   */
  | { kind: "refused"; detail: string }
  /** Hand the messages over again, unchanged. */
  | { kind: "resync" }
  /** Another branch is being read. */
  | { kind: "branch"; leafId: string };

export function reduce(state: ChatState, action: ChatAction): ChatState {
  switch (action.kind) {
    case "cleared":
      return state === EMPTY || state.conversationId === null
        ? EMPTY
        : { ...EMPTY };
    case "opening":
      // A different conversation is a different page, not this one with other
      // messages: what is on the screen goes, so that nothing of the one
      // before it is ever shown under the new one's name -- a notice about
      // something done here included. Reading the same one again -- which is
      // what follows a turn -- keeps what is there until the answer arrives.
      return state.conversationId === action.conversationId
        ? { ...state, loading: true }
        : { ...EMPTY, conversationId: action.conversationId, loading: true };
    case "opened": {
      // **A message the store still says the same thing about is the message
      // this state already holds.** Identity is what the chat converts for
      // assistant-ui by (`./runtime.tsx`, `converted`), so rebuilding every
      // object on the read that ends a turn would convert a whole
      // conversation again -- and move every `createdAt` -- over one answer.
      const before = new Map(state.messages.map((each) => [each.id, each]));
      const messages = action.messages.map((message) => {
        const fresh = held(message);
        const already = before.get(message.id);
        return already !== undefined && unchanged(already, fresh)
          ? already
          : fresh;
      });
      return {
        ...state,
        conversationId: action.conversationId,
        loading: false,
        failure: null,
        messages,
        leafId: action.leafId,
        runId: action.runId,
        sending: false,
        // A run in flight says what its next message hangs under; a
        // conversation at rest hangs the next one under the branch's end.
        follows:
          action.runId === null
            ? action.leafId
            : (action.resume?.follows ?? null),
        writing: null,
        thinking: null,
        ended: action.endedBadly,
        before: null,
      };
    }
    case "unopened":
      // Nothing is being watched either: a conversation that could not be
      // read is one whose run, if it had one, this client is not following.
      // Leaving `runId` set would be a thread that says it is answering
      // behind a page that says it could not be opened.
      return {
        ...state,
        loading: false,
        runId: null,
        sending: false,
        writing: null,
        thinking: null,
        failure: { detail: action.detail, missing: action.missing },
      };
    case "asked": {
      const asked: ChatMessage = {
        id: action.id,
        parentId: action.parentId,
        role: "user",
        parts: [{ kind: "text", text: action.text }],
        state: "stored",
      };
      return {
        ...state,
        messages: [...state.messages, asked],
        before: {
          asked: asked.id,
          leafId: state.leafId,
          follows: state.follows,
        },
        leafId: asked.id,
        follows: asked.id,
        sending: true,
        ended: null,
        // The person has asked for something that went out, so whatever they
        // were last told about a turn that did not is behind them.
        notice: null,
      };
    }
    case "again":
      // Nothing is added: a regeneration answers the question the turn
      // already had (`docs/specs/conversations.md`), so what changes is only
      // where the answer about to arrive will hang.
      return {
        ...state,
        before: {
          asked: null,
          leafId: state.leafId,
          follows: state.follows,
        },
        follows: action.parentId,
        sending: true,
        ended: null,
        notice: null,
      };
    case "started":
      return {
        ...state,
        conversationId: action.conversationId,
        runId: action.runId,
        sending: false,
        before: null,
        ended: null,
      };
    case "told":
      return { ...state, notice: action.detail };
    case "event":
      return applied(state, action.event);
    case "lost":
      // Nothing is watching the run, so nothing will say that the message it
      // was writing is over: it is closed here, or it spins for ever.
      // `cancelled` and not `failed`, because nothing is known to have gone
      // wrong with the answer -- only with the watching of it -- and the
      // sentence beside it says which (`LOST_TOUCH`).
      return { ...ending(state, "cancelled"), ended: action.detail };
    case "refused":
      // The question this turn put on the screen comes off: the server
      // refused the turn that would have put it in the conversation, and
      // leaving it would show a message that does not exist. **That one and
      // no other** -- a question from a turn that is still going may be on
      // the screen too, and an answer may already hang under it.
      // `before` is read as a value and not with `??`: a turn asked for on
      // an empty chat, or one whose run had nothing to hang under, saved a
      // `follows` of `null`, and that is where the branch goes back to.
      return where({
        ...state,
        messages: withoutAsked(state),
        leafId: state.before !== null ? state.before.leafId : state.leafId,
        follows: state.before !== null ? state.before.follows : state.follows,
        before: null,
        sending: false,
        ended: action.detail,
      });
    case "resync":
      // The same messages in a new array. The runtime re-imports what it is
      // given when the object is not the one it was given last, and this is
      // the smallest thing that says "all of it, again" -- the messages
      // themselves keep their identity, so nothing is converted twice
      // (`./runtime.tsx`, `converted`).
      return { ...state, messages: [...state.messages] };
    case "branch":
      return { ...state, leafId: action.leafId, follows: action.leafId };
  }
}

/**
 * One AG-UI event.
 *
 * **The three no-ops of `docs/specs/wire.md` are here**, and they are what
 * lets a client re-attach without seeing anything twice: a `*_START` for a
 * message it already holds open, a `*_END` for one it does not hold, and the
 * terminal event of a run it has already seen end. Everything else arrives
 * once.
 *
 * It is also deliberately forgiving in the other direction -- content for a
 * message no start was seen for opens one -- because the alternative is an
 * answer that arrives and is not shown.
 */
function applied(state: ChatState, event: AguiEvent): ChatState {
  switch (event.type) {
    case "RUN_STARTED":
      // The run is already known from the response's headers, which arrive
      // before any event does. Re-attaching never replays this one.
      return state.runId === null ? { ...state, runId: event.runId } : state;

    case "TEXT_MESSAGE_START": {
      // **Already held: nothing to do.** Held *open* is the no-op a re-attach
      // in the middle of a message relies on; held complete is one this
      // client already has from the store, and either way an id stands for
      // one message and never for a second copy of it.
      if (find(state, event.messageId) !== null) return state;
      const started: ChatMessage = {
        id: event.messageId,
        parentId: state.follows,
        role: event.role === "user" ? "user" : "assistant",
        parts: [],
        state: "running",
      };
      return {
        ...state,
        messages: [...state.messages, started],
        leafId: started.id,
        writing: started.id,
        thinking: null,
      };
    }

    case "TEXT_MESSAGE_CONTENT": {
      const open = find(state, event.messageId);
      // A message whose opening this client never saw: open it. Being
      // forgiving here is what keeps an answer that arrives from being
      // dropped over a bracket that went missing.
      if (open === null) {
        return applied(applied(state, opening(event.messageId)), event);
      }
      // One that is **already complete**: nothing to add to. It is the store's
      // now, and a delta arriving for it is a stream repeating something it
      // should not (`docs/specs/wire.md`: no delta is repeated) -- appending
      // would say the answer twice.
      if (open.state !== "running") return state;
      return appended(state, event.messageId, {
        kind: "text",
        text: event.delta,
      });
    }

    case "TEXT_MESSAGE_END": {
      const ending = find(state, event.messageId);
      // Not held: the no-op for an end a re-attach derived for a message this
      // client never had open.
      if (ending === null || ending.state !== "running") return state;
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.id === event.messageId
            ? { ...message, state: "stored" }
            : message,
        ),
        writing: null,
        thinking: null,
        follows: event.messageId,
        leafId: event.messageId,
      };
    }

    case "REASONING_MESSAGE_START": {
      if (state.thinking === event.messageId) return state;
      const writing = state.writing;
      // Thinking belongs to the answer that is open. The backend announces
      // the answer before anything it thinks (`application/turns.py`), so
      // there is nothing to do with a stretch that belongs to no message.
      if (writing === null) return state;
      return {
        ...state,
        thinking: event.messageId,
        messages: state.messages.map((message) =>
          message.id === writing
            ? {
                ...message,
                parts: [
                  ...message.parts,
                  { kind: "reasoning", id: event.messageId, text: "" },
                ],
              }
            : message,
        ),
      };
    }

    case "REASONING_MESSAGE_CONTENT": {
      const writing = state.writing;
      if (writing === null) return state;
      if (state.thinking !== event.messageId) {
        // A stretch whose opening this client did not see: open it, then
        // append. A re-attach derives the same id from the same position, so
        // this is that stretch and not a second one.
        return applied(
          applied(state, {
            type: "REASONING_MESSAGE_START",
            messageId: event.messageId,
          }),
          event,
        );
      }
      return appended(state, writing, {
        kind: "reasoning",
        id: event.messageId,
        text: event.delta,
      });
    }

    case "REASONING_MESSAGE_END":
      return state.thinking === event.messageId
        ? { ...state, thinking: null }
        : state;

    case "RUN_FINISHED": {
      // **The terminal event of a run this client has already seen end.**
      // Reachable only from a re-attach at or past the last position: a
      // stream of its own run sets `runId` before its first event (the
      // response's headers, `started`), so the first ending always lands on
      // a run this state knows about. A message still open is closed all the
      // same -- an ending is never something to ignore while something is
      // waiting to be told it is over.
      if (state.runId === null && !anyRunning(state)) return state;
      return {
        ...ending(state, event.cancelled ? "cancelled" : "stored"),
        ended: event.cancelled ? (ENDED_BADLY.get("cancelled") ?? null) : null,
      };
    }

    case "RUN_ERROR": {
      if (state.runId === null && !anyRunning(state)) return state;
      const said = saidFor(event.code);
      const after = ending(state, "failed", said);
      // A run that failed before it announced anything has no message to put
      // the sentence on, so the thread says it instead.
      return state.writing === null ? { ...after, ended: said } : after;
    }
  }
}

/** Whether an answer is still being written. */
function anyRunning(state: ChatState): boolean {
  return state.messages.some((message) => message.state === "running");
}

/** A `TEXT_MESSAGE_START` for a message whose start never arrived. */
function opening(messageId: string): AguiEvent {
  return { type: "TEXT_MESSAGE_START", messageId, role: "assistant" };
}

/**
 * The messages without the one the refused turn added.
 *
 * **Only that one, and only if nothing hangs under it.** A message with a
 * child is one an answer is already being written under, and taking it away
 * would leave that answer with a parent the tree does not have -- which
 * assistant-ui refuses with an exception, so a refusal would take the whole
 * interface down with it.
 */
function withoutAsked(state: ChatState): ChatMessage[] {
  const asked = state.before?.asked ?? null;
  if (asked === null) return state.messages;
  const hasChild = state.messages.some((message) => message.parentId === asked);
  if (hasChild) return state.messages;
  return state.messages.filter((message) => message.id !== asked);
}

/**
 * That state, with the branch somewhere the messages really are.
 *
 * `leafId` and `follows` name messages, and a message that has just been
 * taken off the screen is not one of them. Falling back to what is left is a
 * guess, but it is a branch; naming something that is not there is an
 * exception thrown from inside the library on the next render.
 */
function where(state: ChatState): ChatState {
  const has = (id: string | null) =>
    id === null || state.messages.some((message) => message.id === id);
  const last = state.messages[state.messages.length - 1]?.id ?? null;
  const leafId = has(state.leafId) ? state.leafId : last;
  return {
    ...state,
    leafId,
    // The branch, never what was there before: a `follows` that is not in the
    // messages is not made good by another that may not be either.
    follows: has(state.follows) ? state.follows : leafId,
  };
}

/** That message, or `null`. */
function find(state: ChatState, id: string): ChatMessage | null {
  return state.messages.find((message) => message.id === id) ?? null;
}

/**
 * `piece` added to that message: onto its last part, or as a new one.
 *
 * **Onto the last part and no other.** An answer that thinks, says something
 * and thinks again holds three parts in the order it produced them, and a
 * delta belongs to whichever is open. Adding text to an earlier text part
 * would put a sentence in front of the thinking that came before it.
 */
function appended(
  state: ChatState,
  messageId: string,
  piece: ChatPart,
): ChatState {
  return {
    ...state,
    messages: state.messages.map((message) => {
      if (message.id !== messageId) return message;
      const last = message.parts[message.parts.length - 1];
      const same =
        last !== undefined && last.kind === piece.kind && last.id === piece.id;
      const parts = same
        ? [
            ...message.parts.slice(0, -1),
            { ...last, text: last.text + piece.text },
          ]
        : [...message.parts, piece];
      return { ...message, parts };
    }),
  };
}

/** The run is over: nothing is being written, and the answer stands as it is. */
function ending(
  state: ChatState,
  how: ChatMessageState,
  detail?: string,
): ChatState {
  return {
    ...state,
    runId: null,
    sending: false,
    writing: null,
    thinking: null,
    // **Every message still open, not only the one being written.** One
    // answer at a time is the rule and the platform keeps it, so there is
    // never more than one; a run that ends leaving two would leave the second
    // spinning for ever, which is worse than closing a message twice.
    messages: state.messages.map((message) =>
      message.state === "running"
        ? {
            ...message,
            state: how,
            ...(detail === undefined ? {} : { detail }),
          }
        : message,
    ),
  };
}

/**
 * Whether the store is still saying exactly what this state already holds.
 *
 * Only what is drawn: a message's place in the tree, who said it, and what it
 * says. Nothing else of a stored message is kept here.
 */
function unchanged(already: ChatMessage, fresh: ChatMessage): boolean {
  return (
    already.parentId === fresh.parentId &&
    already.role === fresh.role &&
    already.state === fresh.state &&
    already.detail === fresh.detail &&
    already.parts.length === fresh.parts.length &&
    already.parts.every((part, at) => {
      const other = fresh.parts[at];
      return (
        other !== undefined &&
        part.kind === other.kind &&
        part.id === other.id &&
        part.text === other.text
      );
    })
  );
}

/** One message of the API's, as the chat holds one. */
function held(message: Message): ChatMessage {
  return {
    id: message.id,
    parentId: message.parent_id,
    role: message.role,
    // Reasoning is shown and never stored (`docs/specs/conversations.md`), so
    // a message that came out of the store has text in it and nothing else.
    parts: message.parts
      .filter((part) => part.kind === "text")
      .map((part) => ({ kind: "text" as const, text: part.text })),
    state: "stored",
  };
}
