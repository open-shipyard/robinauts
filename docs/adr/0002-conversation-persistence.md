# ADR 0002 — Conversation persistence: the platform owns the record, agent frameworks are stateless per turn

> **Superseded. Skip this ADR unless you need its history.**
> [ADR 0005](0005-the-framework-owns-the-loop-and-the-memory.md) replaces
> all of it. The application no longer works the way it describes. For the
> current design, read ADR 0005.

- Status: superseded by
  [ADR 0005](0005-the-framework-owns-the-loop-and-the-memory.md)
- Date: 2026-09-20

## Context

The core spec asks for an agent port with two swappable implementations,
LangGraph and Pydantic AI. Any conversation must continue with any framework
and any vendor. Conversations stay in the deployment's one database (goals 3
and 6).

Each framework persists differently:

- **LangGraph** persists through a *checkpointer*. It stores a snapshot of
  the whole graph state at every step, in tables it creates and migrates.
  That is execution state, for resuming, interrupts and forks. It is not a
  conversation record for anything else to read.
- **Pydantic AI** persists nothing. The caller passes `message_history` and
  stores the new messages itself.

The platform needs its own store either way. The question was whether
LangGraph's checkpointer should also hold conversations.

A licence settles part of it. `langgraph-checkpoint-postgres` depends on
`psycopg`, which is **LGPL-3.0-only** (checked 2026-09-20). Our policy
forbids LGPL, even transitively (goal 1). It is also why the platform's own
driver is `asyncpg`.

## Decision

**The platform owns the conversation record. Both agent adapters are
stateless per turn. No framework persistence is used.**

- Conversations live in the platform's own tables, in a format of its own.
  That store is the only source of truth.
- LangGraph runs without a checkpointer. Pydantic AI gets
  `message_history` from its adapter. Neither framework remembers anything
  between turns.
- Each adapter translates between the platform's format and its
  framework's, both ways, on every turn.

Every turn runs the same way. The controller loads the conversation, calls
the agent port with the history and the new message, streams the deltas to
the interface, and appends the new messages in the platform's format. The
next turn starts over, with whichever adapter and vendor are configured then.

Later work may need a framework's own persistence, for example to pause a
tool call for approval or to recover after a crash. This ADR left it open.

## Consequences

Good:

- The adapters are symmetric. A conversation can take its next turn on
  another framework or vendor with no migration.
- Every feature reads one store with a known schema. A delete removes a
  conversation whole.
- No LGPL dependency.

Costs:

- The platform maintains its own message format, and one translator per
  adapter.
- No adapter gets LangGraph's resume, interrupts or time travel.

## Alternatives considered

- **LangGraph's checkpoints as the source of truth.** We rejected it.
  Switching frameworks would need a migration, Pydantic AI cannot read
  checkpoints, and every feature would parse a library's blobs. It also
  needs the excluded dependency.
