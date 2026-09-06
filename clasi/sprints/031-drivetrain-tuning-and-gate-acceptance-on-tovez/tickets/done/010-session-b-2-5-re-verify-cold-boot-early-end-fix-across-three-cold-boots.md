---
id: '010'
title: 'Session B (2/5): re-verify cold-boot early-end fix across three cold boots'
status: done
use-cases:
- SUC-003
depends-on:
- '005'
- 009
github-issue: ''
issue: segment-moves-end-early-just-after-boot.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Session B (2/5): re-verify cold-boot early-end fix across three cold boots

**Type: (a) hardware/playfield — team-lead executes personally.**

## Description

With ticket 005's fix flashed (via ticket 008/009's consolidated
build), repeat the cold-boot protocol from ticket 001: three
independent cold boots, each with the first ~10 `MOVE_X`/pivot segments
polled at 8 Hz from send. Confirm the sprint's own success criterion
directly: no early-ending segment in the first ten moves after any of
the three boots.

If any boot still shows an early end, capture it with the same
fidelity as ticket 001 and treat it as a reopened finding for ticket
005 (do not silently rationalize it away) — the sprint's success
criterion is zero, not "mostly fixed."

## Acceptance Criteria

- [x] Three independent cold boots on the ticket-005-fixed firmware,
      each with its first ten commanded segments polled at 8 Hz.
- [x] Zero early-ending segments across all three boots' first ten
      moves — this sprint's own Success Criteria bar, quoted verbatim.
- [x] Capture cited per boot (path, board, date) per
      `measurement-citations.md`.
- [x] Any residual early end is captured with full fidelity and flagged
      back to ticket 005, not minimized.

## Testing

- **Existing tests to run**: N/A — hardware verification of ticket
  005's host-tested fix.
- **New tests to write**: none (ticket 005 owns the host-test coverage;
  this is the hardware confirmation).
- **Verification command**: N/A (hardware ticket).

## Closing Note

MEASURED tovez 2026-09-05, firmware 1.20260904.5 (ticket 008's
consolidated build carrying ticket 005's fix). Captures at
`captures/session-b-20260905/ticket010/boot{1,2,3}/` (committed;
`captures/` is gitignored but these files are tracked in the working
tree). Three genuine stakeholder power cycles. Each boot was confirmed
cold AT THE WIRE before anything was commanded — `cyc=0 next=1
connL=0 connR=0` — with `otos=1` on all three. Ten `MOVE_X 40 0 100
4000` segments per boot, camera fix at every boundary, STATUS polled
at 8 Hz from BEFORE the repositioning pivot (a correction over Session
A's harness, which started its poller after the pivot).

| boot | cold | early ends | travel | % cmd | net yaw | deg/cm | i2cf/cyc |
|---|---|---|---|---|---|---|---|
| 1 | yes | none | 29.80 cm | 74.5 | +19.18 | +0.644 | +9/193 |
| 2 | yes | none | 29.74 cm | 74.3 | +23.91 | +0.804 | +8/192 |
| 3 | yes | none | 29.99 cm | 75.0 | +10.11 | +0.337 | +6/192 |

**Bar: zero early-ending segments in the first ten moves after three
cold boots. Result: 0 across 30 segments. PASS.**

All thirty segments landed between 2.75 and 3.24 cm. For contrast,
Session A's boot 3 on the PRE-fix build produced 0.93 cm and 1.84 cm on
the identical protocol — far outside that band. This confirms ticket
005's `wrongWay()` minimum-progress gate on hardware, which is exactly
what this ticket existed to verify.

Incidental finding, recorded here to support ticket 009's reanalysis:
these cold boots on the POST-fix build show yaw drift of +0.337 to
+0.804 deg/cm — squarely inside the pre-fix band (+0.577..+0.936) and
well below the +1.158 that Session A read as a doubling. i2cf per move
is 0.9 / 0.8 / 0.6, back in the pre-fix range (0.60-0.82).

No residual early end to flag back to ticket 005.
