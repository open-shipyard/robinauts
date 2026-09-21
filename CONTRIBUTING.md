# Contributing to Robinauts

Robinauts is Apache-2.0 and means to stay safe to run inside a company and
safe to embed in a commercial product. Most of what follows exists to keep
that true: for any line in the tree, it must be possible to show who wrote
it, under what licence, and that they had the right to. The rules are
summarised in [docs/specs/open-source.md](docs/specs/open-source.md).

## Branching

`main` is the only long-lived branch and must always be releasable.
Changes reach it through pull requests only, and it is never force-pushed.

1. Create a short-lived branch from `main`, prefixed `feature/` or `fix/`.
2. Open a pull request against `main`.
3. Once the checks pass and the review is complete, a maintainer merges it.

One concern per pull request. A change of dependency is a pull request of
its own.

## Repository layout

    backend/     the Python backend (the `robinauts` package)
    frontend/    the web UI (not there yet)
    docs/        specs, decisions, legal records, working notes

The backend is split into layers with enforced dependency rules. Read
[docs/layout.md](docs/layout.md) before adding a module: where code goes is
not a matter of taste here, and the test suite fails on an import that
crosses a layer the wrong way.

## Development setup

The backend uses [uv](https://docs.astral.sh/uv/). From `backend/`:

    uv sync

Run the checks before opening a pull request:

    uv run pytest
    uv run ruff check .
    uv run black --check .

and, from the root of the repository:

    uvx reuse lint

## Licence header

Every source file starts with:

    # SPDX-License-Identifier: Apache-2.0
    # Copyright The Robinauts Authors

in the comment syntax of its language. A file that cannot carry a header is
covered by [REUSE.toml](REUSE.toml), which lists the files at the root by
name: a new file there is added to it. `reuse lint` must pass: every file
in the tree has a stated licence.

Never remove or alter a header that came with someone else's file.

## Developer Certificate of Origin

All contributions must be signed off under the
[Developer Certificate of Origin 1.1](https://developercertificate.org/).
Add `-s` to your commit:

    git commit -s -m "component: short imperative summary"

which appends:

    Signed-off-by: Jane Doe <jane@example.com>

Use your real name and a reachable email address. Sign-off is a statement about
the provenance of your contribution, so pseudonymous sign-offs cannot be
accepted. If you are contributing on behalf of an employer, make sure you have
their authorization.

There is no contributor licence agreement. You keep the copyright in your
contribution and license it to everyone under Apache-2.0.

## AI-assisted contributions

AI coding assistants are allowed. By signing off, you certify that:

- you have reviewed and understand every line you submit;
- the contribution does not reproduce third-party code under a license
  incompatible with Apache-2.0, and does not carry attribution requirements
  we have not satisfied;
- you have disclosed in the PR description any substantially machine-generated
  file or block.

## Where code may come from

- Write it yourself, or take it from a source whose licence is on the
  allowed list in [DEPENDENCIES.md](DEPENDENCIES.md) — and then say so:
  keep the copyright line and the header that came with the file, add the
  text of its licence to [LICENSES/](LICENSES/) if it is not there yet, and
  record it as described below.
- Earlier work of your own is yours to contribute, published or not, as
  long as you alone hold the rights to it — no co-author, no employer with
  a claim. Signing off is your statement that this is so.
- **No code from Stack Overflow, blogs or forums.** Their licences are
  usually incompatible. Understand the idea, close the tab, write your own.
- **Nothing copied, ported or translated** from someone else's work that is
  GPL, AGPL, LGPL, proprietary, or has no licence at all. A repository without a
  licence file is "all rights reserved", not public domain.
- Code that enters the tree other than as your own work in an ordinary
  signed-off pull request — a vendored file, a component copied from a
  registry, code derived from another project, an asset — gets an entry in
  [docs/legal/ip-clearance.md](docs/legal/ip-clearance.md), in the same
  pull request. Third-party code and assets that stay in the tree are also
  listed in [docs/legal/third-party.md](docs/legal/third-party.md).
- Do not import a codebase in one commit.

## Dependencies

Adding or upgrading a dependency follows [DEPENDENCIES.md](DEPENDENCIES.md).
In short: its licence, and the licence of everything it brings, must be on
the allowed list; the pull request says why the dependency is needed; and
the lockfile is committed.
