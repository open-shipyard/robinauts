// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * A stubbed `fetch` that answers by route, for the tests that need several.
 *
 * Every test here stubs `fetch` itself and none of them touches a network
 * (`src/test/setup.ts` takes the stub back afterwards). Once a test renders
 * more than one thing that calls the API -- the shell asks for the agents
 * and for the conversations, and a view asks for one of them -- answering
 * every call with one body is answering the wrong question, so what is
 * stubbed is a little router.
 */
import { vi, type Mock } from "vitest";

/** One call, as the answering function is shown it. */
export interface Call {
  url: string;
  /** Upper case, as the client sends it. */
  method: string;
  /** The JSON body it sent, if it sent one. */
  body: unknown;
}

/** An answer in the shape every route of ours answers in. */
export function json(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A refusal in the one shape the API makes them (`api/errors.py`). */
export function refusal(
  status: number,
  error: string,
  detail: string,
): Response {
  return json({ error, detail }, status);
}

/** Answer every call with `answer`, and remember what was asked. */
export function stubFetch(
  answer: (call: Call) => Response,
): Mock<typeof globalThis.fetch> {
  const fetch = vi.fn<typeof globalThis.fetch>((input, init) => {
    const raw = init?.body;
    const body: unknown = typeof raw === "string" ? JSON.parse(raw) : undefined;
    return Promise.resolve(
      answer({
        url: String(input),
        method: (init?.method ?? "GET").toUpperCase(),
        body,
      }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

/** The calls made to one path, in order. */
export function callsTo(
  fetch: Mock<typeof globalThis.fetch>,
  path: string,
  method = "GET",
): { url: string; body: unknown }[] {
  return fetch.mock.calls
    .map(([input, init]) => ({
      url: String(input),
      method: (init?.method ?? "GET").toUpperCase(),
      raw: init?.body,
    }))
    .filter(
      (call) =>
        call.method === method &&
        (call.url === path || call.url.startsWith(`${path}?`)),
    )
    .map((call) => ({
      url: call.url,
      body: typeof call.raw === "string" ? JSON.parse(call.raw) : undefined,
    }));
}
