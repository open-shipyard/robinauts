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
  `tests/unit/test_architecture.py` which runs them. Every layer has
  something in it, `api` included, and `app.py` wires them together.
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
- The schema and the credential store, on PostgreSQL through `asyncpg` —
  the one runtime dependency there is. `datastore/schema.sql` is the whole
  schema of a deployment, shipped in the wheel: `schema_version` (one row),
  `users`, `sessions`, `pending_logins`, `timestamptz` throughout, the
  expiry columns indexed, sessions cascading from their user, and the two
  hash columns refusing anything that is not 64 lower-case hex digits. It
  is **one definition edited in place**, and the conversation and run
  tables are added to the bottom of it later. The version row is the
  file's **last** statement and is `DO NOTHING`, so a half-applied file
  records no version and applying the file can never relabel an older
  schema as this one. `datastore/schema.py`: `SCHEMA_VERSION`,
  `SCHEMA_SHA256` (the file's hash, pinned: editing the schema without
  bumping the version fails a test that says so — the guard that stands
  where a migration would), `SCHEMA_TABLES`, `schema_sql`,
  `create_schema`, which **looks before it writes**, under an advisory
  lock so that two at once make one schema — it applies the file to an
  empty database, does nothing to one already at this version, and refuses
  everything else — `schema_version` and `check_schema`. All of them judge
  **one schema**, `current_schema()`, which is where the file's
  unqualified `CREATE TABLE`s land: a table of ours further along the
  search path is not this deployment's, and a stranger's `users` there is
  none of our business. `check_schema` also requires every table to be
  there, to be a table rather than a view of the same name, and to be the
  one an unqualified statement in a store would actually reach — so the
  arrangement the rest of the code assumes, a search path whose first
  entry is the deployment's schema, is refused rather than assumed — on
  the create path too, before a statement of the file runs. A relation
  *further along* the path is harmless and explicitly allowed, which is
  how a deployment lives beside another application's `users`. Every
  refusal is the new `domain.SchemaError` (`missing`, `mismatch`,
  `unversioned`, `unreadable`, `incomplete`, `shadowed`, `no_schema`),
  naming `domain.DB_INIT_COMMAND` — `robinauts db init`, the command of a
  later step — and saying it works on an empty database only, because
  there are no migrations yet; `shadowed` and `no_schema` instead say to
  fix the connection, since nothing is wrong with the database. Each of
  the three functions asks everything on **one** connection.
  `datastore/pool.py`: `open_pool`, the one place a pool is made,
  which deliberately sets no session time zone. `datastore/credentials.py`:
  `PostgresCredentialStore` over a pool it is **given**, passing the same
  contract suite as the fake. Every method is one statement — the take is
  `DELETE … RETURNING`, get-or-create is `INSERT … ON CONFLICT … DO UPDATE
  … RETURNING`, the sweeps count in a CTE — except the cap, which holds a
  transaction-scoped advisory lock keyed on the table's own OID around the
  count and the insert, because no isolation level makes `count(*)` see a
  row another transaction has not committed. Nothing calls `now()`: times
  come in from the application's clock, and a naive datetime is refused
  rather than read as UTC by every method that takes one. Driver errors
  propagate, bar two constraints that exist to say no to a caller — a
  session hash already held and a session for a user who is not there,
  both `InvalidValueError`, told apart by the constraint's **name**, which
  `schema.sql` spells out, so that a constraint added later is not
  mistaken for one of them. A key that is not the hash of a secret is
  refused in Python before either statement, because the column's CHECK
  never runs on the path where the cap is reached and nothing is inserted.
  The contract now requires the same refusals of the in-memory fake, so
  the two stores no longer differ where the port was silent.
  `backend/tests/postgres.py` gives every test a schema of its own on the
  database named by `ROBINAUTS_TEST_DATABASE_URL`, cleaning up after
  itself if opening one fails, with a warm pool of eight connections so
  the contract's concurrency tests really race;
  `backend/tests/integration/` holds the modules that use it, plus one
  that builds a wheel and checks `schema.sql` is in it. Without the
  variable the database tests skip and the suite is green — unless
  `ROBINAUTS_REQUIRE_POSTGRES` is set, which turns a skip into a failure
  and is what stops CI going green on tests that quietly stopped running.
  It is checked on what happened, not on what was meant: a session hook in
  `backend/tests/conftest.py` counts the tests marked `database` that
  really ran and fails a required run that counted none, or that was
  narrowed with `-m`, `-k` or a path and so can prove nothing — or split
  across processes, where it could not count at all. It keeps quiet about
  a session that was interrupted or only collected, which has its own
  story. CI also waits for the database to answer a real query before the
  tests, with `scripts/wait_for_postgres.py`: a container health check
  cannot tell the server apart from the private one `initdb` runs while it
  sets the data directory up.
  An import-linter contract keeps `asyncpg` under `datastore`. CI runs the
  same tests against a PostgreSQL service container, pinned by digest,
  deliberately not on UTC, and required.
- `adapters/` — the rest of the outside world, and the second runtime
  dependency, `httpx` (BSD-3-Clause; it brings `certifi`, MPL-2.0, which has
  a row in `DEPENDENCIES.md` as an unmodified, unbundled runtime
  dependency). An import-linter contract keeps `httpx` under `adapters`, as
  `asyncpg` is kept under `datastore`. `adapters/identity_provider.py`:
  `HttpIdentityProvider`, the `IdentityProvider` port over an
  `httpx.AsyncClient` it **makes for itself** in its constructor
  (`open_client` is the one place one is made; `aclose` closes it, and the
  composition root holds the adapter for the life of the process, as it
  does the pool). The client is deliberately not a parameter: one made with
  `verify=False` is a keyword away, and an adapter whose TLS depended on
  what it was handed could promise nothing. What a deployment may choose is
  the timeouts, the bound, `trust_env` and where the secret is read from.
  It fetches and posts and decides nothing — the mappings come back as the
  provider sent them — but it is strict about the HTTP: a connect timeout,
  a read timeout and a ceiling on the whole exchange (`asyncio.timeout`);
  **no redirects**, set on the client and again on every send, because
  following one from a token endpoint would post the authorization code
  wherever the answerer chose; **a bounded body, uncompressed** — every
  request asks `Accept-Encoding: identity`, an answer that carries a content
  encoding anyway is refused unread, a declared `Content-Length` over
  `MAX_RESPONSE_BYTES` is refused before a byte of body, and what is read is
  the **raw** stream, counted off the wire (counting after decompression is
  counting the wrong thing: half a megabyte of gzip is sixty-seven of
  memory); `Accept: application/json` and a fixed, version-less
  `User-Agent`; and TLS through `ssl_context()`, built here so that it can
  be looked at, with **no argument anywhere to weaken it** — `trust_env`
  decides where the trust store and the proxy come from, never whether the
  certificate is checked; loopback `http` is the only unencrypted endpoint,
  and it is `core` that permits it. Failures are the port's two codes: a
  transport failure, a timeout, a `5xx`, a redirect, a compressed or
  oversized body, a body that is not a JSON object (or is nested past the
  recursion limit — forty kilobytes of `[` is a `RecursionError`, not a
  `ValueError`, and uncaught it would be a 500) are `provider_unavailable`,
  and so are `408`, `425` and `429`, which mean "ask again" rather than
  "no"; every other `4xx` from the token endpoint, and an OAuth `error` in a
  `200`, are `provider_refused`, with the provider's `error` and
  `error_description` bounded in the detail. The client secret is read at
  the moment it is used, through the injected `SecretLookup`, and never held
  on the object. **Nothing raised from an exchange can print it**: the
  frames of a code exchange hold the secret, the code and the verifier, and
  an `httpx` exception holds the `Request` that holds all three and stays
  reachable through `__context__` even after `raise ... from None`. So
  `_exchanged` *returns* the answer or a `_Refused`, unbinds every
  credential on the way out, and `exchange_code` raises from a frame that
  holds none of them while no exception is being handled — leaving
  `__cause__` and `__context__` both empty. Discovery, which carries no
  credential, keeps its cause for the operator. `client_secret_basic`
  form-encodes each half before joining them (RFC 6749 2.3.1), so a secret
  holding a colon works. `adapters/clock.py`: `SystemClock` (aware, UTC).
  `adapters/secrets.py`: `OsSecretSource` on `secrets.token_urlsafe`,
  passing the same `SecretSourceContract` as the fake.
  `adapters/config_file.py`: `read_toml` — raw tables, and a `ConfigError`
  naming the file (and the line, which tomllib puts in its own message) when
  it cannot be read; `environment`, where an empty variable is no secret;
  and `check_client_secrets`, which refuses to start a deployment naming
  **every** provider whose variable is unset, at once. *For the composition
  root, next:* that is every missing **variable** together, not every
  start-up problem together, which is what `operations.md` asks for and which
  only the root can assemble. A file that does not parse stops there — there
  is no configuration to check secrets against — but once `core` has accepted
  one, merge the secret check's problems into the same `ConfigError` as every
  other start-up problem the root can gather, rather than failing twice.
  Nothing here imports `core`: the reader hands raw tables to `core.parse_sign_in_config`, and
  the composition root (step 6 onwards) calls the two in turn.
  `backend/tests/standin/` is a **real** OpenID Connect provider on a
  loopback port the operating system picks (`http.server`, no new
  dependency): discovery, an authorization endpoint that redirects straight
  back with a code, and a token endpoint that checks the client
  authentication, the code, the `redirect_uri` and the PKCE verifier and
  issues an unsigned ID token carrying the claims the test scripted.
  `Misbehaviour` scripts the rest — held (behind a gate of its own, so that
  one `release()` cannot make the next hold vacuous), `5xx`, HTML, a
  redirect, an oversized body with or without a length, a length that lies,
  a gzip bomb, JSON nested past any parser, an OAuth error — and `received`
  records every request with its headers, so "the redirect was not followed"
  is a statement about what the server saw. It authenticates the client
  before it redeems a code, as a real authorization server does. It is meant to be reused by the routes and the browser
  test. `tests/integration/test_sign_in_end_to_end.py` runs the whole flow
  over it: `application.SignIn` + `HttpIdentityProvider` + `SystemClock` +
  `OsSecretSource` + the in-memory store, begin, follow the redirect,
  complete, resolve, sign out.
- `api/` — the inbound side, on FastAPI, the third runtime dependency
  (`fastapi`, MIT, bringing `starlette` BSD-3-Clause, `pydantic`,
  `pydantic-core`, `annotated-types`, `annotated-doc` and `typing-inspection`,
  all MIT) — all on the allowed list, so no row of `DEPENDENCIES.md` was
  needed. **`uvicorn` is deliberately not a dependency yet**: nothing imports
  it until `robinauts start` exists, and it arrives with the CLI step. The
  import-linter contract already names it beside FastAPI and Starlette, so
  the day the import is written the rule is already there. `api/web.py`: `create_api`, which is handed the
  application's `SignIn` (or `None`, where a deployment has no sign-in
  configuration) and constructs nothing; `/docs` and `/redoc` are **not**
  served, because they load scripts from a CDN, while `/openapi.json` is.
  `api/auth_routes.py`: the four routes of `docs/specs/sign-in.md` —
  `GET /auth/session` (never a 401: "nobody" is an answer),
  `GET /auth/login/{provider}`, `GET /auth/callback/{provider}` and
  `POST /auth/logout`, the two middle ones out of the OpenAPI document,
  being browser navigations. Every failure of a sign-in, whatever it was,
  ends as a 303 to `{public_url}/ui/#/sign-in?error=<code>` with the login
  cookie cleared and the detail in the log alone. `api/cookies.py`: the two
  cookies, `__Host-` prefixed and `Secure` on https and plain on a loopback
  `http` deployment, `HttpOnly`, `SameSite=Lax` (not `Strict`, which would
  drop the state cookie on the provider's own redirect back), `Path=/`.
  `api/access.py`: the guard — the session cookie resolved to a `User`, the
  **one place** that answers "who is this" and therefore the seam the local
  development mode goes through (`local_access`) — and the declaration, `public()` and
  `signed_in()`, which every route carries. `undeclared()` walks what an
  application serves and **fails closed**: it reads every list a router keeps
  routes in (`ROUTE_LISTS`: `routes`, and `_low_priority_routes`, where
  FastAPI's `frontend()` puts a whole served directory), recurses into
  included routers and into a mounted application's own router, and names
  anything that is not an `APIRoute` carrying a declaration — a mounted
  sub-application, a mounted directory, a plain Starlette route, a websocket
  handler, a frontend, and a permission passed to `include_router` rather than
  written on the route. The one escape hatch is `FRAMEWORK_PATHS`, keyed on
  the name the walk reports (`/openapi.json` today), which is how the step
  that serves the built interface will allow it: one line, `"/ui"`, whether it
  is served by `frontend()` or by a `StaticFiles` mount. It never lets an
  `APIRoute` off — a route with dependencies can declare a permission and
  so must. Underneath is `unknown_route_lists()`, the backstop that needs no
  knowledge of the framework at all: any attribute of a router holding routes
  under a name nothing reads stops the deployment, so a FastAPI that grows a
  third list cannot be served out of quietly. It is not only a test:
  `check_declarations` runs both when `create_api` builds the application and
  again when it starts — the two moments anything is looked at, so
  **routes are added between them and never after**.
  `tests/unit/test_api_access.py` shows it bite on every shape, and pins the
  FastAPI releases whose `APIRouter` somebody has read; the dependency is
  pinned to the same range (`fastapi>=0.141,<0.142`), so the metadata and the
  test say one thing rather than two.
  `domain.Permission` has the two levels there are while roles are deferred,
  and `domain.is_provider_id` — the shape `core` validates a configured id
  against — is what `api` checks a `{provider}` path parameter with before
  anything looks at it; the two sign-in routes are navigations, so a
  mis-shaped id lands on the sign-in page with `unknown_provider` and the
  login cookie cleared, like every other failed sign-in, rather than showing
  a browser a JSON body. `api/protection.py`: the request protection, as **middleware**
  rather than a dependency — FastAPI reads a declared body before it solves
  that route's dependencies, and a route written later could omit one — so
  a write is refused before a byte of it is read: each of the three deciding
  headers sent at most once (two values of `Sec-Fetch-Site` are read
  differently by us and by the next parser along), `application/json`, and,
  when it carries a session cookie, `Origin` equal to `public_url` or
  `Sec-Fetch-Site: same-origin`. `Sec-Fetch-Site` is read as an **allow
  list** — `same-origin`, `none`, or no header at all — rather than as the
  two words that mean another site: a proxy that folds two headers into one
  sends `same-origin, cross-site`, which is neither of them. The header names
  are folded **here**, in one pass over the scope's own list, and the cookies
  are read out of that same pass: ASGI only says a server *should* lower-case
  them, and a framework that compares what it was given finds
  `Sec-Fetch-Site: cross-site` beside `sec-fetch-site: same-origin` to be one
  header. A refusal answers a **fixed sentence** and repeats nothing that was
  sent; the particulars go to the log.
  It also decides what is **not** served: a `lifespan` scope passes through,
  a `websocket` is closed with a policy-violation code before it is accepted
  (the platform streams over SSE and has no websocket route, and a websocket
  carries cookies and answers no preflight), and a scope of any other kind is
  not served at all. Beside it, the headers every answer carries (`nosniff`,
  `Referrer-Policy: same-origin`); `Cache-Control: no-store` is set by the
  auth routes. `api/errors.py`: one exhaustive table from the error
  hierarchy to a status, the body `{"error": "<ClassName>", "detail": …}` —
  Starlette's own 404 and 405 put in that same shape, `Allow` header and all —
  and **a body that never repeats what the request carried**: a 5xx says only
  that the request could not be served; a `SignInError` says one fixed
  sentence per code (`SIGN_IN_DETAIL`), never a provider's words; and a
  request that could not be read names the field and the rule and never the
  value pydantic refused. All of it goes to the log.
  `api/logs.py`: `shown()`, the one way text from a request reaches a log —
  quoted and escaped with `ascii()`, so a `%0A` in a path (which a server
  hands over decoded) cannot forge a line, and bounded, so a log cannot be
  filled a megabyte at a time. Every log call in `api` that carries a path, an
  origin, a header, a provider id or a provider's words goes through it.
  `api/schemas.py` holds what the JSON API sends; the committed
  snapshot of it is `backend/openapi.json`, rewritten by
  `scripts/update-openapi.sh` and kept honest by
  `tests/unit/test_openapi_snapshot.py`.
- `app.py` — the composition root. `Deployment.configured(...)` reads the
  TOML file (path from `ROBINAUTS_AUTH_CONFIG`), has `core` validate it,
  looks for the client secrets and for `ROBINAUTS_DATABASE_URL`, and reports
  **every problem it can see in one `ConfigError`** — which is the promise
  `check_client_secrets` could not make on its own. A file that does not
  parse stops there, since there is no configuration to check secrets
  against. `Deployment.open()` then does what needs a running loop, in the
  ASGI **lifespan**: the pool, `check_schema` (a database of another version
  is a server that does not start), `PostgresCredentialStore`,
  `HttpIdentityProvider`, `SystemClock`, `OsSecretSource`, `SignIn`; and
  `aclose()` gives every one of them back, logging a close that fails rather
  than stopping the rest. A `Deployment` is opened **once** — a second open
  would leave the first pool and client unreachable and held for the life of
  the process — and `aclose` is idempotent and safe on one never opened. Every collaborator may be handed in instead, which
  is how the tests wire fakes and the stand-in provider with no database,
  no file and no environment variable; the environment itself is read
  through the one injected `SecretLookup`. An identity provider that holds
  an HTTP client is closed whichever way it arrived.
  `backend/tests/webapp.py` is the test wiring (the fakes, a client over
  `httpx.ASGITransport`, and `running`, which drives an ASGI lifespan as a
  server does); `tests/integration/test_api_sign_in.py` signs in
  browser-shaped through the routes against the stand-in provider, and
  `tests/integration/test_create_app.py` does it again through `create_app`
  against the real PostgreSQL, naming its schema in the connection string,
  and checks the refusal to start on a database with no schema.
  There is no CLI yet and no UI served.
- The **local development mode** (`docs/specs/sign-in.md`): no sign-in at
  all, everything as one fixed local user, loopback only. `domain/local.py`
  holds what more than one layer needs — `LOCAL_PROVIDER` (`!local`, spelt so
  that `is_provider_id` refuses it, which is what reserves it: `core` and now
  `ProviderConfig` both hold a configured provider to that shape, so no
  configuration and no identity can ever be this person), `LOCAL_SUBJECT`,
  `is_loopback` (moved here from `core`, as `is_provider_id` was, because
  `api` asks it of a `Host` header and may not import `core`), `host_of`, and
  `LocalMode`, which **carries the bind host, normalises it and refuses a
  non-loopback one at construction** (by the stricter
  `is_loopback_bind_host`: a literal address or exactly `localhost`, since a
  bind address is not left to a resolver, while a request's `Host` may name
  this machine any way that reaches it): the root binds no socket, so the
  rule is kept at the one moment that cannot be got around later. `application/local.py`:
  `LocalAccess`, the counterpart of `SignIn`, which **reads** the one **real
  row** through the new `CredentialStore.user_by_key` (a plain indexed
  lookup that writes nothing) and falls back to the same get-or-create
  `user_at_sign_in` a sign-in uses when there is nobody there — so the user
  has an id, owns what the mode creates, is the same person after a restart,
  and an ordinary request leaves no row version behind (`user_at_sign_in` is
  an upsert). It caches nothing. `api.current_user` resolves every request to
  them with no cookie; `SignIn.resolve_session` refuses a session that names
  them, so a database kept from a run of the mode hands nobody the account.
  The request protection gains, in this mode only, a check on **every**
  request (one `Host` header naming a loopback host, and an address the
  server answered on that is loopback — a unix socket counts, a scope that
  says nothing is refused; the defence against DNS rebinding, which is the
  attack a same-origin rule cannot see, since the page really does own that
  origin),
  and it judges **every** write as credentialed: `Origin` equal to the
  loopback origin the request was addressed to, or `Sec-Fetch-Site:
  same-origin` with none. `GET /auth/session` answers `sign_in: false`,
  `local_development: true`, no providers and the local user (what the
  interface's banner is drawn from); `/auth/login/*` and `/auth/callback/*`
  redirect to `/ui/`; `POST /auth/logout` is 204. It is asked for by
  `create_app(local_development_host=...)` — the address it will be served on
  — and by nothing else: **no environment variable switches it on**, and
  asking for it together with a sign-in configuration (including
  `ROBINAUTS_AUTH_CONFIG` in the environment) is a start-up `ConfigError`, as
  is wiring both into one `create_api`. `Deployment.open` logs one WARNING
  saying sign-in is off. The CLI flag (`--dev-no-sign-in`) comes with
  `robinauts start`.
  **For the CLI step:** the server must be started with the access log off, or
  with query strings stripped for `/auth/callback`, because an ordinary ASGI
  access log would otherwise write `GET /auth/callback/…?code=…&state=…` — the
  authorization code and the state, in a file, for every sign-in.
- The **conversation format**, domain and core (standard library only): the
  platform's own record, owned by nothing else (ADR 0002). `domain/agents.py`:
  `Engine` (`langgraph` | `pydantic-ai`) and `is_config_id` /
  `checked_config_id`, the shape an agent's and a model's id are written in —
  a provider id's rule, for the same reasons. `domain/conversation.py`:
  `FORMAT_VERSION`, `Role` (with `TOOL` reserved and refused), `Channel`
  (`web`), `PartKind` naming **every** kind of content the spec gives a
  message and `SUPPORTED_PART_KINDS` saying which two are built — `TextPart`
  and `ReasoningPart`; an image, a file, a tool call, a tool result and the
  tool role are refused by name with `UnsupportedContentError`, whatever else
  the content carries, so the discriminator they will be stored under is
  reserved without being built. `MessagePart` is the closed union,
  `checked_parts` the one rule about how many there may be, `Provenance` what
  an answer records (agent, engine, model, run), `Message` a node of the tree
  (id, conversation, parent, role, parts, `created_at`, channel, provenance —
  required on an assistant message and refused on any other; no token counts),
  and `Conversation` the owner, the agent, the title and the active leaf. A
  part holds up to a million characters and a message 64 of them, so no answer
  a model can produce has to be cut. `domain/values.py` holds the checks these
  records share. `checked_uuid` and `checked_text` (bounded, and no NUL and
  no unpaired surrogate, so what the format holds is storable and encodable);
  `checked_fragment`, the same bound with none of that, for a piece of a
  message still streaming; `checked_instant`, which is aware **and** inside
  the years 1970..9998 once it is UTC, so no record holds a time that could
  not be written back; `checked_line` for a title; `clean_text`, the lossy
  repair applied to what a provider sent, which joins a character that
  arrived in two halves before it replaces what is left; `publishable` and
  `flush`, which are how the application turns an engine's fragments into
  the deltas it publishes — NUL dropped first, a trailing half held back, what
  is still half replaced, so that everything published joined is exactly
  `clean_text` of everything the engine sent; and `describe`,
  which is what a refusal says **instead of** repeating the value it refused.
  `domain/run.py`: `RunState`, `ACTIVE_RUN_STATES`, `ENDED_RUN_STATES`,
  `FAULTED_RUN_STATES` and `Run`, which holds what its state asks for — an end
  when it ended, an error only when it ended badly — with `is_active` and
  `provenance`; its times are checked for being times and not against each
  other, because a wall clock that steps backwards must not make a run in
  flight unrecordable. `domain/turn.py`: what a running turn streams, as the
  platform's own events and not AG-UI's (`RunStarted`, `MessageStarted` —
  carrying the role and the parent, so a watcher can place a message before
  any of it exists — `TextDelta`, `ReasoningDelta`, `MessageCompleted`,
  `RunEnded`, `TurnEvent` as their union) and `RunEvent`, the envelope that
  gives each event its position in its run (`FIRST_POSITION`, from 1, no
  gaps): engines yield bare events, the application numbers them, and a
  watcher re-attaches by the last number it saw. New errors:
  `UnsupportedContentError`, `UnsupportedFormatError`, `StoredDataError`,
  `NotFoundError` and its three, `NotTheOwnerError`, `RunAlreadyActiveError`,
  `IllegalTransitionError`, `InvalidMessageTreeError` — each with its status in
  `api/errors.py`, which the exhaustive table there required. The whole
  not-found family **and** `NotTheOwnerError` answer one body, byte for byte,
  so an id cannot be probed for existence; `StoredDataError` is a 500 that says
  nothing, since a row of ours that cannot be read is not the request's fault.
  In `core`: `conversation_format.py` owns the **one** encoding, in both
  directions (`message_to_data` / `message_from_data`, `part_to_data` /
  `part_from_data`, `provenance_to_data`, `instant` — a time is always written in UTC, so one instant has one
  spelling). It reads the kind **before** anything else, so unsupported
  content is never reported as malformed; it refuses an unknown key, an id
  spelt any way but the canonical one, a naive time and a message with no
  parts; and it dispatches on the recorded version through one upgrade
  table **per document shape** — a message, a run event — so a build reads every version up to its own, refuses one above it, and
  an upgrade written for one shape can never be handed another (each hook is
  exercised with a stand-in version 0). `domain/stored.py` holds
  `reading_stored`, and it is **the read path**. It is in `domain` because a
  store may import `domain` and must not import `core` (`docs/layout.md`),
  and it is how a store turns its own columns into the flat records it owns
  them for — `Conversation`, `Run`, `User`: each validates itself, an
  `InvalidValueError` escaping a store would be answered as though the
  request had been at fault, and the four ways a malformed row breaks the
  code reading it (`KeyError`, `TypeError`, `AttributeError`, `ValueError`,
  and `RecursionError`) are converted too. `tree_of_stored`,
  `message_from_stored`,
  `run_event_from_stored`, `active_run_stored` and
  `check_may_start_run_stored` are that wrapping already done, in `core`, and
  **their callers are the application**. A fault of the
  data becomes `StoredDataError`, chained, which `api` answers with nothing
  and logs **with its causes** (`api.chain`); the `*_from_data` readers are
  for what the platform itself wrote, since a request carries no
  `format_version` at all. An id a request named and that is not there stays
  a `MessageNotFoundError` throughout, because nothing is wrong with the rows. `domain.text_parts` makes content out of text too long
  for one part, so an answer is never lost to a bound; it sits in `domain`
  beside `clean_text` and for the same reason, that its caller is an agent
  adapter, which may not import `core`. `domain.kept_parts` is what the
  application keeps of an answer: reasoning dropped, and one empty piece of
  text if that leaves nothing, because a message always has content and a
  turn answered with nothing should be recorded rather than left out. The format reserves one key,
  `extras`, on every document it writes and on every part of one — a message
  and each of its parts, a run event and the event inside it: an object of at
  most 64 KiB of storable text that a build which does not use it accepts and
  reads past, which is what lets a
  field be **added** without moving the version, and where vendor-specific
  extras will live. This build writes none and keeps none. `conversation_tree.py` owns the
  tree. **`ConversationTree` is a conversation read once and checked once** —
  every message by id, in order, and every parent's children in order — built
  by `tree_of` (messages a request brought) or `tree_of_stored` (rows,
  checked as stored data at that one door), and every question afterwards is
  a method on it that can fail for one reason only: an id the request named
  that is not there. `may_follow` is the whole rule of what may hang under what — a root is
  a question, a question follows an answer, an answer follows a question, an
  answer or a tool result, a tool message follows the answer that called it,
  so a turn is a chain and tools need no rewrite — with `check_parent`,
  `check_tree`, `path_to`, `children_of`, `siblings_of`,
  `leaves`, `default_leaf` (the branch below the author's last position whose
  own last message is newest), `turn_start`, `parent_for_edit`,
  `parent_for_regenerate` (which goes back to the question of the whole turn),
  `branches_along` and `branches_of` (a message with the branches beside it
  and where it falls among them — what the interface draws as "2 of 3") and
  `check_attachment` (a parent from somebody else's conversation is simply
  not among these messages). They are methods, not free functions: the only
  way to have a tree is `tree_of` or `tree_of_stored`, both of which say
  which conversation they are reading and check it first, so there is one way
  to ask and one set of rules. `check_tree` is the one wrapper kept, for a
  caller that wants the rules applied and has no further question.
  `titles.py` derives the title from the question's text as a whole
  (`title_from_text`, `derive_title`, `first_question`), cutting at a word
  boundary and never inside a character. `history.py` is the **placeholder**
  context policy (`message_chars`, `history_chars`, `trim_history` —
  characters, not tokens, dropping whole turns from the front and always
  keeping the turn being answered). `runs.py` is the state machine
  (`RUN_TRANSITIONS`, `may_transition`, `check_transition`, `transition` —
  which clamps each stamp to the one before it, gives an ending run the start
  it never recorded, and puts the error through `run_error`, so that ending a
  run never fails over the text of what went wrong: `UNSAID_ERROR` for a
  failure with nothing to say, `TRUNCATED` on the end of one that was too long
  — `active_run`, `may_start_run`, `check_may_start_run`) **For the next step:** a store never parses or builds a message or a run
  event — the format is `core`'s and a store may not import it. What crosses
  the conversation and run ports for those two is the **document** (the plain
  mapping `message_to_data` / `run_event_to_data` writes), which a store keeps
  as jsonb and hands back untouched, with the record passed beside it when it
  needs a field for one of its own indexed columns (id, conversation id,
  parent id, created at, seq); the application encodes before it writes and
  decodes with the `*_stored` readers after it reads. `Conversation` and `Run`
  cross as records, since the store owns their columns.
  `resume_point` says where a
  watcher opening a conversation with a run in flight attaches: `after`, the
  run's last completed message or the event that started it, and `follows`,
  what the next announcement will hang under — so a caller has both of the
  things a slice is checked with, and is replayed the message still being
  produced and none it already has. And
  the two order checks: `check_event_order` for what the application publishes — one
  message at a time, each hanging under the one before it, completed as it was
  announced, of this run and this conversation (both **required**), a run that
  finished leaving nothing half-written, numbered without gaps, the deltas published for a message adding up to the
  message that was stored, in one linear pass — over a whole run, a run **still going** (`ended=False`, which is what
  a watcher of a live one receives) or **the slice a re-attaching watcher
  receives**
  (`after=<the position it last saw>` and `follows`, with `open_message` for
  the message the cut fell inside); and `check_engine_events` for what an engine yields, which
  is what the shared contract suite will hold both engines to: one answer at a
  time, announced, streamed, completed; streaming is optional, and an answer
  that streamed any text completes with exactly what it streamed
  (`cut_short=True` for the failure cases, where a turn ends wherever it
  ended). What the specs left open and this step settled is written into
  `docs/specs/conversations.md` and `docs/specs/runs.md`, not only here.
  `backend/tests/conversations.py` holds the builders every later step will
  use; the tests are the `backend/tests/unit/test_conversation_*.py`,
  `test_run_*.py` and `test_turn_events.py` modules, one per source module.
  **For the run-executor step:** a `Run` records no owning process and no
  heartbeat. The POC is one process, so nothing can tell an orphan from a
  running run; `runs.md` describes both, and they arrive with the second
  process, not before.
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

### Step 4 — credential-store   (feature/poc-4-credential-store)

Summary: the first real adapter. `datastore/schema.sql` — one idempotent
definition with a version row written last, named constraints, `timestamptz`
everywhere, CHECKs that a key is a SHA-256 — shipped in the wheel.
`datastore/schema.py`: `create_schema` (apply on an empty schema, no-op on
this version whole, refuse anything else and leave it untouched),
`check_schema`, `schema_version`, all pinned to `current_schema()`.
`PostgresCredentialStore` over a pool it is given, passing the whole
contract suite including the concurrency tests. `asyncpg` is the one new
dependency (Apache-2.0, brings nothing). CI runs the tests against a
PostgreSQL service pinned by digest. No CLI, no conversations or runs
tables, no wiring yet.

Review: 3 rounds.
- High: 2
  - `create_schema` stamped the current version onto an old schema, so the
    start-up check passed on a database it must refuse — fixed: the SQL
    never overwrites a version, `create_schema` looks before it writes, and
    a pinned SHA-256 of `schema.sql` fails a test when the file changes
    without the version and the hash being updated.
  - The schema checks judged the whole search path while the file writes
    only to its first schema: a foreign schema further along passed the
    check, and another application's tables were named as ours — fixed:
    every lookup is pinned to `current_schema()`, real tables only, and a
    relation the path reaches first is refused as shadowing.
- Medium: 6 (6/0)
- Low: 15 (15/0)

Checks: `scripts/check-all.sh` without a database (873 passed, 64 skipped)
and with one, `ROBINAUTS_REQUIRE_POSTGRES=1` (935 passed, 2 skipped); no
flakes over repeated and parallel runs; shown by mutation that removing
either advisory lock, the atomic take or the upsert fails the contract.
Not done / to watch: the CI service container and the wait script have not
run on GitHub before this push. About 3,000 lines with tests, over the aim.
Important design decisions made / open questions:
- The schema is edited in place (no migrations): any edit of `schema.sql`
  must update `SCHEMA_SHA256`, and bump `SCHEMA_VERSION` once anything is
  deployed; `robinauts db init` (a later step) works on an empty schema
  only.
- The connection's search path must start with the schema the tables live
  in; `check_schema` verifies that the names resolve there.
- The cap on pending sign-ins is held by a transaction-scoped advisory
  lock; `create_schema` takes another, keyed on the schema.
- Exactly four refusals are translated from constraint violations to
  `InvalidValueError`, by constraint NAME; the names in `schema.sql` are
  interface. Every other driver error propagates.
- Tests take `ROBINAUTS_TEST_DATABASE_URL`; without it they skip; with
  `ROBINAUTS_REQUIRE_POSTGRES=1` (CI) a skipped or deselected database
  suite fails the run. Each test works in a schema of its own.

### Step 5 — oidc-adapter   (feature/poc-5-oidc-adapter)

Summary: the HTTP side of sign-in. `adapters/`: `HttpIdentityProvider` on
`httpx` (it builds and owns its client: no redirects, TLS that cannot be
weakened, connect/read/total timeouts, an uncompressed raw-byte response
bound, client authentication by basic or post, and an exchange from which
no credential can be reached), `SystemClock`, `OsSecretSource`, the TOML
reader `read_toml` (raw data; `core` validates) and `check_client_secrets`.
`tests/standin/`: a real loopback identity provider that checks client
authentication, the code, the redirect URI and PKCE, and can be scripted to
misbehave. An end-to-end test drives `SignIn` through the real adapter. No
routes, cookies, wiring or CLI yet.

Review: 2 rounds.
- High: 1
  - A deeply nested JSON answer raised `RecursionError`, escaping the
    port's contract with a traceback whose frames held the client secret,
    the code and the verifier — fixed: caught on both endpoints, and the
    exchange restructured so that nothing reachable from an exception it
    raises (frames, `__cause__`, `__context__`) holds a credential,
    cancellation included.
- Medium: 5 (5/0)
- Low: 6 (6/0)

Checks: `scripts/check-all.sh` without a database (1007 passed, 64
skipped) and with one required (1069 passed, 2 skipped); the step's io
tests three times over, no flakes, no sleeps; hardening probed by a
reviewer with raw sockets (slow drip, no headers, lying lengths, encodings,
redirects, pool after 30 timeouts and 30 cancellations).
Not done / to watch: no HTTPS stand-in, so "TLS verification is on" is
proved by inspecting the SSL context and the absence of any parameter to
weaken it. About 3,300 lines with tests and the stand-in, over the aim.
Important design decisions made / open questions:
- `httpx` brought `certifi` (MPL-2.0): the first runtime row of the
  restricted table in `DEPENDENCIES.md` (unmodified, installed by the
  package manager, never inside the wheel).
- The library-confinement contracts (`httpx`, `asyncpg`, the agent
  frameworks) and the `api` contract are about DIRECT imports
  (`allow_indirect_imports`): infrastructure may import the package that
  holds a library, never the library.
- Token endpoint statuses: 408/425/429 and 5xx are `provider_unavailable`;
  other 4xx, and an OAuth `error` in a 200, are `provider_refused`.
- The client secret is looked up by variable name at the moment of the
  exchange and never kept.
- Configuration has no port: an adapter reads raw tables, `core` validates,
  the composition root calls both and must merge every start-up problem it
  can gather into one `ConfigError`.
- Derived from neorc; recorded in `docs/legal/ip-clearance.md`.

### Step 6 — auth-api   (feature/poc-6-auth-api)

Summary: the web layer of sign-in. `robinauts.api` on FastAPI: the four
auth routes and `/health`; cookies (`__Host-` on https, plain on loopback
http); request protection as ASGI middleware that reads the raw headers
itself; the guard and the per-route declaration `public()` /
`signed_in()`, checked by a test and again when the application is built
and when it starts; fixed error bodies; one helper that escapes everything
request-derived before it is logged. `robinauts.app`: `Deployment` and
`create_app`, merging every start-up problem into one `ConfigError`,
opening and closing the pool and the adapters in the ASGI lifespan, every
collaborator injectable. `backend/openapi.json` is committed and a test
keeps it in step. No CLI, no UI serving, no development mode yet.

Review: 3 rounds.
- High: 2
  - The "every route declares a permission" check saw only `APIRoute`s: a
    mounted application, a plain Starlette route and a websocket were
    served while it stayed green — fixed: the walk fails closed on anything
    it does not recognise, recurses into mounts, and runs at build and at
    start-up so such an application does not start.
  - The same check did not see FastAPI's `frontend()` routes, kept in a
    private list — fixed: every route list is read, a backstop refuses any
    route-bearing attribute it does not know, and the FastAPI range is
    pinned to the version whose internals were read.
- Medium: 8 (8/0)
- Low: 13 (13/0)

Checks: `scripts/check-all.sh` without a database (1171 passed, 67
skipped) and with one required (1236 passed, 2 skipped); the step's tests
three times over under `-W error`, no flakes. Reviewers drove the real ASGI
application with raw scopes.
Not done / to watch: `uvicorn` is not a dependency yet; it arrives with
`robinauts start`. That step must start the server with the access log off
(or query strings stripped for `/auth/callback`): an access log would
write `code` and `state`. About 4,500 lines with tests, over the aim.
Important design decisions made / open questions:
- To serve the UI, a later step adds one line, `"/ui"`, to
  `api.FRAMEWORK_PATHS`; the walk refuses it otherwise. A permission is
  declared on the route itself, not on `include_router`. Routes are never
  added after start-up.
- `fastapi>=0.141,<0.142`: the route walk reads FastAPI internals; bumping
  the range means re-reading `fastapi.routing.APIRouter`
  (`ROUTE_LISTS`, `READ_FASTAPI`).
- A state-changing request is accepted only with `Content-Type:
  application/json`, `Sec-Fetch-Site` absent or exactly `same-origin` /
  `none`, no duplicated deciding header in any casing, and — with a session
  cookie — `Origin` equal to `public_url` (or, with no `Origin`,
  `Sec-Fetch-Site: same-origin`). Websocket and unknown scopes are refused.
- Error bodies never repeat the request; sign-in errors answer one fixed
  sentence per code; no 5xx says why. Navigation routes answer every
  failure with a redirect to the sign-in page.
- `GET /auth/login` changes state by design; the consequence is in the
  known limits of `docs/specs/sign-in.md`.
- The guard (`api.access.current_user`) is the seam for the development
  mode.
- Derived from neorc; recorded in `docs/legal/ip-clearance.md`.

### Step 7 — dev-mode   (feature/poc-7-dev-mode)

Summary: the local development mode — no sign-in, one fixed local user who
is a real row, loopback only. `domain/local.py` (`LocalMode`, the reserved
key `("!local", "developer")`, the loopback predicates),
`application/local.py` (`LocalAccess`), the guard resolving every request
to that user, the protection refusing anything not addressed to this
machine, `GET /auth/session` saying `local_development: true`, and
`create_app(local_development_host=…)` as the only way to ask for it. The
CLI flag and the banner come with later steps.

Review: 1 round.
- High: 0
- Medium: 1 (1/0)
- Low: 3 (3/0)

Checks: `scripts/check-all.sh` without a database (1265 passed, 70
skipped) and with one required (1333 passed, 2 skipped). The reviewer tried
and failed to switch the mode on unasked, to combine it with sign-in, and
to get past the loopback and origin rules (trick host spellings, other
loopback ports, `null` origins, DNS rebinding shapes).
Not done / to watch: "the local user owns what it creates" can only be
shown once conversations exist. About 1,700 lines with tests, over the aim.
Important design decisions made / open questions:
- No environment variable can switch the mode on: only the explicit
  argument, which is also the bind host. Asking for it together with a
  sign-in configuration, or for neither, is a start-up `ConfigError`.
- The bind host must be a literal loopback address or exactly `localhost`
  (`domain.is_loopback_bind_host`), stored normalised; a request's `Host`
  is judged by the looser `is_loopback` (which moved to `domain`, still
  exported by `core`). Every request, reads included, needs one loopback
  `Host` and a server that answered on loopback (a unix socket counts; an
  absent `server` is refused).
- Every write in the mode is judged as credentialed: `Origin` equal to the
  host the request was addressed to (port and scheme matter), or
  `Sec-Fetch-Site: same-origin` with no `Origin`. A client that sends
  neither (curl) is refused.
- The reserved provider id `!local` cannot be configured (`ProviderConfig`
  now holds ids to their shape) and `SignIn.resolve_session` never answers
  the local user, so nothing reaches that account in normal mode.
- `CredentialStore.user_by_key` reads a user without writing; the local
  user is read per request and written once.

### Step 8 — conversation-format   (feature/poc-8-conversation-format)

Summary: the platform's own conversation format, pure, standard library
only. `domain`: `Message` (parts, provenance, channel), `Conversation`,
`Run`, `RunEvent`, the engine's events (no ids) and the platform's turn
events, the value checks and the text helpers (`clean_text`, `text_parts`,
`kept_parts`, `publishable` / `flush`), `reading_stored`. `core`: the two
canonical, versioned, strict documents (a message, a run event) with their
upgrade registries and the reserved `extras`; the stored readers;
`ConversationTree`; titles; trimming by whole turns; the run state machine
with `run_error`; the order checks `check_engine_events` and
`check_event_order`; `resume_point`. No ports, stores, application,
engines or wire yet — they are built on this.

Review: 8 rounds.
- High: 17, all fixed. The ones that shaped the contract:
  - A conversation that exists but is not yours could be told apart from
    one that does not exist — one identical body for the whole not-found
    family.
  - Exact-version matching would have made the first version bump a data
    migration — a build reads every version up to its own through
    upgraders; adding a kind, a role or data under `extras` never moves the
    version.
  - The role rule made tools impossible — a turn is a chain: a user message,
    then assistant (and later tool) messages.
  - `clean_text` destroyed a character split across two deltas, and later a
    NUL between the halves still broke it — one function, `publishable`,
    with a property test: what is published is what is stored.
  - Stored-data faults answered 422 with internal ids, then were logged
    without their cause — `StoredDataError`, a 500 that says nothing, with
    the escaped cause chain and stack frames in the log.
  - An engine could not yield "a message as it was stored" — two event
    vocabularies: the engine's (no ids) and the platform's.
  - Non-streaming answers were illegal; a reasoning-only answer left a
    message with no parts; a turn with no answer could end `finished`.
  - One upgrade registry served two document shapes; then the parts
    document was dropped: exactly two versioned documents exist.
  - The read path lived in `core` with the datastore as its caller, against
    the layering contract — documents cross the store ports, flat records
    are built in stores inside `domain.reading_stored`, the application
    decodes.
  - Run events had no canonical encoding.
- Medium: 39 (39/0)
- Low: 49 (48/1)

Checks: `scripts/check-all.sh`, with the database required: 1932 passed, 2
skipped; stable over repeated and randomised runs, no test over a second.
Reviewers property-tested `publishable` (100,000 sequences), the two order
checks end to end (4,000 answers at every re-attach prefix), and the
encoding (30,000 encode/mutate/decode rounds).
Not done / to watch: the one low left is `Run` recording no owning process
or heartbeat — single process is the POC's scope (`docs/specs/runs.md`
describes the multi-process rules). About 6,500 lines with tests: far over
the aim, and eight review rounds — this step should have been two (records
and encoding; tree, runs and events).
Important design decisions made / open questions:
- Messages and run events cross the store ports as DOCUMENTS
  (`core.message_to_data`, `core.run_event_to_data`), with the record
  beside them for a store's indexed columns; conversations and runs cross
  as records. Stores never import core.
- Completed messages are appended when complete; a message in flight lives
  in its run's numbered events. Opening a conversation with an active run
  returns the run id and `resume_point` (`after`, `follows`); attaching
  there replays exactly the message in flight.
- An engine yields `AnswerStarted`, `AnswerTextDelta`,
  `AnswerReasoningDelta`, `AnswerCompleted(parts)`; it reports failure by
  raising and is cancelled by cancelling its task. Text deltas are
  optional; if any were streamed they join to the completed text.
  Reasoning is streamed and not stored in this version.
- The application publishes through `publishable` / `flush`, stores
  `kept_parts(...)`, ends runs through `transition` and `run_error`, and
  assigns event positions; whoever marks a run `interrupted` appends its
  `RunEnded`.
- Bounds: 1,000,000 characters a part, 64 parts, 120 a title, 64 KiB of
  `extras`, positions up to 2^53 − 1, years 1970–9998.
- A turn request names the conversation and either a new user message with
  its parent, or the assistant message whose turn is produced again
  (`docs/specs/wire.md`).

