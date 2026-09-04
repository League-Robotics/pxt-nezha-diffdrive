---
status: in-progress
sprint: 029
tickets:
- 029-002
---

# One velocity shaper for every entry point; MotionLimits and Segment objects; delete the legacy taper and the thirteen knobs

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: MK-04, MK-06, CO-01 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #5.
Design: [motion-profile-unification.md](../../../docs/design/motion-profile-unification.md)
(the whole document; this issue is its sections 4.1-4.4, 4.7, 5, 6.1,
6.4, 6.5, 7, 8, 9).

## Description

Jerk is unbounded where it matters (MEASURED, `profile_probe.out` E1/E4/E7):
the first tick of every move steps to max(70 mm/s, 25 % cruise) in every
mode including `jerk = 4000` (2932-4167 mm/s^2); the end is a hard neutral
from the crawl; `wheelsV()` hands a step straight to the kernel (0 -> 200
mm/s in one tick); the port's 25 %/tick slew is ~1040 %/s. The legacy
taper demands decel proportional to v^2 (6058 mm/s^2 at cruise 400) and
overshoots +5.6 mm with 80 ms motor lag where shaped mode lands -0.6 mm.
Shaped mode exists but is opt-in and only `tools/field_dance.py` opts in.
`serviceMove()` is two algorithms braided through five mode forks, ~360
lines, thirteen knobs, five of them inert at tour speeds.

## Remedy (the design)

- `MotionLimits`: one value object, nine fields, units in trailing comments.
- `VelocityShaper::advance()`: the one per-tick scalar (braking plan, rate
  limit, optional jerk, the floor, the arrival decision) for segments and
  for the continuous hold alike.
- `Segment`: targets and progress; lazy origin capture on the first serviced
  tick (retires the engine's epoch guard).
- `MotionEngine::service()`: ~40 lines, no forks; `wheelsV` becomes a shaped
  hold; `wheelsX` becomes closed-loop like `moveX`.
- Delete the legacy ramp/taper, `distTaper_`, `yawTaper_`, `distFloor_`,
  `turnFloor_`, `rampMs_`, `brakeFrac_`, `plateauMinS_`, `profileExitMmS_`,
  `pivotOverrunMm_`, `awaitingHandoffNeutral`, the two epoch copies.
- Config surface per design 4.7 and 8 (wire names, removed ordinals answer
  `err 1`, blocks as hidden no-ops for one release, `test.ts` profiles as
  two `MotionLimits` literals, `tools/` and `firmware_bake` keys updated).
- Rename every unit-suffixed identifier left in `motion/` per
  `.claude/rules/no-units-in-identifiers.md` while the files are open.

## Acceptance

- `test_velocity_shaper.py`, `test_profile_probe.py`, `test_segment_lazy_origin.py`,
  `test_config_descriptor_table.py` per design section 9, green.
- Design section 7's "after" column measured by the probe and recorded.
- Bench gates G2-G6 (design 10.1) pass and are cited.
- No `MmS`/`Ms`/`Mm`/`Rad`/`Counts` suffix remains in `src/motion/`.

## Related

- `moves-crawl-and-correct-instead-of-gliding-to-a-stop.md` and
  `dist-taper-ceiling-defeats-constant-decel-above-200-mm-s.md` (done)
  covered the taper's tail only.
