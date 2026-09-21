# POC progress

The plan is [poc-scope.md](poc-scope.md). The process is the three-agent
recipe (`recipes/three-agent-steps.md`, beside this repository).

## What exists

For a reader with no memory of it. Kept short; rewritten as the steps land.

- `docs/specs/` — the specs; start at `core.md`. `docs/adr/` — two
  decisions that needed a discussion. `docs/layout.md` — the backend layers
  and their enforced dependency rules.
- `backend/` — an empty skeleton of the `robinauts` package with every
  layer as an empty sub-package, `pyproject.toml` with the import-linter
  contracts, and `tests/unit/test_architecture.py` which runs them.
  Checks: `uv run pytest`, `uv run ruff check .`, `uv run black --check .`
  from `backend/`.
- No frontend yet.

## Steps

None landed yet.
