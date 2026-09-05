# tovez kernel FF/I gain retune — host model candidates, 2026-09-04

Sprint 031 ticket 006. **Desk work, no hardware.** Everything below is
a MODEL PREDICTION from `tests/host/test_profile_probe.py`'s own
`LaggedRig`, run against the real compiled `DiffDrive::DifferentialDrive`
kernel (`src/core/diffdrive.cpp`). Per `.claude/rules/measurement-
citations.md`, nothing here is `MEASURED` — the artifact backing every
number in this report is
`tests/host/test_profile_probe.py::test_kernel_ff_i_gain_retune_candidates`,
runnable with:

```
uv run pytest tests/host/test_profile_probe.py -k gain_retune -s
```

Ticket 011 is the hardware session that tries these candidates on
tovez via live `SET pid_kp` / `SET pid_ki` / `SET pid_kaff` and either
confirms or refutes them; ticket 015 bakes whichever one converges.
This ticket changes no firmware default — `shims.cpp`'s `cfg.kp = 0.0f`
/ `cfg.ki = 6.0f` are untouched.

## The scenario

tovez's kernel (`shims.cpp`'s baked defaults, `kp=0, ki=6`) overshoots a
`WHEELS_V 200 200` step to 226–256 mm/s on hardware, with measured
acceleration up to 993 mm/s² on a 400 mm/s²-limited command
(`clasi/sprints/031-.../issues/tovez-drivetrain-tuning-and-restated-
acceptance-bars.md`). `WHEELS_V` calls `MotionEngine::wheelsV()`
directly — unlike a `MOVE_X` segment it never goes through
`VelocityShaper`'s braking/arrival math, so `MotionLimits.lag` (the
arrival-side knob from sprint 029 ticket 009) plays no role in this
scenario; only the wheel's own physical response lag matters, modeled
here by `LaggedRig`'s `tau=0.13` (tovez's baked `lag_s 0.13`,
radio-robot-lib `eafccd2`).

This sprint's own bars (`sprint.md`): peak ≤ 210 mm/s, acceleration ≤
1.5×`accel`. The compiled engine's own `MotionLimits.accel` default is
confirmed 400 mm/s² via `Rig.limits_accel()` in this same test file, so
the acceleration bar is ≤ 600 mm/s².

## Methodology

`tests/host/test_profile_probe.py::_wheels_v_step_response()` (new,
this ticket) runs a `WHEELS_V 200 200` hold for 3 s against
`LaggedRig(tau=0.13, breakaway=70)` — `breakaway=70` is this test
file's own pre-existing `_LAG_MODEL_BREAKAWAY` constant (matching
`docs/code-review/2026-09-02/raw/stiction_probe.cpp`'s own model), not
independently fitted for tovez. `meApplyStictionProbeKernelConfig()`
supplies the rest of tovez's real `Config` (`iMax 765.6`, `pidMax
1276`, `twistHoldGain 2.0`, adaptation/stall terms); a new shim,
`meSetPidGains(handle, kp, ki, kaff)` (`tests/host/
motion_engine_shim.cpp`), overrides just the three gains under test.

**A known gap in a bare `LaggedRig`**: it has no per-wheel gain
mismatch by default (`gain_left == gain_right == 1.0`), so a
`ki=0` candidate "settles" with near-zero steady-state error almost by
construction — there is nothing modeled for an integrator to correct.
`reports/tovez-wheel-velocity-pid-20260828.md` records the robot's real
per-wheel feedforward calibration as `wheel_gain_left 0.80` /
`wheel_gain_right 0.9567`; using that spread directly as an
*uncorrected* physical mismatch would double-count the calibration the
firmware's own `correctedCommand()` already applies. Instead this
sweep injects a much smaller, explicitly **hypothesized** residual —
`gain_left=0.97`, `gain_right=1.02` — via `LaggedRig`'s own per-wheel
gain (sprint 029 ticket 010's model), just large enough to make
steady-state bias visible and rankable without pretending to know the
real residual. **This is a modeling assumption, not a measurement** —
if ticket 011 measures a materially different real residual, re-running
this same sweep with that value is the right way to extend it.

The full sweep grid searched: `kp` in `[0, 0.2]` step `0.025`, `ki` in
`[0, 3]` step `0.5`, `kaff` in `[0, 0.1]` step `0.05` (126 combinations),
ranked by steady-state bias (`|settle_left − 200| + |settle_right −
200|`), then peak acceleration, then peak speed, restricted to
combinations meeting both the peak and acceleration bars.

## Results (model predictions)

| label | kp | ki | kaff | peak (mm/s) | peak accel (mm/s²) | settle L / R (mm/s) |
|---|---|---|---|---|---|---|
| today (kp=0, ki=6) | 0.000 | 6.00 | 0.00 | **237.5** | **654.1** | 200.2 / 199.9 |
| candidate 1 | 0.000 | 0.50 | 0.10 | 207.8 | 489.9 | 201.1 / 200.2 |
| candidate 2 | 0.075 | 0.50 | 0.05 | 204.1 | 474.7 | 201.3 / 200.4 |
| candidate 3 | 0.100 | 0.00 | 0.00 | 199.7 | 489.6 | 199.2 / 199.0 |

`today` fails both bars in the model (237.5 > 210, 654.1 > 600) —
consistent with, though not a re-measurement of, the hardware finding
of 226–256 mm/s. All three candidates hold the peak and acceleration
bars with margin.

## Candidates, ranked, with the tradeoff each one makes

1. **Candidate 3 (`kp=0.10, ki=0.0, kaff=0.0`) — widest margin, no
   integral action.** Lowest peak (199.7) and comfortable accel margin
   (489.6 vs 600). Relies entirely on proportional velocity feedback;
   has no mechanism to correct a persistent bias the model doesn't
   capture (real wheel-to-wheel differences, temperature drift, wire
   noise) beyond what `kp` itself damps each tick. Best first thing to
   try on hardware if the real overshoot mechanism turns out to be
   close to what this model captures — widest headroom against the
   210/600 bars if reality is worse than the model.
2. **Candidate 2 (`kp=0.075, ki=0.5, kaff=0.05`) — balanced.** Keeps a
   small integral term (for the real, unmodeled asymmetry this sweep's
   own hypothesis stands in for) plus modest proportional and
   acceleration feedforward terms. Second-best peak (204.1) with the
   best acceleration margin of the three (474.7).
3. **Candidate 1 (`kp=0.0, ki=0.5, kaff=0.10`) — closest to today's
   shape (I-only, no P).** Cuts `ki` from 6 to 0.5 and adds a modest
   accel feedforward instead of a proportional term. Peak 207.8, closer
   to the 210 bar than the other two, but keeps the control structure
   ("I-term is the distance deficit," per
   `reports/tovez-wheel-velocity-pid-20260828.md`'s own mechanism note)
   most similar to what's running today, which may make it easier to
   reason about mid-session if ticket 011 needs to hand-tune further.

**Recommended order to try on ticket 011: candidate 2, then candidate
3, then candidate 1** — candidate 2 has the best acceleration margin
and still carries some integral robustness; candidate 3 is the
fallback with the most headroom if the model understates the real
transient; candidate 1 is the closest to today's behavior if neither
of the others holds up.

## What this model does NOT capture (read before the hardware session)

`reports/tovez-wheel-velocity-pid-20260828.md` (bench, wheels off the
ground, 2026-08-28) found, on real hardware:

- **`pid_kp` made the spike WORSE, not better**, on a real step —
  `kp·err` adds a kick proportional to the full step at t=0, before
  there is anything to damp.
- **Halving `pid_i_max` left the peak unchanged** — the initial spike
  is not mostly the I-term; it is closer to the feedforward slamming
  steady-state duty into a wheel that has not yet broken away from
  stiction.
- The two real fixes that report identified were **using `MOVE_X`
  instead of raw `WHEELS_V`** (closes the loop on distance, both ends
  of the profile shaped) and, if a velocity-mode step genuinely must
  not overshoot, **a reference ramp** — neither of which this ticket's
  scope covers (this ticket's own scenario is specifically the raw
  `WHEELS_V` step the sprint's bars are stated against).

That report's own `pid_kp` finding directly contradicts what candidates
2 and 3 propose (adding `kp`). Two things are different between that
bench session and this model, and either could explain the gap:

1. **This model's own control ordering differs from that report's
   naive read.** In `fastPid()` (`src/core/diffdrive.cpp`), `err` is
   the CURRENT tick's velocity error against a reference that
   `WHEELS_V` itself ramps via `accel*dt` (design S9.2, confirmed by
   this file's own `test_wheels_v_ramp_never_exceeds_accel_per_tick`)
   — not a bare step reference. The 2026-08-28 report's own framing
   ("`kp·err` adds a kick proportional to the full step at t=0") may
   describe a different, more literal step than what `WHEELS_V`
   actually commands into the kernel.
2. **The report's own bench run was WHEELS OFF THE GROUND** — real
   stiction/breakaway dynamics on an unloaded wheel may differ from
   this model's simplified breakaway constant (`70` mm/s, not fitted to
   tovez) in ways that change which knob actually helps.

Either way, **this contradiction is exactly why ticket 011 exists as a
live hardware session rather than this ticket baking a value directly.**
If candidates 2 and 3 (nonzero `kp`) reproduce that report's "kp makes
it worse" result on real hardware, candidate 1 (`kp=0`, `ki` reduced
from 6 to 0.5, no proportional term) is the fallback this sweep already
ranked third for exactly that reason, and ticket 011's own acceptance
criteria already allow for "if no candidate converges within budget"
feeding a discrepancy back into this model rather than accepting a
value that doesn't meet the bar.

## Reproducing / extending this sweep

- Committed test: `tests/host/test_profile_probe.py::
  test_kernel_ff_i_gain_retune_candidates` (asserts each candidate
  holds both bars; asserts `today` fails them, as a sanity check that
  the model still reproduces the problem).
- Helper: `tests/host/test_profile_probe.py::_wheels_v_step_response()`.
- New shim: `tests/host/motion_engine_shim.cpp::meSetPidGains()`.
- To try a different hypothesized asymmetry or a wider grid, edit
  `_ASYM_GAIN_LEFT`/`_ASYM_GAIN_RIGHT` and `_GAIN_RETUNE_CANDIDATES` in
  that same file, or copy `_wheels_v_step_response()`'s pattern into a
  throwaway script for a one-off sweep.
