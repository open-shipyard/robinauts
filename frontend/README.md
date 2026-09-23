# The Robinauts web UI

A single-page application: Vite, React, TypeScript, Vitest, ESLint. It is
served by the backend under `/ui/`, and it ships inside the `robinauts` wheel
([../docs/specs/frontend.md](../docs/specs/frontend.md)).

What is here is the shell: the design tokens and the Tailwind theme over
them, the collapsible panel with the profile block, the session and the
sign-in page, the theme toggle and the banner of the local development mode.
The history, the routing and the chat arrive in the steps after this one
([../docs/working-notes/poc-scope.md](../docs/working-notes/poc-scope.md)); the
main area is a placeholder with the agent picker in it until they do.

## Running it

Node.js at the version in `.nvmrc`; with [nvm](https://github.com/nvm-sh/nvm),
`nvm use` in this directory.

    npm ci                  # never `npm install`, except to change a dependency
    npm run dev             # the dev server, proxying the API to 127.0.0.1:8000

`npm run dev` expects a local `robinauts start` on port 8000: `/api`, `/auth`,
`/health` and `/openapi.json` are proxied to it, with nothing in the way of a
run's event stream.

The backend to run beside it is the **local development mode**
([../docs/specs/sign-in.md](../docs/specs/sign-in.md)): no identity provider
to register anything with, one fixed local user, loopback only, and the
interface shows its permanent banner. `robinauts start` and its
`--dev-no-sign-in` flag arrive with the wheel, so until then the mode is
asked for through `create_app`, from `../backend/`:

    DB=postgresql://127.0.0.1/robinauts uv run python -c "
    import uvicorn, os
    from robinauts.app import create_app
    uvicorn.run(create_app(local_development_host='127.0.0.1',
                           database_url=os.environ['DB'],
                           config_path=os.environ.get('ROBINAUTS_CONFIG')),
                host='127.0.0.1', port=8000)"

With `ROBINAUTS_CONFIG` naming a file, only its model tables are read, and
the agents it defines are the ones the picker offers.

Signing in for real needs a `public_url`, a provider registration and the
redirect URI — that is a deployment, not a laptop. To see the sign-in page
itself, use the fixture server below.

### Looking at the shell without a backend

`scripts/fixture-server.mjs` serves a built `dist/` and answers
`/auth/session` and `/api/agents` from fixtures, which is how the states that
would otherwise take a real sign-in are looked at:

    npm run build
    node scripts/fixture-server.mjs signed-out 5173

The scenes are `signed-in`, `signed-out`, `local`, `one-agent`, `no-agents`.
It is a development tool: it is in no check, no bundle and no wheel.

## The checks

    scripts/check-frontend.sh   # from the root of the repository: all of it

or one at a time, from here:

    node scripts/check-licences.mjs   # the licence policy, and the exact pins
    npm run check-format    # prettier
    npm run lint            # eslint, including the seam rule of ADR 0001
    npm run typecheck       # tsc, in strict mode
    npm test -- --run       # vitest
    npm run build           # the bundle, its licence gate and its size budget

`npm run format` rewrites what `check-format` complains about.

## Things a tool writes

Two of these are generated and thrown away; one is generated and committed.

- `src/api/schema.d.ts` — **not committed.** The types of our own API, written
  by `npm run generate` from `../backend/openapi.json`, the snapshot the
  backend commits. `dev`, `build`, `typecheck`, `lint` and `test` all run
  `generate` first, so a route that changed without the snapshot being
  refreshed is a failing check here rather than a surprise in a browser.
- `dist/` — **not committed.** The built assets; CI builds them, and a bundle
  built on a laptop is never released.
- `bundled-packages.txt` — **committed**, and written by `npm run build`: it is
  how a new package in the bundle becomes a line in a diff. Never edit it by
  hand. `scripts/check-frontend.sh` and CI set `CHECK_BUNDLED=1`, which makes
  the build compare the file instead of rewriting it, so a package that entered
  the bundle is a red build rather than a quiet amendment.

## The rules

- Dependencies: [../docs/contributing/js-dependencies.md](../docs/contributing/js-dependencies.md).
  Few of them, each one vetted, exact versions, install scripts off, a licence
  allowlist the build enforces over the bundle and
  `scripts/check-licences.mjs` enforces over everything installed, and one
  dependency change per pull request — never a version published fewer than
  ten days ago, first pin included.
- The chat seam: [../docs/adr/0001-chat-ui-assistant-ui-with-tailwind.md](../docs/adr/0001-chat-ui-assistant-ui-with-tailwind.md).
  assistant-ui will live only under `src/chat/assistant-ui/`; the rest of the
  application imports `src/chat/index.ts`. `eslint.config.js` refuses anything
  else, and `src/test/seam-rule.test.ts` proves the rule still fires.
- Styling: `src/tokens.css` holds the design tokens as CSS custom properties
  and is the source of truth for every colour and radius; `src/styles.css`
  imports Tailwind and maps its theme onto them, so a component is written in
  Tailwind utilities (`bg-panel`, `text-muted`, `rounded-ui`) and the tokens
  survive a change of Tailwind. Plain `.css` only: no CSS Modules, no
  preprocessor, no `<style>` in `index.html`.
- Nothing from a third-party origin: no CDN, no external font, no inline
  script. An air-gapped install has to work. Icons come from `lucide-react`,
  the one allowlisted icon package, imported by name so that the bundle
  carries the icons used and no more.
- Every file carries the SPDX header ([../CONTRIBUTING.md](../CONTRIBUTING.md));
  what cannot is listed in [../REUSE.toml](../REUSE.toml).
