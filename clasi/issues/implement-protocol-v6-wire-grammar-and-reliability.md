---
status: pending
---

# Implement protocol v6: wire grammar, verb catalog, and the reliability layer

Bring this extension's wire protocol up to **protocol v6** as specified in
`/Volumes/Proj/proj/RobotProjects/radio-robot-lib/docs/design/protocol.md`
(canonical) and summarised in `specification.md` §2–§6, §8.

That repository is the **specification authority**. This repo is a separate
implementation of the same wire format for the MakeCode/micro:bit target —
we are not vendoring its C++, we are conforming to its grammar so a host
speaking v6 can drive either.

## What v6 requires that we do not currently do

1. **Case is direction, and load-bearing.** Commands (host→robot) UPPERCASE,
   replies (robot→host) lowercase, lookup case-**sensitive**. A verb starting
   lowercase is dropped silently and does NOT count malformed — it is another
   robot's reply on a shared channel. This structurally prevents the v5
   debug-flood failure where a robot's own output parsed as a command to every
   other robot. (`protocol#2.1`)
2. **Mandatory sequence id `#<n>`**, always the line's LAST token, strictly
   incrementing from 1, on every sequenced verb. Bare unsigned digits only:
   `#+5`, `#-5`, `# 5` are malformed and need a digits-only parser, not the
   general signed-integer one. `#0` is not special — it simply always compares
   less than `expectedNext_` and lands in the stale/retransmit bucket.
   (`protocol#2.2`)
3. **Cumulative ack/nack.** Handler state is exactly two values:
   `expectedNext_` and `gapOutstanding_`. Three-way classification of every
   inbound id (`protocol#8.1`):

   | inbound id | action | reply |
   |---|---|---|
   | `== expectedNext_` | decode fields FIRST; only on success dispatch and advance | `ack <id> <lastDone> <reason>` |
   | `< expectedNext_` | **do NOT re-execute** — retransmit whose ack was lost | `ack <expectedNext_-1> <lastDone> <reason>` |
   | `> expectedNext_` | discard, do NOT execute — a gap | `nack <expectedNext_> <lastDone> <reason>` |

   The middle row is the one that is easy to get wrong and expensive when
   wrong: a resent `WHEELS_V` must not drive the wheels a second time.
4. **A decode failure is a NAK, not an ack** (`protocol#8.9`). Unknown verb,
   wrong arity, or an unparseable field does NOT advance the sequence. This is
   the whole point: a corrupted turn in an eight-move square gets resent
   rather than silently skipped. A **merits** rejection (decoded fine, adapter
   refused it — e.g. out-of-range speed) still acks and advances, paired with
   `err <code> #<id>`.
5. **Unsequenced exemptions**: `HELLO` (resets the sequence), `ESTOP`, `PING`.
   These never carry an id at all and are maximally forgiving of trailing
   content. (`protocol#8.3`)
6. **No timer in the handler.** The periodic re-nack rides the existing
   telemetry cadence. Keeping the handler clock-free is load-bearing, not
   incidental — `feed()` stays a pure function of input bytes plus that
   two-value state. (`protocol#8.5`)
7. **Outcome model**: `ok` and `done` are deleted. Acceptance IS the
   transport-layer `ack`. Error codes 1/2/3/4/6/8/10 as tabulated in
   `protocol#6.1`; code 11 `ERR_DUPLICATE_ID` is deleted, not merely unused —
   the handler enforces monotonicity before the adapter ever sees an id.
8. **Grammar details that bite**: max line 240 bytes including terminator,
   overlong lines discarded to the next `\n` and counted malformed; a run of
   spaces is ONE separator; a lone `\r` before `\n` is stripped; a blank or
   all-whitespace line is ignored silently and is NOT malformed.

## Verb catalog

`HELLO PING ID VER STATUS HELP GET SET TLM WHEELS_X WHEELS_V MOVE_X MOVE_V
GO_TO_R GO_TO_W STOP ESTOP RUN`, per the table in `protocol#6`. `SEED`/`CAL`
stay deferred.

Note `WHEELS` is renamed `WHEELS_V`. `STOP` gains an optional `now` token
before the id.

## Testing — this is the hard part, and it is the point

This repo has **no test suite at all** (`uv run pytest` collects nothing), and
the protocol is exactly the kind of code that cannot be validated by driving a
robot around: the interesting cases are loss, reordering, retransmits and
malformed input, which are hard to provoke on hardware and trivial to provoke
on a laptop.

Build a **native host test harness** — the protocol source is ordinary C++ and
does not depend on micro:bit headers if the transport seam is kept clean.
Compile it for the host and test it there. At minimum:

- golden wire vectors for every verb, both directions
- the full three-way id classification table, including the retransmit row
  asserting the adapter was NOT called twice
- decode-failure-is-NAK, and its distinction from a merits rejection
- gap stalling and self-healing on a lost nack
- the unsequenced exemption set
- adversarial input: overlong lines, embedded NULs, lone `\r`, all-whitespace,
  partial lines split across `feed()` calls, a lowercase verb

`radio-robot-lib/tests/protocol/` and its `tools/sim` are a working reference
for what this harness should look like; read them before inventing one.

## Related

- Depends on / pairs with [[implement-motion-api-six-operations]] — the six
  motion verbs are this issue's wire surface and that issue's behaviour.
- The existing `RUN` handling in `src/protocol.cpp` already has dedupe by
  arrival time; under v6 that is superseded by the sequence id.
