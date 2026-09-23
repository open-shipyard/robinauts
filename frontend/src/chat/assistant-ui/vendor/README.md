# Vendored chat components

Copied source, not a dependency. One file apart, everything in this directory
came from somebody else's repository through a shadcn-style registry, and it
is here because that is how its authors distribute it: the styled layer of
assistant-ui is not published on npm, it is source you copy into your own tree
and compile with your own Tailwind
([ADR 0001](../../../../../docs/adr/0001-chat-ui-assistant-ui-with-tailwind.md)).
The exception is `lib/utils.ts`, which is this project's, carries our header
and is not listed in `docs/legal/third-party.md` (modification 2 below).

The rules that come with the rest are in the ADR, and the short version is:
**edits inside this directory are kept to what is listed under "Local
modifications" below**, each with its reason, so that a re-sync is a small
merge rather than a fork; our own code goes in the directory above this one.
Every copy and every re-sync is also an entry in
[`docs/legal/ip-clearance.md`](../../../../../docs/legal/ip-clearance.md).

Nothing imports these files yet. Step 21 of
[the POC plan](../../../../../docs/working-notes/poc-scope.md) wires them up
behind `src/chat/index.ts`; until then they are here, type-checked and linted
like every other file under `src/`, and out of the bundle — out of the
JavaScript because rollup follows imports and nothing imports them, and out of
the CSS because `src/styles.css` says
`@source not "./chat/assistant-ui/vendor"`. **Tailwind's scan is not a module
graph**: without that line it reads these files as it reads any other and
compiles every class name in them, which took the built stylesheet from
18.0 kB to 58.2 kB (4.6 kB to 11.0 kB gzipped) — 40 kB of utilities for markup
no page renders. Step 21 deletes the line.

## Where it came from

Two upstreams, both MIT, fetched on **2026-09-22** (01:14 UTC on 2026-09-23).

| upstream     | repository                                   | commit at fetch time                       | registry                                                 |
| ------------ | -------------------------------------------- | ------------------------------------------ | -------------------------------------------------------- |
| assistant-ui | https://github.com/assistant-ui/assistant-ui | `92d16d77a684cff61e6812c0803ea698a8db8b2f` | `https://r.assistant-ui.com/<item>.json`                 |
| shadcn/ui    | https://github.com/shadcn-ui/ui              | `98a1fe67b439324ddc857f47fbdce056600a4329` | `https://ui.shadcn.com/r/styles/new-york-v4/<item>.json` |

The registry JSON carries no version and no commit of its own — it is built
and served from each project's default branch — so the commit recorded above
is that branch's head, read with `git ls-remote` at the moment of the fetch.
It is the closest thing to a revision these registries offer, and a re-sync
records a new one the same way.

Upstream's licence texts are beside this file: [`LICENSE`](LICENSE) for
assistant-ui and [`LICENSE.shadcn-ui`](LICENSE.shadcn-ui) for shadcn/ui, each
copied from its repository at the commit above, copyright lines as they state
them.

**The CLI was not run.** `npx shadcn@latest add https://r.assistant-ui.com/thread.json`
is upstream's documented command; it installs packages, runs their install
scripts and rewrites `components.json`, `package.json` and the stylesheet,
none of which this repository lets a tool do
([../../../../AGENTS.md](../../../../AGENTS.md)). The registry JSON was
fetched with `curl` and the `files[].content` of each item written out
instead, which is the same bytes without the side effects.

## What was copied

Sixteen files copied from registry items — eleven from assistant-ui's and
five from shadcn/ui's, which is the closure of `thread` less the attachment
items (see below) — and one, `lib/utils.ts`, written here in place of the
`@assistant-ui/utils` item, which is not in the closure of `thread` and was
looked up on purpose: twelve of the sixteen copied files import `cn` from it,
and `shadcn add` would have pulled it in the same way (modification 2). One
file per item, at the path the item names — shadcn serves its files under
`registry/new-york-v4/ui/x.tsx`, and its CLI writes them to
`components/ui/x.tsx`, which is what every import names and where they are
here.

| file                                                             | registry item                             |
| ---------------------------------------------------------------- | ----------------------------------------- |
| `components/assistant-ui/elements/file.tsx`                      | `@assistant-ui/file`                      |
| `components/assistant-ui/elements/follow-up-suggestions.aui.tsx` | `@assistant-ui/follow-up-suggestions`     |
| `components/assistant-ui/elements/image.tsx`                     | `@assistant-ui/image`                     |
| `components/assistant-ui/elements/markdown-text.tsx`             | `@assistant-ui/markdown-text`             |
| `components/assistant-ui/elements/reasoning.aui.tsx`             | `@assistant-ui/reasoning`                 |
| `components/assistant-ui/elements/reasoning.tsx`                 | `@assistant-ui/elements-reasoning`        |
| `components/assistant-ui/elements/thread.aui.tsx`                | `@assistant-ui/thread`                    |
| `components/assistant-ui/elements/tool-fallback.aui.tsx`         | `@assistant-ui/tool-fallback`             |
| `components/assistant-ui/elements/tool-group.aui.tsx`            | `@assistant-ui/tool-group`                |
| `components/assistant-ui/elements/tooltip-icon-button.tsx`       | `@assistant-ui/tooltip-icon-button`       |
| `components/ui/button.tsx`                                       | shadcn/ui `button`                        |
| `components/ui/collapsible.tsx`                                  | shadcn/ui `collapsible`                   |
| `components/ui/skeleton.tsx`                                     | shadcn/ui `skeleton`                      |
| `components/ui/textarea.tsx`                                     | shadcn/ui `textarea`                      |
| `components/ui/tooltip.tsx`                                      | shadcn/ui `tooltip`                       |
| `hooks/use-copy-to-clipboard.ts`                                 | `@assistant-ui/use-copy-to-clipboard`     |
| `lib/utils.ts`                                                   | **ours**, replacing `@assistant-ui/utils` |

`LICENSE`, `LICENSE.shadcn-ui` and this `README.md` are the only other files
in this directory. `src/test/vendor.test.ts` holds the table above and this
directory to each other, so neither can drift from the other unnoticed.
`REUSE.toml` states the copyright of each of the three groups: shadcn for
`components/ui/`, AgentbaseAI for the rest of the copy, and The Robinauts
Authors for `lib/utils.ts` and this file.

**No attachments.** `@assistant-ui/attachment` and
`@assistant-ui/use-attachment-src`, which `thread` also asks for, were not
copied: the POC has no attachments and no images
([`docs/working-notes/poc-scope.md`](../../../../../docs/working-notes/poc-scope.md),
"Out"), and a composer offering to attach a file the backend will not take is
worse than one that does not. Skipping them also leaves out shadcn's `avatar`
and `dialog`. It saves no package: `zustand`, which
`@assistant-ui/use-attachment-src` would have used, is a dependency of
`@assistant-ui/react` and is installed either way. `file` and `image` are not
attachment items and were copied: they render `file` and `image` message
_parts_, which a model can produce on its own, and `thread` imports them
directly.

The tool and reasoning components (`tool-fallback`, `tool-group`, `reasoning`,
`elements-reasoning`, and shadcn's `collapsible` and `textarea` under them)
are copied although the POC has neither tools nor reasoning content. They are
what `thread` imports, and cutting them out would mean rewriting the part of
`thread.aui.tsx` that dispatches on a message part's type — a fork of the one
file this whole directory exists for, paid for again at every re-sync. They
cost one package (`tw-shimmer`) and no bundle: nothing imports them yet, and
when step 21 does, a tool call that never arrives renders nothing.

## Local modifications

Six, and no others.

1. **`@/` path aliases rewritten to relative paths**, in every file that had
   one. A shadcn-style project resolves `@/components/...` and `@/lib/utils`
   through `paths` in `tsconfig.json`; this package has none, and adding them
   would give every path under `src/` a second spelling, which the seam rules
   of ADR 0001 are written to refuse (`eslint.config.js`,
   `src/test/seam-rule.test.ts`). Mechanical: `@/x/y` became the relative path
   to `vendor/x/y`.
2. **`lib/utils.ts` written here** rather than copied, which makes it the one
   file in this directory that is this project's: it carries our SPDX header,
   and `REUSE.toml` says Apache-2.0 for it. The registry's `utils` item is now
   one line, `export { cn } from "cn";`, against a `cn` package whose current
   incarnation is three weeks old under a name dormant since 2013, with one
   maintainer and four releases in the last two days. The rules for adding a
   package
   ([`docs/contributing/js-dependencies.md`](../../../../../docs/contributing/js-dependencies.md))
   ask for more than one maintainer, or a single one with years of settled
   releases; three weeks on a squatted name is neither, adoption
   notwithstanding, so it was not adopted. The file holds the `clsx` and
   `tailwind-merge` implementation of `cn` instead — the one assistant-ui and
   shadcn/ui both shipped in this file until the package existed, written
   against the two packages `docs/specs/frontend.md` names.
   `import { cn } from "cn"` in the five shadcn components was rewritten to
   the relative path of this file, as in (1).
3. **The attachment composer removed from `thread.aui.tsx`**: the import of
   `./attachment.aui` and its three uses (`<ComposerAttachments />`,
   `<ComposerAddAttachment />`, `<UserMessageAttachments />`). See "No
   attachments" above. `ComposerPrimitive.AttachmentDropzone` is left as it
   is: it belongs to `@assistant-ui/react`, not to the skipped item, and with
   no attachment adapter configured it does nothing.
4. **One field read as optional in `tool-fallback.aui.tsx`**
   (`approval.dismissible`). The registry serves files written against the
   newest `@assistant-ui/react`; the ten-day cooldown on a first pin holds us
   one release behind, and that release's `ToolApproval` has no `dismissible`
   yet. Reading it as an optional property compiles and behaves exactly as
   upstream does for an approval that does not set the field. It goes at the
   re-sync where the pin catches up. The comment in the file says so too.
5. **Formatted with this repository's Prettier**, which is not upstream's.
   `npm run check-format` covers every file in the package and an exception
   for this directory would be a hole in it. It touched six files and nothing
   but whitespace and line breaks.
6. **Two ESLint rules turned off for this directory alone**, in
   `eslint.config.js`, with the reasons written there: `no-empty` is relaxed
   to allow an empty `catch` (four of them discard a failure on purpose), and
   `react-hooks/refs` is off (`markdown-text.tsx` memoises a component table
   through a ref during render, deliberately). Every other rule, the seam's
   hygiene rules included, still applies here.

Nothing else was touched: no renaming, no restyling, no change to a class
name, a token or a piece of behaviour.

## What it needs

Nine packages, pinned in `package.json` like any other dependency, and
**one dependency change**: the chat library and what its styled components
import. They were adopted with the copy because the copy does not type-check
without them — a vendored file that imports a package that is not installed is
a red build, not a later pull request.

In module graph terms the copied files import `@assistant-ui/react`,
`@assistant-ui/react-markdown`, `remark-gfm`, `radix-ui`, `lucide-react`
(already pinned), `class-variance-authority`, `clsx`, `tailwind-merge`,
`react` and `react-dom`. `markdown-text.tsx` also imports
`@assistant-ui/react-markdown/styles/dot.css` — **a package stylesheet
reached from a module**, so rollup does see it and it needs no hand-written
entry; it is plain CSS and imports nothing further.

Two packages are reached _only_ through the stylesheet, so nothing discovers
them and they are written by hand in `CSS_PACKAGES` in `vite.config.ts`, with
their `@import`s at the top of `src/styles.css` where both registries' install
instructions put them: **`tw-animate-css`** (the `animate-in`, `fade-in-*`,
`zoom-in-*`, `slide-in-from-*` utilities) and **`tw-shimmer`** (the `shimmer`
one). `src/styles.css` also carries the two `@custom-variant` declarations and
the two `@keyframes` that the registry items declare in their `css` blocks and
that `shadcn add` would have merged into it.

`assistant-cloud` 0.2.2 arrives as a dependency of `@assistant-ui/react` and
is never configured: conversations live in this project's database only
(ADR 0001). `eslint.config.js` names it in the seam rule for that reason.

### Vetting judgements

What
[`docs/contributing/js-dependencies.md`](../../../../../docs/contributing/js-dependencies.md)
asks before a package is added, answered for each of the nine, on 2026-09-22.
Each is pinned at the newest version published on or before 2026-09-12, which
is the ten-day cooldown; none has an install script; every licence is on the
allowed list of [`DEPENDENCIES.md`](../../../../../DEPENDENCIES.md), and the
whole installed tree passes `node scripts/check-licences.mjs`. What is left is
the two questions that are a judgement rather than a check, and the judgement
is here so that it can be disagreed with.

| package                        | version, published  | licence    | provenance | maintainers | judgement                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------ | ------------------- | ---------- | ---------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@assistant-ui/react`          | 0.15.19, 2026-09-11 | MIT        | yes        | 2           | The library this whole directory is for. Two years, 450 releases, 1.3 M downloads a week.                                                                                                                                                                                                                                                                         |
| `@assistant-ui/react-markdown` | 0.14.15, 2026-09-11 | MIT        | yes        | 2           | Same project and release train; `markdown-text.tsx` is written against it.                                                                                                                                                                                                                                                                                        |
| `remark-gfm`                   | 4.0.1, 2025-02-10   | MIT        | **no**     | 3           | Predates the release: 4.0.1 is from before this project would have asked, and npm has held attestations only since April 2023 — the unified/remark family publishes without them. Six years, three maintainers, 28 M downloads a week. Accepted.                                                                                                                  |
| `radix-ui`                     | 1.6.7, 2026-07-24   | MIT        | yes        | 2           | Installed either way: `@assistant-ui/react` depends on it. 9.8 M a week.                                                                                                                                                                                                                                                                                          |
| `class-variance-authority`     | 0.7.1, 2024-11-26   | Apache-2.0 | **no**     | **1**       | Both exceptions at once, and the weakest row here. 0.7.1 is four years into the package and two years old itself, unchanged since; one maintainer (its author), 48 M downloads a week, one dependency (`clsx`). A takeover would have to publish 0.7.2 for it to reach us, which the cooldown and the lockfile would both show. Accepted.                         |
| `clsx`                         | 2.1.1, 2024-04-23   | MIT        | **no**     | **1**       | Eight years, fifteen releases, 90 M downloads a week, zero dependencies, ~200 lines. The canonical single-maintainer package the amended rule was written for. Accepted.                                                                                                                                                                                          |
| `tailwind-merge`               | 3.7.0, 2026-09-12   | MIT        | yes        | **1**       | Five years, 474 releases, 62 M a week, zero dependencies, provenance on the release we take. Accepted on the single-maintainer exception.                                                                                                                                                                                                                         |
| `tw-animate-css`               | 1.4.0, 2025-09-24   | MIT        | yes        | **1**       | Eighteen months and 56 releases — short of "years", and said so plainly. Accepted on three other grounds: provenance on every release; it is the package shadcn's own Tailwind v4 instructions prescribe, at 29 M downloads a week; and it is CSS with no JavaScript, reached through a stylesheet, so a bad release could restyle a page but could not run code. |
| `tw-shimmer`                   | 0.4.13, 2026-09-11  | MIT        | yes        | 2           | Ten months, 18 releases, and small — but it is published by the assistant-ui project itself, from the same repository and the same release train as the copied components, so it is the same trust decision as the library. CSS only, as above. Only the tool and reasoning components need it.                                                                   |

**Refused: `cn`.** The registry's `utils` item now re-exports it, and it is
not taken (modification 2). It has provenance and 3.2 M downloads a week, so
it fails neither of those; what it fails is the maintainer rule as amended —
one maintainer, and a history of three weeks on a package name that had lain
dormant since 2013, which is the shape of a name worth watching rather than
one worth trusting. `clsx` and `tailwind-merge` do the same work.

## Re-syncing

1. Read the two heads and write them down:
   `git ls-remote https://github.com/assistant-ui/assistant-ui HEAD` and
   `git ls-remote https://github.com/shadcn-ui/ui HEAD`.
2. Fetch each item in the table above — `curl -sS
https://r.assistant-ui.com/<item>.json` and `curl -sS
https://ui.shadcn.com/r/styles/new-york-v4/<item>.json` — and write each
   `files[].content` to its path here, overwriting. An assistant-ui item's
   `files[].path` is already the path here; a shadcn item's is
   `registry/new-york-v4/ui/x.tsx` and drops that prefix, landing at
   `components/ui/x.tsx`. `lib/utils.ts` is not fetched: it is ours. Do not
   run the CLI.
3. Re-apply modifications 1 to 4 (5 and 6 apply themselves): `npm run format`,
   then `npm run lint` and `npm run typecheck`, and read the diff — it is the
   whole of what upstream changed, and the whole of what this project has to
   judge again.
4. Check the item list: an item that gained or lost a file, or a new
   `registryDependencies` entry, is a change to the table above and to
   `docs/legal/third-party.md`. `src/test/vendor.test.ts` fails until the
   table matches what is on disk.
5. If a package's version has to move with it, that is a separate pull
   request under the rules in
   [`docs/contributing/js-dependencies.md`](../../../../../docs/contributing/js-dependencies.md),
   cooldown included.
6. Append an entry to
   [`docs/legal/ip-clearance.md`](../../../../../docs/legal/ip-clearance.md)
   with the new date, the new commits and what changed. Entries there are
   never edited; a re-sync is a new one.
