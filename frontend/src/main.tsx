// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("index.html has no #root to mount on");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
