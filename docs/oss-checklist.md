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
- [ ] `NOTICE`: exactly `Robinauts` and
      `Copyright 2026 The Robinauts Authors`. Nothing that is not a
      required attribution. **(neorc gap: an extra paragraph)**
- [ ] `AUTHORS`.
- [ ] `CONTRIBUTING.md`: the DCO 1.1 text; the **AI-assisted
      contributions** section (you reviewed every line; it reproduces no
      incompatibly licensed code; machine-generated files or blocks are
      disclosed in the pull request); the provenance rule (no Stack
      Overflow or blog code; nothing copied or ported from a forbidden or
      unlicensed source). **(neorc gap: no AI section)**
- [ ] `DEPENDENCIES.md`: the three categories, the named MPL-2.0 and
      development-only exceptions.
- [ ] `docs/legal/ip-clearance.md`, `docs/legal/third-party.md`,
      `docs/legal/name-search.md`, `docs/legal/assets.md`; a `licenses/`
      directory. First `ip-clearance` entries: the layout convention and
      `pyproject.toml` brought from fetchy; later, the sign-in code derived
      from neorc and the vendored assistant-ui components.
- [ ] `REUSE.toml` for files that cannot carry a header; `reuse lint`
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

- [ ] Python: ruff, black, the test suite with the architecture contracts,
      a licence gate over the locked set, `pip-audit`. **(neorc gap: no
      Python licence gate)**
- [ ] JavaScript: lint, type check, tests, build with the licence
      allowlist, `bundled-packages.txt` diff, size budget, `npm audit`,
      `npm audit signatures --omit=dev`; `.npmrc` with `ignore-scripts` and
      `save-exact`; `npm ci` only.
- [ ] `reuse lint`; a DCO check as a required status **(neorc gap)**;
      `gitleaks`; the ESLint import rule that confines assistant-ui
      (ADR 0001).
- [ ] Workflows: `permissions: contents: read`, `persist-credentials:
      false`, actions pinned to commit SHAs **(neorc gap: pinned by tag)**.
- [ ] Dependabot for pip, npm and github-actions, 10-day cooldown
      **(neorc gap: npm only)**.
- [ ] Branch protection on `main`: pull requests only, linear history, no
      force-push, required checks, signed commits.

## Releases

- [ ] Built in CI from a signed `v*` tag; the frontend bundle built only
      there. PyPI trusted publishing, no long-lived tokens.
- [ ] `LICENSE`, `NOTICE` and `THIRD_PARTY_LICENSES.txt` inside the wheel,
      and listed in `license-files`. **(neorc gap: the third-party file is
      shipped but not listed)**
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
