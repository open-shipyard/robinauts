// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { THEME_KEY, ThemeToggle, applyRememberedTheme } from "./ThemeToggle";

const theme = () => document.documentElement.getAttribute("data-theme");
const kept = () => localStorage.getItem(`robinauts.${THEME_KEY}`);

test("the operating system's is no attribute at all", () => {
  render(<ThemeToggle />);
  expect(theme()).toBeNull();
  expect(screen.getByRole("button", { name: "System" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("a choice is put on <html> and remembered", () => {
  render(<ThemeToggle />);
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  expect(theme()).toBe("dark");
  expect(kept()).toBe("dark");
  fireEvent.click(screen.getByRole("button", { name: "Light" }));
  expect(theme()).toBe("light");
  expect(kept()).toBe("light");
});

test("going back to the operating system's takes the attribute off", () => {
  render(<ThemeToggle />);
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  fireEvent.click(screen.getByRole("button", { name: "System" }));
  expect(theme()).toBeNull();
  expect(kept()).toBe("system");
});

test("what this browser chose is what it opens with", () => {
  localStorage.setItem(`robinauts.${THEME_KEY}`, "dark");
  render(<ThemeToggle />);
  expect(theme()).toBe("dark");
  expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("the remembered choice is applied before anything is drawn", () => {
  localStorage.setItem(`robinauts.${THEME_KEY}`, "light");
  applyRememberedTheme();
  expect(theme()).toBe("light");
});

test("a stored value that is not a theme is no choice", () => {
  localStorage.setItem(`robinauts.${THEME_KEY}`, "puce");
  applyRememberedTheme();
  expect(theme()).toBeNull();
});
