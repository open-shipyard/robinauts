# ADR 0003 — One visible thread: the tree stays in storage, users see the newest path

- Status: accepted
- Date: 2026-09-27

## Context

A conversation is stored as a tree since ADR 0002. Every message has a
parent. Editing a question or regenerating an answer writes a new message
beside the old one, never over it. The first version also **showed** the
tree:

- every message carried its `parent_id` to the browser;
- the browser walked the parents to draw a branch;
- `< 1/2 >` arrows moved between sibling branches;
- the backend remembered which branch the author was on
  (`conversations.active_leaf_id`, `PUT /api/conversations/{id}/leaf`), so
  that a conversation opened where they had left it.

That bought a feature few people use, and a lot of state to keep in step. It
took a branch picker in the chat, and a tree reducer in the browser with a
`resync` path for the library's own rewrites. The leaf moved with every
completed message and every navigation. A rule turned "the message the author
was on" into "the branch it opens on". A route, a store method and a column
existed for the position alone. Every reader had to be told which branch to
show: the interface, a project member, a share link, the model's history.

The product decision is that users see **one thread**. Editing a message or
regenerating an answer discards everything after that point, as the user sees
it. Analytics still needs what was discarded, because the lineage of edits and
regenerations is worth keeping. No other reader may see it.

## Decision

**Storage keeps the tree. Readers see one path of it: from a root to the
newest leaf.**

- The newest leaf is the one that sorts last by the order every message
  already has: `created_at`, then id. That rule already served a
  conversation whose remembered position named nothing. Without branch
  switching, it is the only rule.
- The rule holds for two reasons. An edit or a regeneration always writes
  the newest message. A conversation has at most one active run, so an
  older branch never gains a newer message than the one that set it aside.
- A regeneration in flight is the one exception. It sets the old answer
  aside before it has written anything. So while a run is in flight, the
  visible path ends at the message the run extends: its last completed
  message, or the question it answers. For every other turn, that message
  is the newest leaf anyway.
- **The shape of the tree is the soft deletion.** No column marks a message
  as discarded. A message is discarded when it is off the visible path. The
  schema gains nothing. `conversations.active_leaf_id` and the route that
  moved it are removed.
- `ConversationTree.visible_path()` in `core` decides what a reader sees,
  with `extending=` while a run is in flight. The application hands out
  nothing else. Analytics, once it exists, reads the whole tree through the
  store.
- Starting a turn stays the same. An edit still makes the new version a
  child of the edited message's parent. A regeneration still names the
  answer to produce again. Only what is shown afterwards changes. Since
  2026-10-03 an edit names the edited question, and the backend works out
  its parent ([wire.md](../specs/wire.md)).

## Consequences

Good:

- The branch navigation code goes: the picker's data, the tree reducer and
  its resync in the browser, the leaf route, the store method, the column
  and the position rule. The wire sends a list.
- Analytics keeps the edit lineage at no cost. It is the tree that was
  already there, with the parents already stored.
- Every reader sees the same thread by the same rule. Nothing has to be
  told, and nothing has to be kept in step.

Costs:

- A user cannot go back to a branch an edit replaced. That is the product
  decision itself.
- A stale tab can edit an old message. Its edit becomes the newest, and the
  other tab's newer turns drop out of view, though they stay in storage. A
  guard on the turn request would refuse it: the client sends the id it
  believes is last. That guard is a follow-up, outside this decision.

## Alternatives considered

- **Linear storage: a `seq` per message and a `discarded_at` column.** We
  rejected it. Every read path would have to filter discarded rows out:
  opening, the model's history, a share link, export, retention. A path
  that forgot would show them. Keeping an edit's lineage would need one more
  field naming what the edit replaced, which the tree's `parent_id` already
  says. The tree costs nothing to keep and one function to read.
- **Deleting the discarded messages outright.** We rejected it. The lineage
  is the reason to keep them. A soft deletion with no column and no read
  filter is cheaper than a hard one.
