# The demo, in containers

The same demo as [../local/](../local/README.md), in two containers with
Docker Compose: a PostgreSQL with a password, and the server built from a
**shallow clone of the repository's `main`** — not from this checkout — with
its interface built and its backend installed from `backend/uv.lock`, on
CPython 3.12.

    demo/compose/start.sh            # build, start, wait: http://127.0.0.1:8000/
    demo/compose/stop.sh             # both down again; the conversations stay
    demo/compose/stop.sh --reset     # and drop the database

It is the same **local development mode**, and just as much not a deployment
([../../docs/deployment.md](../../docs/deployment.md)): no sign-in, one local
user, published on this machine's loopback interface only.

## What it needs

Docker with Compose v2, and nothing else: no uv, no Node.js, no Python. The
first start builds an image, which takes a few minutes and a few GB.

## What it reads

`demo/.env` — the same file `demo/local/start.sh` reads — and the environment,
which wins over the file:

    ROBINAUTS_DEMO_DB_PASSWORD=...   # required: the database's password
    OPENROUTER_API_KEY=...           # or ANTHROPIC_API_KEY, or OPENAI_API_KEY
    ROBINAUTS_GITHUB_TOKEN=...       # optional: GitHub's tools for both agents

The file must be `chmod 600`, as the other demo also asks, and `start.sh`
says how to add a password if it has none; a long random one does, such as
`openssl rand -hex 32`. `demo/local/start.sh` reads the same file and ignores
the password. Compose itself only looks for a `.env` beside `compose.yaml`,
which is why `start.sh` exists: it hands Compose `demo/.env`. By hand, from
this folder, that is `docker compose --env-file ../.env up --build`.

**The password is read once**, when the database's volume is first made.
After changing it, `demo/compose/stop.sh --reset` makes the database again,
and the conversations go with it.

## What is the same as the other demo, and what is not

- **The same choices, from the same variables.** The provider order,
  `ROBINAUTS_DEMO_PROVIDER`, and `ROBINAUTS_DEMO_MODEL`, `_2` and `_3` mean
  what [../local/README.md](../local/README.md) says they mean, and the
  configuration is written by the clone's own [config.py](../config.py). Only
  the chosen key reaches the server; the others are unset before it starts,
  and no key is written to a file.
- **The code is `main` as it is when the image is built**, not your working
  tree. `ROBINAUTS_DEMO_REF=<branch>` builds another branch, and
  `demo/compose/start.sh` builds again whenever the branch has moved.
- **The database has a password, and it is needed.** It is on a network of
  its own that Compose makes `internal`: no port published on this machine,
  no route out, and no other container reaches it. This machine itself still
  does, at the container's address on that network — Linux routes to every
  bridge Docker makes — so the password is what keeps the other accounts on
  this machine out, as it is for the other demo's.
- **The server still binds its container's loopback**, as the local
  development mode insists, and `socat` forwards the container's port to it.
- **Both demos use port 8000**, so run one of them at a time.
- **The keys and the password are in the containers' environment**, which
  `docker inspect` shows to anybody who may use Docker here. Nobody else can:
  whoever can use Docker on a machine can already do anything on it.

## When something goes wrong

| what you see | why | what to do |
|---|---|---|
| `no demo/.env`, or `no ROBINAUTS_DEMO_DB_PASSWORD in …` | the database has no password to be made with | write the file, or add the line `start.sh` printed |
| `demo/.env is mode 644 and holds secrets` | anybody on this machine could read it | `chmod 600 demo/.env` |
| `set OPENROUTER_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY in demo/.env`, in the server's log | no key | add one to `demo/.env` |
| `password authentication failed` in the server's log | the password changed after the database was made | `demo/compose/stop.sh --reset` |
| `address already in use` for port 8000 | the other demo, or something else, is on it | `demo/local/stop.sh`, then `demo/compose/start.sh` again |
| `permission denied while trying to connect to the docker API` | this account may not use Docker | add it to the `docker` group and log in again, or use rootless Docker |

Everything else the server says is in
`docker compose -f demo/compose/compose.yaml logs robinauts`.
