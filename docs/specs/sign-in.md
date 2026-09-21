# Sign-in, users and roles

People sign in through the company's identity provider. There are no local
passwords. The design is neorc's
(`neorc/docs/working-notes/sso-plan.md`), re-implemented in this project's
[layout](../layout.md): the code is written fresh, from neorc's design and
with neorc's code open, and that is recorded in
`docs/legal/ip-clearance.md` when it lands.

## Providers

- Google and Okta, over OpenID Connect. One generic client serves both:
  Google is recognised by its issuer; Okta is any other issuer, with a
  `groups_claim`. Other providers may work and are not claimed to.
- The client is written on `httpx`. There is no OIDC, JWT or crypto
  dependency.
- Authorization code flow with `state`, `nonce` and PKCE (S256).
- Discovery happens at the first sign-in, not at start-up; a success is
  cached, a failure is not. The issuer it names must equal the configured
  one. The authorization and token endpoints must be `https`, loopback
  excepted.
- **The ID token signature is not verified.** The token comes from the
  token endpoint over TLS, which OIDC Core 3.1.3.7 allows for the code
  flow. Claims are checked: `iss`, `aud`, `azp`, `exp` and `iat` (60 s
  skew), `nonce`, `sub`. If a token ever has to be accepted from anywhere
  else, this no longer holds: that needs a JWT library, JWKS, and a
  decision of its own.
- Google's `email_verified` is trusted only when `hd` is present or the
  address is `gmail.com`.
- Sign-in buttons are text ("Sign in with Google"). No provider logos.

## Who may sign in

An allow list. Each entry names a provider and one matcher:

| matcher | meaning |
|---|---|
| `everyone` | anyone the provider authenticates |
| `subject` | one account, by the provider's subject id |
| `email` | a verified email, case-insensitive |
| `email_domain` | verified emails of a domain — not for Google |
| `hosted_domain` | Google's `hd` claim — Google only |
| `group` | a value of the provider's groups claim |

With providers configured and no allow entry, start-up fails.

## Users

- The first successful sign-in creates a user, keyed by
  `(provider, subject)`. Later sign-ins refresh its name and verified
  email.
- A user owns their conversations and projects
  ([privacy.md](privacy.md)).

## Roles

- Two roles: **user** and **admin**.
- Admins are named in the configuration, with the same matchers as the
  allow list.
- The role is decided at sign-in and held by the session. The UI is told
  the role so it can show admin screens; the server enforces it regardless.
- What an admin can and cannot see is in [privacy.md](privacy.md).
- Roles map to permissions in one fixed, exhaustive table in `core`. Every
  route declares the permission it needs, and a test asserts that every
  route declares one. Ownership and project membership are checked in the
  application, not in routes.

## Sessions

- A session is a row in the database. The cookie holds a random 256-bit
  secret; the database holds its SHA-256.
- Cookie: `__Host-` prefix, `HttpOnly`, `SameSite=Lax`, `Secure`.
- Fixed lifetime, `session_hours`, 12 by default. No renewal. The
  provider's tokens are discarded after sign-in.
- Sign-out deletes the row and clears the cookie.

## Request protection

- No CSRF token. Every write must be `application/json` and must not be
  cross-site (`Sec-Fetch-Site`). A cookie-authenticated write must also
  carry `Origin` equal to `public_url`.
- The deployment is at the origin root; `public_url` is mandatory and
  drives the redirect URI, the cookie prefix and the origin check.

## Local development mode

- A mode for developing on one's own machine, which **requires no
  sign-in**: no identity provider, no sign-in configuration.
- Everything runs as one fixed local user, who owns the conversations
  created in this mode. The rest of the platform behaves as usual, so
  ownership checks and everything built on users is exercised.
- It is never the default. It is asked for explicitly when starting the
  server, and it cannot be combined with a sign-in configuration.
- It serves the loopback interface only, and refuses to start on any other
  address.
- The server logs a warning at start-up, and the interface shows a
  permanent banner saying that sign-in is off.
- The checks on writes (JSON, same origin) stay on.
- Tests still exercise the real sign-in flow, against a stand-in identity
  provider; this mode is not a substitute for that.

## Not there yet

- **API tokens** are planned. Until they exist every API is reached with a
  signed-in session. They are also what channels other than the browser
  will sign in with ([channels.md](channels.md)).

## Details likely to change

Configuration — a TOML file; secrets are given as the *name* of an
environment variable; unknown keys are errors; all problems are reported
at once:

```toml
public_url = "https://robinauts.example.com"
session_hours = 12

[providers.google]
title = "Google"
issuer = "https://accounts.google.com"
client_id = "..."
client_secret_env = "ROBINAUTS_GOOGLE_SECRET"

[providers.okta]
title = "Okta"
issuer = "https://example.okta.com/oauth2/default"
client_id = "..."
client_secret_env = "ROBINAUTS_OKTA_SECRET"
scopes = ["openid", "email", "profile", "groups"]
groups_claim = "groups"

[[allow]]
provider = "google"
hosted_domain = "example.com"

[[allow]]
provider = "okta"
group = "robinauts-users"

[[admin]]
provider = "okta"
group = "robinauts-admins"
```

Routes:

| route | purpose |
|---|---|
| `GET /auth/session` | who is signed in, their role, the providers; never a 401 |
| `GET /auth/login/{provider}` | start a sign-in |
| `GET /auth/callback/{provider}` | finish it; the redirect URI to register |
| `POST /auth/logout` | sign out |

- A pending sign-in is stored under the SHA-256 of `state`, single use, for
  10 minutes; their number is capped.
- A failure redirects to the sign-in page with a fixed error code; the
  provider's own words go to the log only.
- The UI shows the sign-in page in place of every page until there is a
  principal, and returns the person to where they were.
- Sign-ins, refusals and sign-outs are written to the audit log.

## Known limits

- The allow list, the admin list and group membership are evaluated at
  sign-in only. A person removed at the identity provider keeps access
  until the session ends, or an operator clears sessions. A shorter
  `session_hours` is the available control.
- No sign-out at the identity provider.
- No rate limit on sign-in beyond the cap on pending sign-ins. The cap
  bounds the table; it does not protect sign-in. Beginning a sign-in needs
  no credentials, so one client that keeps the table full denies sign-in
  to everyone for as long as it goes on. The protection is a rate limit in
  front of the platform — the operator's reverse proxy today, the
  per-client limits of [operations.md](operations.md) later.
- Beginning a sign-in is a plain navigation (a `GET`), so any page can make
  a visitor's browser begin one: it adds a pending sign-in and replaces the
  login cookie of a sign-in that visitor had in flight, which then fails
  and has to be started again. It cannot sign the visitor in to anything:
  the cookie is `SameSite=Lax` and `__Host-`, and the callback checks it.
