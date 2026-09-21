# Dependency policy

Robinauts is Apache-2.0, and a dependency must not put that in question —
for a company running it, or for a product embedding it. The policy is the
Apache Software Foundation's category model, which is the strictest in
common use. The reasoning is in
[docs/specs/open-source.md](docs/specs/open-source.md).

The policy applies to every dependency **and to everything it brings with
it**: the whole locked set is checked, not the direct dependencies alone.

## Categories

### Allowed

Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, 0BSD, ISC, Zlib, PostgreSQL,
PSF-2.0, CC0-1.0, Unlicense.

### Restricted

MPL-2.0, EPL-2.0, CDDL-1.x.

Only as an **unmodified, unbundled** dependency, and only if it is listed
by name below with its reason. Never in the JavaScript bundle, which is
bundled code: the bundle uses the allowed list only.

### Forbidden

GPL (any version), AGPL, LGPL (any version, dynamic linking included),
SSPL, BSL, Elastic-2.0, Commons Clause, CC-BY-NC, CC-BY-ND, any "no
commercial use" or "do no evil" term, proprietary licences, and **no licence
at all**.

Forbidden means forbidden transitively, and for development-only and
test-only dependencies too.

## Development-only and test-only dependencies

They follow the same categories. One may be excepted only by name, below,
with the licence somebody read, the version they read it in, and the reason.

An exception is a signature, not a switch. It can cover metadata that names
a licence family and no more — the trove classifier
`License :: OSI Approved :: BSD License` names no version of the BSD licence,
and only a person can open the package and see which one it is. It can never
cover a forbidden licence, a package that states no licence at all, or
metadata nobody can read; and it holds for the version it names, so the next
upgrade fails until somebody reads the licence again.

## Assets

Fonts, icons, images, fixtures, sample data, model files and tokenizers
need a stated licence on the allowed list, and an entry in
[docs/legal/third-party.md](docs/legal/third-party.md). No model weights or
datasets are shipped. No third-party logos are shipped.

## Adopting or upgrading a dependency

1. One dependency change per pull request, and the pull request says why
   the dependency is needed and what was considered instead.
2. The licence of the package and of everything it brings is on the allowed
   list — or restricted, and then added to the table below in the same
   pull request. The licence is re-checked on every upgrade: a minor
   version has changed a licence before.
3. The package is what it claims to be: look at what the registry actually
   serves, not only at the repository.
4. The lockfile is committed.

Points 2 and 4 are enforced by CI, with a licence gate over the whole
locked set: a dependency that fails is a broken build, not a ticket. Run it
yourself with `scripts/check-licences.sh`, from the root of the repository.

The gate reads the categories above and the tables below out of this
document, so a dependency is excepted here or nowhere. It fails closed: a
licence it cannot resolve to an identifier stops the build as surely as a
forbidden one. Metadata that names only a family resolves to nothing — the
classifier `License :: OSI Approved :: BSD License` names no version of the
BSD licence, and the gate will not guess one. It reads that metadata from the
environment `uv` synced from this lockfile, or — for a package locked from
PyPI and not installed here — from the very file this lockfile pins by hash,
whose metadata PyPI publishes with a digest of its own. Metadata it cannot
tie to the lock, or cannot verify, it does not use, and a package it cannot
read is a package that does not pass.

A package may state its licence three times over — in `License-Expression`,
in the free-text `License` field and in its classifiers — and the three do
not always agree. Every claim that names a licence counts, and the worst of
them decides: a package claiming MIT in one field and the GPL in another is a
question for a person, not something to settle in our own favour. A claim
that names no licence counts for nothing, because that field so often holds
the licence text rather than its name.

## Tools that are not dependencies

`reuse` and `pip-audit` run as isolated tools (`uvx`), in their own throwaway
environments, and are deliberately **not** in `backend/uv.lock`: `reuse`
brings `python-debian`, which is GPL-3.0, and adding it would put a forbidden
licence in our locked set for the sake of a program that only reads our files.
Neither is imported, linked or shipped; each is a separate process that looks
at the tree and exits.

Both are pinned to an exact version in
[scripts/tool-versions.sh](scripts/tool-versions.sh) and bumped by hand —
Dependabot does not see them. The licence gate itself needs no tool at all:
it is the Python standard library.

## Restricted dependencies in use

Three things in the row below are checked against reality on every run, so a
dependency that changes under us breaks the build rather than slipping
through on its name:

- the **licence** must be the one the package's own metadata states, and the
  only restricted licence it states. A package offered under a choice of two
  restricted licences fails until the row says which one we rely on;
- the **scope**, where it says *development only*: the gate fails if the
  runtime dependencies ever bring the package in;
- the row must name a licence that is restricted at all — a row is not a way
  to invent a category.

| package | licence | scope | why it is acceptable |
|---|---|---|---|
| `pathspec` | MPL-2.0 | development only; brought by `black` | unmodified, not shipped in any artifact |

## Excepted development-only dependencies

The licence is the one that was read, and the version is the one it was read
in; the gate checks both.

| package | version | licence | why it is acceptable |
|---|---|---|---|
| `colorama` | 0.4.6 | BSD-3-Clause | development only; brought by `pytest` on Windows. Its metadata states the classifier `License :: OSI Approved :: BSD License` and nothing else, which names no version of the BSD licence; the LICENSE.txt shipped in the 0.4.6 wheel is the three-clause text |

## Known exclusions

| package | licence | consequence |
|---|---|---|
| `psycopg`, `psycopg-pool` | LGPL-3.0-only | not used; the PostgreSQL driver is `asyncpg` |
| `langgraph-checkpoint-postgres` | MIT, but depends on `psycopg` | cannot be adopted as it is ([ADR 0002](docs/adr/0002-conversation-persistence.md)) |
| `pgserver` | no licence metadata published | not a dependency; tests take the URL of a PostgreSQL they are given |
