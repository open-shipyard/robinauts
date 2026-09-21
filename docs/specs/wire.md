# The wire between the UI and the backend

The wire is one of the seams: the backend is not shaped by the UI library
([ADR 0001](../adr/0001-chat-ui-assistant-ui-with-tailwind.md)), and
another UI — or no UI — can drive it.

## A chat turn

- Streamed as [AG-UI](https://docs.ag-ui.com) events over **server-sent
  events**, on the same origin. The UI starts a turn with a POST; the
  response is the event stream.
- The request names the conversation, the parent message, and the new user
  message. **The server loads the history from its own store**; it does
  not accept a history from the browser. This makes our wire a profile of
  AG-UI, not its stock run input, and it is documented with the API.
- **The `api` layer emits the events.** The application yields the
  platform's own turn events; `api` maps them to AG-UI. One mapping,
  shared by both engines.
- **The frameworks' AG-UI bridges are not used** — neither
  `ag-ui-langgraph` nor Pydantic AI's `ag-ui` extra. Every turn goes
  through the agent port, the controller and the platform's persistence,
  and the wire is the same whatever the engine.
- Tool calls, when they come, already have AG-UI events.

## Everything else

- Conversations, projects, sharing, session, audit: a plain JSON API,
  described by OpenAPI. The OpenAPI document is committed as a snapshot,
  and the frontend's typed client is generated from it.

## Details likely to change

State of the packages, checked 2026-09-21:

| package | version | licence | note |
|---|---|---|---|
| `ag-ui-protocol` (PyPI) | 1.0.0 | MIT | event types and encoder; depends on pydantic only. Imported only in `api` |
| `@ag-ui/core`, `@ag-ui/client` (npm) | 1.0.0, released 2026-09-17 | MIT | |
| `@assistant-ui/react-ag-ui` (npm) | 0.0.60 | MIT | still pinned to `@ag-ui/client ^0.0.59` |

- The protocol is at 1.0. The immature piece is assistant-ui's bridge, and
  it sits inside `src/chat/assistant-ui/`, the place that is cheapest to
  replace. If it proves too immature, a small AG-UI client of our own
  takes its place behind the same seam; the wire does not change.
- Same-origin SSE passes the Content-Security-Policy
  (`connect-src 'self'`).
