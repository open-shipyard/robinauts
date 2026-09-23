// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyRememberedTheme } from "./shell/ThemeToggle";
import "./styles.css";

// Before the first paint, so a browser set to dark by hand does not show the
// light page for a frame first.
applyRememberedTheme();

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root to mount on");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
