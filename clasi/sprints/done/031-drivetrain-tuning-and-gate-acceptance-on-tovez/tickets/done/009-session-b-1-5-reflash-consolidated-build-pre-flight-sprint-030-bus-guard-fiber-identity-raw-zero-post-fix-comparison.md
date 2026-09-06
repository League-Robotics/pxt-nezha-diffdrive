---
id: 009
title: 'Session B (1/5): reflash consolidated build; pre-flight; sprint-030 bus-guard,
  fiber-identity, raw-zero post-fix comparison'
status: done
use-cases:
- SUC-008
depends-on:
- '001'
- 008
github-issue: ''
issue: sprint-030-hardware-acceptance-needs-one-bench-session.md
completes_issue: true
exception_history:
- thrown_by: programmer
  thrown_at: '2026-09-05T13:56:27.695501+00:00'
  surface: user-visible
  status: "RECOVERED \u2014 premise found to be an analysis error, see Closing note\
    \ below. Superseded, not merely appended to."
  original_conflict: 'Item 1 FAILED as written: i2cf climbed 0 to 35 across the pre-pivot
    plus ten segments on the post-030 build, against 0 to 6 on the pre-fix build in
    boot 1 (the only like-for-like otos=1 comparison; boots 2 and 3 ran otos=0 with
    no OTOS bus traffic). Yaw drift also roughly doubled to +1.158 deg/cm vs +0.577..+0.919
    pre-fix.'
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (1/5): reflash consolidated build; pre-flight; sprint-030 bus-guard, fiber-identity, raw-zero post-fix comparison

**Type: (a) hardware/playfield — team-lead executes personally. First
step of Session B (see sprint.md Test Strategy).**

## Description

Flash tovez with ticket 008's consolidated build. Confirm identity
(`HELLO` returns `device NEZHA2 robot tovez ...`) and run the standard
pre-flight: room lights ON (Shelly `192.168.1.122`), camera calibrated,
AprilTag 1 at world (0,0), tag 52's registration confirmed. Then run
sprint 030's remaining three (of four) deferred hardware acceptance
checks — the fourth (stack canary, item 5B) is deliberately NOT here;
see ticket 014.

1. **Item 1 — bus-ownership guard**: script a wire-issued OTOS read to
   land mid-drive; confirm it no longer corrupts the encoder sample;
   watch `i2cf` across the run (it must not climb).
2. **Item 2 — fiber-identity check**: (a) a button-handler tour during
   a live `RUN` job must not corrupt the shared `lineBuf_`; (b) a
   block-side `startMove()` during a live wire motion obligation must
   be refused (`kBusy`), not silently superseding it.
3. **Item 4 — raw-zero rejection, post-fix**: repeat the cold
   power-up run from ticket 001 on THIS (post-fix) firmware; compare
   directly against ticket 001's pre-fix baseline — no odometry
   position jump in the first ~40 cm on the post-fix run, where the
   pre-fix run (if it showed one) did.

## Acceptance Criteria

- [x] tovez identifies as running the ticket-008 build (`HELLO`/`ID`
      cited) before any check below is attempted.
- [x] Item 1: `i2cf` does not climb across a mid-drive OTOS-read
      scenario, capture cited. (Restated as a controlled busguard
      comparison after the original bar proved unanswerable on this
      firmware — see Closing note.)
- [ ] Item 2: both fiber-identity scenarios behave as designed, capture
      cited for each. PARTIAL, not fully met — 2(b) passes with a
      capture cited; 2(a) is BLOCKED on ticket 017, not merely
      unverified. Left unchecked deliberately per this ticket's own
      "never a fabricated pass" criterion.
- [x] Item 4: ticket 001's pre-fix baseline and this run's post-fix
      result are compared explicitly in the closing note, not just
      individually reported — the comparison IS the acceptance
      criterion, per `sprint-030-hardware-acceptance-needs-one-bench-session.md`.
      (Done by the previous session, `captures/session-a-20260904/notes.md`.)
- [x] Any item that cannot be verified is recorded as `UNVERIFIED` with
      what was tried, per `measurement-citations.md` — never a
      fabricated pass. (Item 2(a) recorded as BLOCKED-on-017 rather
      than a fabricated pass.)

## Testing

- **Existing tests to run**: N/A — hardware verification of
  already-tested (host-level) sprint 030 code.
- **New tests to write**: none (host coverage already exists from
  sprint 030; this is the hardware confirmation those host tests
  couldn't provide).
- **Verification command**: N/A (hardware ticket).

## Closing note (recovers the thrown exception — the original "bus
regression" premise does not survive its own captures)

**The exception thrown 2026-09-05T13:56:27Z is withdrawn, not merely
appended to.** Its two headline numbers (i2cf 0->35 vs 0->6; yaw drift
~doubled) were real reads but a wrong comparison. Restated below.

### Item 1 — "bus regression" was an analysis error, on three counts

1. **The otos=1 vs otos=0 confound does not exist.** `i2cf` increments
   on a cycle whose WHEEL-ENCODER sample timestamp failed to advance
   (`src/core/diffdrive.cpp`) — the OTOS is not in that counter. A
   wire-issued `MOVE_X` never reads the OTOS at all: sampling lives in
   `test/test.ts`'s `tickToCompletion()` (the on-robot RUN-handler
   loop), while wire motion is ticked by the protocol fiber through
   `tickDrive()` (`src/shims.cpp`), which issues no OTOS transaction.
   All four Session A runs had identical (zero) OTOS traffic, so boots
   2 and 3 were valid comparators that were wrongly discarded.
2. **"0 -> 35 vs 0 -> 6" compared a run WITH a repositioning pivot
   against the one run WITHOUT one.** Session A's harness started its
   8 Hz STATUS poller AFTER the pre-pivot, so each log opened at
   whatever the pivot had already spent: boot 3's first sample reads
   25, boot 4's reads 22, and boot 1 (no pre-pivot) reads 0.
3. MEASURED across Session A's own four logs
   (`captures/session-a-20260904/*/status-8hz.log`): 100% of i2cf
   increments landed within 1 s of a command, in a window covering
   only 19-29% of wall time. On post-028 firmware `i2cf` is largely a
   BREAKAWAY counter, not a bus-health counter. Per move: pre-fix
   0.60/0.64/0.82, post-fix 1.08 and 1.00 — a factor of 1.3, and
   expected from ticket 005's own fix driving through breakaway
   instead of terminating in it.

Item 1's original bar ("i2cf must not climb") is unanswerable on this
firmware, so it was RESTATED as a controlled comparison and run:
`turn_calibration.py --mode busguard`, alternating 120 mm legs, every
other one interfered with by a mid-drive `RUN:fix` (a real OTOS I2C
transaction issued from the protocol fiber). Across two runs, NINE
interfered legs against NINE clean:

```
mean length error  -6.90 mm (interfered) vs -6.97 mm (clean)  — 0.1 mm apart
i2cf per move      2.2 vs 1.8
heading            interfered was LOWER in both runs (noise, not an effect)
```

All ten `RUN:fix` calls answered with a real `OCAL:` line, so the OTOS
read genuinely completed mid-drive. A destroyed encoder sample would
show up as distance and does not. **Sprint 030's bus-ownership guard
does what it claims.** Captures: `captures/session-b-20260905/busguard/`,
`captures/session-b-20260905/busguard-repeat/`.

One outlier stays open and must NOT be averaged away: run 1 leg 5
accrued 4293 control cycles (~100 s) and +251 i2cf while still
delivering 112.9 mm and +1.49 deg. Ten further interfered legs did not
reproduce it. Not attributable to the OTOS read on this evidence, not
explained either. Recommend a follow-up issue and an 8 Hz STATUS poll
on the next busguard run.

The "yaw drift roughly doubled" figure in the withdrawn exception was
never re-investigated as a separate claim — it rode on the same single
uncontrolled sample (battery cycles, otos=1/0 mismatch, differing start
poses) named in the original conflict text, and item 1's controlled
busguard rerun above is the actual answer to whether post-030 firmware
corrupts anything mid-drive. No further action taken on the yaw-drift
number specifically; it is superseded by the busguard result, not
separately confirmed or denied.

### Item 2(b) — PASSES

MEASURED 2026-09-05 on the baked firmware, over WiFi, stakeholder
pressing the button. Control: button A alone drove 99.2 cm of a
commanded 100 with -0.08 deg heading change. Test: with a live wire
`MOVE_X 600 0 60 20000` running (~10 s window; status trace shows
active=1 from t=0.1 to t=7.3, 0 by t=9.7), button A was pressed
mid-drive and the wire leg delivered 59.5 of 60.0 cm and stopped — it
neither ran on toward button A's 100 cm nor came up short. The
block-side move was REFUSED, not superseding. Honest limit: the wire
cannot report WHEN the press landed, only that the window existed and
the leg was unaffected; with the idle control at 99.2 cm a press
anywhere in that window would have shown. n=1.

### Item 2(a) — BLOCKED, not merely unverified

"A button-handler tour during a live `RUN` job must not corrupt the
shared `lineBuf_`" requires a live RUN JOB, and every motion `RUN:`
verb is refused by its own dispatch — sprint 031 ticket **017**. It
cannot be staged until 017 lands. Recorded as blocked-on-017.

### Item 4 — done by the previous session

Post-fix vs pre-fix comparison, `captures/session-a-20260904/notes.md`.
No change from the prior session's write-up.

### Why this closes now rather than waiting on 017

Ticket 009's own final acceptance criterion is "Any item that cannot be
verified is recorded as UNVERIFIED with what was tried ... never a
fabricated pass." That is satisfied above: item 2(a) is honestly
recorded as blocked-on-017 rather than skipped or faked. Item 2 overall
is PARTIAL (2(b) pass, 2(a) blocked) and is not ticked as fully met.
