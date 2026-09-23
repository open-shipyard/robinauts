// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * The left panel: the collapse button and the brand, "new chat", the
 * history, and the profile block pinned to the bottom
 * (`docs/specs/frontend.md`).
 *
 * **The panel is ours**, not the chat library's (ADR 0001). Nothing here
 * knows about assistant-ui, and nothing here ever will.
 *
 * There is **no projects section**: projects are out of the POC
 * (`docs/working-notes/poc-scope.md`, "Out"). The spec's panel has one, and
 * it goes here, between the history and the profile block, when they exist.
 *
 * The shape is neorc's, written again for this project; recorded in
 * `docs/legal/ip-clearance.md`.
 */
import { LogOut, PanelLeft, Plus, X } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";

import { ApiError } from "../api/client";
import type { User } from "../session/session";
import { useWide } from "./breakpoint";
import { ThemeToggle } from "./ThemeToggle";

/**
 * What can be tabbed to, in the order a browser would tab through it.
 *
 * `[tabindex="-1"]` is excluded from **every** clause, not only the last:
 * a `tabindex` of -1 takes an element out of the tab order whatever it is,
 * and a button carrying one would otherwise come back in through
 * `button:not([disabled])`.
 */
const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "select:not([disabled])",
  "input:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]",
]
  .map((one) => `${one}:not([tabindex="-1"])`)
  .join(", ");

/**
 * The stops a Tab would actually land on, in order.
 *
 * **What is drawn, not what is written.** This panel holds controls that
 * belong to the other layout -- "Collapse the panel" is `max-md:hidden`, so
 * at drawer width it is `display: none` -- and a selector cannot see that.
 * An element that is not rendered cannot take the focus, so `.focus()` on it
 * does nothing; having already called `preventDefault()`, the trap would
 * then leave the focus where it was and Tab would be dead.
 *
 * Four ways an element is not a stop, and they need different questions:
 *
 * - **`aria-hidden`**: drawn, but not there for a reader. The two must not
 *   disagree about what the panel contains.
 * - **`inert`**: the browser takes a whole subtree out of the tab order.
 *   The panel is never `inert` while the drawer is open -- that is what
 *   `inert` is for when it is closed -- so this only ever matches an inert
 *   subtree *inside* it.
 * - **`visibility: hidden`**: it has a box, so `getClientRects()` says
 *   nothing, and only the computed style does.
 * - **no box at all**: `display: none`, a hidden ancestor,
 *   `content-visibility`. `getClientRects()` is the question a browser
 *   itself answers, and the panel is asked first, because an environment
 *   that lays nothing out (jsdom, which has no layout engine) reports no
 *   boxes for *everything*: filtering on that would drop every stop and
 *   leave a trap that traps nothing. If the panel itself has no box, boxes
 *   are not being computed and the rest of the DOM is all there is to go on.
 *
 * What is **not** covered: an element scrolled out of an overflow container
 * (still a stop, and rightly), `opacity: 0` (still focusable, and still a
 * stop for a browser), and `tabindex` above 0, which nothing here uses and
 * which would reorder the tab sequence rather than leave it in DOM order.
 */
function unreachable(element: HTMLElement): boolean {
  if (element.closest("[aria-hidden='true']") !== null) return true;
  if (element.closest("[inert]") !== null) return true;
  const view = element.ownerDocument.defaultView;
  return (
    view !== null && view.getComputedStyle(element).visibility === "hidden"
  );
}

function stops(node: HTMLElement): HTMLElement[] {
  const named = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (element) => !unreachable(element),
  );
  if (node.getClientRects().length === 0) return named;
  return named.filter((element) => element.getClientRects().length > 0);
}

/** What the button that opens the drawer says it controls. */
export const PANEL_ID = "robinauts-panel";

export interface PanelProps {
  user: User | null;
  /** Collapsed to a rail of icons. Only on a screen wide enough for one. */
  collapsed: boolean;
  onCollapse: (collapsed: boolean) => void;
  /** Open as an overlay drawer. Only on a small screen. */
  drawer: boolean;
  onCloseDrawer: () => void;
  onNewChat: () => void;
  signOut: () => Promise<void>;
  /** Whether there is a sign-in to end. The local mode has none. */
  signInConfigured: boolean;
  /** What is focused when the drawer opens. */
  closeRef: RefObject<HTMLButtonElement | null>;
}

export function Panel({
  user,
  collapsed,
  onCollapse,
  drawer,
  onCloseDrawer,
  onNewChat,
  signOut,
  signInConfigured,
  closeRef,
}: PanelProps) {
  // Below the breakpoint the panel *is* the drawer; above it, it stands
  // beside the page and none of what follows applies.
  const asDrawer = !useWide();
  const open = asDrawer && drawer;
  const offScreen = asDrawer && !drawer;
  const self = useRef<HTMLElement>(null);
  useTrappedFocus(self, open);
  useLockedScroll(open);
  return (
    <aside
      id={PANEL_ID}
      ref={self}
      aria-label="Panel"
      // A closed drawer is translated off the screen, not removed, so
      // without this it is a handful of invisible tab stops -- sign-out
      // among them -- that a keyboard walks into and cannot see.
      inert={offScreen}
      // Open, it covers the page and is the only thing to be in.
      {...(open ? { role: "dialog" as const, "aria-modal": true } : {})}
      data-collapsed={collapsed}
      data-drawer={drawer ? "open" : "closed"}
      className={
        "z-20 flex h-screen shrink-0 flex-col gap-1 overflow-x-hidden overflow-y-auto border-r border-line bg-panel p-3 " +
        "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:w-70 max-md:transition-transform md:sticky md:top-0 " +
        (drawer ? "max-md:translate-x-0 " : "max-md:-translate-x-full ") +
        (collapsed ? "md:w-14 md:items-center md:px-2" : "md:w-70")
      }
    >
      <div
        className={`flex items-center gap-2 ${collapsed ? "md:flex-col" : ""}`}
      >
        <button
          type="button"
          title={collapsed ? "Expand the panel" : "Collapse the panel"}
          aria-label={collapsed ? "Expand the panel" : "Collapse the panel"}
          aria-expanded={!collapsed}
          onClick={() => {
            onCollapse(!collapsed);
          }}
          className="rounded-ui p-1.5 text-muted hover:bg-hover hover:text-ink max-md:hidden"
        >
          <PanelLeft size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          ref={closeRef}
          title="Close the panel"
          aria-label="Close the panel"
          onClick={onCloseDrawer}
          className="rounded-ui p-1.5 text-muted hover:bg-hover hover:text-ink md:hidden"
        >
          <X size={16} aria-hidden="true" />
        </button>
        {/* The brand is text. No logo image: this project ships no mark. */}
        <span className={`text-lg font-bold ${collapsed ? "md:hidden" : ""}`}>
          Robinauts
        </span>
      </div>

      <button
        type="button"
        title="New chat"
        onClick={onNewChat}
        className="my-2 flex items-center justify-center gap-2 rounded-ui border border-accent bg-accent px-3 py-2 font-semibold text-on-accent hover:opacity-90"
      >
        <Plus size={16} aria-hidden="true" />
        <span className={collapsed ? "md:hidden" : ""}>New chat</span>
      </button>

      <nav
        aria-label="History"
        className={`min-w-0 ${collapsed ? "md:hidden" : ""}`}
      >
        <h2 className="mt-2 mb-1 px-2 text-xs font-semibold tracking-wider text-muted uppercase">
          History
        </h2>
        {/* Empty until the history lands; the list is labelled so that what
            fills it needs no new structure around it. */}
        <ul aria-label="Conversations" className="m-0 list-none p-0" />
        <p className="px-2 text-sm text-muted">No conversations yet.</p>
      </nav>

      {/* Everything that is not the history sits at the foot of the panel,
          because `docs/specs/frontend.md` leaves no top bar to put it in.
          In the rail the toggle goes with the labels: three buttons do not
          fit in it, and the theme is not what a rail is for. */}
      <div className="mt-auto flex flex-col gap-2">
        <div className={collapsed ? "md:hidden" : ""}>
          <ThemeToggle />
        </div>
        <ProfileBlock
          user={user}
          collapsed={collapsed}
          signOut={signOut}
          signInConfigured={signInConfigured}
          onSignedOut={onCloseDrawer}
        />
      </div>
    </aside>
  );
}

/**
 * While the drawer is open, Tab stays inside it.
 *
 * It covers the page, so tabbing to what is behind it means a focus ring
 * nobody can see. The listener is on the document rather than on the panel,
 * because the focus may already be outside it -- on the backdrop's
 * neighbours, or nowhere at all -- and that is the case a trap has to catch.
 * Escape and the backdrop are how it is left (`Shell.tsx`).
 */
function useTrappedFocus(
  panel: RefObject<HTMLElement | null>,
  open: boolean,
): void {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const node = panel.current;
      if (node === null) return;
      const inside = stops(node);
      const first = inside[0];
      const last = inside[inside.length - 1];
      if (first === undefined || last === undefined) return;
      const active = document.activeElement;
      if (!node.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [panel, open]);
}

/** While the drawer is open, the page behind it does not scroll under it. */
function useLockedScroll(open: boolean): void {
  useEffect(() => {
    if (!open) return;
    const { body } = document;
    const before = body.style.overflow;
    body.style.overflow = "hidden";
    return () => {
      body.style.overflow = before;
    };
  }, [open]);
}

/** Who is signed in, and the way out. Pinned to the bottom of the panel. */
function ProfileBlock({
  user,
  collapsed,
  signOut,
  signInConfigured,
  onSignedOut,
}: {
  user: User | null;
  collapsed: boolean;
  signOut: () => Promise<void>;
  signInConfigured: boolean;
  onSignedOut: () => void;
}) {
  const [leaving, setLeaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  if (user === null) return null;
  const name = user.name ?? user.email ?? "Signed in";
  const leave = async () => {
    setLeaving(true);
    setRefused(null);
    try {
      await signOut();
      // The drawer belongs to a page that is about to be replaced by the
      // sign-in page; left open it would cover it.
      onSignedOut();
    } catch (failure) {
      // The session is still open, and the reader has to be told: a button
      // that quietly did nothing is worse than a refusal.
      setRefused(
        failure instanceof ApiError ? failure.detail : String(failure),
      );
    } finally {
      // However it went. Usually this component is on its way out, and
      // setting state on one that has gone is a no-op; when it is not --
      // signing out succeeded but the page is still here -- a button left
      // disabled is one nobody can press again.
      setLeaving(false);
    }
  };
  return (
    // A region rather than a labelled div: a name on a <div> names nothing.
    <section
      aria-label="Profile"
      className={`flex flex-wrap gap-2 border-t border-line pt-3 ${
        collapsed ? "md:flex-col md:items-center" : "items-center"
      }`}
    >
      {/* The initial is a picture of the name, and in the rail it is the
          only thing left of the profile, so it says whose it is rather than
          being hidden from a reader who cannot see it. */}
      <span
        role="img"
        aria-label={name}
        title={name}
        className="grid size-8 shrink-0 place-items-center rounded-pill bg-accent text-sm font-semibold text-on-accent"
      >
        {name.slice(0, 1).toUpperCase()}
      </span>
      <span
        className={`flex min-w-0 flex-1 flex-col text-sm leading-tight ${collapsed ? "md:hidden" : ""}`}
      >
        <span className="truncate" title={name}>
          {name}
        </span>
        {user.email !== undefined && user.email !== null && (
          <span className="truncate text-xs text-muted" title={user.email}>
            {user.email}
          </span>
        )}
      </span>
      {/* Outside the block above, so that the rail keeps it: collapsed, it
          is the icon alone, with its name on the button rather than beside
          it. In the local development mode there is no session to end --
          the route answers 204 and the same local user comes back -- and a
          button that changes nothing is worse than saying why there is
          none. */}
      {signInConfigured ? (
        <button
          type="button"
          onClick={() => void leave()}
          disabled={leaving}
          title="Sign out"
          aria-label="Sign out"
          className="flex shrink-0 items-center gap-1 rounded-ui p-1 text-xs text-muted hover:bg-hover hover:text-ink disabled:opacity-60"
        >
          <LogOut size={14} aria-hidden="true" />
          <span className={collapsed ? "md:hidden" : ""}>Sign out</span>
        </button>
      ) : (
        <span
          className={`shrink-0 text-xs text-muted ${collapsed ? "md:hidden" : ""}`}
        >
          Sign-in is off
        </span>
      )}
      {refused !== null && (
        <span role="alert" className="basis-full text-xs text-bad">
          Not signed out: {refused}
        </span>
      )}
    </section>
  );
}
