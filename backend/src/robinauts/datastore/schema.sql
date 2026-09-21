-- SPDX-License-Identifier: Apache-2.0
-- Copyright The Robinauts Authors
--
-- The whole schema of a Robinauts deployment, in one file.
--
-- Until there is an active production deployment this file is **edited in
-- place** and there are no incremental migrations (docs/specs/backend.md):
-- a database made from an older definition is recreated rather than
-- upgraded. Every change here therefore comes with a bump of
-- `SCHEMA_VERSION` in schema.py, which is what a server compares against
-- the row in `schema_version` before it agrees to start.
--
-- It is applied by a command (`robinauts db init`), never by the server
-- itself, and it is applied in one transaction: the whole file goes in as
-- one simple query, so a failure half way leaves nothing behind. Applying it
-- by hand needs that transaction asked for explicitly:
--
--     psql -v ON_ERROR_STOP=1 --single-transaction -f schema.sql
--
-- Without both flags psql runs the statements one by one and keeps going
-- after an error, which is exactly the half-applied database the version row
-- at the bottom of this file is placed to expose.
--
-- **Editing this file means bumping `SCHEMA_VERSION` in schema.py.** There
-- is no migration to write -- a database of an older version is made again --
-- but a build that reads this schema while calling it the previous version
-- would run against tables it was not written for. A test pins the SHA-256
-- of this file beside the version so that an edit without a bump fails.
--
-- Later steps add the conversation, run and usage tables to the bottom of
-- this file. Keep each table's block self-contained -- the table, its
-- comments, then its indexes -- so that adding one is an addition and not
-- an edit.
--
-- Conventions:
--
--   * every point in time is `timestamptz`. A `timestamp` would be a wall
--     clock with no zone, read as one thing by the server and another by
--     the process, and an expiry that means two things is no expiry.
--   * **no default reads the clock for a decision.** Expiry times and
--     creation times are computed by the application from its own `Clock`
--     port and passed in, so that one clock decides what has expired
--     (docs/specs/backend.md, "Where expiry is involved, one clock
--     decides"). The one `now()` below dates the schema itself, which is
--     not a decision any code makes.
--   * anything looked up by a secret is looked up by the SHA-256 of it, in
--     lower-case hex, and the column says so with a CHECK. The secret
--     itself is never stored (ports/credentials.py). The store checks the
--     same shape in Python before it writes, because a constraint only runs
--     when a row is really inserted and there are statements that decline
--     to insert one; this is the backstop under that, for the row nobody
--     went through the store to write.
--   * every column a sweep deletes by is indexed.
--
-- The statements are idempotent where that is honest -- `IF NOT EXISTS` on
-- what can simply already be there -- so that applying the file twice is a
-- no-op rather than an error. It is not a migration tool: it will not
-- reshape a table that exists with the wrong columns, which is what the
-- version check is for.


-- ---------------------------------------------------------------------------
-- The schema's own version.
-- ---------------------------------------------------------------------------

-- One row, for ever: `only_row` is a boolean primary key that must be true,
-- so a second row cannot be inserted and the version cannot become ambiguous.
CREATE TABLE IF NOT EXISTS schema_version (
    only_row boolean PRIMARY KEY DEFAULT true CHECK (only_row),
    version integer NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Users.
-- ---------------------------------------------------------------------------

-- Keyed by (provider, subject): the same address at two providers is two
-- users, and a provider that reassigns an address does not hand over an
-- account. `name` and `email` are refreshed at every sign-in and may be
-- null; `email` is only ever an address the provider verified.
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    subject text NOT NULL,
    name text,
    email text,
    created_at timestamptz NOT NULL,
    UNIQUE (provider, subject)
);


-- ---------------------------------------------------------------------------
-- Sessions.
-- ---------------------------------------------------------------------------

-- A signed-in browser. The cookie carries the secret; this table holds its
-- SHA-256 and nothing that could open the session. A session is never
-- renewed, so `expires_at` is written once.
-- Every constraint here is named, and the names are not decoration: the
-- store translates a violation of one of them into an answer for its caller
-- (`datastore/credentials.py`), and it tells them apart by name. A
-- constraint left to PostgreSQL to name would still be told apart, until the
-- day somebody added a second one of the same kind and every violation
-- started being reported as the first.
CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_hash text NOT NULL
        CONSTRAINT sessions_secret_hash_key UNIQUE
        CONSTRAINT sessions_secret_hash_is_a_hash CHECK (secret_hash ~ '^[0-9a-f]{64}$'),
    user_id uuid NOT NULL
        CONSTRAINT sessions_user_id_fkey REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL
);

-- Deleting a user ends their sessions with them (ON DELETE CASCADE above),
-- which needs the foreign key's own column indexed or every delete is a scan.
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions (user_id);

-- What the sweep deletes by.
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions (expires_at);


-- ---------------------------------------------------------------------------
-- Sign-ins in progress.
-- ---------------------------------------------------------------------------

-- What a sign-in leaves between the button and the callback: short-lived,
-- single use, found by the SHA-256 of the `state` handed to the provider.
-- The `nonce` and the PKCE verifier are in the clear on purpose -- the
-- callback compares them with what the provider sent, and a hash cannot be
-- compared with something it has not seen (ports/credentials.py says why
-- the row is worth nothing to a reader all the same).
--
-- No foreign key: a sign-in in progress belongs to nobody yet.
CREATE TABLE IF NOT EXISTS pending_logins (
    state_hash text PRIMARY KEY
        CONSTRAINT pending_logins_state_hash_is_a_hash
        CHECK (state_hash ~ '^[0-9a-f]{64}$'),
    provider text NOT NULL,
    nonce text NOT NULL,
    verifier text NOT NULL,
    return_to text,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL
);

-- What the sweep deletes by, and what the cap counts by.
CREATE INDEX IF NOT EXISTS pending_logins_expires_at_idx ON pending_logins (expires_at);


-- ---------------------------------------------------------------------------
-- The version, written last.
-- ---------------------------------------------------------------------------

-- Last on purpose. This row is the claim "every table above exists, in the
-- shape version 1 describes", so it must not be written until they do: a file
-- that stopped half way -- an interrupted `psql`, a permission error, a
-- disconnection -- leaves no version, and `create_schema` and `check_schema`
-- both refuse what they find rather than believing it.
--
-- `DO NOTHING`, never `DO UPDATE`. Relabelling an older schema as this one
-- would be the worst thing this file could do: the `CREATE TABLE IF NOT
-- EXISTS` statements above leave an existing table exactly as it is, so an
-- `UPDATE` here would stamp "version 1" on version 0's tables and every
-- check afterwards would pass. Deciding whether this database may be
-- written to at all is `create_schema`'s job, before any of this runs.
--
-- The version this file defines must equal `SCHEMA_VERSION` in schema.py;
-- tests/unit/test_datastore_schema.py fails if the two drift apart.
INSERT INTO schema_version (version) VALUES (1)
ON CONFLICT (only_row) DO NOTHING;
