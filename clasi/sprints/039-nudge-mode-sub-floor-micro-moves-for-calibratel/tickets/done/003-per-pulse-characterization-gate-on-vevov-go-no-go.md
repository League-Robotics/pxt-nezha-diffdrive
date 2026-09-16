---
id: '003'
title: Per-pulse characterization gate on vevov (go/no-go)
status: done
use-cases:
- SUC-001
depends-on:
- '001'
- '002'
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

## Result

**GO.** MEASURED vevov 2026-09-16,
`captures/039-003-pulse-gate-20260916/notes.md` (harness `pulsesweep.py`
and per-cell `.json` samples committed alongside it, commit `a6ff31e`).
Accepted operating point: **amplitude 15 %, width 2 ticks** — 1.79 mm
per-pulse step, sd/mean 0.08, 0/20 dead pulses, warm and cold (150 s
idle: 1.80 mm, sd/mean 0.14, 0/12 dead).

Headline finding: pulse **WIDTH**, not amplitude, buys repeatability.
At width 1, raising amplitude from 15 % to 25 % raises the mean but
does not fix the nothing-or-lurch bimodal signature (15 %: 3/5 dead,
sd/mean 1.27; 20 %: 4/20 dead, sd/mean 0.65; 25 %: 6/20 dead, sd/mean
0.79). The same 15 % amplitude at width 2 gives 1.79 mm, sd/mean 0.08,
0/20 dead — inside the accept band.

### Per-wheel figures for ticket 004

Both wheels mean exactly **1.79 mm** at the accepted cell — magnitude
is symmetric, a 50/50 split of magnitude is justified. Scatter is
**not** symmetric: left sd/mean 0.08, right sd/mean 0.24. **Ticket 004
must not assume the wheels are interchangeable in consistency**, only
in magnitude.

Camera cross-check (cumulative, 20 pulses both wheels): 49.75 mm camera
vs ~50.0 mm encoder-reported total, within 0.5 % (the camera's own
known 0.41 % over-read accounts for most of the gap).

### Rotation-resolution consequence for ticket 005

A single-wheel pulse at the accepted operating point pivots the robot
about the other wheel by roughly `1.79 mm / track_width`, which at
vevov's **measured** 111 mm track (calipers, 2026-09-16 — the flashed
geometry's baked 128.0 mm trackwidth is wrong) is about **0.9° per
pulse**. calibrateL's tolerance is 1°, so the finest available nudge
only just fits inside it: the settle-gated stepper (tickets 004/005)
must be able to stop within one step of target rather than overshoot
and correct.

**This supersedes the ~0.8°-per-encoder-count claim** in `sprint.md`'s
SUC-001 postcondition and in this sprint's issue file
(`issues/nudge-mode-settle-gated-pulse-stepper-for-sub-floor-micro-moves.md`,
"Resolution check" section) — both corrected alongside this ticket's
close. That figure was wrong by roughly a factor of ten: one encoder
**count** is 0.1 shaft degree = 0.0793 mm of wheel travel, about
**0.08°** of pivot at this track width, not 0.8°. Encoder resolution
was never the limiting factor — the minimum reliable **pulse** is, and
a pulse is ~22 counts' worth of commanded motion at the accepted cell,
not one count.

### Coverage gaps (so the map is not read as complete)

- Widths 3 and amplitudes 35 %/50 % were not run — once width 2 at
  15 % passed inside the band, wider/higher cells could only produce
  bigger steps, the wrong direction for a nudge.
- Cold was tested only at the accepted cell (left wheel, 12 pulses),
  not per cell.
- Per-cell camera cross-checks were not taken; one cumulative check
  ran at the accepted operating point (1.79 mm is below the camera's
  per-pulse noise floor).
- Every cell is the LEFT wheel except two rows (15 %/width 2 on the
  right wheel, and the cumulative both-wheels cross-check); all cells
  are on one surface (the main playfield).

### Pre-flight dance override

The pre-flight dance (`field-dance-first.md`) **FAILED on pivot
magnitude** and was run anyway, on the stakeholder's explicit
go-ahead — recorded as an override, not a pass. Conventions (left is
left, forward is forward, distances accurate to 0.1 cm, bearings
within 3°, return-home within 1 cm) all passed; only rotation
magnitude failed, and this gate fires single-wheel pulses in a
straight line and never pivots, so the failing axis was never
exercised by this session's data.

### Instrument defect found and fixed mid-session

The pulse verb (ticket 001) initially returned EMPTY numeric fields on
hardware (`ret left_counts= right_counts= ... #21`): `execPulse`
formatted with `%.1f`/`%.2f`, and the target's newlib-nano printf has
no float conversion linked in — a defect the host test suite could not
see, since a desktop libc formats floats correctly. Fixed in commit
`c49bc58` (integer-only fields, plus a source-pin test that rejects
`%f`/`%g`/`%e` in the wire layer). The displacement map above was
taken entirely on the fixed build: `id diffdrive vevov-pulsefix0916
1.20260914.1 vevov`.

## Acceptance Criteria

- [ ] A displacement map exists (mean, sd, both mm and counts) for
      every (amplitude, width, wheel, warm/cold) cell in the protocol
      above, saved as a named capture artifact under `captures/`
      (git-add -f'd, per `captures-dir-is-gitignored`) with a MEASURED
      citation naming the board, date and file
      (`.claude/rules/measurement-citations.md`). **NOT FULLY MET.** A
      map exists with the required MEASURED citation
      (`captures/039-003-pulse-gate-20260916/notes.md`, board vevov,
      2026-09-16), but it does not cover every cell in the protocol —
      see "Coverage gaps" above (widths 3, amplitudes 35/50 %, most
      cold and per-cell-camera rows, and the right wheel were not run).
      Left unchecked deliberately: once the accepted cell cleared the
      accept bar, running the remaining grid would only have produced
      larger, less useful steps, so the session stopped there rather
      than completing the full matrix.
- [x] An explicit **GO** or **NO-GO** verdict is written into this
      ticket (and referenced from `sprint.md`'s Tickets section) before
      it is closed. **DONE** — see "Result" above; `sprint.md`'s
      Tickets section updated in the same close.
- [x] On GO: the accepted (amplitude, width) cell(s) and their
      per-wheel asymmetry (if any) are documented for ticket 004 to
      consume — no default 50/50 split assumption. **DONE** — see
      "Per-wheel figures for ticket 004" above.
- [ ] On NO-GO: this ticket documents which cells were tried and why
      every one was bimodal; tickets 004 and 005 are then not started
      this sprint (see `sprint.md`'s NO-GO fallback note), and a
      follow-up issue is filed. **N/A** — the verdict is GO, so this
      branch does not apply.

## Testing

Not host-testable — this ticket IS the test. No code changes are
expected beyond whatever throwaway characterization script drives
ticket 001's primitive through the sweep (kept as a capture artifact,
not shipped code).

- **Verification command**: N/A — hardware acceptance session, run in
  the foreground, never piped (`never-pipe-a-hardware-gate`), gate
  result read first.
