---
status: in-progress
sprint: 029
tickets:
- 029-007
- 029-009
---

# Pivot end: predictive termination and a yaw-unit floor; retire pivot_overrun as a calibration constant

Priority: **High** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: MK-01, MK-05, MK-07 ([motion-and-kernel](../../../docs/code-review/2026-09-02/raw/motion-and-kernel.md)). Triage #3.
Design: [motion-profile-unification.md](../../../docs/design/motion-profile-unification.md)
sections 6.2 and 6.3 (this issue is one slice of that design; see
`one-velocity-shaper-profile-object-out-of-servicemove.md` for the rest).

## Description

MEASURED (`profile_probe.out` E3c/E3d, ideal wheels): a 90 deg pivot at
cruise 100 reads 88.69 -> 90.22 deg (completion fires, `neutral()` is
staged) and the wheels keep moving through the next tick because the
neutral lands on the following `step()`. Terminal crawl is 1.5 deg/tick:
the 70 mm/s kernel floor is 21 counts per tick against a 4-count yaw
margin. Final yaw with the twist servo off: +1.95 (cruise 60), +2.56 (100),
+0.81 (200). The fleet's measured "+2 deg per pivot, 3 and 90 deg alike"
and the `pivotOverrunMm = 2.2 mm` compensation are this latency: one tick
of floor crawl (1.68 mm) plus stop lag.

Also: the engine's floor knobs (`distFloor_` 0.25 / `turnFloor_` 0.12)
sit below the kernel's 70 mm/s for any cruise under 280 mm/s (583 for
turns), so `SET dist_floor`, `setTaperFloors()` and `test.ts`'s two
profiles change nothing at tour speeds (MK-05). The completion margins
(4/10 counts) are smaller than one tick of crawl, so they test "have we
crossed", not "have we arrived" (MK-07).

## Remedy (per the design)

- Terminate predictively: the last commanded tick is the one that carries
  the wheel to the target (`remain <= v_cmd*dt + stopDistance`), then
  command neutral that tick.
- A pure-turn floor in deg/s (`omegaFloor`, sized so one tick is ~0.5 deg)
  and a cap (`omegaMax`), converted to wheel speed through
  `effectiveTrackWidth()`.
- Replace `pivot_overrun` with a measured `stopDistance` (per-wheel coast
  after the last nonzero command lands); measure it per design 10.2.
- One floor, in the profile, per axis; the kernel's `vMin` set to 0.

## Acceptance

- Probe-as-test: 90 deg pivots at cruise 60/100/200 end within 0.5 deg on
  ideal wheels with no reverse duty on either wheel.
- Bench gate G1 (design 10.1): 12 alternating 90 deg pivots, camera at
  rest, mean |error| <= 0.5 deg, sd <= 0.4 deg.
- `pivot_overrun` is gone from `kFields`, the bake, and every robot config.

## Related

- `pivots-over-rotate-on-corrected-firmware.md` (done) added the compensation.
