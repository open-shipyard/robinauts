// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import type { History } from "../history/history";
import { Panel, PANEL_ID } from "./Panel";
import { DEFAULT_WIDTH, MIN_WIDTH, PANEL_WIDTH_KEY } from "./PanelResizer";

const history: History = {
  status: "ready",
  items: [],
  more: false,
  loadingMore: false,
  refreshing: false,
  error: null,
  refresh: () => undefined,
  loadMore: () => undefined,
  rename: () => Promise.resolve(),
  archive: () => Promise.resolve(),
  remove: () => Promise.resolve(),
};

function drawn(collapsed = false) {
  return render(
    <Panel
      history={history}
      current={null}
      collapsed={collapsed}
      onCollapse={() => undefined}
      onNewChat={() => undefined}
      onSearch={() => undefined}
    />,
  );
}

const panel = () => document.getElementById(PANEL_ID) as HTMLElement;
const edge = () => screen.getByRole("separator");
const stored = () => localStorage.getItem(`robinauts.${PANEL_WIDTH_KEY}`);

afterEach(() => {
  window.innerWidth = 1024;
});

test("the arrow keys move the right edge, Right widening it, and keep the width", () => {
  drawn();
  expect(edge()).toHaveAttribute("aria-valuenow", String(DEFAULT_WIDTH));
  expect(panel().style.getPropertyValue("--panel-width")).toBe("280px");
  fireEvent.keyDown(edge(), { key: "ArrowRight" });
  expect(edge()).toHaveAttribute("aria-valuenow", "296");
  expect(stored()).toBe("296");
  fireEvent.keyDown(edge(), { key: "ArrowLeft" });
  fireEvent.keyDown(edge(), { key: "ArrowLeft" });
  expect(edge()).toHaveAttribute("aria-valuenow", "264");
  fireEvent.keyDown(edge(), { key: "End" });
  expect(edge()).toHaveAttribute("aria-valuenow", "409");
  fireEvent.keyDown(edge(), { key: "Home" });
  expect(edge()).toHaveAttribute("aria-valuenow", String(MIN_WIDTH));
});

test("dragging the right edge to the right widens it, kept when let go", () => {
  drawn();
  fireEvent.pointerDown(edge(), { button: 0, clientX: 280, pointerId: 1 });
  fireEvent.pointerMove(edge(), { clientX: 330, pointerId: 1 });
  expect(edge()).toHaveAttribute("aria-valuenow", "330");
  expect(stored()).toBeNull();
  fireEvent.pointerUp(edge(), { clientX: 350, pointerId: 1 });
  expect(stored()).toBe("350");
});

test("a remembered width comes back, and a bad one is the default", () => {
  localStorage.setItem(`robinauts.${PANEL_WIDTH_KEY}`, "300");
  const { unmount } = drawn();
  expect(edge()).toHaveAttribute("aria-valuenow", "300");
  unmount();
  localStorage.setItem(`robinauts.${PANEL_WIDTH_KEY}`, "wide");
  const again = drawn();
  expect(edge()).toHaveAttribute("aria-valuenow", "280");
  again.unmount();
  localStorage.setItem(`robinauts.${PANEL_WIDTH_KEY}`, "-5");
  drawn();
  expect(edge()).toHaveAttribute("aria-valuenow", "280");
});

test("a narrower window narrows the most the panel may take", () => {
  drawn();
  fireEvent.keyDown(edge(), { key: "End" });
  act(() => {
    window.innerWidth = 800;
    window.dispatchEvent(new Event("resize"));
  });
  expect(edge()).toHaveAttribute("aria-valuemax", "320");
  expect(edge()).toHaveAttribute("aria-valuenow", "320");
});

test("the rail has no edge to drag", () => {
  drawn(true);
  expect(screen.queryByRole("separator")).toBeNull();
});

test("the drawer has no edge to drag", () => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  drawn();
  expect(screen.queryByRole("separator")).toBeNull();
});
