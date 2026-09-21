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
  end: each message, each tool call, each tool result. At any moment the
  conversation in the database is consistent and complete up to that
  moment.
- The stream of a run is **re-attachable**: the UI can reconnect to an
  active run and receive what it missed, then the rest, live. Opening a
  conversation that has an active run attaches to it.
- A run can be **cancelled** by the conversation's author. What was
  produced before the cancellation stays.

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
  whose owner is gone is marked `interrupted`.
- An `interrupted` or `failed` run can be retried by the author. The retry
  is a new run from the conversation as it stands, so nothing already
  produced is lost or repeated.
- With several backend processes a run lives in exactly one. A watcher
  connected to another process receives the run's events through the
  database.
- Every model call, every tool call and every run has a timeout.

## In the layout

- `application` owns the run lifecycle: start, persist as it goes, publish
  events, suspend, finish, cancel, retry.
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
