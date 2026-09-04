---
status: pending
---

# PID error uses a stale velocity sample after an encoder fault

## Description

Sprint 028 ticket 001 stopped the platform layer from manufacturing a
phantom zero velocity on a frozen or rebaselined encoder read: the
port now withholds the sample-time stamp on all three trigger paths
(read failure, raw-unchanged-under-duty, glitch-armor rebaseline), so
`DifferentialDrive::refreshSample()` holds the previous velocity.
MEASURED gopiv 2026-09-02, `captures/gopiv-frozen-encoder-fix-20260902/notes.md`:
exact-zero velocity at a cruising frozen tick went from 5 of 6 tours
to 0 of 20; duty jumps shrank from 11-17 points to mostly 4-12.

A smaller, real transient remains, correlated with encoder-fault
recovery: peak 447 mm/s against a no-recent-fault ceiling of about
330-354 mm/s. Cause, from reading the vendored kernel:
`DifferentialDrive::controlStep()` computes the PID error against
`sampleLeft_/sampleRight_.velocity` unconditionally, while the
`freshLeft`/`freshRight` staleness flags it already computes are used
only to gate bias adaptation. On the tick after a held sample the
error is computed against a velocity that is one interval old while
the setpoint has moved on, and the recovery tick then integrates the
catch-up.

## Why it is not in sprint 028

`src/core/diffdrive.{h,cpp}` is vendored and kept byte-identical with
radio-robot-firm's copy (`src/DESIGN.md` §2); the sprint's binding
scope decision was platform-layer only. Closing this needs a kernel
change coordinated with the upstream copy: gate the velocity error on
freshness the same way bias adaptation already is, or hold the duty
command on a stale tick.

## What would settle it

Re-run the gopiv tight tour (the analyzer in
`captures/gopiv-acceptance-028-20260902/analyze_frozen.py`) on a
kernel that gates the PID error on `freshLeft`/`freshRight`, and show
the post-fault peak stays inside the no-fault ceiling. UNVERIFIED
until then.

## CORRECTION (code review 2026-09-02, MK-03) -- the mechanism is the position reference, not the velocity error

With the fleet bake's `kp = 0`, `errLeft/errRight` reach the duty only
through `adaptBias()` (tau 30 s); gating them on freshness would change
nothing. MEASURED on the real kernel with ideal wheels
(`docs/code-review/2026-09-02/raw/profile_probe.out`, E5): freezing one
encoder for a single tick at 300 mm/s steps that wheel's duty 35.3 ->
41.3 % because `positionError()` advances `ref.reference` by `speed*dt`
(92 counts) while `sample.position` holds; 6 * 92 = 551 counts/s = 5.1 %
duty. That reproduces the 4-12 point jumps above. The fix is to skip the
reference advance for a wheel whose sample did not advance -- patch K2 in
`code-review/kernel-reference-handling-twist-floor-stale-tick-antiwindup.md`,
which supersedes the "what would settle it" plan above.
