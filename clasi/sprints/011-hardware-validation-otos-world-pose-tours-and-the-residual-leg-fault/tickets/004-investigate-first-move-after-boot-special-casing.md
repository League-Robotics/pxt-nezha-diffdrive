---
id: '004'
title: Investigate first-move-after-boot special-casing
status: open
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: intermittent-cw-pivot-abort-wheel-reversal.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Investigate first-move-after-boot special-casing

## Description

The residual-fault issue's third next-probe: first-move-after-boot
special-casing. No code evidence was found either way during this
sprint's planning pass — it stays an open item for this ticket to
chase. Trace, by code inspection, what state exists before the very
first `startMove()`/`serviceMove()` call after power-on that might
differ from steady-state behavior: the encoder baseline
(`nezha_port.cpp`'s zeroing/offset logic), the pose seed (`shims.cpp`'s
`Rig` initialization), any cached filter/velocity state in the kernel
(`diffdrive.cpp`), and whether `OtosPort`/`EncoderPoseSource` have any
first-read-is-different behavior.

**This is a code-review ticket, not a host-test ticket.** `shims.cpp`
includes `pxt.h` (confirmed: `shims.cpp:54`) and is outside
`tests/host/`'s compile reach by construction — no `_SHIM_SOURCES` list
anywhere in `tests/host/` includes it (confirmed during this sprint's
planning; several existing host tests document this explicitly, e.g.
`tests/host/test_continuous_mode_odometry.py:25`). `nezha_port.cpp`
carries the same constraint. This investigation cannot honestly claim
test coverage it cannot provide — see `design/src-root-DESIGN.md` §15
for the full framing, which explicitly scopes this ticket as a
documented finding, not a verified one.

## Acceptance Criteria

- [ ] A finding is written into
      `intermittent-cw-pivot-abort-wheel-reversal.md`: either a
      plausible mechanism identified (name the specific state and why
      it could produce a short/truncated first leg), or an explicit
      statement that no such mechanism was found after tracing the
      boot-to-first-move path.
- [ ] The finding explicitly states it is a **code-review finding, not
      a hardware-confirmed one** — ticket 006 (the residual-fault
      campaign procedure) is where any hypothesis from this ticket gets
      tested against reality, not this ticket.
- [ ] No acceptance criterion in this ticket, or produced by it, claims
      test coverage for `shims.cpp`/`nezha_port.cpp` that does not
      exist — no fabricated or token test is added to `tests/host/`
      for a path that cannot actually be exercised there.
- [ ] If the review surfaces a mechanism concrete enough to warrant a
      code change, do NOT make that change in this ticket — flag it in
      the finding and note it as a candidate for a follow-up ticket
      (inside this sprint, if the team-lead agrees to expand scope, or
      as a new issue otherwise). This ticket's own scope is
      characterization, matching this sprint's "instrumented and
      characterized, not fixed sight unseen" success criteria.
- [ ] No robot required.

## Implementation Plan

**Approach:** Read-only investigation. Trace, in order: (1) what
`nezha_port.cpp` does for the encoder baseline before any move has run
(is `encOffset_` zeroed differently on first use vs. after a
rebaseline?); (2) what `shims.cpp`'s `Rig` struct's initial state is
before `seedPose()` or the first `startMove()` call; (3) whether
`DiffDrive::DifferentialDrive` (the kernel) has any state that behaves
differently on its first `step()` call (e.g. an uninitialized filter,
a ramp that assumes a prior velocity); (4) whether `OtosPort`'s or
`EncoderPoseSource`'s first `x()/y()/heading()` read differs from
subsequent reads. Cross-reference each against
`intermittent-cw-pivot-abort-wheel-reversal.md`'s own signature
("occasional distance-leg errors... heading usually still closes") —
a plausible mechanism should be able to explain that specific
signature, not just "something about boot is different."

**Files to modify:** none — this ticket produces a written finding,
not code. If the finding recommends a fix, that fix is explicitly
out of scope for this ticket (see Acceptance Criteria).

**Testing plan:** none — this ticket is code review producing
documentation, matching sprint 006 ticket 006's precedent for a
similarly review-only deliverable. Do not run `pytest` beyond
confirming no unrelated regressions from this sprint's other tickets.

**Documentation updates:** the issue file (see Acceptance Criteria) is
this ticket's deliverable. No `design/` overlay edit is needed unless
the review surfaces something concrete enough that
`design/src-root-DESIGN.md` §15's "no source change planned" statement
for `shims.cpp` needs correcting to name the specific finding — if so,
update it and regenerate the `.diff.md` by hand.

## C++11 Gate Coverage

Not applicable — this ticket makes no source change; it is a
code-review finding only.
