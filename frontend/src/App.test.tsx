// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("the application renders its heading", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Robinauts" })).toBeVisible();
});
