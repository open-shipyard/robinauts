# The demo

The whole platform on this machine, two ways. Both are the **local development
mode** — no sign-in, one fixed local user, this machine's loopback interface
only — and neither is a deployment ([../docs/deployment.md](../docs/deployment.md)).

| | [local/](local/README.md) | [compose/](compose/README.md) |
|---|---|---|
| start | `demo/local/start.sh` | `demo/compose/start.sh` |
| stop | `demo/local/stop.sh` | `demo/compose/stop.sh` |
| needs | uv and Node.js | Docker with Compose |
| runs | this checkout, as it is | the repository's `main`, cloned when the image is built |
| database | a throwaway PostgreSQL under `demo/local/.state`, with a password made for it | a `postgres:16` container, with the password from `demo/.env` |
| served at | `http://127.0.0.1:8000/` | `http://127.0.0.1:8000/` |

Use `local/` to see what you are working on, and `compose/` to try the
platform without installing its tools. They share port 8000, so run one at a
time.

## What they share

- **`demo/.env`**, which both read and neither writes: one model provider key
  (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`), optionally
  `ROBINAUTS_GITHUB_TOKEN`, and for `compose/` the database's password,
  `ROBINAUTS_DEMO_DB_PASSWORD`. It is never committed, and both refuse it
  unless it is `chmod 600`.
- **[config.py](config.py) and [robinauts.toml.in](robinauts.toml.in)**, which
  write the platform's configuration for either: the same providers, models,
  agents and tools, from the same variables.
