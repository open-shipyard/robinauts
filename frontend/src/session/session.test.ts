// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors
import { expect, test, vi } from "vitest";

import { request } from "../api/client";
import {
  loadSession,
  signOut,
  snapshot,
  startSession,
  subscribe,
} from "./session";

/** Answers each `fetch` in turn with a body and a status. */
function answering(...answers: { status?: number; body?: unknown }[]) {
  const fetch = vi.fn<typeof globalThis.fetch>();
  for (const answer of answers) {
    fetch.mockResolvedValueOnce(
      new Response(
        answer.body === undefined ? null : JSON.stringify(answer.body),
        {
          status: answer.status ?? 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );
  }
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const SIGNED_IN = {
  sign_in: true,
  local_development: false,
  providers: [{ id: "google", title: "Google" }],
  user: { id: "u-1", provider: "google", name: "Ada", email: "ada@x.test" },
};

test("nothing is known until the first answer", () => {
  expect(snapshot().status).toBe("loading");
  expect(snapshot().session).toBeNull();
});

test("a user in the answer is somebody signed in", async () => {
  answering({ body: SIGNED_IN });
  await loadSession();
  expect(snapshot().status).toBe("signed-in");
  expect(snapshot().session?.user?.name).toBe("Ada");
});

test("no user is somebody signed out, and the providers are kept", async () => {
  answering({ body: { ...SIGNED_IN, user: null } });
  await loadSession();
  expect(snapshot().status).toBe("signed-out");
  expect(snapshot().session?.providers).toHaveLength(1);
});

test("the local development mode is signed in with sign-in off", async () => {
  answering({
    body: {
      sign_in: false,
      local_development: true,
      providers: [],
      user: { id: "u-0", provider: "!local", name: "Local developer" },
    },
  });
  await loadSession();
  expect(snapshot().status).toBe("signed-in");
  expect(snapshot().session?.local_development).toBe(true);
});

test("a first ask that fails leaves nothing but the refusal", async () => {
  answering({ status: 500, body: { error: "broken", detail: "no" } });
  await loadSession();
  expect(snapshot().status).toBe("signed-out");
  expect(snapshot().session).toBeNull();
  expect(snapshot().error?.status).toBe(500);
});

test("a retry says it is loading rather than showing a cleared refusal", async () => {
  answering({ status: 500, body: { error: "broken", detail: "no" } });
  await loadSession();
  expect(snapshot().status).toBe("signed-out");

  // The second ask, still in flight: nothing is known and nothing is being
  // claimed, so the page says the one true thing.
  let answer: (response: Response) => void = () => undefined;
  const pending = new Promise<Response>((settle) => {
    answer = settle;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn<typeof globalThis.fetch>().mockReturnValue(pending),
  );
  const asking = loadSession();
  expect(snapshot().status).toBe("loading");
  expect(snapshot().error).toBeNull();

  answer(
    new Response(JSON.stringify(SIGNED_IN), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  await asking;
  expect(snapshot().status).toBe("signed-in");
});

test("a later ask that fails keeps the session that was there", async () => {
  answering(
    { body: SIGNED_IN },
    { status: 503, body: { error: "down", detail: "not now" } },
  );
  await loadSession();
  await loadSession();
  expect(snapshot().status).toBe("signed-in");
  expect(snapshot().error?.status).toBe(503);
});

test("a 401 from any call flips the interface to signed out", async () => {
  answering(
    { body: SIGNED_IN },
    { status: 401, body: { error: "not_signed_in", detail: "gone" } },
  );
  await loadSession();
  const seen: string[] = [];
  const stop = subscribe(() => seen.push(snapshot().status));
  await expect(request("get", "/api/agents")).rejects.toThrow();
  stop();
  expect(seen).toContain("signed-out");
  expect(snapshot().status).toBe("signed-out");
  expect(snapshot().session?.user).toBeNull();
  // What the deployment offers is still true, and the sign-in page needs it.
  expect(snapshot().session?.providers).toHaveLength(1);
});

test("signing out posts JSON to the route, then asks again", async () => {
  const fetch = answering(
    { status: 204 },
    { body: { ...SIGNED_IN, user: null } },
  );
  await signOut();
  const [url, init] = fetch.mock.calls[0] ?? [];
  expect(url).toBe("/auth/logout");
  expect(init?.method).toBe("POST");
  expect((init?.headers as Record<string, string>)["content-type"]).toBe(
    "application/json",
  );
  expect(fetch.mock.calls[1]?.[0]).toBe("/auth/session");
  expect(snapshot().status).toBe("signed-out");
});

test("a sign-out whose re-ask fails is still a sign-out", async () => {
  answering(
    { body: SIGNED_IN },
    // The route answered: the session is gone on the server.
    { status: 204 },
    // And then the interface could not ask who is in any more.
    { status: 503, body: { error: "down", detail: "not now" } },
  );
  await loadSession();
  await signOut();
  // Not "still signed in with a refusal beside it": the session ended, and
  // showing the person as signed in would be showing them something false.
  expect(snapshot().status).toBe("signed-out");
  expect(snapshot().session?.user).toBeNull();
  // What the deployment offers is still true, and the sign-in page needs it.
  expect(snapshot().session?.providers).toHaveLength(1);
});

test("a 401 on signing out is a session already gone, not a refusal", async () => {
  answering(
    { status: 401, body: { error: "not_signed_in", detail: "gone" } },
    { body: { ...SIGNED_IN, user: null } },
  );
  await expect(signOut()).resolves.toBeUndefined();
  expect(snapshot().status).toBe("signed-out");
});

test("anything else on signing out is thrown, and the session stays", async () => {
  answering(
    { body: SIGNED_IN },
    { status: 500, body: { error: "broken", detail: "no" } },
  );
  await loadSession();
  await expect(signOut()).rejects.toThrow(/broken/);
  expect(snapshot().status).toBe("signed-in");
});

test("the session is asked for once, however often it is started", async () => {
  const fetch = answering({ body: SIGNED_IN });
  await startSession();
  await startSession();
  expect(fetch).toHaveBeenCalledTimes(1);
});
