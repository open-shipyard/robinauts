# POC progress

The plan is [poc-scope.md](poc-scope.md). The process is the three-agent
recipe (`recipes/three-agent-steps.md`, beside this repository).

## What exists

For a reader with no memory of it. Kept short; rewritten as the steps land.

- `docs/specs/` — the specs; start at `core.md`. `docs/adr/` — two
  decisions that needed a discussion. `docs/layout.md` — the backend layers
  and their enforced dependency rules.
- `backend/` — the `robinauts` package with every layer as a sub-package,
  `pyproject.toml` with the import-linter contracts, and
  `tests/unit/test_architecture.py` which runs them. `domain`, `core`,
  `ports` and `application` have something in them; `api`, `adapters` and
  `datastore` are still empty.
  Checks: `uv run pytest`, `uv run ruff check .`, `uv run black --check .`
  from `backend/`, or `scripts/check-all.sh` from the root.
- Sign-in, domain and core (standard library only). `domain/errors.py`:
  `RobinautsError` and, under it, `InvalidValueError`, `ConfigError` (which
  carries every problem at once) and `SignInError` with the spec's fixed
  `SignInErrorCode` — plus `NotAllowedError`, `UnknownProviderError` and
  `InvalidIdTokenError`. `domain/identity.py`: `Identity` (what a provider
  asserts), `User` (keyed by `(provider, subject)`), `Session`,
  `PendingLogin`. `domain/sign_in.py`: `Matcher`, `AllowEntry`,
  `ProviderConfig` (which holds `client_secret_env`, the *name* of the
  variable, never a secret), `is_google_issuer` — the one answer, by host, to
  "is this Google", which decides whether Google's rules about `hd` and
  `email_verified` hold — and `SignInConfig` with `redirect_uri()`,
  `provider()`, `secure` and `session_life`. Roles and admin entries are
  deferred and are not there. `core/allow.py`: `is_allowed`, `matches`,
  `verified_email`, `ascii_lower` (case is ignored inside ASCII only:
  `.lower()` folds U+212A onto `k`). `core/claims.py`: `decode_id_token` (no signature
  check, and the docstring says why and when that stops holding),
  `check_id_token_claims` with `now` passed in, `identity_from_claims`,
  `identity_from_id_token`, `accepted_issuers` (the configured issuer alone,
  plus Google's bare host) and `check_published_issuer`, which is how a
  discovery document's issuer is checked against the configured one.
  `core/urls.py`: `normalise_origin`, `normalise_issuer`, `is_loopback`.
  `core/sign_in_config.py`: `parse_sign_in_config`, from the raw tables a
  TOML reader will hand it into a `SignInConfig`, unknown keys refused and
  every problem reported at once. `core/hashing.py`: `secret_hash` and
  `pkce_challenge` — making a secret needs randomness and is not here.
  The tests are the `backend/tests/unit/test_signin_*.py` modules, one per
  source module.
- Sign-in, ports, fakes and the application flow (standard library only).
  It added to `core` what is pure in a sign-in and was not there yet:
  `core/oidc.py` (`authorization_url` — the request, PKCE and all —
  `AUTHORIZATION_PARAMETERS`, `TOKEN_PARAMETERS`, `parameters_taken`,
  `MAX_CODE_CHARS`), `core/urls.py` (`normalise_endpoint`, `endpoint_query`,
  `safe_return_to`) and, in `core/hashing.py`, what a secret must be:
  `MIN_SECRET_CHARS` (43, for 256 bits), `MAX_SECRET_CHARS` (256, past which
  nothing is looked up), `MAX_PKCE_CHARS`, the two alphabets,
  `is_secret_shaped`, `same_secret` (constant time) and `checked_secret`,
  which is what a broken secret source runs into.
  `ports/`: `Clock` (aware datetimes, and a monotonic count for intervals),
  `SecretSource` (`secret`, `pkce_verifier` — the only randomness in a
  sign-in), `CredentialStore` (users get-or-created by `(provider, subject)`,
  sessions, pending sign-ins; found by the SHA-256 of a secret, never the
  secret) and `IdentityProvider`, which only fetches the discovery document
  and posts the code, returning raw data. **The store keeps no clock**: the
  application computes every expiry from `Clock` and hands it in, and every
  method that must know the time is told it, so one clock decides what has
  expired and no test sleeps. `application/sign_in.py`: `SignIn` with
  `begin`, `complete`, `resolve_session`, `sign_out`, `sweep` and
  `endpoints`. Discovery is lazy, cached on success only, and
  **single-flight**: everyone waiting on one provider shares one fetch and is
  told what it said, so ten people behind a provider that takes ten seconds
  to fail wait ten seconds, not a minute and a half; a cancelled caller waits
  on a shield and takes nobody's fetch with it. The application validates the
  discovery document and the ID token with `core`; the port decides nothing.
  Endpoints go through `core.normalise_endpoint` — https or loopback, no
  userinfo, no fragment, no whitespace — which **rebuilds** them from the
  pieces it checked, so a newline smuggled into a URL cannot reach a
  `Location` header; an endpoint whose own query sets, in any case, what its
  own request sets is refused, since its query goes in front of ours. An
  authorization code over `MAX_CODE_CHARS` is refused before it is posted
  anywhere. `core.safe_return_to` (printable ASCII, a path of this origin) is
  what keeps the return target from becoming an open redirect. Of what the
  identity provider port may raise, only `OSError` and `TimeoutError` become
  `provider_unavailable`, with the type alone in the detail and the original
  chained — an adapter's `TypeError` is a bug and propagates, and
  `CancelledError` passes through. Sweeping records its interval only after
  the deletes, and a sweep that fails is counted (`sweep_failures`) rather
  than failing the sign-in. A secret the source gave is refused at either end
  — under the 43 characters 256 bits need, over the 256 anything is looked up
  by, or spelt with what a URL would escape.
  `backend/tests/fakes/` holds an implementation of every port — a settable
  clock, counting secrets, an in-memory credential store and a scripted
  identity provider — and `backend/tests/contracts/` holds the two contract
  suites the real implementations will be held to: `credential_store.py`
  (override `new_store`, awaited inside the test's own loop, `close_store`,
  called in a `finally` by the `opened()` context manager every test uses so
  that a pool is released on the loop that made it, and `dump`, which writes
  out every field of every row so that the suite can look for a raw secret in
  it) and `secrets.py`. The store suite says in its docstring what
  a PostgreSQL implementation will need — a pool, one statement per
  operation, an advisory lock or `SERIALIZABLE` for the cap — and includes
  what a suite without it certifies wrongly: four `asyncio.gather` tests of
  what must be atomic, and two of sweeping running beside a take and a
  lookup. `test_fake_credential_store.py` proves they have teeth by running
  them against a deliberately racy store, which must fail them and does pass
  the one-caller-at-a-time ones. The other tests are `test_signin_flow.py`
  (the whole flow, both provider kinds and all eight error codes) and
  `test_fake_secret_source.py`; the pure rules are tested where they live, in
  `test_signin_urls.py`, `test_signin_hashing.py` and `test_signin_oidc.py`.
  There is no `pytest-asyncio`: `backend/tests/aio.py` has `@asyncio_test`,
  which runs an `async` test on an event loop of its own.
- Open source groundwork at the root: `NOTICE`, `AUTHORS`,
  `CONTRIBUTING.md` (DCO, AI-assisted contributions, where code may come
  from), `DEPENDENCIES.md` (licence categories, the named restricted and
  excluded packages), `REUSE.toml` and `LICENSES/`; `docs/legal/` with the
  IP clearance log, the third-party list, the name-search and assets
  records. `uvx reuse lint` passes from the root: a new root-level file
  must be added to `REUSE.toml`, and prose that quotes a licence tag or
  someone else's copyright line goes between `REUSE-IgnoreStart` /
  `REUSE-IgnoreEnd` comments.
- `scripts/` — one script per gate, all of them runnable on a laptop:
  `check-lint.sh` (ruff and black, over `backend/` and `scripts/`),
  `check-tests.sh`, `check-licences.sh`, `check-audit.sh` (`pip-audit` over
  the exported locked set, markers stripped so nothing is skipped, and a
  cross-check that every pinned package really was audited), `check-reuse.sh`,
  `check-dco.sh` (sign-off on a commit range, by default what the branch adds
  to `main`), and `check-all.sh`. `reuse` and `pip-audit` run as isolated
  `uvx` tools, pinned in `scripts/tool-versions.sh` and bumped by hand: they
  are deliberately outside the lock, because `reuse` brings a GPL dependency.
  `.github/workflows/ci.yml` runs those scripts and nothing else, one per
  job, on Python 3.12, with `contents: read`, `persist-credentials: false`
  and actions pinned to commit SHAs, on pull requests and on pushes to
  `main`, `feature/**` and `fix/**`; `.github/dependabot.yml` watches `uv`
  and `github-actions` with a 10-day cooldown. The scripts are documented in
  `CONTRIBUTING.md`.
- The licence gate is `scripts/licence_gate.py`, standard library only. It
  reads the categories and the named exceptions out of `DEPENDENCIES.md` —
  the single source of truth — and applies them to every package of
  `backend/uv.lock`, runtime and development alike. It fails closed: a
  licence it cannot classify, metadata it cannot verify, a lock it cannot
  believe, all fail. Exit 1 is "a dependency fails the policy", exit 2 is
  "the gate could not do its work". To add a dependency whose metadata is
  vague or restricted, add a row to the right table of `DEPENDENCIES.md`
  (licence, version, scope are all checked). Tests:
  `backend/tests/unit/test_licence_gate.py` (also reads the real
  `DEPENDENCIES.md` and `uv.lock`) and `test_check_scripts.py` (the shell
  scripts, against stand-in tools). `backend/tests/conftest.py` stops
  bytecode being written, so that importing from `scripts/` does not litter
  the tree.
- No frontend yet, so no JavaScript gates. Still outstanding, and unticked in
  `docs/oss-checklist.md`: secret scanning (`gitleaks`, which has nothing to
  do with the frontend — it is listed among the day-zero checks in
  `docs/specs/open-source.md` and simply is not done yet), the SBOM and the
  release workflow, which `poc-scope.md` puts outside the POC.

## Steps

### Step 0 — documents   (feature/poc-0-documents)

Summary: the open source groundwork — `NOTICE`, `AUTHORS`,
`CONTRIBUTING.md`, `DEPENDENCIES.md`, `REUSE.toml`, `LICENSES/`, and
`docs/legal/` (IP clearance log with the neorc sign-in design as first
entry, third-party list, name-search and assets records). `reuse lint`
passes over the whole tree. Implemented by the driver. CI, `SECURITY.md`,
the code of conduct and governance files are not in this step.

Review: 1 round.
- High: 2
  - No provenance record for the backend layout convention — left as is, by
    the project owner's decision: it is his own earlier work, contributed
    under the DCO. `CONTRIBUTING.md` now states the rule that covers it
    (one's own earlier work, sole rights).
  - `DEPENDENCIES.md` claimed the build enforces the licence rules while no
    CI exists — fixed: reviewers check by hand until the gate lands
    (step 1).
- Medium: 5 (5/0)
- Low: 4 (4/0)

Checks: `uvx reuse lint` (compliant, 46 files), `uv run pytest` in
`backend/` (1 passed).
Not done / to watch: step 1 must remove the "until that gate is in place"
sentence from `DEPENDENCIES.md` once the gate exists. Branch protection and
the DCO check are GitHub settings for the project owner.
Important design decisions made / open questions: `pgserver` is not to be a
dependency (no licence metadata) — tests take the URL of a PostgreSQL they
are given. The name-search record is still to be added by the owner.

### Step 1 — ci-python   (feature/poc-1-ci-python)

Summary: every gate is a script under `scripts/` that runs locally, and
`.github/workflows/ci.yml` only calls them: lint, tests with the
architecture contracts, the licence gate over the whole locked set,
`pip-audit`, `reuse lint`, the DCO check. Dependabot for `uv` and
`github-actions` with a 10-day cooldown; actions pinned to SHAs verified
upstream. The licence gate reads its policy from `DEPENDENCIES.md` and fails
closed. JavaScript gates, `gitleaks`, SBOM and the release workflow are not
in this step.

Review: 4 rounds.
- High: 4
  - An editable path dependency was treated as this repository and passed
    unread (a GPL package passed as Apache-2.0) — fixed.
  - A named development exception covered "no licence at all" and
    non-commercial terms, which the policy forbids — fixed.
  - `check-audit.sh` passed having audited nothing when `uv export` failed
    inside a pipeline — fixed; the other scripts swept for the same bug.
  - The licence gate passed over a lock with no packages, or of an unknown
    format — fixed: such a lock is an error (exit 2).
- Medium: 11 (11/0)
- Low: 19 (19/0)

Checks: `scripts/check-all.sh` — lint, 147 tests, licences (20 packages),
audit (19 of 19 pinned packages audited), reuse, DCO — all pass. Shown to
bite: an LGPL dependency, a vendored GPL package, a removed or relicensed
row of `DEPENDENCIES.md`, an empty lock, all turn the gate red.
Not done / to watch: the workflow has never run on GitHub from here; the
first push is its first run. Making the checks required is branch
protection, for the project owner. The step is about 2,500 lines, well over
the aim: most is the licence gate and its tests.
Important design decisions made / open questions: `reuse` and `pip-audit`
run as pinned `uvx` tools outside the lock (`reuse` would bring a GPL
package into it); `uv` is pinned in `scripts/tool-versions.sh` too, bumped
by hand. `colorama` (development only) declares only "BSD License" and is
excepted by name, licence and version after a hand check. A dependency
whose metadata names only a licence family will need the same hand check. A
branch with an open pull request runs CI twice (push and pull_request).

### Step 2 — signin-core   (feature/poc-2-signin-core)

Summary: the rules of sign-in, pure and standard library only. `domain`:
the records (identity, user, session, pending sign-in, provider, allow
entry, the sign-in configuration) and the error hierarchy with the spec's
eight fixed codes. `core`: allow-list matching, ID token decoding and claim
checks, identity extraction, URL and issuer normalisation, validation of a
raw configuration into domain objects with every problem reported at once,
secret hashing and the PKCE challenge. No ports, no IO, no random
generation, no roles: those come later or are outside the POC.

Review: 2 rounds.
- High: 2
  - `exp` / `iat` accepted NaN and Infinity, which skipped the expiry check
    — fixed, in the claim check and in the token decoder.
  - A trailing dot in the configured Google issuer switched every
    Google-specific rule off (`email_domain` accepted, the `hd`/gmail rule
    on verified email skipped) — fixed: hosts are normalised, and one
    function, `domain.is_google_issuer`, decides by host.
- Medium: 5 (5/0)
- Low: 11 (11/0)

Checks: `scripts/check-all.sh` — 563 tests with the architecture contracts,
lint, licences, audit, reuse, DCO — all pass.
Not done / to watch: `now` is a timezone-aware `datetime` everywhere; the
Clock port must hand out aware datetimes. About 2,900 lines with tests,
over the aim.
Important design decisions made / open questions:
- The issuer that discovery publishes must equal the configured one
  (`core.check_published_issuer`); it is never added to the accepted `iss`
  values.
- An empty `providers` table is a configuration error (nobody could sign
  in); running without sign-in is the local development mode, which has no
  sign-in configuration at all.
- Email and domain matchers compare ASCII only; an IDN domain is written in
  its A-label form.
- `docs/layout.md` forbids adapters from importing `core`. The OIDC adapter
  will therefore only fetch and post; the application checks the discovery
  document, the endpoints and the claims above the port.
- Derived from neorc's code, written again for this layout; recorded in
  `docs/legal/ip-clearance.md`.

### Step 3 — signin-application   (feature/poc-3-signin-application)

Summary: the sign-in flow, proven with fakes and no IO. Ports: `Clock`,
`SecretSource`, `CredentialStore`, `IdentityProvider` (which only fetches
and posts). Application: `SignIn` — begin, complete (the callback), resolve
a session, sign out, sweep; discovery is lazy, single-flight, cached on
success only, and validated above the port. Pure pieces live in `core`
(`oidc.py`, `hashing.py`, `urls.py`). Fakes for every port under
`backend/tests/fakes/`, and two reusable contract suites under
`backend/tests/contracts/` that the real store and secret source must pass.
No HTTP, no database, no cookies or routes yet.

Review: 3 rounds.
- High: 1
  - The store contract suite had no concurrency test, so a store breaking
    every atomicity guarantee of the port (double take, cap bypass, two
    users for one person) passed it — fixed: `asyncio.gather` tests, and a
    deliberately racy store kept in the tests that they must fail against.
- Medium: 7 (6/1)
- Low: 21 (21/0)

Checks: `scripts/check-all.sh` — 815 tests with the architecture contracts,
lint, licences, audit, reuse, DCO — all pass; the tests are also clean
under `PYTHONASYNCIODEBUG=1 -W error`.
Not done / to watch: the medium left is the global cap on pending sign-ins
as a denial-of-service lever — no code fixes it without a rate limit; it is
now in the known limits of `docs/specs/sign-in.md`. The sweep's "tick read
after the deletes" has no test (the fake clock does not move during a
sweep). About 3,400 lines with tests, over the aim.
Important design decisions made / open questions:
- One clock: the application computes every deadline from the `Clock` port
  and tells the stores what "now" is; stores keep no clock.
  `docs/specs/backend.md` was changed to say so (it said the database
  clock).
- `CredentialStore` must be safe under concurrent calls: the take is one
  `DELETE … RETURNING`, the cap holds exactly (an advisory lock or
  SERIALIZABLE with retry), get-or-create is one `INSERT … ON CONFLICT`.
  A duplicate `state` hash is refused, not replaced.
- A contract subclass provides `new_store`, `close_store` and `dump`.
- The application wraps only `OSError` / `TimeoutError` from the identity
  provider port as `provider_unavailable`; an adapter's bug propagates.
- The application may hold in-process state only for caches of public
  data, scheduling hints and diagnostic counters (`docs/layout.md`).
- Derived from neorc; recorded in `docs/legal/ip-clearance.md`.

