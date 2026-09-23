// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The chat window: the vendored Thread, over our runtime.
 *
 * Everything drawn here is assistant-ui's copied components
 * (`./vendor/README.md`) -- the message list, the box, the action bar with
 * edit, regenerate and copy, the branch picker, the collapsed block of
 * thinking -- and everything they are given is ours (`./runtime.tsx`). What
 * is written in this file is only what is between the two: the two things
 * about a conversation the Thread has no place for.
 *
 * - **A conversation that is not here**, which is a 404 and is what somebody
 *   else's conversation answers as well (`docs/specs/privacy.md`). There is
 *   no thread to show, so this stands in place of one.
 * - **A sentence about the last run** where no message carries it: a run that
 *   failed before it said anything, a cancellation, a turn the server refused
 *   (`docs/specs/wire.md`). Where there **is** a message, the Thread shows it
 *   under that message itself and this says nothing.
 * - **A notice about what the person just did**, which is a different thing
 *   and outlives the run that follows it: a message that was not sent, a
 *   stop that did not reach the server. Only their next turn clears it.
 *
 * The welcome slot is the shell's agent picker on an empty chat: in the
 * Thread's empty state the welcome sits directly above the box, which is
 * where a choice of who you are about to talk to belongs
 * (`docs/specs/agents.md`).
 */
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useMemo } from "react";

import type { ChatProps } from "../index";
import { useChat } from "./runtime";
import { Thread } from "./vendor/components/assistant-ui/elements/thread.aui";

export function Chat(props: ChatProps) {
  const { state, runtime } = useChat(props);
  const welcome = props.welcome;
  // Held across renders: a component identity that changed on every one of
  // them would remount the welcome -- and a `<select>` that is remounted
  // loses the focus, on every keystroke in the box beside it. What the shell
  // passes is held across its own renders for the same reason.
  const components = useMemo(
    () => ({ Welcome: () => <>{welcome}</> }),
    [welcome],
  );

  if (state.failure !== null) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-8">
        <p role="alert" className="text-bad">
          {state.failure.missing
            ? "This conversation is not here. It may have been deleted, or it was never yours."
            : `This conversation could not be opened: ${state.failure.detail}`}
        </p>
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {/* `min-h-0` on both, so the Thread's own scrolling viewport is what
          scrolls rather than the page: a flex child's minimum size is its
          content unless it is told otherwise. */}
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1">
          <Thread components={components} />
        </div>
        {state.ended !== null && (
          <p
            role="status"
            data-ended=""
            className="mx-auto w-full max-w-3xl px-6 pb-4 text-sm text-muted-foreground"
          >
            {state.ended}
          </p>
        )}
        {state.notice !== null && (
          <p
            role="alert"
            data-notice=""
            className="mx-auto w-full max-w-3xl px-6 pb-4 text-sm text-bad"
          >
            {state.notice}
          </p>
        )}
      </div>
    </AssistantRuntimeProvider>
  );
}
