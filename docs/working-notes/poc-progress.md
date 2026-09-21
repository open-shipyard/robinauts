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
  from `backend/`, or `scripts/check-all.sh` from the root.
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
