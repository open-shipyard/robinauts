# ADR 0003 — One visible thread: the tree stays in storage, users see the newest path

- Status: accepted
- Date: 2026-09-27

## Context

A conversation has been stored as a tree since ADR 0002: every message has
a parent, and editing a question or regenerating an answer writes a new
message beside the old one rather than over it. The first version also
**showed** the tree. Every message carried its `parent_id` to the browser,
the browser walked the parents to draw a branch, `< 1/2 >` arrows moved
between sibling branches, and the backend remembered which branch the
author was on (`conversations.active_leaf_id`, `PUT
/api/conversations/{id}/leaf`) so that a conversation opened where they had
left it.

That bought a feature few people use and a great deal of state to keep in
step: a branch picker in the chat, a tree reducer in the browser with a
`resync` path for the library's own rewrites, a leaf that moved with every
completed message and with every navigation, a rule for resolving "the
message the author was on" to "the branch it opens on", and a route, a
store method and a column for the position alone. Every reader — the
interface, a project member, a share link, the model's history — had to be
told which branch to show.

The product decision is that users see **one thread**. Editing a message
or regenerating an answer discards, from the user's point of view,
everything after the edit point. What was discarded must still be
available to analytics, because the lineage of edits and regenerations is
worth keeping, and must reach no other reader.

## Decision

**Storage keeps the tree. Readers are shown one path of it: from a root to
the newest leaf.**

- The newest leaf is the one that sorts last by the order every message
  already has, `created_at` and then id. This was already the rule for a
  conversation whose remembered position named nothing; without branch
  switching it is the only rule.
- It holds because an edit or a regeneration always writes the newest
  message, and because a conversation has at most one active run, so an
  older branch can never gain a newer message than the one that put it
  aside.
- The one moment it does not hold is a regeneration in flight: it puts the
  old answer aside before it has written anything. So while a run is in
  flight the visible path ends at the message the run is extending (its
  last completed message, or the question it answers), which for every
  other turn is the newest leaf anyway.
- **Soft deletion is the shape of the tree.** No column says a message is
  discarded: a message is discarded when it is not on the visible path.
  Nothing is added to the schema; `conversations.active_leaf_id` and the
  route that moved it are removed.
- `ConversationTree.visible_path()` in `core` (with `extending=` while a
  run is in flight) is the one function that
  decides what a reader sees, and the application hands out nothing else.
  Analytics, when it exists, reads the whole tree through the store.
- Starting a turn does not change: an edit still makes the new version a
  child of the edited message's parent, a regeneration still names the
  answer to produce again. Only what is shown afterwards changes. (Since
  2026-10-03 an edit names the edited question and the backend works out
  its parent, [wire.md](../specs/wire.md).)

## Consequences

Good:

- The branch-navigation code goes: the picker's data, the tree reducer and
  its resync in the browser, the leaf route, the store method, the column
  and the position rule. The wire sends a list.
- Edit lineage is kept for analytics at no cost: it is the tree that was
  already there, with the parents that were already stored.
- Every reader sees the same thread by the same rule, with nothing to be
  told and nothing to keep in step.

Costs:

- A user cannot go back to an edited-away branch. That is the product
  decision, not a side effect.
- A stale tab that edits an old message makes its edit the newest, which
  hides the other tab's newer turns from view. They stay in storage. A
  guard on the turn request (the id the client believes is last, refused
  when it is not) is a follow-up and is not part of this decision.

## Alternatives considered

- **Linear storage: a `seq` per message and a `discarded_at` column.**
  Rejected. Every read path — opening, the model's history, a share link,
  export, retention — would have to filter discarded rows out, and one that
  forgot would show them. Keeping the lineage of an edit would need a
  further field naming what the edit replaced, which the tree's
  `parent_id` already says. The tree costs nothing to keep and one
  function to read.
- **Deleting the discarded messages outright.** Rejected. The lineage is
  the reason to keep them, and a soft deletion that adds no column and no
  read-path filter is cheaper than a hard one.
