---
status: pending
---

# FUNCS ack precedes the listing (not terminates it) and stale RUN-colon / signature comments

MEASURED tigez 2026-09-09, fw 1.20260907.5,
`captures/tigez-funcs-run-20260909/session-1-funcs.log` and
`session-4-terminator.log`; written up with a parser recipe in
`docs/knowledge/2026-09-09-funcs-and-run-verified-on-tigez.md`.

`FUNCS` and `RUN` both work on hardware. Three things the source says
about them are wrong or empty, and each one misleads a UI author:

## 1. The ack is sent BEFORE the `funcs` lines, so it cannot terminate them

`WireHandler::dispatch()` calls `replyAck(id)` and then the executor
(`src/comms/wire_handler.cpp:626-635`). On the wire that is `ack 1 0
none`, then 17 `funcs` lines over the next ~18 ms, then nothing. Yet:

- `execFuncs()`'s header comment: "Sequenced, so the `ack` terminates
  the variable-length reply".
- `tools/robotlink.py:149-151`: "the ack is what tells the host it has
  them all".
- `tools/wire_acceptance.py:586-599`: same claim; the check passes only
  because `link.ask()` waits a fixed 1.5 s.

Decide which is intended. Options: (a) fix the comments and document
the trailer idiom (`FUNCS #n\nPING\n`; `pong` lands after the last
`funcs` line, measured session-4) as the terminator; (b) emit a
`funcs end` (or count) line; (c) move `replyAck` after execute for
listing verbs only. (a) is cheapest and matches bare `GET`, which has
the same shape. Whatever is chosen, `wire_acceptance` should assert on
the order it actually sees.

## 2. `wire_adapter.h:263-273` still says listed names are `RUN:<name>` only

"A listed name is addressable as `RUN:<name>`, NOT as `RUN <name> #id`,
which still errs kUnknown." Reversed since d4d8e4e (2026-09-07):
`RUN <name> #id` dispatches (session-2: `RUN trace 1 #1` -> `ack`,
`trace=1`) and the colon form is silently dropped
(`clasi/issues/high/colon-run-form-is-silently-not-dispatched.md`).
Rewrite the comment.

## 3. The signature slot is never populated

`onRun()` registers every name with `""` (`src/blocks/run.ts:128`), so
every entry is `funcs <name>` and a UI learns names but not arity or
types. Either give `onRun()` (or a sibling block) a way to declare a
signature, or state in protocol/DESIGN docs that the second token is
reserved and currently unused, so nobody builds a parser expecting it.

Also worth a line in the protocol docs, measured the same session: a
lowercase verb (`funcs #1`, `run trace 0 #4`) is dropped with no nack
and no err and does not consume its id (S2.1 by design), and a
non-numeric first argument reaches the handler as 0 with no error.
