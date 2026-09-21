# Conversations

## Shape

- A conversation is a **tree of messages**: every message has a parent.
- Editing a user message, or regenerating an answer, adds a sibling
  branch. The earlier branch is kept and can be revisited. Nothing is
  overwritten.
- A conversation belongs to one user, optionally inside a project, and is
  bound to an agent ([privacy.md](privacy.md), [agents.md](agents.md)).
- A conversation has at most one active run. The answer keeps being
  produced when its author is not watching ([runs.md](runs.md)).

## The format

The format is the platform's own
([ADR 0002](../adr/0002-conversation-persistence.md)): not that of an
agent framework, not that of a model vendor. Each engine translates to and
from it on every turn ([agents.md](agents.md)).

**What a message can contain**

| content | notes |
|---|---|
| text | |
| image | passed to the model where the model accepts images |
| file | an attachment, stored in the database |
| reasoning | the thinking some models emit, kept apart from the answer |
| tool call, tool result | planned with tools; a call may stand without a result while its run waits |

**Reasoning**

- It is stored, as its own kind of content.
- It is shown collapsed under the answer, to everyone who can read the
  conversation.
- It is included in a JSON export and left out of a Markdown export.
- It is never sent to a vendor other than the one that produced it.

**What crosses a swap of engine or vendor**

- The portable content always crosses: text, images, files, the tool
  history.
- Vendor-specific extras — signed reasoning, provider message ids, cache
  hints — are kept with the message as opaque vendor data. They are
  replayed only to the vendor that produced them, and ignored otherwise.
- A swap never fails because of them.

**What an answer records**

- Every assistant message records the agent, the engine, the model and the
  run that produced it. The interface can show it.
- Every message records the delivery channel it came from
  ([channels.md](channels.md)); a conversation is not tied to one.

**The system prompt**

- It is not a message. It is taken from the agent's current configuration
  at every turn.
- Editing an agent therefore takes effect at the next turn of its existing
  conversations.

**Persistence**

- Messages are persisted as they are produced. At any moment the stored
  conversation is consistent and complete up to that moment.

## Branches

- A conversation opens on the branch its author was last on.
- Only the author creates branches and moves between them.
- **Every other reader — a project member, someone with a share link —
  sees the author's current branch only**, live: it follows the author
  when they continue or switch branch. The other branches stay private to
  the author.

## Forking

- A project member can fork a conversation from any message of the branch
  they see.
- The fork is a new conversation owned by the person forking, in the same
  project. It holds a copy of the path up to that message, attachments
  included.
- It shows where it was forked from.
- It is independent from then on: later changes to the original do not
  reach it, and deleting the original does not delete it.

## Titles

- After the first exchange the platform asks the conversation's model for
  a short title. This is not a run and not a message.
- If that fails, the title is the beginning of the first user message.
- The author can rename at any time. A renamed title is never overwritten.

## What a user can do

- Start a conversation with an agent; the application opens on an empty
  chat.
- Edit and regenerate, and move between branches.
- Rename, archive and delete.
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

- Whether to store the provider's raw token counts on each assistant
  message before usage reporting exists. They cannot be recovered
  afterwards, and storing them costs almost nothing.
