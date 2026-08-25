---
status: in-progress
sprint: '011'
tickets:
- 011-007
---

# Brick-reset rebaseline: confirm on hardware that the ~4 m teleport is gone

Priority: **Medium** — successor to `brick-reset-odometry-teleport.md`
(code review R-07 / KERN-07), whose **code fix shipped in sprint 006
ticket 005** and whose bench checklist was written in sprint 006 ticket
006. This issue carries only the part that needs a robot.

## What already shipped (sprint 006, closed 2026-08-24)

- `src/encoder_glitch_armor.h` — `EncoderGlitchArmor::evaluate(raw)`
  returning `kAccept` / `kAcceptAsRebaseline` / `kRejectPending`, host-tested
  (13 tests) and inside the C++11 syntax gate.
- `src/nezha_port.cpp` — on `kAcceptAsRebaseline`, re-anchors
  `encOffset_ = raw - lastPosition_ * fwdSign_` so position stays
  **continuous** across a detected discontinuity and that tick's velocity
  comes out ~0 instead of spiking. (Note: the naive `encOffset_ = raw`
  reproduces `rebaseline()`'s target-0 form, which merely relocates the
  discontinuity rather than removing it — do not "simplify" it back.)
- `src/shims.cpp` — DIAG ordinal **27** = `left.rebaselineCount_ +
  right.rebaselineCount_`.
- Threshold `kMaxDeltaCounts = 5000`, numerically unchanged but now a named
  constant with its derivation recorded: 24 ms cycle × `fullDutyVelocity`
  10795 counts/s ≈ 259 counts/cycle, ~518 for a worst-case two-cycle gap;
  5000 sits ~10× above plausible motion and ~10× below the ~50,000-count
  confirmed discontinuity.

## What is still unproven

`nezha_port.cpp` and `shims.cpp` both include `pxt.h` and are **not
host-testable at all**. So the `collect()` call sites, the offset re-anchor
formula, and the DIAG counter increment are **verified by code review only**.
Nothing above has ever run on a robot.

The full bench checklist — including how to reset a brick mid-session and
what to record — is in the archived issue at
`clasi/sprints/done/006-motion-correctness-goto-geometry-and-odometry-truth/issues/brick-reset-odometry-teleport.md`.
Read it before running; it is more specific than this summary.

## The four questions the bench run must answer

1. Does the armor fire on a real brick reset — does `probe(27)` increment?
2. Does pose stay continuous across it (no ~4 m jump)? This is the actual
   user-visible claim.
3. Does it **not** fire during legitimate fast driving? The false-positive
   side matters just as much — a too-tight threshold would rebaseline during
   normal motion, and all three counters must read 0 through a no-reset pass.
4. Are rebaseline and reject distinguishable in the instruments —
   `probe(23)`/`probe(24)` (`glitchCount_`, per wheel) versus `probe(27)`?

## Practical constraints

- **The counters are not telemetry columns.** `posl`/`posr` and `x`/`y`/`h`
  ride the `TLM FULL` frame, but `probe(27)`/`probe(23)`/`probe(24)` are
  reachable only through the `//%`-annotated `probe(int)` TS shim — getting
  them needs a small on-device script (array-sample-then-dump, per
  `shims.cpp`'s own comment).
- Reading even the telemetry columns live means raw serial text until sprint
  005's `tools/` v6 retrofit lands.
- This project's test robot is **vevov**.

## Related

- `clasi/sprints/done/006-*/issues/brick-reset-odometry-teleport.md` — the
  parent issue and the full checklist.
- `host-tests-compile-newer-standard-than-target.md` (sprint 008) — why
  "host tests pass" could not have caught a wiring error here.
