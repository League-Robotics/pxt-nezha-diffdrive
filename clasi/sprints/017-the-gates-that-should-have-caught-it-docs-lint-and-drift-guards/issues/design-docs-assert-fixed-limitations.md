---
status: in-progress
sprint: '017'
tickets:
- 017-003
---

# `src/DESIGN.md` S10 lists three limitations the code fixed, and three status headers are stale

Priority: **Medium** -- a limitations list that is wrong in the *reassuring*
direction is where a planner goes to decide what still needs work.

## S10 "Open questions / known limitations" -- three present-tense falsehoods

1. *"nothing in `tools/` consumes [the v6 frames] yet -- that retrofit is sprint
   005 (roadmapped, not yet detail-planned)"* -- `tools/tlm.py` is a 430-line
   `thdr`/`t` decoder with header tracking, seq-gap loss counting with 7-bit
   wraparound, orphan-frame accounting, CSV + meta sidecar, and two fail-loud
   guards, with its own 522-line test suite. Sprint 005 is closed.
2. *"`WireAdapter::lastDone()`/`lastDoneReason()` permanently inert -- hosts
   cannot observe motion completion"* -- sprint 005 ticket 004 built the whole
   resolution machine (`armPendingMotion`, `resolvePendingReason`,
   `resolvePendingIfDue`, `forceResolvePending`, `engineMoveActive`). S5 of the
   same document describes it.
3. *"radio's own TX cap (`kMaxPayloadBytes` = 200)"* and *"An inbound line
   longer than one fragment is clamped to a parseable prefix"* -- sprint 010
   raised the cap to 240 (drift-tested) and changed over-length RX to reject the
   whole frame (`radio_transport.cpp:63`, with a comment on exactly why
   truncate-and-accept was the hazard). **The single-fragment RX limit itself is
   still real**, so the bullet's headline is right and only its two specifics
   are wrong -- which is the dangerous shape: enough truth to be believed.

## Stale status headers

| Doc | Says | Actually |
|---|---|---|
| `docs/design/design.md` | "as-built through sprint 008 ... Sprint 005 roadmapped, not yet detail-planned" | 005-013 closed and merged |
| `src/DESIGN.md` | "as-built through sprint 008 ... sprint 012 **executed and closing**" | 012 and 013 both merged |
| `docs/design/overview.md` Status | "Code reflects work through sprint 003 ... sprints 004/005 are **planned, not built**" | both shipped; ten sprints stale |

`overview.md` is the stakeholder-facing document, carries no `Last reviewed:`
header at all, and currently tells a reader the radio command plane does not
exist.

`design.md`'s *body* is partly current (its subsystem map knows about sprint
013's grouping), which makes the stale header worse than a uniformly old
document: it invites trust.

## Also

`docs/design/specification.md` S4.3 transcribes `startGoTo`'s arc math
faithfully and then describes the result as *"a curved (constant-curvature) path
to a point"* -- true only below 50 deg. See
`block-go-to-misses-its-target.md`; both the spec and the code need to move.

Detail: [`docs/code-review/2026-08-26/raw/design-docs.md`](docs/code-review/2026-08-26/raw/design-docs.md) (D-03, D-04, D-06).
