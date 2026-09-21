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

### 2026-09-21 — sign-in rules (domain and core), derived from neorc

- Source: https://github.com/open-shipyard/neorc, commit `68e3805`:
  `python/neorc-core/src/neorc_core/_access.py` (allow-list matching, the
  verified-email rule, secret hashing), `python/neorc/src/neorc/auth/_oidc.py`
  (ID token claim checks, identity extraction, token payload decoding, the
  PKCE challenge), `python/neorc/src/neorc/auth/_config.py` (URL and issuer
  normalisation, the shape of the configuration validator).
- Their licence: Apache-2.0, Copyright The neorc Authors.
- Landed as: `backend/src/robinauts/core/allow.py`, `claims.py`, `urls.py`,
  `sign_in_config.py`, `hashing.py`, and the records they use in
  `backend/src/robinauts/domain/`.
- Modifications: no file was copied. The logic was written again for this
  project's layers — pure functions in `core`, records in `domain`, this
  project's error types and names — with neorc's code open as the
  reference. Substantially machine-generated, reviewed by the maintainers.
- Attribution added to: this entry. Same authors and the same licence; no
  notice is required.

### 2026-09-21 — sign-in flow (ports and application), derived from neorc

- Source: https://github.com/open-shipyard/neorc, commit `68e3805`:
  `python/neorc-core/src/neorc_core/_access.py` (beginning a sign-in, taking
  a pending sign-in, opening a session, sweeping, the cap on pending
  sign-ins), `neorc_core/ports/_credentials.py` (the shape of the store
  port), `neorc_core/local/_memory_credentials.py` and
  `neorc_core/testing/contracts/_credentials.py` (the in-memory store and
  the idea of a contract suite), `python/neorc/src/neorc/auth/_oidc.py`
  (discovery, the authorization URL, the code exchange),
  `python/neorc/src/neorc/manager/_auth_routes.py` (the order of the
  callback's checks).
- Their licence: Apache-2.0, Copyright The neorc Authors.
- Landed as: `backend/src/robinauts/ports/`,
  `backend/src/robinauts/application/sign_in.py`, `backend/tests/fakes/`,
  `backend/tests/contracts/credential_store.py`.
- Modifications: no file was copied. Written again for this project's
  layers; deadlines are computed by the application from a clock port
  rather than by the store; the identity provider port only fetches and
  posts, and the application validates what comes back. Substantially
  machine-generated, reviewed by the maintainers.
- Attribution added to: this entry. Same authors and the same licence; no
  notice is required.

### 2026-09-21 — OIDC HTTP adapter and the stand-in provider, derived from neorc

- Source: https://github.com/open-shipyard/neorc, commit `68e3805`:
  `python/neorc/src/neorc/auth/_oidc.py` (the discovery fetch, the code
  exchange, client authentication by basic or post with the RFC 6749
  section 2.3.1 encoding, timeouts, no redirects) and the `StandInProvider`
  and `unsigned_jwt` of the root `conftest.py`.
- Their licence: Apache-2.0, Copyright The neorc Authors.
- Landed as: `backend/src/robinauts/adapters/identity_provider.py` and
  `backend/tests/standin/`.
- Modifications: no file was copied. The adapter only fetches and posts and
  returns raw data, where neorc's client also validates; the stand-in is a
  real loopback HTTP server, where neorc's is an ASGI application.
  Substantially machine-generated, reviewed by the maintainers.
- Attribution added to: this entry. Same authors and the same licence; no
  notice is required.

<!-- Entries go above this line. -->
<!-- REUSE-IgnoreEnd -->
