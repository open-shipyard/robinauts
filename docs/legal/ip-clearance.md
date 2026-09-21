# IP clearance log

An entry is appended whenever something enters the tree other than as a
contributor's own work in an ordinary signed-off pull request: vendored
code, a component copied from a registry, code or text derived from another
project, an asset. The entry is part of the pull request that brings it in.

Each entry states where it came from and at which commit, under what
licence, where it landed, what was changed, and where attribution was
added.

Entries are never edited after the fact; a correction is a new entry.

---

<!-- REUSE-IgnoreStart -->
<!-- The entries quote other projects' copyright and licence lines. They
     are statements about those projects, not about this file. -->

### 2026-09-21 — sign-in design, from neorc

- Source: https://github.com/open-shipyard/neorc, commit `68e3805`,
  `docs/working-notes/sso-plan.md` and the code it describes
  (`neorc_core/_access.py`, `neorc/auth/`, `neorc/manager/`).
- Their licence: Apache-2.0, Copyright The neorc Authors.
- Landed as: `docs/specs/sign-in.md` so far — the design only. The code
  will be written for this project's layout with neorc's code as the
  reference; an entry is added here when it lands.
- Modifications: a users table, person roles, a local development mode; no
  API tokens yet.
- Attribution added to: this entry. No code has been copied, so no notice
  is required yet.

<!-- Entries go above this line. -->
<!-- REUSE-IgnoreEnd -->
