# Conversations

## Shape

- A conversation is a **tree of messages**: every message has a parent.
- Editing a user message, or regenerating an answer, adds a sibling
  branch. The earlier branch is kept and can be revisited. Nothing is
  overwritten.
- The format is the platform's own
  ([ADR 0002](../adr/0002-conversation-persistence.md)): not that of an
  agent framework, not that of a model vendor. Each engine translates to
  and from it on every turn ([agents.md](agents.md)).
- A message carries text, attachments and images. The format leaves room
  for tool calls and tool results.
- A conversation belongs to one user, optionally inside a project, and is
  bound to an agent ([privacy.md](privacy.md), [agents.md](agents.md)).

## What a user can do

- Start a conversation with an agent; the application opens on an empty
  chat.
- Edit and regenerate, and move between branches.
- Rename, archive and delete. A title is generated from the first
  exchange.
- Attach files and images. They are stored in the database; images are
  passed to the model where the model accepts them.
- Search the conversations they can see.
- Export a conversation, as Markdown or JSON.
- Share it, or put it in a project ([privacy.md](privacy.md)).

## Deletion

- Deleting is soft. A deleted conversation sits in a trash for a fixed 30
  days; its author can restore it, or delete it for good.
- After 30 days it is removed for good, with its messages, attachments and
  share links.
- Retention and purge are in [privacy.md](privacy.md).

## Details likely to change

- Search is PostgreSQL full-text search, so that no other service is
  needed.
- Attachments are stored as `bytea`. The maximum size is an operator limit
  ([operations.md](operations.md)). An object store could later sit behind
  the same port.
- Fitting a long history into a model's context is done above the agent
  port, so that both engines behave the same.

## Open

- **The format itself**: the schema of the tree, the kinds of message
  part, how attachments are referenced, the room for tool calls, what an
  export looks like. The agent port, both engines, the datastore and the
  wire all depend on it; it is the next thing to specify.
- Whether to store the provider's raw token counts on each assistant
  message before usage reporting exists. They cannot be recovered
  afterwards, and storing them costs almost nothing.
