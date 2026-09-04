---
status: pending
sprint: '031'
---

# test.ts: one job lifecycle (reset aborted, apply a profile, emit TOUR:end), abort calls stopMove, non-blocking display, typo-safe args

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: BT-01, BT-07, BT-11, BT-02 (test half), BT-22
([blocks-and-test](../../../docs/code-review/2026-09-02/raw/blocks-and-test.md)). Triage #7.

## Description

- **BT-01.** `aborted` (`test.ts:59`) is reset only by the eight tours.
  After any `RUN:abort`, every `RUN:pivot`/`straight`/`face`/`cal`/`arc`
  stops after one tick and emits a normal `*:end` -- a bench tool then
  records a 90 deg pivot that "under-rotated by 99 %". The source-pin test
  counts resets in tours only.
- **BT-07.** The five 2026-09-01 tours and `leverCal` set no shaping
  profile (they inherit 40 cm/s + 180 ms ramp after `RUN:goto`) and emit
  no `TOUR:end:<reason>` -- a regression of 08-26 C-12 and half of C-08.
- **BT-11.** `RUN:abort` cannot interrupt a `goToWorld` leg; since sprint
  028 the abort bypass runs inside the leg's own `tickDrive()`, so a
  `stopMove()` in the abort handler ends any loop in any file.
- **BT-02 (test half).** Handlers run on the protocol fiber; every
  `basic.showNumber` (750 ms), `showString`, `pause(400)` and the boot
  `otosBegin()` wait leaves PING/ESTOP/abort unserviced for that long.
- **BT-22.** `runArg()` maps a typo to 0: `RUN:circle:abc` pivots in place
  eight times.

## Remedy

- One `beginJob(name)` that sets `touring`, clears `aborted`, applies a
  named profile, resets `maxGapMs`; one `endJob(reason)` that emits `GAP:`
  and `<VERB>:end:<reason>`; every motion handler uses both.
- The `abort` handler calls `diffDrive.stopMove()`.
- Replace `showNumber`/`showString`/`pause` in handlers with non-blocking
  forms or tick-serviced waits.
- `runArgOr(i, default)` that rejects NaN and non-positive radii.

## Acceptance

- `test_run_abort_source_pin.py` extended: every motion handler resets the
  flag (or `beginJob` is the only entry).
- `test_run_tour_programs.py`: every tour emits a terminal line with a reason.
- No `basic.pause`/`showString`/`showNumber` inside a RUN handler body.
