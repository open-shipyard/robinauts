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
with a reason.

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

Points 2 and 4 are for CI to enforce, with a licence gate over the whole
locked set: a dependency that fails is a broken build, not a ticket. Until
that gate is in place, whoever reviews the pull request checks them by
hand.

## Restricted dependencies in use

| package | licence | scope | why it is acceptable |
|---|---|---|---|
| `pathspec` | MPL-2.0 | development only; brought by `black` | unmodified, not shipped in any artifact |

## Excepted development-only dependencies

None.

## Known exclusions

| package | licence | consequence |
|---|---|---|
| `psycopg`, `psycopg-pool` | LGPL-3.0-only | not used; the PostgreSQL driver is `asyncpg` |
| `langgraph-checkpoint-postgres` | MIT, but depends on `psycopg` | cannot be adopted as it is ([ADR 0002](docs/adr/0002-conversation-persistence.md)) |
| `pgserver` | no licence metadata published | not a dependency; tests take the URL of a PostgreSQL they are given |
