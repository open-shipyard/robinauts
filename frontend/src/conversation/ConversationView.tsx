// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * A conversation, read.
 *
 * **A stand-in.** The chat is step 21, behind `src/chat/` (ADR 0001); what
 * stands here until then is the part that is ours anyway -- the title, the
 * branch, and what the run is doing -- so that the history, the routing and
 * the conversation routes can be used and seen without it. There is no
 * message box and no streaming: a run in flight says so, and a reload is how
 * its answer appears.
 *
 * The title is the first line of the view, as an `<h1>`, because
 * `docs/specs/frontend.md` leaves no top bar to put it in. Renaming is in
 * the panel, on the row this conversation has there.
 */
import { useState } from "react";

import { detailOf } from "../api/client";
import type { ConversationId } from "../chat";
import { formatRoute, NEW_CHAT } from "../router";
import type { EndedBadly, Message } from "./conversation";
import { cancelRun, shownTitle, textOf, useConversation } from "./conversation";

/**
 * How a run that ended badly is said, one sentence per state.
 *
 * A `Map`, as `SIGN_IN_ERRORS` is and for the same reason: the states are
 * the API's closed set today, and a build that met a state it did not know
 * must still say that something went wrong rather than render whatever an
 * object inherited under that name.
 */
export const ENDED_BADLY = new Map<string, string>([
  ["cancelled", "The last answer was stopped before it was finished."],
  [
    "failed",
    "The last answer did not finish: something went wrong while it was being produced.",
  ],
  [
    "interrupted",
    "The last answer was interrupted when the server stopped. Asking again is how it is retried.",
  ],
]);

const ENDED_SOMEHOW = "The last answer did not finish.";

/** Who said it. The roles the format has in this version. */
const SPEAKER = new Map<string, string>([
  ["user", "You"],
  ["assistant", "Assistant"],
]);

export interface ConversationViewProps {
  id: ConversationId;
  /**
   * The title the panel is showing for this conversation, when it has it.
   *
   * The panel is where renaming happens, and its list is asked for again
   * after one; taking the title from there is what keeps the heading and the
   * row from saying two different things until the next reload. The two are
   * kept in step from this side as well: whenever this view rereads the
   * conversation, it asks for the list again too (`onReread`), so neither is
   * ever the older of the pair.
   */
  title?: string | null;
  /** The list is asked for again whenever this conversation is. */
  onReread?: () => void;
}

export function ConversationView({
  id,
  title,
  onReread,
}: ConversationViewProps) {
  const { state, reload } = useConversation(id);
  const reread = () => {
    reload();
    onReread?.();
  };

  if (state.status === "failed") {
    return (
      <article className="mx-auto w-full max-w-3xl px-4 py-8">
        <p role="alert" className="text-bad">
          {state.missing
            ? "This conversation is not here. It may have been deleted, or it was never yours."
            : `This conversation could not be opened: ${state.detail}`}
        </p>
        <p className="mt-3">
          <a href={formatRoute(NEW_CHAT)} className="text-link">
            Start a new chat
          </a>
        </p>
      </article>
    );
  }

  const heading =
    title ?? (state.status === "loaded" ? state.conversation.title : null);

  return (
    <article className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
      <h1 className="text-xl font-semibold">
        {heading === null ? "…" : shownTitle(heading)}
      </h1>
      {state.status === "loading" ? (
        <p className="text-muted">Loading the conversation…</p>
      ) : (
        <>
          {state.branch.length === 0 ? (
            <p className="text-muted">Nothing has been said in it yet.</p>
          ) : (
            <ol aria-label="Messages" className="m-0 flex flex-col gap-4 p-0">
              {state.branch.map((message) => (
                <MessageRow key={message.id} message={message} />
              ))}
            </ol>
          )}
          {state.runId !== null && (
            <Answering id={id} runId={state.runId} onCancelled={reread} />
          )}
          {state.endedBadly !== null && <Ended ended={state.endedBadly} />}
          <p className="text-sm text-muted">
            The message box arrives with the chat. Until then this is a
            conversation as it is stored.
          </p>
        </>
      )}
    </article>
  );
}

/** One message: who said it, when, what it says, and what produced it. */
function MessageRow({ message }: { message: Message }) {
  const said = textOf(message);
  return (
    <li className="m-0 list-none rounded-card border border-line bg-paper p-3">
      <p className="m-0 flex flex-wrap items-baseline gap-2 text-xs text-muted">
        <span className="font-semibold text-ink">
          {SPEAKER.get(message.role) ?? message.role}
        </span>
        <time dateTime={message.created_at}>{when(message.created_at)}</time>
      </p>
      {/* `whitespace-pre-wrap`, because what is stored is the text as it was
          produced: the paragraphs of an answer are its newlines. */}
      <p className="m-0 mt-1 whitespace-pre-wrap">
        {said === "" ? (
          <span className="text-muted">Nothing was said in this one.</span>
        ) : (
          said
        )}
      </p>
      {message.provenance !== null && (
        <p className="m-0 mt-2 text-xs text-muted">
          {message.provenance.agent} · {message.provenance.engine}
        </p>
      )}
    </li>
  );
}

/**
 * When it was said, in this browser's own way of writing a time.
 *
 * The machine-readable one is on `<time dateTime>`; this is the one a person
 * reads. A stored time that is not a time is shown as it is rather than as
 * "Invalid Date": our rows, and saying what is really there is more use.
 */
function when(at: string): string {
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * A run in flight.
 *
 * No streaming here: the events are AG-UI over server-sent events and belong
 * to the chat (`docs/specs/wire.md`, step 21). What this can do is say that
 * an answer is being produced, and stop it.
 */
function Answering({
  id,
  runId,
  onCancelled,
}: {
  id: ConversationId;
  runId: string;
  onCancelled: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const cancel = async () => {
    setBusy(true);
    setRefused(null);
    try {
      await cancelRun(id, runId);
      // The run's state is the server's to report, and cancelling is not
      // instant: what the conversation looks like now is asked for again.
      onCancelled();
    } catch (failure) {
      setRefused(detailOf(failure));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-card border border-line bg-panel p-3">
      <p role="status" className="m-0 text-muted">
        Answering…
      </p>
      <button
        type="button"
        onClick={() => void cancel()}
        disabled={busy}
        className="rounded-ui border border-edge bg-paper px-3 py-1 hover:bg-hover disabled:opacity-60"
      >
        Cancel
      </button>
      {refused !== null && (
        <p role="alert" className="m-0 basis-full text-sm text-bad">
          The answer was not stopped: {refused}
        </p>
      )}
    </div>
  );
}

/** How the last run ended, when it did not end well. */
function Ended({ ended }: { ended: EndedBadly }) {
  return (
    <p
      role="status"
      data-ended={ended.state}
      className="m-0 rounded-card border border-line bg-panel p-3 text-muted"
    >
      {ENDED_BADLY.get(ended.state) ?? ENDED_SOMEHOW}
    </p>
  );
}
