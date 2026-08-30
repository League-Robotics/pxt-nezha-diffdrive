# vevov — subtracting the pivot overrun (2026-08-29)

Stakeholder: "if we literally have a constant 2 % overshoot, then let's
just subtract 2 %." It is a constant **2 degrees**, not 2 % — a 3° pivot
landed at 5° and a 90° pivot at 92° — so the firmware now subtracts a
constant per-wheel distance (2.2 mm, the wheel travel that 2° at
vevov's 128 mm track amounts to) from every rotation target. A 2 %
scale would have fixed the corners and left a 3° pivot at 5°.

**Result on the robot** (firmware `0.20260829.2`, `GET pivot_overrun
2.2`): the in-direction overshoot over a ten-pivot ladder (±3°, ±10°,
±45°, ±90°, ±3°) went from **+2.37° (sd 0.81) to +0.32° (sd 1.49)** in
the robot's own encoders; the four 90° corner pivots of a square tour
went from landing +1.6…+2.0° long to +0.4/+0.1/+0.1/−0.0; the tour
closed at **1.0 cm with −0.6° of heading error**, believed net rotation
**+359.9°** (was +361.4…+362.0). Straight legs are untouched (no
end-of-leg bump, final error +0.5…+1.3 mm). One consequence to know
about: **pivots commanded under ~3° now produce no motion at all** (§4).

Artifacts: `captures/vevov-square-20260829/` — `pivot_check.py`,
`pivot_check_before.json` / `.log` (12:34, firmware .1),
`pivot_check_after.json` / `.log` (12:44, firmware .2), `runD.json` /
`runD.log` (tour D), `analyze_d.py` (every table below),
`vevov_square_tourD.png`. Companion reports:
[vevov-tour-C-firmware-and-telemetry-20260829.md](vevov-tour-C-firmware-and-telemetry-20260829.md)
(the measurement that found the constant),
[vevov-square-tours-20260829.md](vevov-square-tours-20260829.md).

## 1. The change

Commit `b99294f` (PR #2 → `origin/master` `85d61a1`, see §5), 17 files,
+186/−9:

| where | what |
|---|---|
| `src/motion/motion_engine.h` | `pivotOverrunMm_` (default **0.0** — no robot changes behaviour until measured), `pivotOverrunMm()` / `setPivotOverrunMm(mm)` (≥ 0, else keep) |
| `src/motion/motion_engine.cpp` `startSegment()` | after `yawTarget = rotation·b/2·cpm`, subtract `pivotOverrunMm_·cpm` from its magnitude; clamp at 0 rather than flip sign |
| `src/comms/wire_adapter.cpp` | `kFields` row `{"pivot_overrun", 18}` (appended after `stall_clear`, so the bare `GET` dump order is unchanged) |
| `src/shims.cpp` | `setKernelValue`/`getConfigValue` case 18 → the engine setter/getter |
| `src/blocks/motion.ts` | `ConfigField.PivotOverrun = 18` ("pivot overrun mm") |
| `tools/make_deploy.py` | bake key `firmware_bake.pivot_overrun_mm` → `pivotOverrunMm_` (same opt-in path as `travel_calib` / `trackwidth` / `rotational_slip`) |
| `radio-robot-lib/config/robots/vevov.json` | `firmware_bake.pivot_overrun_mm: 2.2` with provenance (`d5b0ed6`, pushed to that repo's `main`) |
| tests | `test_motion_engine_reductions.py` (+2: the subtraction, both signs, the clamp, the validation), the GET/SET sweep and bare-`GET` order, the ConfigField/kFields drift guard's baseline, the toolbox ENUM order, the geometry-bake test, both shims mirrored |
| `src/DESIGN.md`, version | field table note; `dotconfig version bump` → **0.20260829.2** |

`uv run pytest tests`: **793 passed** (the two failures on the way were
mine — I had inserted the `kFields` row before `stall_clear`, and the
enum baseline list needed the new member). Built from the worktree
with `make_deploy.py --robot vevov` (log: bake applied
`travel_calib 0.70066 / trackwidth 128.0 / rotational_slip 0.987 /
pivot_overrun_mm 2.2`, `kVersion 0.20260829.2`, hex 1,499,844 B),
flashed with `mbdeploy deploy --remote vevov`.

Why a worktree: the main checkout carries another session's
uncommitted work in `src/comms/protocol.*`, `radio_transport.*`,
`src/blocks/*.ts` and `test/test.ts`; a hex built from that tree would
have put their half-finished change on a field robot.

## 2. Before / after: the pivot ladder

Same script, same robot, same spot on the field, ten minutes apart.
"err" is the overshoot **in the direction of the pivot**, from the
robot's encoders (telemetry `h` before send vs after stillness) and
from the camera's at-rest fixes.

| cmd | before: believed | err | camera | err | after: believed | err | camera | err |
|---|---|---|---|---|---|---|---|---|
| +3° | +5.5 | +2.5 | +7.3 | +4.3 | +1.8 | −1.2 | +1.7 | −1.3 |
| −3° | −4.4 | +1.4 | — | | −1.6 | −1.4 | −3.0 | 0.0 |
| +10° | +12.5 | +2.5 | — | | +11.2 | +1.2 | +12.3 | +2.3 |
| −10° | −11.6 | +1.6 | −13.3 | +3.3 | −10.2 | +0.2 | −10.0 | 0.0 |
| +45° | +48.7 | +3.7 | +49.4 | +4.4 | +47.9 | +2.9 | +46.7 | +1.7 |
| −45° | −48.4 | +3.4 | — | | −47.5 | +2.5 | −46.5 | +1.5 |
| +90° | +92.3 | +2.3 | +93.1 | +3.1 | +90.1 | +0.1 | +91.1 | +1.1 |
| −90° | −93.2 | +3.2 | −92.5 | +2.5 | −91.2 | +1.2 | −92.9 | +2.9 |
| +3° | +4.3 | +1.3 | +3.7 | +0.7 | +2.0 | −1.0 | +3.1 | +0.1 |
| −3° | −4.7 | +1.7 | −5.0 | +2.0 | −1.7 | −1.3 | −1.5 | −1.5 |
| **mean (believed)** | | **+2.37** | | +2.90 (n=7) | | **+0.32** | | +0.67 (n=10) |
| sd | | 0.81 | | | | 1.49 | | |

The constant is gone. What remains is pivot-to-pivot scatter of about
±1.5°, which the "before" column also had on top of its offset
(+1.3…+3.7): the 45° pair sat high both times, the 3° pair is now a
little short. That scatter is per-wheel: the two wheels never split a
pivot evenly (−733/+814, +936/−597 counts on the 45° pair), and the
2.2 mm is a single shared number. If a tighter value is wanted, `SET
pivot_overrun <mm>` tunes it live without a reflash; the before-ladder
camera fixes were thin (the docker build was starving the daemon —
load average 80–150 during that run) so trust the believed column.

## 3. Tour D on the new firmware

![tour D](../captures/vevov-square-20260829/vevov_square_tourD.png)

| | tour C (0.20260829.1) | **tour D (0.20260829.2)** |
|---|---|---|
| closure (camera) | 2.8 cm | **1.0 cm** |
| end heading vs start | −0.5° | −0.6° |
| believed net rotation | +361.8° | **+359.9°** |
| corner pivots, commanded → believed | +89.3→+91.0, +87.8→+89.4, +87.1→+89.1, +87.3→+89.2 (**+1.6…+2.0**) | +89.4→+89.8, +89.1→+89.2, +89.6→+89.7, +89.4→+89.3 (**+0.4…−0.0**) |
| corners NW / SW / SE / NE | 2.4 / 2.1 / 2.4 / 2.6 | 3.8 / 4.5 / 2.3 / 1.6 |
| travel, believed vs camera | 320.5 / 321.9 cm | 320.4 / 321.6 cm (+0.40 %) |
| leg ends (stop-short / bump / final) | −0.6…−1.5 / 0 / +0.6…+1.5 mm | −0.5…−1.3 / 0 / +0.5…+1.3 mm |
| acks first try | 8/8 | 8/8 |

The closed-loop corners now ask for ~89.4° instead of ~87.5° and land
on it. The NW/SW corners are worse than C's only because the start
heading was ~1.5° off (the camera was still slow: 2–3 samples per park
fix) and leg 1 carried it 3.2 cm north; the tour then closed to 1.0 cm,
the tightest of the day. Legs are untouched by the change, as they
should be — the overrun is taken off the rotation term only.

## 4. The dead zone this creates

A rotation whose wheel arc is smaller than the overrun is clamped to
zero, and a rotation only slightly larger leaves a target the position
loop completes without breaking away. Measured (`runD.log`
12:48–12:50): seven `MOVE_X 0 -37` (−2.1°) commands acked and
"completed" in 0.3 s each with the camera heading unchanged; the
after-ladder's 3° commands did move, landing ~1.8°. So on this
firmware **the smallest pivot vevov will execute is ~3° commanded
(~2° actual)**; anything under ~2.5° is a no-op. Before the change the
same commands moved, but ~2° too far.

Consequences and where they landed:

- `drive_square.py::park` now commands the 3° minimum for residuals
  between 1° and 3° (`--park-offset 0`), and converged in one pivot.
- Any student block or host loop that nudges heading by 1–2° will see
  nothing happen. Two firmware options if that matters, neither taken
  today: floor the compensated target at the smallest step that moves
  (so any nonzero request turns ~2°, error +1° instead of −1° — but
  always in the asked direction), or a real minimum-move path. Filed
  here rather than guessed at.

## 5. State

- vevov: `ver 0.20260829.2`, `pivot_overrun 2.2`, parked near the NE
  dot (49.3, 31.3) @ 180.6°, `tlm=off`, `i2cf=1` since the reboot.
- **Merged.** Commit `b99294f` on `fix/pivot-overrun`, merged to
  `origin/master` as `85d61a1` via PR #2 (2026-08-29 20:29 UTC);
  `radio-robot-lib` `d5b0ed6` (vevov's bake) pushed to `main`. The exact
  hex on vevov is archived as
  `captures/vevov-square-20260829/vevov-0.20260829.2-b99294f.hex`.
  The local `master` in the main checkout still sits at `2d8394c`
  because another session's uncommitted edits touch three of the same
  files (`src/blocks/motion.ts`, `tests/host/test_block_toolbox_order.py`,
  `uv.lock`); once they commit, `git pull --ff-only` brings it level (one
  trivial overlap: the enum's last member). Worktree and branch removed.
