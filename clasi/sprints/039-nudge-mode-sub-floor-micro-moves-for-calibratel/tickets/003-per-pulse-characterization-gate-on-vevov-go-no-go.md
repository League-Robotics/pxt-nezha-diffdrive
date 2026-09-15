---
id: '003'
title: Per-pulse characterization gate on vevov (go/no-go)
status: open
use-cases: [SUC-001]
depends-on: ['001', '002']
github-issue: ''
issue: nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Per-pulse characterization gate on vevov (go/no-go)

## Description

**Hardware ticket — team-lead runs this session**
(`hardware-tickets-run-them-yourself`), scripted, on the floor, with
the playfield camera live. This is the go/no-go gate the whole nudge
feature is contingent on: build the per-pulse displacement map and
record an explicit verdict before any settle-gated loop is written
(ticket 004).

Depends on ticket 001 (the pulse primitive to drive) and ticket 002
(the reverse-to-forward hang must be understood/fixed first, or this
session risks silently corrupting its own data on the exact kind of
transition ticket 002 investigates — direction changes between
opposite-wheel pulses).

Run `field-dance-first.md`'s dance before any commanded motion this
session, and keep the 12 cm playfield margin
(`.claude/rules/playfield-testing.md`).

## Protocol

For amplitude in {15, 20, 25}% (plus {35, 50}% at width 2) x width in
{1, 2, 3} ticks, per wheel, warm and cold:

1. Fire ~20 pulses from rest using ticket 001's primitive.
2. Record each pulse's encoder-count delta (both counts and mm, using
   vevov's ~0.79 mm/count / ~0.8 deg-per-count-per-wheel pivot
   conversion) and camera-cross-check a sample of them per cell.
3. Compute mean and sd per (amplitude, width, wheel, warm/cold) cell.

**Accept** if some cell gives a repeatable 0.3-2 mm increment with
sd/mean <= 0.4. **Reject** the whole nudge-engine build (tickets
004/005) if every cell is nothing-or-lurch bimodal.

Wheels-up bench data is not a substitute for this — loaded stiction is
what matters (`playfield-testing.md`).

## Acceptance Criteria

- [ ] A displacement map exists (mean, sd, both mm and counts) for
      every (amplitude, width, wheel, warm/cold) cell in the protocol
      above, saved as a named capture artifact under `captures/`
      (git-add -f'd, per `captures-dir-is-gitignored`) with a MEASURED
      citation naming the board, date and file
      (`.claude/rules/measurement-citations.md`).
- [ ] An explicit **GO** or **NO-GO** verdict is written into this
      ticket (and referenced from `sprint.md`'s Tickets section) before
      it is closed.
- [ ] On GO: the accepted (amplitude, width) cell(s) and their
      per-wheel asymmetry (if any) are documented for ticket 004 to
      consume — no default 50/50 split assumption.
- [ ] On NO-GO: this ticket documents which cells were tried and why
      every one was bimodal; tickets 004 and 005 are then not started
      this sprint (see `sprint.md`'s NO-GO fallback note), and a
      follow-up issue is filed.

## Testing

Not host-testable — this ticket IS the test. No code changes are
expected beyond whatever throwaway characterization script drives
ticket 001's primitive through the sweep (kept as a capture artifact,
not shipped code).

- **Verification command**: N/A — hardware acceptance session, run in
  the foreground, never piped (`never-pipe-a-hardware-gate`), gate
  result read first.
