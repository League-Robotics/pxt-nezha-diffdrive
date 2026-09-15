---
id: '006'
title: 'Creep self-lock: host-sim stiction plant investigation'
status: open
use-cases: [SUC-004]
depends-on: []
github-issue: ''
issue: slow-continuous-creep-self-locks-below-breakaway.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Creep self-lock: host-sim stiction plant investigation

## Description

Independent of the nudge-mode work (tickets 001-005) — a slow
continuous hold (`whileDriving`/`setWheelSpeeds` at a few cm/s, driven
below breakaway) appears to self-lock: the wheel is driven every tick
but its raw encoder count never advances, and the robot never moves,
until the caller's own timeout.

**Now backed by a real capture**, not just the peer's report:
`captures/calibratel-vevov-20260915/bench-log.md` run 5 — reverse
sweep at -4 cm/s for 30 s (its own 30 s time limit), serial link:
`i2cf` 1247 -> 2493 (delta 1246) over `cyc` 1414 -> 2666 (delta 1252),
camera frame `after-back2.jpg` showing the robot unmoved. `i2cf` ~=
`cyc` over the whole sweep is the signature the issue describes: the
wheel is driven on essentially every tick but its sample never
advances. (Applied duty was never captured this session — `TLM FULL`
was not enabled — so the duty-level claim in the issue's source
reading is still UNVERIFIED; this ticket's own investigation should
close that gap on the host-sim side, and flag it for a hardware
`TLM FULL` capture if the sim needs one to confirm.)

**Suspected mechanism** (source reading, `src/core/diffdrive.cpp:977`
area — READ ONLY, do not edit): K2 does not integrate `PositionRef` on
a tick whose sample did not advance, so the I-term (`ki` 6) never
winds up enough to overcome static breakaway; feedforward alone
(~0.5% duty at 40 mm/s) sits below the port's 3% output deadband.
Nothing else rescues it: the continuous-hold path passes floor 0 to
the shaper (`motion_engine.cpp:397`), and `stallDemand` (~400 mm/s
equivalent) never arms at creep speed.

## Scope

1. Build a host-sim stiction plant (fake motor: zero velocity below a
   breakaway duty threshold, quantized increments above), driven
   through the same continuous-hold path `wheelsV()`/`moveV()` use.
2. Reproduce the suspected lock in the sim: confirm (or refute) that a
   driven-but-frozen tick blocks I-term windup the way the source
   reading predicts.
3. Recommend a fix location. Implement it **only if it is
   `MotionEngine`-level and small** — e.g., a floor or breakaway
   allowance for a continuous `Hold` (today it passes floor 0,
   `motion_engine.cpp:397`). Do not patch
   `src/core/diffdrive.{h,cpp}` — that needs the paired-upstream-patch
   process or an explicit stakeholder decision
   (`.claude/rules/fiber-yield-safety.md`'s "Related invariants"),
   neither of which this ticket is positioned to produce.
4. `crawl_pulse` is not a known-good fix for this — it made end-of-leg
   stalls worse on tovez
   (`captures/tovez-taper-20260829/variants.json`). Creep is a
   different use case, but treat that measurement as prior evidence
   against reaching for the same knob without a fresh test.

## Acceptance Criteria

- [ ] A host-sim stiction plant exists, testable in isolation, and its
      breakaway/quantization parameters are documented (not tuned to
      make a predetermined conclusion true).
- [ ] The sim either confirms or refutes the suspected K2 lock
      mechanism, with the host-sim run itself as the artifact (a host
      test, not a captured hardware run).
- [ ] `captures/calibratel-vevov-20260915/bench-log.md` run 5's
      i2cf/cyc numbers are cited as the hardware anchor exactly as
      given above — cite the artifact, do not re-derive or round the
      numbers from memory (`.claude/rules/measurement-citations.md`).
- [ ] A written recommendation exists regardless of outcome: either a
      landed `MotionEngine`-level fix with a host-sim regression test,
      or a documented "needs a kernel patch, needs a stakeholder
      decision" conclusion with a follow-up issue filed.
- [ ] No edit to `src/core/diffdrive.{h,cpp}`.

## Testing

- **Existing tests to run**: `MotionEngine` continuous-hold host
  suites (`wheelsV`/`moveV` paths).
- **New tests to write**: the stiction-plant sim itself, plus (if a fix
  lands) a regression test pinning the fix's behavior against the sim.
- **Verification command**: the project's host test runner, scoped to
  touched modules. No hardware run is required for this ticket — the
  bench-log capture already anchors it; a fresh `TLM FULL` hardware
  capture is a candidate follow-up only if the sim result is
  ambiguous.
