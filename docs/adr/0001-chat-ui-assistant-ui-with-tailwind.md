# ADR 0001 — Chat UI: assistant-ui styled components on Tailwind, behind an explicit seam

- Status: accepted
- Date: 2026-09-20

## Context

The first version of the frontend uses the open source
[assistant-ui](https://github.com/assistant-ui/assistant-ui) library for the
chat window (core spec, "Stack"). The rest of the frontend — the collapsible
left navigation, the sign-in page, the profile block — follows the neorc UI.

assistant-ui is distributed in two layers:

- `@assistant-ui/react` on npm (MIT): runtime, state, streaming and
  **unstyled** primitives. It has no Tailwind dependency.
- The **styled** components (`Thread`, `Composer`, messages, …) are not an
  npm dependency. They are source files in a shadcn-style registry; a CLI
  copies them into the consuming repo, where they are compiled by that
  repo's Tailwind build.

The npm packagings of the styled layer are not an option:
`@assistant-ui/react-ui` is stale (0.2.1, October 2025) and
`@assistant-ui/styles` is marked deprecated on npm. Checked 2026-09-20.

So there were two real options:

- **A.** Adopt Tailwind and copy the styled components.
- **B.** Use only the npm primitives and hand-write the markup and CSS, the
  way the neorc UI is written.

Three things in the core spec bear on the choice:

- *Compose over build* (goal 4): build only the glue and the missing parts.
- *Components are swappable* (goal 4): the project must be able to discard
  assistant-ui entirely.
- *Open source without restrictions* (goal 1): code that enters the tree
  from outside an ordinary signed-off PR is a provenance event and is
  recorded.

## Decision

**Option A**: Tailwind CSS, with assistant-ui's styled components vendored
into the repository — and assistant-ui confined behind an explicit seam, so
it can be discarded.

### The seam

There are two boundaries. assistant-ui exists only between them.

**1. The wire.** The backend knows nothing about assistant-ui. The UI and
the backend talk through a protocol that is not specific to any UI library —
AG-UI, per goal 4; its details are a separate ADR. No backend route, payload
or stored record is shaped by assistant-ui. In particular `assistant-cloud`,
which `@assistant-ui/react` pulls in as a dependency, is never configured:
conversations live in our database only (goal 3).

**2. The chat module.** In the frontend source:

```
src/
  shell/                 layout, navigation, sign-in, session, profile
  chat/
    index.ts             the seam: what the rest of the app may import
    assistant-ui/        the ONLY place assistant-ui exists
      vendor/            styled components copied from upstream
      ...                runtime wiring: our API/AG-UI client <-> assistant-ui
```

Rules:

- `src/chat/index.ts` exports a small interface owned by this project —
  in essence a `<Chat>` component taking a conversation id and callbacks
  (conversation created, title changed). Its types mention nothing from
  assistant-ui.
- Only files under `src/chat/assistant-ui/` may import `@assistant-ui/*`
  or anything under `vendor/`. An ESLint `no-restricted-imports` rule
  enforces this; it is a blocking check.
- The shell owns everything outside the chat window: the conversation list
  in the sidebar, "new chat", routing, session. These read our backend API
  directly. assistant-ui's thread-list runtime and components are not used
  for them.
- Design tokens are CSS custom properties, carried over from neorc. The
  Tailwind theme refers to the tokens; the tokens do not depend on Tailwind
  or on assistant-ui.

**The discard test.** Deleting `src/chat/assistant-ui/` and removing the
`@assistant-ui/*` packages must leave exactly one thing broken: the missing
implementation behind `src/chat/index.ts`. The shell, the routes, the
backend and the stored data are untouched. A change that would make this
untrue is a change to this ADR.

### Vendoring rules

- The copied files live only in `src/chat/assistant-ui/vendor/`, with a
  `README.md` stating the upstream URL, the exact upstream commit, local
  modifications, and how to re-sync. Upstream's MIT licence text is kept
  beside them.
- Every copy and every re-sync is an entry in `docs/legal/ip-clearance.md`,
  and the components are listed in `docs/legal/third-party.md`.
- Edits inside `vendor/` are kept minimal, so a re-sync is a small diff. Our
  own code goes outside it.
- The packages the styled components bring (`clsx`, `tailwind-merge`,
  `class-variance-authority`, `lucide-react`, `tw-animate-css`, Radix) pass
  the same bundle licence gate as every other dependency. Icons come from
  the one allowlisted icon package only; no fonts are added.

### Shell

The neorc shell (sidebar, rail collapse persisted in `localStorage`, bottom
profile block, OS-driven dark mode) is ported to Tailwind using the neorc
tokens as the theme, so the shell and the chat share one look. There is one
styling system in the frontend, not two.

## Consequences

Good:

- A working chat window — streaming, edit, branch picker, copy, scroll —
  in hours rather than days. Later features (tool-call UI, attachments)
  arrive as upstream components rather than as styling work.
- This is upstream's supported path, and a stack most React contributors
  know.
- The seam keeps the cost of leaving assistant-ui bounded and known.

Costs:

- Vendored files are closer to a fork than to a dependency: upstream fixes
  do not arrive through `npm update`. Each re-sync is a manual merge plus
  provenance bookkeeping.
- assistant-ui is pre-1.0 and changes often; the wiring under
  `src/chat/assistant-ui/` absorbs that churn.
- The neorc shell cannot be reused verbatim; porting it to Tailwind is
  about a day.
- The seam forbids some conveniences assistant-ui offers, such as its
  thread list and its cloud persistence. That is intended.

## Alternatives considered

- **B. Primitives only, hand-written CSS.** Fully dependency-based, reuses
  the neorc shell as is, nothing copied. Rejected because it builds a
  styled chat layer that already exists upstream, and pays that again for
  each future feature — against *compose over build*. It remains the
  fallback: the seam above is what would make the move cheap.
- **The npm-packaged styled layer** (`@assistant-ui/react-ui`,
  `@assistant-ui/styles`). Unmaintained or deprecated.
