// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The shell: the panel on the left, the chat on the right, and no top bar
 * (`docs/specs/frontend.md`).
 *
 * Two things about the panel are decided here rather than inside it, because
 * both are about the window and not about the panel's contents:
 *
 * - **the rail**, remembered per browser, which is what the panel looks like
 *   on a screen wide enough to keep it beside the page;
 * - **the drawer**, which is what it is on a screen that is not. Which of
 *   the two applies is a CSS breakpoint's decision, so the drawer's state is
 *   kept whatever the width is and simply has no effect above `md`.
 *
 * The shape is neorc's, written again for this project; recorded in
 * `docs/legal/ip-clearance.md`.
 */
import { Menu } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ConversationView } from "../conversation/ConversationView";
import { conversationIn, useHistory } from "../history/history";
import { navigate, NEW_CHAT, useRoute } from "../router";
import type { Session } from "../session/session";
import { signOut as endSession } from "../session/session";
import { AgentPicker, useAgents, type Agents } from "./AgentPicker";
import { LocalModeBanner } from "./LocalModeBanner";
import { PANEL_ID, Panel } from "./Panel";
import { remember, remembered } from "./storage";

export const PANEL_KEY = "panel";

/** The rail, as this browser last left it. */
function usePanelCollapsed(): [boolean, (collapsed: boolean) => void] {
  const [collapsed, setCollapsed] = useState(
    () => remembered(PANEL_KEY) === "rail",
  );
  return [
    collapsed,
    (next: boolean) => {
      setCollapsed(next);
      remember(PANEL_KEY, next ? "rail" : "open");
    },
  ];
}

export function Shell({
  session,
  signOut = endSession,
}: {
  session: Session;
  signOut?: () => Promise<void>;
}) {
  const [collapsed, setCollapsed] = usePanelCollapsed();
  const [drawer, setDrawer] = useState(false);
  // Where the interface is: `#/` or `#/c/<id>` (`src/router.ts`).
  const route = useRoute();
  const history = useHistory();
  // "New chat" pressed while the empty chat is already up changes no hash
  // and so re-renders nothing; the count is what remounts the area, so
  // nothing typed into it carries over into the next one.
  const [chat, setChat] = useState(0);
  // Asked for here, not inside the empty chat: that is remounted on every
  // "New chat", and the agents do not change while the server is running.
  const agents = useAgents();
  const opener = useRef<HTMLButtonElement>(null);
  const closer = useRef<HTMLButtonElement>(null);

  // Closing puts the focus back on the button that opened it, so a keyboard
  // is never left on an element that has slid off the screen -- or, worse,
  // on <body>, which is where the focus falls when what held it goes away.
  const close = useCallback(() => {
    if (drawer) opener.current?.focus();
    setDrawer(false);
  }, [drawer]);

  // Escape closes the drawer, wherever the focus is inside it, and it is a
  // close like any other: the same `close`, so the focus comes back.
  useEffect(() => {
    if (!drawer) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [drawer, close]);

  // The focus follows the drawer into it when it opens, so a keyboard
  // carries on where the eye is rather than behind the overlay.
  useEffect(() => {
    if (drawer) closer.current?.focus();
  }, [drawer]);

  const current = route.kind === "conversation" ? route.id : null;
  const listed = conversationIn(history.items, current);

  return (
    <div className="flex min-h-screen bg-ground text-ink">
      <Panel
        user={session.user ?? null}
        history={history}
        current={current}
        collapsed={collapsed}
        onCollapse={setCollapsed}
        drawer={drawer}
        onCloseDrawer={close}
        onNewChat={() => {
          navigate(NEW_CHAT);
          setChat((count) => count + 1);
          close();
        }}
        signOut={signOut}
        signInConfigured={session.sign_in}
        closeRef={closer}
      />
      {drawer && (
        <div
          data-backdrop=""
          aria-hidden="true"
          onClick={close}
          className="fixed inset-0 z-10 bg-scrim md:hidden"
        />
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <LocalModeBanner local={session.local_development ?? false} />
        {/* The one thing above the chat, and only where the panel is a
            drawer: `docs/specs/frontend.md` says there is no top bar, so
            above the breakpoint this is gone and nothing replaces it. */}
        <button
          type="button"
          ref={opener}
          title="Open the panel"
          aria-label="Open the panel"
          aria-controls={PANEL_ID}
          aria-expanded={drawer}
          onClick={() => {
            setDrawer(true);
          }}
          className="m-2 self-start rounded-ui p-1.5 text-muted hover:bg-hover hover:text-ink md:hidden"
        >
          <Menu size={16} aria-hidden="true" />
        </button>
        {route.kind === "conversation" ? (
          <main className="flex min-w-0 flex-1 flex-col">
            {/* Keyed by the id: opening another conversation is another
                page, not this one with different props. */}
            <ConversationView
              key={route.id}
              id={route.id}
              title={listed === null ? null : listed.title}
              onReread={history.refresh}
            />
          </main>
        ) : (
          <main className="flex flex-1 flex-col items-center justify-center gap-4 px-4 pb-16">
            <EmptyChat key={chat} agents={agents} />
          </main>
        )}
      </div>
    </div>
  );
}

/**
 * Where the chat goes.
 *
 * The chat itself is step 21, behind `src/chat/` (ADR 0001); what stands
 * here until then is the part of an empty chat that is ours anyway -- the
 * invitation and the agent picker -- so that the shell can be seen and used
 * without it.
 */
function EmptyChat({ agents }: { agents: Agents }) {
  return (
    <>
      <h1 className="text-2xl font-semibold">New chat</h1>
      <AgentPicker agents={agents} />
      <p className="max-w-prose text-center text-muted">
        The message box arrives with the chat. Until then this is where a
        conversation will start.
      </p>
    </>
  );
}
