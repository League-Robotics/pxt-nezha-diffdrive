---
status: pending
---

# A frozen encoder read becomes a phantom zero velocity and the PID overreacts

## Description

When an I2C read of a wheel encoder fails, the kernel reuses the previous
position sample. The difference between two identical positions is zero,
so the derived velocity for that tick is **0 mm/s** — for a wheel that is
in fact turning at full speed. The velocity PID sees a ~300 mm/s error
that does not exist, slams duty toward the rail, and the wheel genuinely
over-speeds before the loop recovers.

This is audible on the bench as a sudden surge, and visible as a narrow
spike in any wheel-speed trace.

MEASURED gopiv 2026-09-01, `captures/gopiv-profile-sweep-20260901/tour_tight.json`,
frames 185-191 of an orange-dot tour (lossless USB serial daemon, so this
is the robot's own I2C, **not** telemetry loss — the frame sequence is
fully contiguous, zero frames lost in transit):

| idx | seq | vl | vr | dutl | dutr | posl | posr | i2cf |
|---|---|---|---|---|---|---|---|---|
| 185 | 85 | 302 | 309 | 3400 | 3300 | 200368 | 254747 | 38 |
| 186 | 86 | 272 | **0** | 3200 | **4400** | 200646 | **254747** | **40** |
| 187 | 87 | 266 | 375 | 3000 | 4500 | 200907 | 254975 | 40 |
| 188 | 88 | 293 | **420** | 3100 | 4400 | 201163 | 255336 | 40 |

At index 186 `posr` is byte-identical to the previous frame — the read
failed — and `i2cf` steps 38 → 40. The reported `vr` is 0 while the wheel
is actually doing ~309 mm/s. Duty jumps 3300 → 4500 and the wheel
overshoots to 420 mm/s, settling back over about five control ticks.

Frequency, same capture set:

| capture | i2c failures | frozen reads while moving | frames > 350 mm/s | of those, within 4 frames of a frozen read |
|---|---|---|---|---|
| `tour_tight.json` | 7 | 1 | 5 | 4 |
| `square120.json` | 45 | 3 | 16 | 8 |

So the excursions are not evenly distributed — they cluster on the frozen
reads. The 45-failure run is the same robot on the same bench minutes
earlier, so the rate is variable and can be high.

## Cause

The position→velocity derivation treats "no new sample" as "no movement".
Nothing distinguishes a genuine stop from a failed read, even though the
kernel already *knows* the read failed — it increments the `i2cf` counter
on exactly that event, and that counter is already surfaced in telemetry
(`wire_adapter.cpp`'s snapshot, column 11).

Contributing: `NezhaMotorPort::tick()` yields mid-transaction
(`fiber_sleep(4)` between the I2C select and read,
`src/platform/nezha_port.cpp`), which is a known window for the
transaction to be disturbed.

## Proposed fix

Do not let a failed read manufacture a velocity sample. In rough order of
preference:

1. **Hold, don't zero.** When the read for a wheel fails, carry the
   previous *velocity* estimate forward for that tick rather than
   deriving a new one from an unchanged position. One tick of slightly
   stale velocity is far cheaper than a phantom full-scale error. This is
   the smallest change and needs no new tuning.
2. **Range-gate the derived velocity.** Reject a sample implying an
   acceleration the drivetrain cannot produce — with the constant-`a`
   work from sprint 025 there is now an explicit `aAccelMmS2_`/
   `aDecelMmS2_` bound to test against, so "impossible" is defined rather
   than guessed. A 309 → 0 step in one 24 ms tick implies about
   12 900 mm/s², far outside anything real.
3. **Short running average** on the velocity estimate (2-3 samples) to
   blunt any single bad sample. Cheapest to write, but it adds lag to
   every tick to fix a rare event, so prefer 1 or 2.
4. **Freeze the PID integrator** for a tick whose read failed, so even a
   bad estimate cannot wind the I-term.

Whichever is chosen, the failure should stay *visible*: `i2cf` already
counts it, and nothing here should mask a genuinely dying encoder or a
loose connector as smooth data.

Note this is separate from, and cheaper than, fixing the I2C failures
themselves — a robot with a flaky connector will still fail reads, and
the control loop should not convert that into a lunge.

## Verification

Host-side: drive the engine with a scripted encoder profile that repeats
one position sample mid-move (`tests/host/motion_engine_shim.cpp` already
has `meMotorArmPosition`/`meArmSettleProfile` for placing encoder
readings directly), and assert the commanded duty does not step toward
the rail on that tick and the next.

On hardware: rerun `captures/gopiv-profile-sweep-20260901/tight_tour.py`
on gopiv, which reliably produces I2C failures, and check that frames
following an `i2cf` increment no longer show a speed excursion. gopiv is
a good test rig for this precisely because its rate is high.

## Related

- `clasi/issues/run-probe-bricks-the-board.md` and the I2C-wedge notes —
  same bus, more severe failure mode.
- `reports/tovez-wheel-velocity-pid-20260828.md` — the velocity PID this
  overreaction runs through.
- Sprint 025's constant-`a` constants give the range gate in option 2 a
  principled bound to use.
