# POC scope

Status: draft, for discussion. The specs in [../specs/](../specs/core.md)
describe the whole platform; this note cuts the smallest thing worth
deploying out of them. Where the POC does less than the specs, it says so;
it never does something the specs forbid, so nothing built here has to be
thrown away.

## What the POC is

A deployed Robinauts that a handful of colleagues can sign in to with
Google or Okta and chat with an agent. Each person sees their own
conversations and nobody else's. Model API keys come from the environment.

It proves, end to end: sign-in, the seams (chat UI, agent engine, wire),
the platform-owned conversation record, runs that survive a dropped
request, and a deployment that is one wheel plus one PostgreSQL.

## In

**Sign-in** ([sign-in.md](../specs/sign-in.md))

- Google and Okta over OpenID Connect, the full flow as specified: state,
  nonce, PKCE, claim checks, allow list, server-side sessions with the
  `__Host-` cookie, origin checks on writes, sign-out.
- A user record created at first sign-in.
- The sign-in page, the error codes, return-to after sign-in.
- The TOML configuration, secrets by environment variable name.
- The local development mode: no sign-in, one fixed local user, loopback
  only, with its warning and banner.

**Conversations** ([conversations.md](../specs/conversations.md))

- Private to their author. Every route checks ownership; there is no other
  way to see a conversation.
- Text only.
- Stored in the platform's own format, as a tree (every message has a
  parent), with what an answer records: agent, engine, model, run.
- Edit and regenerate, with branches, as far as assistant-ui provides them
  over our API. First thing to cut if it costs more than expected; the
  tree stays in the store either way.
- List in the panel, open, rename, delete. The title is the beginning of
  the first message.

**Agents and models** ([agents.md](../specs/agents.md))

- Agents defined in the configuration; a picker on the empty chat when
  there is more than one.
- Provider keys read from the environment at start-up, by the variable
  names the configuration gives. Never stored, logged or sent to the
  browser.
- Providers: Anthropic and OpenAI. OpenRouter comes with the
  OpenAI-compatible client.
- **Both engines**, LangGraph and Pydantic AI, behind the agent port, with
  the shared contract suite and the swap test. This is the seam the
  project exists to prove. Second thing to cut: if time is short, one
  engine ships first and the other follows, but the port and the contract
  suite are written for two from the start.
- Tracing to LangSmith and Logfire forced off.

**Runs and the wire** ([runs.md](../specs/runs.md), [wire.md](../specs/wire.md))

- A message starts a run; the run executes in the background, persists
  messages as they are produced, and survives a dropped request.
- One active run per conversation; cancel.
- AG-UI over SSE, emitted by the `api` layer; re-attach to an active run
  when a conversation is opened.
- On restart, runs left `running` are marked `interrupted`. Retry is
  sending the message again.
- A timeout per model call and per run.

**Interface** ([frontend.md](../specs/frontend.md))

- The neorc shell: the collapsible panel with "new chat", the history and
  the profile block with sign-out; the rail state remembered.
- The chat on assistant-ui with Tailwind, behind the `src/chat/` seam, with
  the lint rule that confines it.
- Dark mode following the operating system.

**Backend and deployment** ([backend.md](../specs/backend.md),
[operations.md](../specs/operations.md))

- The layout and its contracts, as scaffolded. FastAPI, asyncpg,
  hand-written SQL.
- One schema definition, edited in place, applied by `robinauts db init`;
  no incremental migrations. Refusal to start on a schema mismatch.
- `robinauts start`. A health endpoint.
- One wheel containing the built frontend, built in CI.
- A deployment guide: PostgreSQL, the wheel, the configuration, the
  environment variables, a TLS-terminating reverse proxy in front,
  registering the redirect URI with Google and Okta. Tried for real on one
  machine.

**Open source, from day zero** ([open-source.md](../specs/open-source.md))

- Headers, `NOTICE`, `AUTHORS`, `CONTRIBUTING.md` with the DCO and the AI
  section, `DEPENDENCIES.md`, `docs/legal/ip-clearance.md` and
  `third-party.md` with their first entries (fetchy layout, neorc sign-in
  design, vendored assistant-ui components).
- CI, blocking: tests with the architecture contracts, ruff, black; the
  Python licence gate and `pip-audit`; the frontend lint, type check, tests
  and build with the bundle licence gate, `npm audit`; `reuse lint`; the
  DCO check.
- Sign-off on every commit.

## Out

Stated by the scope: **roles** (no admin; nobody sees anybody else's
anything), **projects**, **forking**, **attachments** and images.

Also out, all specified and all addable later without rework:

- share links;
- search, export, archive;
- the trash: delete removes the conversation for good in the POC;
- generated titles;
- reasoning content (dropped if a model emits it; the format has the place
  for it);
- vendor-specific extras kept across turns;
- retention, purge, audit log;
- operator limits other than the timeouts;
- Gemini and Bedrock;
- the responsive drawer and the theme toggle;
- several backend processes (one process; events need not travel through
  the database yet, but the run and its messages are in the database);
- draining runs on shutdown;
- the release workflow, trusted publishing, SBOM, signed tags — the wheel
  is built in CI and installed from the artifact;
- everything the specs already call planned: tools, memories, usage
  reporting, API tokens, other channels, the container image.

## Done when

1. Two people sign in, one through Google and one through Okta, on a
   deployed instance over https. A third person, not on the allow list, is
   refused.
2. Each sees only their own conversations; requesting another person's
   conversation by id is refused.
3. A conversation is held with an agent on one engine and one vendor; the
   agent's engine and model are changed in the configuration; after a
   restart the same conversation continues on the other engine and vendor.
4. A tab is closed in the middle of a long answer; on reopening the
   conversation, the answer is complete, or still arriving and the stream
   re-attaches.
5. With the API keys removed from the environment, start-up fails with a
   message naming the missing variables. The keys appear in no log, no
   response and no database row.
6. A clean machine goes from nothing to a running instance by following
   the deployment guide alone.
7. CI is green with every gate in place, and adding a GPL dependency makes
   it red.

## Order of work

Each step is one branch, reviewed until clean, landed as one signed-off
commit.

1. Repository groundwork: the open source files, CI with the gates over
   the existing skeleton.
2. Domain and core: the conversation format, users, sessions, the claim
   and allow-list rules; ports; in-memory fakes; their tests.
3. Datastore: asyncpg, the schema definition, the store contract suites.
4. Sign-in: the OIDC adapter, the application flow, the `api` routes, the
   stand-in provider for tests.
5. Application: conversations and the run lifecycle, against a fake agent.
6. The run executor and the AG-UI stream in `api`.
7. The first agent engine, with the contract suite.
8. The second agent engine, and the swap test.
9. Frontend: the skeleton, the shell, sign-in page, history.
10. Frontend: the chat behind its seam, on AG-UI.
11. Packaging: the frontend in the wheel, `robinauts start`, the
    deployment guide, the real deployment.

## To settle before starting

- Where the POC is deployed, and under which host name — the redirect
  URIs registered with Google and Okta depend on it.
- The Google and Okta client registrations to use.
