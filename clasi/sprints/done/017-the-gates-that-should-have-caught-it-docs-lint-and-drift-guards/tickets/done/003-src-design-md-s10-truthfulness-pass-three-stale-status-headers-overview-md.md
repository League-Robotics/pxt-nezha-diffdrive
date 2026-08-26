---
id: '003'
title: src/DESIGN.md S10 truthfulness pass; three stale status headers; overview.md
status: done
use-cases:
- SUC-001
depends-on: []
github-issue: ''
issue: design-docs-assert-fixed-limitations.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# src/DESIGN.md S10 truthfulness pass; three stale status headers; overview.md

## Description

`src/DESIGN.md` S10 ("Open questions / known limitations") asserts three
things the code has already fixed, and three status headers across the doc
set are stale by 2 to 10 sprints. This ticket is a truthfulness pass, not a
rewrite -- correct what's wrong, don't restructure what's right.

### S10's three false limitations

1. Claims "nothing in `tools/` consumes [v6 frames] yet -- that retrofit is
   sprint 005 (roadmapped, not yet detail-planned)". `tools/tlm.py` is a
   430-line `thdr`/`t` decoder (header tracking, seq-gap loss counting with
   7-bit wraparound, orphan-frame accounting, CSV + meta sidecar, two
   fail-loud guards) with its own 522-line test suite. Sprint 005 is closed.
2. Claims `WireAdapter::lastDone()`/`lastDoneReason()` are "permanently
   inert -- hosts cannot observe motion completion". Sprint 005 ticket 004
   built the whole resolution machine (`armPendingMotion`,
   `resolvePendingReason`, `resolvePendingIfDue`, `forceResolvePending`,
   `engineMoveActive`) -- S5 of this same document already describes it.
3. Claims the radio TX cap is still 200 bytes and over-length RX is
   "clamped to a parseable prefix". Sprint 010 raised the cap to 240
   (drift-tested) and changed over-length RX to reject the whole frame
   (`radio_transport.cpp:63`, with its own comment on why truncate-and-accept
   was the hazard). **Careful**: the bullet's headline claim -- that a
   single-fragment RX limit exists -- is still true; only the two specifics
   (200-byte cap, clamp-to-prefix) are wrong. Don't delete the whole bullet,
   correct the two facts and keep what's still true.

### Three stale status headers

| Doc | Currently says | Correct to |
|---|---|---|
| `docs/design/design.md` | "as-built through sprint 008 ... Sprint 005 roadmapped, not yet detail-planned, blocked on a hardware bench checkpoint" | as-built through the latest closed sprint; 005-013 are closed and merged |
| `src/DESIGN.md` | "as-built through sprint 008 ... sprint 012 executed and closing" | 012 and 013 both merged |
| `docs/design/overview.md` Status section | "Code reflects work through sprint 003 ... sprints 004/005 (telemetry frames, radio command plane) are planned, not built" | both shipped; add a `Last reviewed:` header (currently has none -- add one so a future reader can judge staleness at a glance, matching the header style `design.md`/`src/DESIGN.md` already use) |

`overview.md` is the stakeholder-facing document and currently tells a
reader the radio command plane does not exist -- fix this one carefully,
it's the doc most likely to be read by someone deciding what's built.

### Also, `docs/design/specification.md` S4.3

S4.3 transcribes `startGoTo`'s arc math correctly and then describes the
result as "a curved (constant-curvature) path to a point" -- true only
below 50 deg turn angle. Above it, `MotionEngine::moveX()` splits into a
pivot plus a straight leg. This is tracked by the separate issue
`block-go-to-misses-its-target.md` (not part of this sprint's scope --
that's a code-behavior issue, this sprint changes no firmware). **Do not
fix the geometry here.** Just add a one-sentence caveat to S4.3 noting the
50-degree threshold and pointing at that issue, so the spec doesn't
overstate what's built while the real fix is pending elsewhere. If that
issue is already resolved by the time this ticket runs, skip this part.

## Scope boundary

Doc-only. Do not touch S12-S16 of `src/DESIGN.md` (that's ticket 004,
which depends on this one finishing first so the two edits don't conflict
in the same sections). Do not touch any `src/**/*.{h,cpp,ts}` file.

## Acceptance Criteria

- [x] `src/DESIGN.md` S10's three false limitations are corrected (not
      deleted wholesale where partially true, per the radio-cap case above).
- [x] `docs/design/design.md`, `src/DESIGN.md`, and `docs/design/overview.md`
      status headers reflect sprints through the actual latest closed
      sprint, not a stale checkpoint.
- [x] `docs/design/overview.md` gains a `Last reviewed:` header.
- [x] `docs/design/specification.md` S4.3 carries a one-sentence caveat
      about the 50-degree threshold (or is skipped with a note if
      `block-go-to-misses-its-target.md` is already resolved). Deviation:
      the issue was resolved (sprint 015), but via a bigger change than
      anticipated -- `startGoTo` no longer reduces to distance+yaw at
      all, it calls `goToR()` directly -- so a one-sentence caveat would
      have left the section wrong in a new way; S4.3 (and the matching
      `usecases.md` UC-006 step 2, found during this pass, same stale
      mechanism) were corrected to describe the current call path
      instead of skipped.
- [x] No claim in `src/DESIGN.md` S10 or any of the three status headers is
      contradicted by the current code.
- [x] No firmware source file is touched.

## Testing

- **Existing tests to run**: none -- doc-only, no test suite asserts on
  doc prose content.
- **New tests to write**: none. (Ticket 001's `clasi design validate` and
  ticket 005's stale-path grep are the mechanical guards for this class of
  drift; this ticket doesn't need its own new test since "is this claim
  true" isn't mechanically checkable the way a path or a constant is.)
- **Verification command**: `clasi design validate` (should still be
  `ok: true` after this ticket, assuming ticket 001 already landed it).
