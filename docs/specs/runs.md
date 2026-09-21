# Runs

A **run** is the work an agent does to answer one user message. It is a
record in the database, it executes in the background, and it does not
depend on the request that started it.

## Behaviour

- Sending a message creates a run and starts it. The request that sent the
  message then only *watches* the run.
- **If the request drops — the tab closes, the network fails — the agent
  keeps working.** The answer is in the conversation when the person comes
  back.
- A conversation has **at most one active run**. While one is active, a new
  message in that conversation is refused; the person can cancel the run.
- Everything a run produces is **persisted as it is produced**, not at the
  end: each message, each tool call, each tool result is appended when it
  is complete. A message still being produced is in the run's events and
  not yet in the conversation. At any moment the conversation in the
  database is consistent and complete up to that moment.
- **An event has one written form**, the platform's own, versioned like a
  message: what the events table keeps and what the wire carries are the
  same document, and the two documents of the platform are that and a
  message ([conversations.md](conversations.md)) — with the same reserved
  `extras` on it and on the event inside it. What the platform
  publishes is storable text, so a delta that would end on half a character
  holds it back until the other half arrives.
- **What was published is what was stored.** The deltas of a message,
  joined, are the text of the message that completed it. A person who
  watched an answer arrive has the answer that is in the conversation.
- **Every event of a run has a position**: a number starting at 1, counting
  up by one, with no gaps, for the life of the run. The application assigns
  it; an engine yields events and knows nothing of positions, so one run is
  numbered one way whichever engine produced it.
- **Opening a conversation with a run in flight is told where to attach.**
  Whoever serves the conversation serves its messages and, when a run is
  active, that run's id and its `resume_point`: the position of the run's
  last completed message, or of the event that started it if it has
  completed none, together with the message a new announcement after that
  point will hang under — the two things anyone checking that stream needs,
  handed over together so that neither is guessed. The watcher has every complete message already, so
  attaching there replays exactly the message still being produced, from its
  announcement. Nothing twice, nothing missed.
- The stream of a run is **re-attachable**, and this is what that promises.
  A watcher gives the position it last saw. What it receives is every event
  of that run after that position, in order, numbered on from it by one
  with no gaps, and nothing else. Giving 0, or nothing, is asking for the
  run from its beginning, the event that started it included; giving any
  later position is asking for what followed it, and the event that started
  the run is never in that. A slice may begin in the middle of a message —
  its remaining deltas, and its completion — and it is the middle of
  **one** message, because a run produces one at a time. So a watcher that
  first loads the conversation's finished messages and then applies the
  slice has the run entire, with nothing shown twice. Opening a
  conversation that has an active run attaches to it.
- A run can be **cancelled** by the conversation's author. Cancelling is the
  application cancelling the engine's task; the engine lets the cancellation
  through and releases what it holds ([agents.md](agents.md)). What was
  produced before it stays: a message that was complete is in the
  conversation, and the one in flight is not.
- An engine reports a failure by **raising**. The run ends `failed`, with a
  description of what was raised recorded on it — made storable and cut to
  fit — and the answer that was in flight is left uncompleted.
- **A turn that ends without an answer is a failed run**, never a finished
  one: the run records that the engine produced no answer. A `finished` run
  has at least one message in the conversation.

## States

| state | meaning |
|---|---|
| `running` | executing in a backend process |
| `waiting` | suspended: a tool call has no result yet; nothing is held in memory |
| `finished` | completed; its messages are in the conversation |
| `failed` | ended with an error, which is recorded on the run |
| `cancelled` | stopped by the author |
| `interrupted` | its process went away while it was running |

`running` and `waiting` are the active states.

Which state may follow which:

- `running` becomes `waiting`, `finished`, `failed`, `cancelled` or
  `interrupted`.
- `waiting` holds no process, so nothing interrupts it: a tool result
  resumes it to `running`, its author cancels it, or it fails.
- The four ended states are ended. A run never leaves one, and never
  re-enters the state it is already in; a retry is a new run.
- A run records when it ended, in every ended state and in no other. Only
  a run that ended badly records an error, and a `failed` run always does.
- The times a run records are the clock's, clamped so that none of them is
  earlier than the one it follows. A wall clock steps backwards now and
  then, and a run in flight must not become unrecordable because of it. A
  run that was executing records when it began, at the latest when it ends.
- **Ending a run never fails.** What went wrong is whatever a provider or a
  traceback said, at whatever length and in whatever characters: it is made
  storable and cut to fit before it is recorded, and a failure with nothing
  to say records that it had nothing to say. A run is never left `running`
  because its error would not fit.

A run records the conversation, the message it answers, the agent, the
engine and the model it used, its state, its times, and its error if any.

## Tools

Tool usage is planned ([agents.md](agents.md)); runs are designed for it.

- A tool call and its result are messages of the conversation, persisted
  like any other.
- **Short tools** run inside the run: the model calls the tool, gets the
  result and continues, in one execution.
- **Long tools** need nothing more: the run outlives the request, the UI
  shows it as running and re-attaches at will.
- **Tools that outlast a process** — an external job, a person's approval —
  suspend the run. The conversation holds a tool call without a result, the
  run is `waiting`, and no process holds anything. When the result arrives
  it is appended as a tool-result message, and execution resumes from the
  history.
- Resuming is therefore the ordinary stateless turn
  ([ADR 0002](../adr/0002-conversation-persistence.md)): **the conversation
  record is the checkpoint.** It works the same with either engine and
  needs no framework persistence.
- The agent port's result is either "finished" or "waiting on these tool
  calls". Without tools it is always "finished".
- A tool declares whether it is safe to execute again. After an
  interruption, a pending call of a safe tool is re-executed; any other is
  recorded as failed, and the model is told.

## Where the work happens

- In the backend process, as asyncio tasks on the same event loop that
  serves requests. There is no separate worker, queue or scheduler
  (goal 6).
- Runs are I/O-bound: they wait on model providers and, later, on tool
  servers. CPU-bound work of our own goes to a thread, never on the loop.
- The database holds everything that matters — the run, its state, its
  messages, its events. The process only executes.
- Periodic housekeeping — retention, emptying the trash, expiring sessions,
  detecting orphaned runs — runs the same way, and a database lock ensures
  that one process does it.

## Restarts and several processes

- On shutdown the backend stops accepting new messages and lets active runs
  drain for a bounded time; what remains is cancelled and marked
  `interrupted`.
- A run records the process that owns it, with a heartbeat. A `running` run
  whose owner is gone is marked `interrupted`. **Whoever marks it appends the
  event that ends it** — `interrupted`, at the next position, which the store
  knows — so that every ended run's stored stream is complete and a watcher
  of one is told it is over rather than waiting.
- An `interrupted` or `failed` run can be retried by the author. The retry
  is a new run from the conversation as it stands, so nothing already
  produced is lost or repeated.
- With several backend processes a run lives in exactly one. A watcher
  connected to another process receives the run's events through the
  database.
- Every model call, every tool call and every run has a timeout.

## In the layout

- `application` owns the run lifecycle: start, persist as it goes, publish
  events, suspend, finish, cancel, retry. **The engine's events are not the
  run's events.** An engine says an answer has begun, more of its text, more
  of its thinking, and here are the parts it ended with: it has no ids, no
  clock and no rows, so it can neither name a message nor say that one is
  stored ([agents.md](agents.md)). The application is what gives an answer
  its id, its parent and its provenance, writes it down, and only then
  publishes it as a message. What it publishes are the platform's own turn
  events, in this order:
  - the run started, once, before anything else;
  - for each message: it is announced — with its role and the message it
    hangs under, so that a watcher can place it before any of it exists —
    then the pieces of its text and of its reasoning as they arrive, then
    the message completed, carrying the message as it was stored;
  - the run ended, once, last, with the state it ended in. Nothing follows
    it.

  Reasoning is published as it arrives and stored nowhere: this version keeps
  none of it ([conversations.md](conversations.md)).

  A run that ended `finished` completed at least one message and left none
  half-written. One that failed, was cancelled or was interrupted may leave a
  message announced and never completed: that is what a cancellation in the
  middle of an answer looks like.
- A `RunExecutor` port: execute this in the background; subscribe to a
  run's events from a given position; cancel. `api` only subscribes and
  maps events to the wire ([wire.md](wire.md)).
- A `RunStore` port for the run records and their events, implemented in
  `datastore`.

## Details likely to change

- The executor is an adapter over `asyncio.create_task`, with a registry of
  live tasks (so that none is lost to garbage collection, every failure
  reaches its run record, and shutdown can drain them), started and stopped
  by the ASGI lifespan. FastAPI's `BackgroundTasks` is not used: it is tied
  to a request.
- Events are kept per run in an events table and announced with
  PostgreSQL `LISTEN/NOTIFY`; a watcher re-attaches with the id of the last
  event it saw. Events of a finished run are removed after a while; the
  messages are the lasting record.
- Housekeeping takes a PostgreSQL advisory lock.
- A later `robinauts worker` process role — the same wheel, claiming runs
  from the database — would be another adapter of `RunExecutor`. It is not
  planned.
- With LangGraph, a graph that keeps state of its own beyond the messages
  cannot be resumed from the conversation alone. That case belongs to the
  open discussion in ADR 0002.
