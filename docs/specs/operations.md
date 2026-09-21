# Operations

What an internal platform team deploys and controls.

## Deployment

- One backend process, which also serves the frontend; one PostgreSQL.
  Nothing else (goal 6).
- Installed from one Python wheel. A container image is planned.
- PostgreSQL is always required. A documented one-command local Postgres
  covers development and demos.
- A local development mode runs without sign-in, on the loopback interface
  only ([sign-in.md](sign-in.md)). It is not a way to deploy.
- Served at the root of an origin, over https. `public_url` is mandatory
  ([sign-in.md](sign-in.md)).
- Upgrades: install the new wheel, bring the schema up to date, restart.
  Until a production deployment exists the schema is edited in place and
  the database is recreated; after that, migrations upgrade it in place
  ([backend.md](backend.md)).
- A restart lets active runs drain for a bounded time; the rest are marked
  interrupted and can be retried by their authors ([runs.md](runs.md)).
  Several backend processes may run against the one database.
- Outbound traffic: the identity providers at sign-in, and the model
  providers the operator configured. Nothing else.

## Configuration

- Files, version-controllable, with no secret in them: a secret is always
  given as the *name* of an environment variable.
- What the operator configures: sign-in providers, the allow list and the
  admins ([sign-in.md](sign-in.md)); model providers, models and agents
  ([agents.md](agents.md)); limits and retention (below).
- Unknown keys are errors, and all problems are reported at once, at
  start-up.

## Limits

All optional, all set by the operator:

- requests per minute per user;
- a maximum attachment size;
- timeouts for a model call, a tool call and a whole run;
- a maximum context per agent. A history that exceeds it is trimmed above
  the agent port, so both engines behave the same;
- a token budget per user per period, which refuses new turns once spent
  and is shown to the user. It depends on usage recording and arrives with
  it.

## Retention

- An optional retention period, after which conversations are deleted
  automatically. By default nothing expires
  ([privacy.md](privacy.md)).
- The trash is a fixed 30 days and is not configurable.

## Audit

- Read and exported by admins through the API
  ([privacy.md](privacy.md)).

## Usage reporting (planned)

All of it — recording, API, screens — is planned and not specified. What
is settled:

- it records the input and output tokens of every model call, against the
  model, the agent, the conversation and the user. Tokens, not prices: a
  company feeds the records into its own cost tooling;
- an API exports the records;
- the records hold no message content, outlive the conversation they refer
  to, and keep their reference to the user even after a purge;
- the admin's view of token usage, and token budgets, arrive with it.

## Details likely to change

- Whether the configuration is one file or several, and the key names.
  Sketches are in [sign-in.md](sign-in.md) and [agents.md](agents.md).
- The `robinauts` command: `start`, `db init`, later `db migrate`, and
  what else it needs.
