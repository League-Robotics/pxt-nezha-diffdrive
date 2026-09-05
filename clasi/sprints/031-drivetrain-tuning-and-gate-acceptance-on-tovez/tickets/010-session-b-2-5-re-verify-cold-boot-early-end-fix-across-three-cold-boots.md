---
id: '010'
title: 'Session B (2/5): re-verify cold-boot early-end fix across three cold boots'
status: open
use-cases: [SUC-003]
depends-on: ['005', '009']
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

- [ ] Three independent cold boots on the ticket-005-fixed firmware,
      each with its first ten commanded segments polled at 8 Hz.
- [ ] Zero early-ending segments across all three boots' first ten
      moves — this sprint's own Success Criteria bar, quoted verbatim.
- [ ] Capture cited per boot (path, board, date) per
      `measurement-citations.md`.
- [ ] Any residual early end is captured with full fidelity and flagged
      back to ticket 005, not minimized.

## Testing

- **Existing tests to run**: N/A — hardware verification of ticket
  005's host-tested fix.
- **New tests to write**: none (ticket 005 owns the host-test coverage;
  this is the hardware confirmation).
- **Verification command**: N/A (hardware ticket).
