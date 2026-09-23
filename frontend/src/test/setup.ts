// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { resetSession } from "../session/session";

// One test leaves nothing behind for the next: the DOM, the spies, the hash
// the routing will read and the browser storage the rail state lives in.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  // A stubbed global outlives restoreAllMocks, and a test that stubbed
  // `fetch` would hand it to the next one.
  vi.unstubAllGlobals();
  location.hash = "";
  localStorage.clear();
  // The theme is an attribute on <html>, which `cleanup` does not touch.
  document.documentElement.removeAttribute("data-theme");
  // The session store is module state, and it is asked for once per page.
  resetSession();
});
