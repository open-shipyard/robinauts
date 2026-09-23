# Open source hygiene — checklist

What the "foundation-ready" policy asks of this repository, as things to
do. The rules themselves are summarised in
[specs/open-source.md](specs/open-source.md). Items marked **(neorc
gap)** are things the sibling project neorc does not do; Robinauts does
them from the start.

## Done

- [x] Repository in a GitHub organisation (`open-shipyard/robinauts`), not
      a personal account.
- [x] `LICENSE`: the unmodified Apache-2.0 text.
- [x] SPDX and copyright header on every source file so far.
- [x] Architecture contracts enforced in the test suite.
- [x] `uv.lock` committed.

## Before more code lands

- [ ] Every commit signed off (`git commit -s`), from the first. Signed
      commits and tags; a `KEYS` file. **(neorc gap: unsigned commits, four
      early commits without sign-off)**
- [x] `NOTICE`: exactly `Robinauts` and
      `Copyright 2026 The Robinauts Authors`. Nothing that is not a
      required attribution. **(neorc gap: an extra paragraph)**
- [x] `AUTHORS`.
- [x] `CONTRIBUTING.md`: the DCO 1.1 sign-off section; the **AI-assisted
      contributions** section (you reviewed every line; it reproduces no
      incompatibly licensed code; machine-generated files or blocks are
      disclosed in the pull request); the provenance rule (no Stack
      Overflow or blog code; nothing copied or ported from a forbidden or
      unlicensed source). **(neorc gap: no AI section)**
- [x] `DEPENDENCIES.md`: the three categories, the named MPL-2.0 and
      development-only exceptions.
- [x] `docs/legal/ip-clearance.md`, `docs/legal/third-party.md`,
      `docs/legal/name-search.md`, `docs/legal/assets.md`; a `LICENSES/`
      directory (the name `reuse` expects). `ip-clearance` entries: the
      sign-in code derived from neorc, and the vendored assistant-ui
      components.
- [x] `REUSE.toml` for files that cannot carry a header; `reuse lint`
      passing. **(neorc gap: no header check; no header on any TypeScript
      or CSS file)**
- [ ] `SECURITY.md` (private reporting, acknowledgement within 3 days,
      disclosure within 90), `CODE_OF_CONDUCT.md` (Contributor Covenant
      2.1), `GOVERNANCE.md`, `MAINTAINERS.md`, `CHANGELOG.md` (Keep a
      Changelog), `CODEOWNERS`, a pull request template with a
      "machine-generated?" field. **(neorc gap: none of these exist)**
- [ ] Name search recorded: run `name_search.py robinauts`, do the manual
      trademark searches it lists (USPTO, EUIPO, WIPO, ASF and CNCF project
      lists), and write the result down. The name is decided; the record is
      what a foundation asks for.

## CI, all blocking

- [x] Python: ruff, black, the test suite with the architecture contracts,
      a licence gate over the locked set, `pip-audit`. **(neorc gap: no
      Python licence gate)**
- [x] JavaScript: lint, type check, tests, build with the licence
      allowlist, `bundled-packages.txt` diff, size budget, `npm audit`,
      `npm audit signatures --omit=dev`; `.npmrc` with `ignore-scripts` and
      `save-exact`; `npm ci` only. All of it in `scripts/check-frontend.sh`,
      which the `frontend` job runs, plus `frontend/scripts/check-licences.mjs`
      — the licence policy over the whole installed tree, not the bundle
      alone, with the development exceptions named in `DEPENDENCIES.md`. The
      size budget is provisional until a bundle with the chat in it exists.
- [x] `reuse lint`; a DCO check over the commits of the pull request
      **(neorc gap)**. Making them required statuses is branch protection,
      below.
- [ ] CSS-reached packages in the bundle record. `bundled-packages.txt` is
      written from rollup's module graph, so a package reached only through a
      stylesheet (`@import "pkg"`, `url(pkg/x)`) is in the bundle and not in
      the record. It is still held to the allowed list by the installed-tree
      gate; what is missing is the record, and a reviewer reads CSS
      `@import`/`url()` targets by hand
      ([DEPENDENCIES.md](../DEPENDENCIES.md)).
- [ ] `gitleaks`. The ESLint import rule that confines assistant-ui
      (ADR 0001) is done: `frontend/eslint.config.js`, with
      `frontend/src/test/seam-rule.test.ts` proving it still fires.
- [x] Workflows: `permissions: contents: read`, `persist-credentials:
      false`, actions pinned to commit SHAs **(neorc gap: pinned by tag)**.
- [x] Dependabot for pip, npm and github-actions, 10-day cooldown
      **(neorc gap: npm only)**. `uv` (the ecosystem that reads `uv.lock`),
      `github-actions`, and npm for `/frontend`.
- [ ] Branch protection on `main`: pull requests only, linear history, no
      force-push, required checks, signed commits.

## Releases

- [ ] Built in CI from a signed `v*` tag; the frontend bundle built only
      there. PyPI trusted publishing, no long-lived tokens. Half of this is
      done: the `wheel` job builds the bundle and the wheel on every run and
      uploads the wheel as an artifact, which is how the POC is deployed. What
      is left is the tag, the signature and the publishing.
- [x] `LICENSE`, `NOTICE` and `THIRD_PARTY_LICENSES.txt` inside the wheel,
      and listed in `license-files`. **(neorc gap: the third-party file is
      shipped but not listed)** All three are in
      `<name>.dist-info/licenses/` and in the metadata as `License-File:`,
      put there by the metadata hook in `backend/hatch_build.py`; the build
      hook beside it refuses to build a wheel whose frontend, or whose
      third-party notices, are not there. `scripts/check-wheel.sh` looks
      inside a real wheel for all three, and CI runs it.
- [ ] An SBOM per release; build provenance attestation; `RELEASING.md`
      that someone else can follow; OpenSSF Scorecard.

## Standing rules

- Never squash-import a codebase. Never force-push `main`.
- Code that enters other than through an ordinary signed-off pull request
  gets an `ip-clearance` entry: source URL and commit, its licence, where
  it landed, what was changed, where attribution was added.
- Never strip an upstream header; never relicense someone else's file.
- Register names and accounts as an individual or a neutral entity, not
  through an employer. If any of this is written on employer time, on
  employer hardware or in the employer's field, get a written waiver first
  and keep it outside the repository.
