// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * Resume, beside Refresh on the last answer when it failed (`docs/specs/ui.md`).
 *
 * assistant-ui has no action for it, so this is a button of ours in the
 * vendored action bar, and what it does comes down from the chat.
 */
import { useAuiState } from "@assistant-ui/react";
import { PlayIcon } from "lucide-react";
import { createContext, useContext } from "react";

import { TooltipIconButton } from "./vendor/components/assistant-ui/elements/tooltip-icon-button";

/** The chat's `onResume`, handed down past the Thread. */
export const ResumeAnswer = createContext<
  ((answerId: string) => Promise<void>) | null
>(null);

export function ResumeButton() {
  const resume = useContext(ResumeAnswer);
  const id = useAuiState((s) => s.message.id);
  // The backend resumes the conversation's latest turn alone.
  const resumable = useAuiState(
    (s) =>
      s.message.isLast &&
      s.message.status?.type === "incomplete" &&
      s.message.status.reason === "error",
  );
  if (resume === null || !resumable) return null;
  return (
    <TooltipIconButton tooltip="Resume" onClick={() => void resume(id)}>
      <PlayIcon />
    </TooltipIconButton>
  );
}
