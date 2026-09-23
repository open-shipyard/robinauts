// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * Opening a conversation: one call, and the branch it is read on.
 *
 * `GET /api/conversations/{id}` answers **one moment** of a conversation
 * (`docs/specs/conversations.md`, "Branches"): every message of the tree,
 * the message it opens on, and the run in flight or the way the last one
 * ended. One request, because two would disagree about a message completed
 * between them.
 *
 * The tree is walked here rather than sent twice: `leaf_id` and each
 * message's `parent_id` are what a branch is, and the server says so in
 * `OpenedConversationResponse`. The branches beside this one are in
 * `messages` all the same, so moving between them will take no new request
 * when the chat arrives (`docs/working-notes/poc-scope.md`, step 21).
 */
import { useCallback, useEffect, useState } from "react";

import { ApiError, detailOf, request } from "../api/client";
import type { components } from "../api/schema";
import type { ConversationId } from "../chat";

export type Conversation = components["schemas"]["ConversationSummary"];
export type Message = components["schemas"]["MessageView"];
export type Resume = components["schemas"]["ResumeView"];
export type EndedBadly = components["schemas"]["EndedBadlyView"];

/** What the panel and the view call a conversation nobody has named. */
export const UNTITLED = "Untitled";

/**
 * The title to show, which is never nothing.
 *
 * A conversation's title is the beginning of its first message and a message
 * with no text in it gives none (`docs/specs/conversations.md`, "Titles"), so
 * an empty title is a state the API really has. A blank line in the panel
 * would be a conversation nobody could aim at.
 */
export function shownTitle(title: string): string {
  return title.trim() === "" ? UNTITLED : title;
}

/** What a message says, as one string: its text parts, joined. */
export function textOf(message: Message): string {
  return message.parts
    .filter((part) => part.kind === "text")
    .map((part) => part.text)
    .join("");
}

/**
 * The branch a conversation is read on: the root above `leafId`, down to it.
 *
 * The walk is upwards -- every message carries the id of its parent -- and
 * the result is turned round, so what comes back is in the order it was
 * said. Two things it refuses to do with rows of ours that are not what they
 * should be, because an interface that hung would be worse than one that
 * shows a short branch: a parent that is not in `messages` ends the walk,
 * and a cycle ends it rather than going round for ever.
 *
 * `leafId` is `null` on a conversation with nothing in it -- and on one whose
 * first answer is still being produced, since a message lives in its run
 * until it is complete (`docs/specs/conversations.md`, "Persistence").
 */
export function branchOf(
  messages: readonly Message[],
  leafId: string | null,
): Message[] {
  const byId = new Map(messages.map((message) => [message.id, message]));
  const branch: Message[] = [];
  const seen = new Set<string>();
  let at = leafId;
  while (at !== null && !seen.has(at)) {
    const message = byId.get(at);
    if (message === undefined) break;
    seen.add(at);
    branch.push(message);
    at = message.parent_id;
  }
  return branch.reverse();
}

/** A conversation, as far as the one call has got. */
export type ConversationState =
  | { status: "loading" }
  | {
      status: "loaded";
      conversation: Conversation;
      /** The branch it opens on, oldest first. */
      branch: Message[];
      /** The run in flight, if there is one. */
      runId: string | null;
      resume: Resume | null;
      /** How the last run ended, when it ended badly and none is in flight. */
      endedBadly: EndedBadly | null;
    }
  | {
      status: "failed";
      detail: string;
      /** A 404: not there, or somebody else's -- one answer for both. */
      missing: boolean;
    };

/** One object, so that "still loading" is one value rather than a new one. */
const LOADING: ConversationState = { status: "loading" };

/**
 * That conversation, and a way to ask for it again.
 *
 * Asking again is what follows a cancel: a run that has been stopped is a
 * conversation in a different state, and the state is the server's to
 * report. It keeps what is on the screen while it runs, rather than putting
 * the whole view back to "Loading…" over a reread of the same conversation.
 */
export function useConversation(id: ConversationId): {
  state: ConversationState;
  reload: () => void;
} {
  /**
   * What is held, and **which conversation it is of**.
   *
   * Asked for again -- after a cancel -- this keeps what is on the screen
   * while the answer travels, rather than putting the view back to
   * "Loading…" over a reread of the same conversation. Asked for another
   * conversation, the id no longer matches and what is returned is
   * "Loading…", which is how a page that is about to be a different
   * conversation stops showing the one before it. Both without setting state
   * in an effect, which would be a render cascading into another.
   */
  const [held, setHeld] = useState<{
    of: ConversationId;
    state: ConversationState;
  }>(() => ({ of: id, state: LOADING }));
  const [asked, setAsked] = useState(0);
  const reload = useCallback(() => {
    setAsked((count) => count + 1);
  }, []);

  useEffect(() => {
    const dropped = new AbortController();
    request("get", "/api/conversations/{conversation_id}", {
      path: { conversation_id: id },
      signal: dropped.signal,
    }).then(
      (opened) => {
        // A body that arrived after this was dropped is as stale as a
        // failure would be: the read was abandoned, and publishing it would
        // put a conversation back on the screen that nothing asked for.
        if (dropped.signal.aborted) return;
        setHeld({
          of: id,
          state: {
            status: "loaded",
            conversation: opened.conversation,
            branch: branchOf(opened.messages, opened.leaf_id),
            runId: opened.run_id,
            resume: opened.resume,
            endedBadly: opened.ended_badly,
          },
        });
      },
      (failure: unknown) => {
        // An abort is this view going away, not something to report.
        if (dropped.signal.aborted) return;
        setHeld({
          of: id,
          state: {
            status: "failed",
            detail: detailOf(failure),
            missing: failure instanceof ApiError && failure.status === 404,
          },
        });
      },
    );
    return () => {
      dropped.abort();
    };
  }, [id, asked]);

  return { state: held.of === id ? held.state : LOADING, reload };
}

/** Stop the run that is in flight. */
export async function cancelRun(
  id: ConversationId,
  runId: string,
): Promise<void> {
  await request(
    "post",
    "/api/conversations/{conversation_id}/runs/{run_id}/cancel",
    { path: { conversation_id: id, run_id: runId } },
  );
}
