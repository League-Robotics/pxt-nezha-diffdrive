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

## Ticket 007 handoff: re-verified against `src/`, sequenced into this sprint's bench sitting

**Re-checked 2026-08-25 against `src/` at commit `940f997` on
`sprint/011-hardware-validation-otos-world-pose-tours-and-the-residual-leg-fault`
— read, not assumed.**

| Cited symbol | Status | Where |
|---|---|---|
| DIAG ordinal 27 / `probe(27)` | **confirmed** | `src/shims.cpp:812-814` (`diagValue()` `case 27`, sums `left.rebaselineCount_ + right.rebaselineCount_`); `probe(int)` shim at `shims.cpp:1078` |
| `EncoderGlitchArmor::evaluate()` — `kAccept`/`kAcceptAsRebaseline`/`kRejectPending` | **confirmed** | `src/encoder_glitch_armor.h:50-60` (enum), `:107-130` (`evaluate()` body — all three returns present, logic matches the two-strike description) |
| `nezha_port.cpp`'s `encOffset_` re-anchor on `kAcceptAsRebaseline` | **confirmed** | `src/nezha_port.cpp:261-277`; the formula itself is line 275: `encOffset_ = raw - static_cast<int32_t>(lastPosition_) * fwdSign_;` |
| `kMaxDeltaCounts = 5000` | **confirmed** | `src/encoder_glitch_armor.h:98`, derivation comment intact above it |

One correction to this issue's own text above: "no sprint between 006
and 011 has touched these files" is not quite right — `shims.cpp` and
`nezha_port.cpp` were both touched by intervening tickets (sprint 007
ticket 007's DIAG case-25 reorder, sprint 009 tickets 007/008's comment
cleanup, sprint 010 ticket 004's I2C bus-hang guard investigation).
`git blame` on the specific cited lines (the `case 27` block, the
`encOffset_` formula, `kMaxDeltaCounts`, and `evaluate()`'s three
`return` statements) shows every one of them still traces to `bffac352`
(006-005, 2026-08-24) — none of the later touches landed on these
particular lines. Files moved around them; the four cited symbols did
not drift.

### Run this alongside tickets 005 and 006, one sitting

This checklist (originally sprint 006 ticket 006, archived at
`clasi/sprints/done/006-motion-correctness-goto-geometry-and-odometry-truth/issues/brick-reset-odometry-teleport.md`)
runs on the same robot (**vevov**) as this sprint's ticket 005 (OTOS
world-pose validation campaign) and ticket 006 (residual leg-fault
campaign). Combine into one bench sitting rather than three separate
robot sessions. This section only restates the four questions and the
pass/fail criteria for a bench operator's convenience — it does not
replace the archived checklist, which has the full mechanics (the
power-cycle procedure, "prove the instrument first," and the
array-sample-then-dump pattern `probe()` requires because a live
request/reply round-trip mid-move is documented dangerous on this rig).

### The four questions, restated with confirmed/ruled-out criteria

1. **Does the armor fire on a real brick reset?** Confirmed:
   `probe(27)` increments at some tick following the brick
   power-cycle. Ruled out: `probe(27)` stays 0 through the whole event
   (either the brick's 0x46 counter didn't actually reset near zero —
   e.g. battery-backed state held it — or the two-strike sequence
   never resolved; see question 4).
2. **Does pose stay continuous across it?** Confirmed: `x`/`y`/`h`
   (the `TLM FULL` pose columns — or raw serial text off
   `poseX()`/`poseY()`/`poseHeading()` if the v6 tools retrofit hasn't
   landed by the time this runs) show no discontinuity at the same
   tick `probe(27)` increments — no jump anywhere near the ~4 m this
   issue's arithmetic predicts for an unmitigated teleport. Ruled out:
   `probe(27)` increments but pose teleports anyway — that is a wiring
   bug distinct from the code-review-confirmed logic above, and its
   own follow-up, not a silent pass.
3. **Does it stay quiet during ordinary fast driving (no false
   positives)?** Confirmed: over a normal full-duty bench pass with no
   brick power-cycle at all, `probe(27)`, `probe(23)`, `probe(24)` all
   read 0 for the entire run. Finding (not ruled-out, not confirmed):
   any of the three increments during ordinary driving — that means
   `kMaxDeltaCounts` (5000) is tighter than this robot's real
   achievable per-cycle motion, a distinct follow-up from the
   reset-detection result, filed separately.
4. **Are rebaseline and reject distinguishable in the instruments?**
   Confirmed: `probe(23)`/`probe(24)` (`glitchCount_`, per wheel — the
   first, still-ambiguous implausible reading) increments one tick,
   then `probe(27)` (`rebaselineCount_`, both wheels summed — the
   second, self-consistent reading) increments the next tick, in that
   order. Finding: `probe(23)`/`probe(24)` climbs repeatedly with
   `probe(27)` never following — the counter kept producing mutually
   *inconsistent* jumps (`rejMag > kMaxDeltaCounts` each time) and the
   two-strike sequence never resolved to a rebaseline.

### Caution for this bench sitting (measured on vevov 2026-08-25 — applies to tickets 005/006/007 alike)

- **Radio relay, not a USB-tethered bench stand.** A stand run —
  wheels off the ground, robot USB-tethered — produces a complete,
  plausible-looking, worthless record: the wheels spin freely and the
  encoders integrate a phantom trajectory. `posl`/`posr` will move and
  the `probe()` counters will read *something*, but none of it says
  anything about a real reset on a real drivetrain. Run over the radio
  relay with the robot on the mat — `tools/robotlink.py`'s docstring
  makes this same bench/playfield distinction.
- **Camera fix only at tour start and end, never mid-tour** (standing
  camera-is-diagnostics-not-control doctrine). An overhead-camera fix
  is independent ground truth for the pose-continuity question (Q2
  above) — vevov is AprilTag 53.
- **`i2cf` (`i2cFaultCount`, DIAG ordinal 8 / `probe(8)`) was observed
  climbing on vevov today**: 60 accumulated at rest, +2 during one
  short drive. Worth recording explicitly in this session's baseline
  and post-event samples, alongside the eight values the archived
  checklist already calls for — I2C health is exactly what a brick
  reset disturbs, so a session that is already accumulating I2C faults
  before the power-cycle even happens muddies whether a post-reset
  signature is the reset itself or pre-existing bus flakiness.

### Still a handoff, not a report

No acceptance criterion in this section, in ticket 007, or produced by
writing it requires actually running the experiment or reports a
pass/fail from hardware. The bench operator running this alongside
tickets 005/006 records the numbers and judges
confirmed/ruled-out/finding against the criteria above; that judgment
is not made here.
