# ADR 0004 — Context management belongs to the agent adapter

> **Superseded. Skip this ADR unless you need its history.**
> [ADR 0005](0005-the-framework-owns-the-loop-and-the-memory.md) replaces
> all of it. The application no longer works the way it describes. For the
> current design, read ADR 0005.

- Status: superseded by
  [ADR 0005](0005-the-framework-owns-the-loop-and-the-memory.md)
- Date: 2026-09-28

## Context

ADR 0002 put above the agent port whatever had to behave the same under both
frameworks. Its first example was trimming a long history to fit the context
window. The code followed: `core.trim_history` counted characters, dropped
whole turns from the front, and the application handed each engine what was
left.

Tools over MCP broke that rule. A real context policy does four things, and
all four are specific to a framework or a vendor:

- it **counts tokens** with the vendor's tokeniser, since the model's limit
  is in tokens;
- it **orders and collapses tool results**, the bulk of a turn with tools;
- it **places cache breakpoints**, which make a loop of model calls
  affordable;
- it **replays a vendor's extras**, such as the signed thinking blocks some
  vendors require back.

A policy above the port could only be the lowest common denominator of the
two engines.

## Decision

**The application hands the agent port the full history and the run's
tools. The adapter decides what the model sees.**

- Trimming, ordering, every other kind of context management and prompt
  caching belong to the adapter, per framework and per vendor.
- Nothing above the port trims. `core.trim_history`, `DEFAULT_HISTORY_CHARS`
  and the `history_chars` setting go.
- One invariant stays: the question being answered reaches the model whole.
  An adapter may drop or fold anything before it.
- The platform owns the tool loop. It calls each tool, appends the result to
  the record and runs the engine again from the stored history. The record
  is the checkpoint, and no framework checkpointer is used.

## Consequences

Good:

- Each adapter can do the right thing for its vendor: count real tokens,
  keep a stable cached prefix, and replay what the vendor needs.
- Every turn takes one path above the port: read the visible path, hand it
  over.

Costs:

- The two engines may send a model different histories from the same
  record. A conversation moved to the other engine may lose something.
- The context policy is one more thing to review in each adapter.

## Alternatives considered

- **Keep the policy above the port and grow it.** We rejected it. It would
  rebuild in `core` what each framework already offers, and still could not
  place a vendor's cache breakpoint or replay its signed blocks.
- **A policy port of its own**, implemented per vendor. We rejected it for
  now. It is the same code in another place, behind a second seam.
