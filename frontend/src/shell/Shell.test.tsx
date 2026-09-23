// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { Session } from "../session/session";
import { json, stubFetch, type Call } from "../test/api";
import { conversation, id, message, opened, page } from "../test/conversations";
import { event, streamHeaders, streamed } from "../test/stream";
import { PANEL_KEY, Shell } from "./Shell";

const RUN = "11111111-2222-4333-8444-555555555555";

const SESSION: Session = {
  sign_in: true,
  local_development: false,
  providers: [{ id: "google", title: "Google" }],
  user: { id: "u-1", provider: "google", name: "Ada", email: "ada@x.test" },
};

/**
 * One agent, so the picker keeps out of the way of what is being tested, and
 * no conversations. A test that is about the history or a conversation
 * answers those calls itself and falls through to these for the rest.
 */
function answering(
  answer: (call: Call) => Response | undefined = () => undefined,
) {
  return stubFetch((call) => answer(call) ?? otherwise(call));
}

function otherwise(call: Call): Response {
  if (call.url.startsWith("/api/agents")) {
    return json({
      items: [{ id: "helper", title: "Helper", engine: "langgraph" }],
    });
  }
  return json(page([]));
}

/** Render, and let the agents and the history arrive. */
async function shell(
  signOut = () => Promise.resolve(),
  answer?: (call: Call) => Response | undefined,
) {
  const fetch = answering(answer);
  const drawn = render(<Shell session={SESSION} signOut={signOut} />);
  await waitFor(() => {
    expect(screen.queryByText("Loading the conversations…")).toBeNull();
  });
  await act(async () => {
    await Promise.resolve();
  });
  return { ...drawn, fetch };
}

const panel = () => screen.getByRole("complementary", { name: "Panel" });

/**
 * Ask for the phone layout, where the panel is a drawer.
 *
 * jsdom's window is 1024 wide and its `matchMedia` answers accordingly, so
 * without this every test is the wide one and the drawer is never the drawer.
 * `src/test/setup.ts` takes the stub back after each test.
 */
function narrow() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

test("the panel holds the brand, a new chat, the history and the profile", async () => {
  await shell();
  expect(screen.getByText("Robinauts")).toBeVisible();
  expect(screen.getByRole("button", { name: "New chat" })).toBeVisible();
  expect(screen.getByRole("navigation", { name: "History" })).toBeVisible();
  expect(
    screen.getByRole("list", { name: "Conversations" }),
  ).toBeEmptyDOMElement();
  expect(screen.getByText("Ada")).toBeVisible();
  expect(screen.getByText("ada@x.test")).toBeVisible();
  // Projects are out of the POC; nothing pretends otherwise.
  expect(screen.queryByRole("navigation", { name: "Projects" })).toBeNull();
});

test("collapsing the panel is remembered by this browser", async () => {
  await shell();
  fireEvent.click(screen.getByRole("button", { name: "Collapse the panel" }));
  expect(panel()).toHaveAttribute("data-collapsed", "true");
  expect(localStorage.getItem(`robinauts.${PANEL_KEY}`)).toBe("rail");
  fireEvent.click(screen.getByRole("button", { name: "Expand the panel" }));
  expect(panel()).toHaveAttribute("data-collapsed", "false");
  expect(localStorage.getItem(`robinauts.${PANEL_KEY}`)).toBe("open");
});

test("a browser that left it as a rail opens it as one", async () => {
  localStorage.setItem(`robinauts.${PANEL_KEY}`, "rail");
  await shell();
  expect(panel()).toHaveAttribute("data-collapsed", "true");
  expect(
    screen.getByRole("button", { name: "Expand the panel" }),
  ).toBeVisible();
});

test("the drawer opens from the header and closes with Escape", async () => {
  narrow();
  const { container } = await shell();
  const open = screen.getByRole("button", { name: "Open the panel" });
  // Held on to: open, the panel stops being a complementary landmark and
  // becomes the dialog it then is.
  const aside = panel();
  expect(aside).toHaveAttribute("data-drawer", "closed");
  fireEvent.click(open);
  expect(aside).toHaveAttribute("data-drawer", "open");
  // The focus goes into the drawer rather than staying behind it.
  expect(screen.getByRole("button", { name: "Close the panel" })).toHaveFocus();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(aside).toHaveAttribute("data-drawer", "closed");
  expect(container.querySelector("[data-backdrop]")).toBeNull();
  // Escape is a close like any other: the focus goes back to the button
  // that opened it, rather than being dropped on <body>.
  expect(open).toHaveFocus();
});

test("the drawer closes on the backdrop, and the focus comes back", async () => {
  narrow();
  const { container } = await shell();
  const open = screen.getByRole("button", { name: "Open the panel" });
  const aside = panel();
  fireEvent.click(open);
  const backdrop = container.querySelector("[data-backdrop]");
  expect(backdrop).not.toBeNull();
  fireEvent.click(backdrop as Element);
  expect(aside).toHaveAttribute("data-drawer", "closed");
  expect(open).toHaveFocus();
});

test("the closed drawer is out of a keyboard's way; the open one is a dialog", async () => {
  narrow();
  await shell();
  // jsdom answers `matchMedia` with "no match", so this is the narrow
  // layout: the panel is the drawer, and closed it is off the screen.
  const aside = panel();
  expect(aside).toHaveAttribute("inert");
  expect(aside).not.toHaveAttribute("aria-modal");

  fireEvent.click(screen.getByRole("button", { name: "Open the panel" }));
  expect(aside).not.toHaveAttribute("inert");
  expect(aside).toHaveAttribute("role", "dialog");
  expect(aside).toHaveAttribute("aria-modal", "true");
  // The page behind it does not scroll under it.
  expect(document.body.style.overflow).toBe("hidden");

  fireEvent.keyDown(document, { key: "Escape" });
  expect(aside).toHaveAttribute("inert");
  expect(document.body.style.overflow).toBe("");
});

/**
 * Say that this environment draws everything but `hidden`.
 *
 * jsdom has no layout engine and reports no boxes for anything, so without
 * this the trap cannot tell what is on the screen -- and the panel holds a
 * control that belongs to the other layout: "Collapse the panel" is
 * `max-md:hidden`, which at drawer width is `display: none`. A stop the
 * browser will not focus is a stop the trap must skip, or Tab deadlocks on
 * it. `vi.restoreAllMocks` in src/test/setup.ts puts this back.
 */
function drawsEverythingBut(hidden: Element) {
  const box = [new DOMRect(0, 0, 100, 20)] as unknown as DOMRectList;
  const none = [] as unknown as DOMRectList;
  vi.spyOn(Element.prototype, "getClientRects").mockImplementation(function (
    this: Element,
  ) {
    return this === hidden ? none : box;
  });
}

test("Tab goes round inside the open drawer, and never behind it", async () => {
  narrow();
  await shell();
  const outside = screen.getByRole("button", { name: "Open the panel" });
  fireEvent.click(outside);

  const collapse = screen.getByRole("button", { name: "Collapse the panel" });
  drawsEverythingBut(collapse);
  // The first stop is therefore the close button, not the collapse button
  // in front of it, which is the other layout's and is not drawn here.
  const first = screen.getByRole("button", { name: "Close the panel" });
  const last = screen.getByRole("button", { name: "Sign out" });

  last.focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(first).toHaveFocus();
  expect(collapse).not.toHaveFocus();

  fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
  expect(last).toHaveFocus();

  // The focus escaped some other way: the next Tab brings it back in.
  outside.focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(first).toHaveFocus();
});

test("a stop taken out of the tab order is not one", async () => {
  narrow();
  await shell();
  fireEvent.click(screen.getByRole("button", { name: "Open the panel" }));
  const collapse = screen.getByRole("button", { name: "Collapse the panel" });
  drawsEverythingBut(collapse);
  // A tabindex of -1 takes an element out of the tab order whatever it is,
  // so the first stop moves on to "New chat".
  screen
    .getByRole("button", { name: "Close the panel" })
    .setAttribute("tabindex", "-1");

  screen.getByRole("button", { name: "Sign out" }).focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(screen.getByRole("button", { name: "New chat" })).toHaveFocus();
});

test("a stop the page has made invisible is not one", async () => {
  narrow();
  await shell();
  fireEvent.click(screen.getByRole("button", { name: "Open the panel" }));
  const collapse = screen.getByRole("button", { name: "Collapse the panel" });
  drawsEverythingBut(collapse);
  // `visibility: hidden` still has a box, so `getClientRects` says nothing
  // about it and only the computed style does. Written inline, because
  // vitest loads no stylesheet and jsdom computes this much for real.
  screen.getByRole("button", { name: "Close the panel" }).style.visibility =
    "hidden";

  screen.getByRole("button", { name: "Sign out" }).focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(screen.getByRole("button", { name: "New chat" })).toHaveFocus();
});

test("with no layout to read, every stop counts", async () => {
  // jsdom as it is: no boxes for anything. Dropping every stop would be a
  // trap that traps nothing, so the DOM is what is left to go on.
  narrow();
  await shell();
  fireEvent.click(screen.getByRole("button", { name: "Open the panel" }));
  const last = screen.getByRole("button", { name: "Sign out" });
  last.focus();
  fireEvent.keyDown(document, { key: "Tab" });
  expect(
    screen.getByRole("button", { name: "Collapse the panel" }),
  ).toHaveFocus();
});

test("the agents are asked for once, however many new chats are started", async () => {
  const { fetch } = await shell();
  expect(
    fetch.mock.calls.filter(([url]) => String(url) === "/api/agents"),
  ).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  fireEvent.click(screen.getByRole("button", { name: "New chat" }));
  await act(async () => {
    await Promise.resolve();
  });
  expect(
    fetch.mock.calls.filter(([url]) => String(url) === "/api/agents"),
  ).toHaveLength(1);
});

test("signing out goes through the session, and a refusal is shown", async () => {
  const signOut = vi
    .fn<() => Promise<void>>()
    .mockRejectedValueOnce(new Error("the server said no"))
    .mockResolvedValueOnce(undefined);
  await shell(signOut);
  const button = screen.getByRole("button", { name: "Sign out" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(signOut).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert")).toHaveTextContent("the server said no");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  });
  expect(signOut).toHaveBeenCalledTimes(2);
});

test("the sign-out button is not left disabled once it has finished", async () => {
  // The shell is usually on its way out by now, so this only shows when it
  // is not -- and then a button stuck disabled is one nobody can press.
  await shell(() => Promise.resolve());
  const button = screen.getByRole("button", { name: "Sign out" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(screen.getByRole("button", { name: "Sign out" })).toBeEnabled();
});

test("the local mode banner is there only in the local mode", async () => {
  answering();
  const { rerender } = render(<Shell session={SESSION} />);
  await waitFor(() => {
    expect(screen.queryByText("Loading the conversations…")).toBeNull();
  });
  expect(screen.queryByRole("note")).toBeNull();
  rerender(<Shell session={{ ...SESSION, local_development: true }} />);
  expect(screen.getByRole("note")).toHaveTextContent(/Local development mode/);
});

test("with no sign-in there is nothing to sign out of", async () => {
  answering();
  render(
    <Shell session={{ ...SESSION, sign_in: false, local_development: true }} />,
  );
  await waitFor(() => {
    expect(screen.queryByText("Loading the conversations…")).toBeNull();
  });
  expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  expect(screen.getByText("Sign-in is off")).toBeVisible();
});

/** Let the event loop run once, which is what a queued `hashchange` waits for. */
const settled = () => new Promise((done) => setTimeout(done, 0));

/** The routes a conversation being open needs answered. */
function withConversation(call: Call): Response | undefined {
  if (call.url === `/api/conversations/${id(1)}`) {
    return json(opened(conversation(1, "Robins"), [], null));
  }
  if (call.url.startsWith("/api/conversations?")) {
    return json(page([conversation(1, "Robins")]));
  }
  return undefined;
}

test("the hash decides which of the two the main area is", async () => {
  location.hash = `#/c/${id(1)}`;
  await shell(undefined, withConversation);

  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Robins");
  expect(screen.queryByText("New chat", { selector: "h1" })).toBeNull();
  // The panel's current item follows the route.
  expect(screen.getByRole("link", { name: "Robins" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("the chat stands where the placeholder stood, on both routes", async () => {
  // The empty chat: the box, and the agent picker above it. What used to be
  // here was a sentence saying the box arrives with the chat.
  const { unmount } = await shell();
  expect(screen.getByRole("textbox", { name: "Message input" })).toBeVisible();
  expect(screen.queryByText(/The message box arrives/)).toBeNull();
  unmount();

  location.hash = `#/c/${id(1)}`;
  await shell(undefined, (call) => {
    if (call.url === `/api/conversations/${id(1)}`) {
      return json(
        opened(
          conversation(1, "Robins"),
          [
            message("m1", null, "user", "Why do robins sing?"),
            message("m2", "m1", "assistant", "Because it is quiet."),
          ],
          "m2",
        ),
      );
    }
    return withConversation(call);
  });
  await waitFor(() => {
    expect(screen.getByText("Because it is quiet.")).toBeInTheDocument();
  });
  expect(screen.getByRole("textbox", { name: "Message input" })).toBeVisible();
});

test("a first message routes to the conversation it created", async () => {
  const created = id(9);
  await shell(undefined, (call) => {
    if (call.url === "/api/turns") {
      return streamed(
        [event("RUN_FINISHED", { threadId: created, runId: RUN }, 2)],
        { headers: streamHeaders(RUN, created) },
      );
    }
    if (call.url === `/api/conversations/${created}`) {
      return json(opened(conversation(9, "Robins"), [], null));
    }
    if (call.url.startsWith("/api/conversations?")) {
      return json(page([conversation(9, "Robins")]));
    }
    return undefined;
  });

  const box = screen.getByRole("textbox", { name: "Message input" });
  fireEvent.change(box, { target: { value: "Why do robins sing?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await settled();
  });
  expect(location.hash).toBe(`#/c/${created}`);
  // The chat is not remounted by the route following it: the answer that is
  // arriving would be thrown away.
  await waitFor(() => {
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Robins",
    );
  });
});

test("an unknown hash is the empty chat, and the hash is left as it is", async () => {
  // The sign-in page reads this one for itself; nothing here may rewrite it.
  location.hash = "#/sign-in?error=not_allowed";
  await shell();
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "New chat",
  );
  expect(location.hash).toBe("#/sign-in?error=not_allowed");
});

test("New chat goes to the empty chat's own hash", async () => {
  location.hash = `#/c/${id(1)}`;
  await shell(undefined, withConversation);

  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));
    await settled();
  });
  expect(location.hash).toBe("#/");
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
    "New chat",
  );
});

test("opening a conversation from the panel is a navigation", async () => {
  await shell(undefined, withConversation);
  await act(async () => {
    fireEvent.click(screen.getByRole("link", { name: "Robins" }));
    await settled();
  });
  expect(location.hash).toBe(`#/c/${id(1)}`);
  await waitFor(() => {
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Robins",
    );
  });
});

test("deleting the conversation that is open leaves the page on the empty chat", async () => {
  location.hash = `#/c/${id(1)}`;
  let gone = false;
  await shell(undefined, (call) => {
    if (call.method === "DELETE") {
      gone = true;
      return json(null, 204);
    }
    if (gone) return json(page([]));
    return withConversation(call);
  });

  fireEvent.click(screen.getByRole("button", { name: "Actions for Robins" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /^Yes, delete/ }));
    await settled();
  });

  expect(location.hash).toBe("#/");
  await waitFor(() => {
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "New chat",
    );
  });
  expect(screen.getByText("No conversations yet.")).toBeVisible();
});
