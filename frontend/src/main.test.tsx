// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { expect, test, vi } from "vitest";

import { THEME_KEY } from "./shell/ThemeToggle";

/**
 * What `<html>` looked like at the moment the first render was asked for.
 *
 * `vi.hoisted`, because `vi.mock`'s factory is lifted above everything else
 * in this file and could not otherwise see it.
 */
const atFirstRender = vi.hoisted(() => ({
  theme: "never rendered" as unknown,
}));

vi.mock("react-dom/client", () => ({
  createRoot: () => ({
    render: () => {
      atFirstRender.theme = document.documentElement.getAttribute("data-theme");
    },
  }),
}));

test("the remembered theme is on <html> before the first render", async () => {
  // A browser told to be dark, on a machine that is not: without the call in
  // main.tsx the light page would be painted first and the theme applied by
  // the toggle's effect, one frame later.
  localStorage.setItem(`robinauts.${THEME_KEY}`, "dark");
  document.body.innerHTML = '<div id="root"></div>';

  await import("./main");

  expect(atFirstRender.theme).toBe("dark");
});
