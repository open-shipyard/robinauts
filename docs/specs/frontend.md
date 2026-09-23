# Frontend

## The interface

- The layout is neorc's: a collapsible left navigation panel, and the chat
  in the middle. There is no top bar.
- **The panel is ours**, not the chat library's
  ([ADR 0001](../adr/0001-chat-ui-assistant-ui-with-tailwind.md)). Top to
  bottom: the collapse button and the brand; "new chat"; the conversation
  history; projects; and, pinned to the bottom, the profile block with
  sign-out. Collapsed, it becomes an icon rail. The state is remembered
  per browser.
- The application opens on an empty chat, ready for a first message, with
  the agent to talk to selectable.
- On a small screen the panel becomes an overlay drawer opened from a
  button, and the chat is usable on a phone.
- The theme follows the operating system by default. A light / dark /
  system toggle is remembered per browser.
- Until someone is signed in, the sign-in page stands in place of every
  page ([sign-in.md](sign-in.md)). In local development mode there is no
  sign-in page, and a permanent banner says that sign-in is off.

## The chat window

- Built on [assistant-ui](https://github.com/assistant-ui/assistant-ui),
  on Tailwind CSS, with its styled components vendored into the
  repository. The rules for vendoring are in ADR 0001.
- **The seam.** assistant-ui exists only under `src/chat/assistant-ui/`.
  The rest of the application imports `src/chat/index.ts`, an interface
  this project owns. A lint rule enforces it. The panel, the history,
  routing and the session read our API directly; assistant-ui's thread
  list and its cloud are not used.
- **The discard test.** Deleting `src/chat/assistant-ui/` and the
  `@assistant-ui/*` packages breaks one thing: the implementation behind
  `src/chat/index.ts`.
- It talks to the backend over AG-UI ([wire.md](wire.md)).

## Shape and delivery

- A single-page application. No Next.js, no server-side rendering, no Node
  process in production.
- The backend serves the built files, under a strict
  Content-Security-Policy. **No CDN, no external font, no third-party
  origin**: an air-gapped install works.
- System fonts. One allowlisted icon package. No third-party logos.
- The deliverable is **one Python wheel** that contains the built
  frontend: `pip install` plus a PostgreSQL is a complete deployment. The
  bundle is built only in CI; built assets are never committed, and a
  bundle built on a laptop is never released. A container image is
  planned.

## Supply chain

neorc's rules (`neorc/contributing/js-dependencies.md`):

- few dependencies, each one looked into before adoption — including what
  `npm pack` actually serves;
- exact versions, `npm ci` only, install scripts disabled;
- a build-time licence allowlist that fails the build, and a committed
  list of bundled packages that CI compares with the build
  ([open-source.md](open-source.md));
- `npm audit` and `npm audit signatures`;
- one dependency change per pull request; a 10-day Dependabot cooldown;
- a bundle size budget.

## Details likely to change

- Vite, React 19, TypeScript in strict mode, Vitest, ESLint. Hash routing,
  so the static files need no fallback route. Served under `/ui/`.
- The typed API client is generated from the committed OpenAPI snapshot.
- Content-Security-Policy: `default-src 'none'`; `script-src`, `font-src`,
  `connect-src` `'self'`; `style-src 'self' 'unsafe-inline'`;
  `img-src 'self' data:`; `frame-ancestors 'none'`; plus `nosniff`.
- Design tokens are CSS custom properties carried over from neorc; the
  Tailwind theme refers to them, so they survive a change of either
  Tailwind or the chat library.
- Packages the styled components bring, as pinned on 2026-09-22 when they
  were copied in: `clsx`, `tailwind-merge`, `class-variance-authority`,
  `lucide-react`, `tw-animate-css`, Radix (the `radix-ui` package, which
  `@assistant-ui/react` depends on anyway), and two the list did not expect —
  `remark-gfm`, for the Markdown, and `tw-shimmer`, a second Tailwind plugin
  the copied components are written against. The two Tailwind plugins are
  reached only through `src/styles.css`, so they are named by hand in
  `CSS_PACKAGES`. `assistant-cloud` arrives as a dependency of
  `@assistant-ui/react`; it is never configured.
- The wheel carries `THIRD_PARTY_LICENSES.txt`, listed in its
  `license-files`.

## Open

- The bundle size budget. neorc's 500 KB does not fit a chat UI with
  Markdown and syntax highlighting; it is set once a first bundle exists.
