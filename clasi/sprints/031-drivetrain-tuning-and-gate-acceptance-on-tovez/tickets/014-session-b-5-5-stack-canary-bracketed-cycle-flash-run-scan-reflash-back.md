---
id: '014'
title: "Session B (5/5): stack-canary bracketed cycle \u2014 flash, run, scan, reflash\
  \ back"
status: open
use-cases: [SUC-008]
depends-on: ['011', '012', '013']
github-issue: ''
issue: sprint-030-hardware-acceptance-needs-one-bench-session.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (5/5): stack-canary bracketed cycle — flash, run, scan, reflash back

**Type: (a) hardware/playfield — team-lead executes personally. Run
LAST in Session B, after all tuning measurements are captured, per
this sprint's Test Strategy and Migration Concerns.**

## Description

Sprint-030 item 5 Part B (the protocol fiber's stack high-water mark)
needs the `DIFFDRIVE_FAULT_SPIN` build from ticket 013. This is
deliberately its own bracketed sub-cycle, not folded into ticket 009,
because the canary build is a distinct binary from the plain
consolidated build every tuning measurement in Session B was taken
against:

1. Flash the ticket-013 canary-enabled build.
2. Run `RUN:tour` with a radio `RUN` issued mid-tour.
3. Halt with pyOCD; scan `currentFiber->stack_bottom .. stack_top` for
   the first non-`0xA5` byte.
4. Pass bar: comfortably under the fiber's documented 2 KB.
5. **Reflash back to the plain consolidated build** (ticket 008's hex,
   NOT the canary build) before Session C begins — Session C's gate
   rerun must run on production firmware.

## Acceptance Criteria

- [ ] The canary build is confirmed running (`HELLO`/`ID` distinct from
      the plain consolidated build) before the scan.
- [ ] Stack high-water mark measured under the tour-plus-radio-RUN
      scenario; first non-`0xA5` byte comfortably under 2 KB, capture
      cited (pyOCD scan output, board, date).
- [ ] tovez is confirmed back on the PLAIN consolidated build (ticket
      008's hex) before this ticket is closed — the reflash-back is
      part of this ticket's own acceptance, not a follow-up.
- [ ] If the canary build fails to run the scenario cleanly (crash,
      hang), record what happened and reflash back regardless — do not
      leave the robot on the debug build.

## Testing

- **Existing tests to run**: N/A — hardware-only verification; the
  scaffold's compile correctness was ticket 013's job.
- **New tests to write**: none.
- **Verification command**: N/A (hardware ticket).
