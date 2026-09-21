# Conversations

## Shape

- A conversation is a **tree of messages**: every message has a parent.
- Editing a user message, or regenerating an answer, adds a sibling
  branch. The earlier branch is kept and can be revisited. Nothing is
  overwritten.
- Editing the first message gives the new message the parent the old one
  had, which is nothing: a conversation then has more than one root. A
  root is a branch like any other.
- **A turn is a chain.** A root is a user message. A user message's parent
  is an assistant message, or nothing. An assistant message's parent is a
  user message, another assistant message, or a tool message: one turn may
  produce several messages, and with tools it produces a call and a result
  among them ([runs.md](runs.md)). A tool message's parent is the
  assistant message that made the call. So a turn is one user message and
  everything the run produced under it.
- Regenerating replaces the **turn**: the new answer hangs under the user
  message that began it, beside the answer that was produced before, not
  under whatever the old answer happened to follow.
- A conversation belongs to one user, optionally inside a project, and is
  bound to an agent ([privacy.md](privacy.md), [agents.md](agents.md)).
- Asking for a conversation that is not there and asking for one that
  belongs to somebody else are answered identically, in status, in words
  and in every header: which of the two it was is a difference only an
  attacker has a use for. Which it really was is in the log.
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

**The version**

- Everything written in the format — a row of the database, a line of an
  export — carries the version of the format it was written in, and
  writing always writes the current version.
- Two things carry one: a **message** and a **run event**
  ([runs.md](runs.md)). A message's parts are written inside its message and
  have nothing of their own: one shape is one thing to version, to upgrade
  and to get wrong. The format has one version number, and each of the two
  documents is read forward on its own terms — an upgrade written for one of
  them would make nonsense of the other.
- A document is written **whole**: every key of it is there, `null` where
  there is nothing, and one that is missing is refused rather than read as a
  default. Only `extras` may be left out, since it is the one a build is
  allowed not to know about.
- **Adding does not move the version**, and there are exactly three ways to
  add: a new kind of content, a new role, and anything at all under
  `extras`. That key is reserved on **every document and every part of one**
  the format writes — a message and each of its parts, a run event and the
  event inside it — always the same thing: an object of at most 64 KiB
  written out, holding storable text, which a build that does not use it
  **accepts and reads past**. Vendor-specific extras, when they are kept —
  signed reasoning, provider message ids, cache hints — live there.
- **Any other new key moves the version**, as does any change to the
  meaning or the shape of what is already written. Nothing else is read
  past: a build that quietly dropped a field it did not recognise would
  write the message back without it.
- A build that meets content of a kind it does not carry refuses **the
  message holding it**, by name — "not supported yet" — whatever else that
  piece of content holds, and never reads it as something else: a message
  shown without its image is a message misread. The other messages of the
  conversation, and every other conversation, are unaffected. An operator
  who rolls a deployment back past a kind that has already been written
  will meet this, which is one more reason the version stays where it is
  for anything additive: rolling **forward** is what is meant to be cheap.
- A build **reads every version up to its own**, lifting older records
  through one upgrade per version — one for each of the two documents — and
  refuses a version above its own: it cannot know what that one means, and a
  build that guessed would write back a conversation it had misread.
- A piece of content holds at most 1,000,000 characters and a message at
  most 64 of them, so that no answer a model can produce has to be cut:
  text longer than one part is carried in the next. A title holds at most
  120.
- Stored text carries no NUL and no unpaired surrogate — one cannot be
  stored, the other cannot be encoded. What a provider sends is repaired on
  its way in: a NUL is dropped **first**, since one can arrive between the
  two halves of a character; a character that arrived in two halves is put
  back together; and a surrogate still on its own becomes U+FFFD. What an
  engine yields is not yet subject to this — it splits its answer where it
  likes — but everything the platform **publishes** is, and what is
  published, joined, is exactly what is stored.
- A time is written in UTC, with its offset. A conversation is dated
  between the years 1970 and 9998, which is the window every offset of a
  time can still be written back in; anything outside it is refused where
  it is read.

**Reasoning**

- It is stored, as its own kind of content.
- **Not in this version**, which keeps none of it: an engine may stream it,
  every watcher sees it arrive, and what an engine returns as reasoning
  with a finished answer is dropped rather than refused — an engine is not
  asked to know what the platform keeps.
- If dropping it leaves an answer with nothing in it — a model that only
  thought, or that said nothing at all — what is stored is one empty piece
  of text. A message always has content, and a turn where the agent
  answered with nothing is something a conversation should record rather
  than leave out.
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
- No message records token counts while the question at the end of this
  document is open. The format has no field for them.

**The system prompt**

- It is not a message. It is taken from the agent's current configuration
  at every turn.
- Editing an agent therefore takes effect at the next turn of its existing
  conversations.

**Persistence**

- Messages are persisted as they are produced: each message is appended
  when it is **complete**. A message still being produced lives in its
  run's events ([runs.md](runs.md)) and not in the conversation. At any
  moment the stored conversation is consistent and complete up to that
  moment.
- A stored conversation this build cannot read — a version above it, a
  kind of content it does not carry, a tree that is no tree — is a fault
  of the deployment and not of the request that met it. It is answered
  like any other fault of ours, saying nothing, and the whole of it goes
  to the log.

## Branches

- A conversation opens on the branch its author was last on. That is the
  message they were last on; if that message has since been answered, it
  is the branch below it **whose own last message is the newest** — the
  branch written in most recently, not the one begun most recently. A
  conversation whose last position names nothing — never opened, or a
  branch since deleted — opens by the same rule over the whole tree.
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
- If that fails, the title is the beginning of the first user message:
  the first line with anything on it of that message's text, its
  whitespace collapsed to single spaces, at most 120 characters, cut at a
  word boundary with an ellipsis. A message with no text in it gives no
  title, and neither does one that is only spaces.
- A cut never falls inside a character: a letter keeps its accents, and an
  emoji sequence stays whole or is left out.
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
  port, so that both engines behave the same. The first version measures
  characters rather than tokens and drops whole **turns** from the front of
  the history; what it sends always begins with a user message, so no turn
  is ever cut in half, and the turn being answered is always whole in it,
  whatever its size.

## Open

- Whether to store the provider's raw token counts on each assistant
  message before usage reporting exists. They cannot be recovered
  afterwards, and storing them costs almost nothing.
