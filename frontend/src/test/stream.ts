// SPDX-License-Identifier: Apache-2.0
// Copyright The Robinauts Authors

/**
 * Streamed bodies to test against, and no network anywhere.
 *
 * A server-sent event stream is bytes arriving over time, and the two things
 * a test of one has to be able to say are **where the chunks end** -- a block
 * cut in half, a `\r` and its `\n` in different chunks -- and **when the
 * stream stops**, which is what a dropped connection is. So a body here is a
 * `ReadableStream` a test pushes into, wrapped in a `Response` the way Node's
 * own `fetch` would hand one over.
 */

/** A response whose body is those chunks, in order, and then ends. */
export function streamed(
  chunks: readonly string[],
  init: ResponseInit = {},
): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, init);
}

/** A body a test writes into by hand, and closes when it likes. */
export function writable(init: ResponseInit = {}): {
  response: Response;
  write: (chunk: string) => void;
  /** End it. A stream that ends with no terminal event is a dropped one. */
  close: () => void;
} {
  const encoder = new TextEncoder();
  let push: ReadableStreamDefaultController<Uint8Array> | null = null;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      push = controller;
    },
  });
  return {
    response: new Response(body, init),
    write: (chunk: string) => push?.enqueue(encoder.encode(chunk)),
    close: () => {
      try {
        push?.close();
      } catch {
        // Already closed, which is what a second close means.
      }
    },
  };
}

/** The headers every stream of ours carries (`docs/specs/wire.md`). */
export function streamHeaders(
  runId: string,
  conversationId: string,
): Record<string, string> {
  return {
    "content-type": "text/event-stream",
    "x-robinauts-run-id": runId,
    "x-robinauts-conversation-id": conversationId,
  };
}

/** One event as the backend writes it: a position, a type and its JSON. */
export function event(
  type: string,
  body: Record<string, unknown>,
  position?: number,
): string {
  const id = position === undefined ? "" : `id: ${position}\n`;
  return `${id}event: ${type}\ndata: ${JSON.stringify({ type, ...body })}\n\n`;
}
