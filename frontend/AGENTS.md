# For coding agents working in frontend/

This package ships to users inside the `robinauts` wheel and runs in a browser
with a signed-in person's session cookie, so any code in it can do whatever
that person may. Its dependency rules are in
[../docs/contributing/js-dependencies.md](../docs/contributing/js-dependencies.md);
read them before touching `package.json`, `package-lock.json`, `.npmrc`,
`vite.config.ts` or `bundled-packages.txt`.

Do not:

- add, remove or bump a package as part of another change. A dependency change
  is its own pull request, vetted as the rules say, with the cooldown kept: no
  version published fewer than 10 days ago. **That holds for a first pin as
  much as for a bump** -- `npm view <pkg> version` is often a release of that
  morning. Read `npm view <pkg> time --json`, pin the newest version at least
  ten days old, and say in the pull request which dates you read. No check can
  catch this for you: the publish dates are not in the lockfile.
- loosen the licence allowlist in `vite.config.ts`, the size budget, or the
  Content-Security-Policy the backend serves, to make a library fit. Choose
  another library, or write the code.
- run `npm install`. Installs are `npm ci`; `save-exact` and `ignore-scripts`
  stay on in `.npmrc`.
- commit `dist/`, `src/api/schema.d.ts` or `node_modules/`. The assets are
  built by CI and by the wheel build, never committed.
- edit `bundled-packages.txt` by hand. The build writes it; a change in it is
  what a reviewer looks at.
- import `@assistant-ui/*` or anything under `src/chat/assistant-ui/` from
  outside that directory, and do not weaken the rules in `eslint.config.js` or
  the tests in `src/test/seam-rule.test.ts` that prove they fire. That seam is
  [ADR 0001](../docs/adr/0001-chat-ui-assistant-ui-with-tailwind.md); what the
  rest of the application may use goes in `src/chat/index.ts`. The rule reads
  a path **segment**, so no spelling of a path is a way round it. Nor reach
  for a specifier no rule can read: `import()` or
  `new URL(..., import.meta.url)` with a variable or an interpolated
  template, and `import.meta.glob`, are refused outside
  `src/chat/assistant-ui/` precisely because nothing could clear them, and
  `require` is refused everywhere.
- edit anything under `src/chat/assistant-ui/vendor/` beyond the
  modifications its `README.md` already lists. That directory is somebody
  else's MIT source, copied from two registries rather than installed
  ([ADR 0001](../docs/adr/0001-chat-ui-assistant-ui-with-tailwind.md)); every
  edit in it is a change to re-apply at every re-sync, for ever. Fix it
  outside, or list the edit there with its reason. `src/test/vendor.test.ts`
  fails when the list and the directory disagree. **Do not "tidy" the two
  ESLint relaxations** scoped to `src/chat/assistant-ui/vendor/**` in
  `eslint.config.js`, or satisfy them by editing the copy: they are there so
  that the copy stays a copy. Re-sync by the procedure in that README —
  `curl` the registry JSON, never the `shadcn` or `assistant-ui` CLI, which
  installs packages, runs install scripts and rewrites configuration — and
  **record every copy and re-sync in
  [../docs/legal/ip-clearance.md](../docs/legal/ip-clearance.md)**, where
  entries are appended and never edited. A package that the copy newly needs
  is still a dependency change of its own, vetted by the rules above, with
  the judgement written into that README's vetting table.
- write a path any way but plainly. `//`, `/./`, a `..` that is not the
  leading prefix and a trailing `/` are refused, as is any path through
  `node_modules/`: a package is imported by its name. One spelling per path
  is what lets the seam rule read one.
- add a CDN, a web font, a third-party origin or an inline script. An
  air-gapped install has to work, and the Content-Security-Policy forbids it.
- use CSS Modules, a stylesheet language other than plain CSS, or a
  `<style>` block in `index.html`. Each fails the build. Style with Tailwind
  and plain CSS, and pick dependencies that ship plain CSS too.

Do:

- add the package's name to `CSS_PACKAGES` in `vite.config.ts`, and say so in
  the pull request, when a stylesheet gains an `@import` or a `url()` that
  names a **package**. Rollup's module graph does not see it, so that list is
  written by hand; from the name the build holds it to the allowed list,
  records it in `bundled-packages.txt` and ships its `LICENSE`
  ([../DEPENDENCIES.md](../DEPENDENCIES.md), "What the bundle's record does
  not see").
- run `scripts/check-frontend.sh` from the root of the repository before
  declaring a change done; CI runs that same script.
- when a package that is not on the allowed list appears or changes version,
  update its row in the "JavaScript build tooling" table of
  `../DEPENDENCIES.md`, having read the licence in the version you are
  pinning. `scripts/check-licences.mjs` refuses a row that names another
  version, another licence, or a package that no longer needs one.
- refresh `../backend/openapi.json` with `scripts/update-openapi.sh` when the
  backend's routes change. `src/api/schema.d.ts` is generated from it by every
  script here and is not committed.
- put the SPDX header on every new file, and add to `../REUSE.toml` anything
  that cannot carry one.
