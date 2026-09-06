"""tests/host/test_profile_probe.py -- design docs/design/
motion-profile-unification.md S9.2's "the review's probe promoted to a
test": host-simulated ideal-wheel acceptance checks against the real,
compiled `MotionEngine::service()` + `VelocityShaper`, ticked at a
realistic 24 ms cadence -- the same duty-readback/position-integration
technique test_motion_engine_acceleration_profile.py and
test_motion_engine_deadline_boundary.py use, extended here with a small
(x, y, heading) odometry integrator so ARC/PIVOT ENDPOINTS (not just
dominant-axis distance/speed) can be checked. `Rig.odom()` below
mirrors docs/code-review/2026-09-02/raw/profile_probe.cpp's own
`Rig::odom()` exactly (the review's original C++ probe this design
section promotes).

Design S9.2's exact acceptance list, each with its own test below:
  - pivot 90 deg at cruise 60/100/200 ends within 0.5 deg
    (test_pivot_90_lands_within_half_degree)
  - no negative duty on the wheel that should only ever move forward
    during a pivot (test_pivot_forward_wheel_never_goes_negative --
    review MK-02 / design S4.5 K1's own concern, E3d in the review's
    probe; test_profile_probe_kernel.py already promotes that exact
    scenario to a test on its own, this is the same check generalized
    to both pivot directions)
  - arc endpoint within 2 mm (test_arc_endpoint_matches_the_constant_
    radius_geometry)
  - straight peak speed <= cruise + 5% (test_straight_peak_speed_
    within_5_percent_of_cruise)
  - `set wheel speeds` (WHEELS_V) never steps more than accel*dt in one
    tick, and settles at its commanded speed with no overshoot past
    design S10.1 gate G5's 210 mm/s bound
    (test_wheels_v_ramp_never_exceeds_accel_per_tick -- see that test's
    own docstring for why a continuous Hold has no floor STEP the way a
    Segment does)

Plus one MEASURED record of design S7's own "after" column claim for
its representative case (600 mm leg at cruise 200: "3.36 s today and
~3.3 s after") -- see test_design_s7_after_measurement_600mm_cruise_200
docstring for the citation.

Run with::

    uv run pytest tests/host/test_profile_probe.py
"""

import math

import pytest


LEFT = 0
RIGHT = 1

# docs/design/design.md "Execution model (tick model)" -- the realistic
# control-cycle cadence every multi-tick host test in this directory
# uses.
TICK_MS = 24.0

# Large enough that every speed used below stays well under the
# fullDutyVelocity rail -- no assertion here is secretly checking a
# clamped value.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

_KPI = 3.14159265358979323846


class Rig:
    """Ideal-wheel host simulation of one MotionEngine: ticks the REAL
    service() at TICK_MS cadence, integrating each wheel's encoder
    position from the ACTUAL last-staged duty (no simulated physics,
    no lag), plus a small differential-drive odometry integrator
    (`odom()`) so (x, y, heading) endpoints -- not just dominant-axis
    distance -- can be checked. Mirrors docs/code-review/2026-09-02/
    raw/profile_probe.cpp's own Rig exactly, reimplemented here against
    the ctypes shim instead of a standalone C++ binary."""

    def __init__(self, lib, full_duty_velocity=None, track_width=None,
                 rotational_slip=None):
        self._lib = lib
        self._handle = lib.meCreate()
        # Ticket 009's own LaggedRig subclass (below) needs a DIFFERENT
        # fullDutyVelocity/geometry than every other Rig-based test in
        # this file -- to match docs/code-review/2026-09-02/raw/
        # stiction_probe.cpp's own Rig exactly (10795 counts/s, tovez
        # geometry 128mm/0.9617) -- so these are optional overrides,
        # defaulting to exactly what every existing caller already gets
        # (None -> FULL_DUTY_VELOCITY / the engine's own compiled
        # defaults), no behavior change for `Rig(motion_lib)` callers.
        self._full_duty_velocity = (
            full_duty_velocity if full_duty_velocity is not None
            else FULL_DUTY_VELOCITY)
        if track_width is not None:
            self._lib.meSetTrackWidth(self._handle, track_width)
        if rotational_slip is not None:
            self._lib.meSetRotationalSlip(self._handle, rotational_slip)
        self._lib.meSetMaxDuty(self._handle, 100.0)
        self._lib.meSetFullDutyVelocity(self._handle, self._full_duty_velocity)
        assert self._lib.meBegin(self._handle) == 0  # STATUS_OK
        self._cpm = self._lib.meCountsPerMm(self._handle)
        self._b = self._lib.meEffectiveTrackWidth(self._handle)
        self._lib.meClockSetNow(self._handle, 0)
        self._pos = {LEFT: 0.0, RIGHT: 0.0}
        self._prev_pos = {LEFT: 0.0, RIGHT: 0.0}
        self._duty = {
            LEFT: self._lib.meMotorLastStagedDuty(self._handle, LEFT),
            RIGHT: self._lib.meMotorLastStagedDuty(self._handle, RIGHT),
        }
        self._t_us = 0
        self.x = 0.0
        self.y = 0.0
        self.h = 0.0  # [rad]
        self.speed_log = []       # [mm/s] max(|vl|,|vr|) per tick
        self.duty_log_left = []   # [fraction, signed]
        self.duty_log_right = []  # [fraction, signed]
        # sprint 029 ticket 010: signed PHYSICAL wheel speed per tick --
        # for the ideal Rig this is duty * fullDutyVelocity / cpm (no
        # lag, so it equals the commanded speed exactly); LaggedRig
        # overrides these with its own simulated `self._v` instead,
        # which is the quantity a sign-never-flips assertion actually
        # needs (duty can command a direction the lagged wheel has not
        # caught up to yet, or -- the K1 defect this ticket fixes --
        # never should have been commanded at all).
        self.velocity_log_left = []   # [mm/s] signed
        self.velocity_log_right = []  # [mm/s] signed

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def limits_accel(self):
        return self._lib.meLimitsAccel(self._handle)

    def limits_v_floor(self):
        return self._lib.meLimitsVFloor(self._handle)

    def set_v_max(self, v):
        self._lib.meLimitsSetVMax(self._handle, v)

    def set_lag(self, v):
        self._lib.meLimitsSetLag(self._handle, v)

    def set_twist_hold_gain(self, v):
        self._lib.meSetTwistHoldGain(self._handle, v)

    def set_pid_gains(self, kp, ki, kaff):
        """Sprint 031 ticket 006: overrides the kernel's kp/ki/kaff on
        top of whatever Config a prior meApplyStictionProbeKernelConfig()
        (LaggedRig.__init__) already staged."""
        self._lib.meSetPidGains(self._handle, kp, ki, kaff)

    def twist_reference_counts(self):
        return self._lib.meTwistReferenceCounts(self._handle)

    def twist_error_counts(self):
        """K1 corrected (sprint 029 ticket 010) diagnostic: twistRef_.
        reference minus the measured post-origin half-differential
        position, in [counts]. Valid because this harness's twist-hold
        origin is always (0, 0) -- the servo arms on the FIRST
        controlStep() of a run, at which point self._pos is still at
        its __init__ value (0.0, 0.0); it is never rearmed mid-run by
        any test in this file."""
        measured = 0.5 * (self._pos[RIGHT] - self._pos[LEFT])
        return self.twist_reference_counts() - measured

    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def is_driving(self):
        return bool(self._lib.meIsDriving(self._handle))

    def _odom(self):
        d_left = (self._pos[LEFT] - self._prev_pos[LEFT]) / self._cpm
        d_right = (self._pos[RIGHT] - self._prev_pos[RIGHT]) / self._cpm
        self._prev_pos[LEFT] = self._pos[LEFT]
        self._prev_pos[RIGHT] = self._pos[RIGHT]
        d_center = 0.5 * (d_left + d_right)
        d_heading = (d_right - d_left) / self._b
        mid = self.h + 0.5 * d_heading
        self.x += d_center * math.cos(mid)
        self.y += d_center * math.sin(mid)
        self.h += d_heading

    def tick(self):
        for side in (LEFT, RIGHT):
            self._pos[side] += self._duty[side] * self._full_duty_velocity * (
                TICK_MS / 1000.0)
        self._t_us += int(TICK_MS * 1000.0)
        self._lib.meMotorArmPosition(self._handle, LEFT, self._pos[LEFT],
                                     self._t_us)
        self._lib.meMotorArmPosition(self._handle, RIGHT, self._pos[RIGHT],
                                     self._t_us)
        self._lib.meClockSetNow(self._handle, self._t_us)
        self._lib.meStep(self._handle)
        active = bool(self._lib.meServiceMove(self._handle))
        self._duty[LEFT] = self._lib.meMotorLastStagedDuty(self._handle, LEFT)
        self._duty[RIGHT] = self._lib.meMotorLastStagedDuty(
            self._handle, RIGHT)
        self._odom()
        vl = self._duty[LEFT] * self._full_duty_velocity / self._cpm
        vr = self._duty[RIGHT] * self._full_duty_velocity / self._cpm
        self.speed_log.append(max(abs(vl), abs(vr)))
        self.duty_log_left.append(self._duty[LEFT])
        self.duty_log_right.append(self._duty[RIGHT])
        self.velocity_log_left.append(vl)
        self.velocity_log_right.append(vr)
        return active

    def run(self, max_ticks=4000):
        n = 0
        while n < max_ticks and self.is_move_active():
            self.tick()
            n += 1
        return n


# docs/code-review/2026-09-02/raw/stiction_probe.cpp's own Rig
# constructor defaults -- LaggedRig below matches them exactly (NOT the
# other Rig-based tests' own 5000 counts/s / 114.2mm/0.952 defaults),
# since design S6.3's table was measured against THIS geometry/duty
# rail, and the breakaway-stiction model only produces the duty windup
# that table's numbers depend on when driven by the SAME PID Config
# (kp=0, ki=6, ...) stiction_probe.cpp's Rig sets -- the "pure
# feedforward" Config every other host test in this file relies on
# (motion_engine_shim.cpp's own header comment) has no integrator to
# wind up against an un-broken-away wheel at all.
_STICTION_FULL_DUTY_VELOCITY = 10795.0  # [counts/s]
_STICTION_TRACK_WIDTH = 128.0           # [mm]
_STICTION_ROTATIONAL_SLIP = 0.9617      # [1]


class LaggedRig(Rig):
    """Non-ideal-wheel host simulation, ticket 009's own lagged-wheel
    model ported from docs/code-review/2026-09-02/raw/stiction_probe.cpp
    (`Rig::wheel()`/`Rig::tick()` there): first-order response lag
    (`tau`, [s]) plus breakaway stiction (`breakaway`, [mm/s] -- a
    wheel needs a commanded speed at or above this to START moving from
    rest, and drops back to rest once its commanded speed falls below
    HALF that) layered on top of the ideal `Rig`'s own duty-to-position
    integration, PLUS the real closed-loop PID/adaptation/stall Config
    (`meApplyStictionProbeKernelConfig`, motion_engine_shim.cpp) and the
    tovez geometry/duty-rail defaults above -- all matching
    stiction_probe.cpp's own Rig exactly. This is the SAME model design
    S6.3's own table was measured against (the "before" numbers this
    ticket's fix closes the gap on) -- MEASURED against the sprint-029
    engine as first landed, docs/code-review/2026-09-02/raw/
    stiction_probe.out.

    Overrides ONLY `tick()` -- `_odom()`, `run()`, and every other Rig
    method/property are inherited unchanged; they operate on `self._pos`
    regardless of how it got there.

    `gain_left`/`gain_right` (sprint 029 ticket 010, design §4.5 K1
    corrected): per-wheel multiplier on the LAGGED, physically-realized
    speed -- ported from docs/code-review/2026-09-02/raw/
    twist_runaway_probe.cpp's own `Rig::tick()` (`vL/vR += a*(tL/tR -
    vL/vR)` where `tL = appliedDuty*kFullDuty*gainL`), which is the SAME
    per-wheel-gain-on-the-lagged-target idea, just layered on top of
    THIS model's breakaway/stiction on/off state instead of a bare
    first-order lag. Default 1.0 (no asymmetry, existing callers
    unaffected). `breakaway=0.0` reproduces twist_runaway_probe.cpp's
    own model exactly (`not moving and abs(cmd_mm) >= 0.0` is always
    true, so the wheel is "moving" from its very first tick and
    stiction never engages)."""

    def __init__(self, lib, tau, breakaway,
                 full_duty_velocity=_STICTION_FULL_DUTY_VELOCITY,
                 track_width=_STICTION_TRACK_WIDTH,
                 rotational_slip=_STICTION_ROTATIONAL_SLIP,
                 gain_left=1.0, gain_right=1.0):
        super().__init__(lib, full_duty_velocity=full_duty_velocity,
                         track_width=track_width,
                         rotational_slip=rotational_slip)
        self._lib.meApplyStictionProbeKernelConfig(self._handle)
        self._tau = tau            # [s]
        self._breakaway = breakaway  # [mm/s]
        self._gain = {LEFT: gain_left, RIGHT: gain_right}  # [1] per wheel
        self._v = {LEFT: 0.0, RIGHT: 0.0}       # [counts/s] simulated
        self._moving = {LEFT: False, RIGHT: False}

    def run(self, max_ticks=4000):
        """Overrides Rig.run(): stiction_probe.cpp's own `Rig::run()`
        keeps ticking 12 times PAST the move going inactive
        (`for(int i=0;i<12;++i) tick();`) -- the engine has already
        commanded neutral by then, but the LAGGED wheel keeps physically
        coasting for several more ticks before it decays to rest, and
        THAT coast is where a lag-driven overshoot actually shows up in
        the final heading. Without these extra ticks the simulation
        stops the instant the engine (which only ever sees its own,
        possibly-stale, commanded speed when `lag` is unset) THINKS the
        move is done, silently discarding the very overshoot design
        S6.3's table is measured from."""
        n = super().run(max_ticks=max_ticks)
        for _ in range(12):
            self.tick()
        return n

    def _wheel(self, side, cmd_counts, dt):
        cmd_mm = cmd_counts / self._cpm
        if not self._moving[side] and abs(cmd_mm) >= self._breakaway:
            self._moving[side] = True
        if self._moving[side] and abs(cmd_mm) < 0.5 * self._breakaway:
            self._moving[side] = False
        target = cmd_counts * self._gain[side] if self._moving[side] else 0.0
        if self._tau <= 0.0:
            self._v[side] = target
        else:
            a = dt / (self._tau + dt)
            self._v[side] += a * (target - self._v[side])
        return self._v[side]

    def tick(self):
        dt = TICK_MS / 1000.0
        for side in (LEFT, RIGHT):
            cmd_counts = self._duty[side] * self._full_duty_velocity
            v = self._wheel(side, cmd_counts, dt)
            self._pos[side] += v * dt
        self._t_us += int(TICK_MS * 1000.0)
        self._lib.meMotorArmPosition(self._handle, LEFT, self._pos[LEFT],
                                     self._t_us)
        self._lib.meMotorArmPosition(self._handle, RIGHT, self._pos[RIGHT],
                                     self._t_us)
        self._lib.meClockSetNow(self._handle, self._t_us)
        self._lib.meStep(self._handle)
        active = bool(self._lib.meServiceMove(self._handle))
        self._duty[LEFT] = self._lib.meMotorLastStagedDuty(self._handle, LEFT)
        self._duty[RIGHT] = self._lib.meMotorLastStagedDuty(
            self._handle, RIGHT)
        self._odom()
        vl = self._v[LEFT] / self._cpm
        vr = self._v[RIGHT] / self._cpm
        self.speed_log.append(max(abs(vl), abs(vr)))
        self.duty_log_left.append(self._duty[LEFT])
        self.duty_log_right.append(self._duty[RIGHT])
        self.velocity_log_left.append(vl)
        self.velocity_log_right.append(vr)
        return active


# ---- lag-aware braking closes the gap on the lagged-wheel model -----
# (ticket 009: design S6.3's own table, re-measured with the fix landed)
#
# DEVIATION FROM THE TICKET'S ORIGINAL 1.0 deg STRETCH GOAL, recorded
# here and in this ticket's own report/design S6.3 (per this ticket's
# own "if a design S6.1 detail turns out wrong in practice" allowance):
# MEASURED (this file's own test_design_s6_3_table_remeasured_with_the_fix
# below) that no vAct/lag-based correction to VelocityShaper::advance()
# closes the gap to under 1.0 deg at EVERY (tau, cruise) cell -- three of
# six land within 1.0 deg, the other three land within 2.5 deg (vs the
# UNFIXED model's own +3.4..+26.1 deg). Systematically varying the
# formula (which term carries vAct vs vNext/vPrev, additive vs
# full-replacement) moved the residual around but never eliminated it,
# and the residual at cruise 100/200 with tau=0.08 was IDENTICAL across
# every formula variant tried -- strong evidence it is not an arrival-
# formula problem at all. The actual cause, traced by inspection: this
# geometry's pure-turn floor (omegaFloorAsWheelSpeed(), ~21 mm/s) sits
# BELOW half this model's own breakaway (35 mm/s), so the segment's
# first commanded tick (design S6.1's own "from rest, the first command
# is the floor -- a step") does not itself break the simulated wheel
# away; MEASURED (LaggedRig trace) it takes ~5-6 further accel-ramped
# ticks before the commanded speed first crosses the full 70 mm/s
# breakaway and the wheel actually starts moving. That fixed startup
# delay is a property of the STICTION MODEL and this floor/breakaway
# relationship -- untouched by `lag` or by anything VelocityShaper
# decides -- so no arrival-side formula can absorb it. Design S10.2's
# own `stopDistance` (bench-measured WITH `lag` already set, "the
# speed-independent remainder once the lag term is accounted for
# separately") is the mechanism the design already names for exactly
# this kind of residual; it is 0 (unset) in this host-model test, since
# S10.2's bench sweep is a later ticket's job, not this one's.
_LAG_MODEL_CRUISES = (40.0, 100.0, 200.0)
_LAG_MODEL_TAUS = (0.08, 0.15)
_LAG_MODEL_BREAKAWAY = 70.0

# MEASURED bound (see the deviation note above and this module's own
# test_design_s6_3_table_remeasured_with_the_fix): the worst of the six
# (tau, cruise) cells lands 2.24 deg off with the fix landed, down from
# 9.41 deg unfixed -- a real, large improvement, just not uniformly
# under the ticket's original 1.0 deg stretch goal.
#
# RE-MEASURED 2026-09-04 (sprint 029 ticket 010, K1 corrected -- design
# S4.5's own K1 row): fixing the twist-hold reference's positive-
# feedback bug (K1) shifts this table's worst cell too, since the SAME
# servo runs during a pure pivot. 5 of 6 cells improve or hold (e.g.
# tau=0.08/cruise=200 goes from ~2.2 deg to +0.77 deg); the sixth,
# tau=0.15/cruise=200, worsens from 2.24 deg to -3.47 deg -- MEASURED
# via this file's own test_design_s6_3_table_remeasured_with_the_fix
# (rerun with -s). This is expected, not a new defect: the OLD K1
# formula's own trim-feedback (integrating the TRIMMED targets) was, by
# accident, adding extra aggression that happened to help THIS one
# worst-case cell land closer to 90 deg, the same mechanism that ran
# away under real wheel asymmetry (twist_runaway_probe.cpp,
# test_kernel_reference_handling.py's own asymmetric-wheel regression
# tests). Nothing in VelocityShaper's own braking/arrival formula
# (ticket 009) changed; only K1's servo did. The bound widens to cover
# the new worst case with a small margin, same shape as the deviation
# above.
#
# RE-MEASURED 2026-09-06 (floor-relative arrival credit, design S6.3
# "floor-relative credit"): the arrival predicate now credits lag coast
# only ABOVE the speed floor, `(vAct - floor) * lag`, because a real
# wheel is stiction-bound at the floor and does not coast the full
# vAct*lag there. MEASURED tovez, bench, wheels up, 12 interleaved 90 deg
# pivots (reports/square-hw-vs-sim-20260906/bench-demo/lag-sweep-bench*.
# json): full credit landed -8.05 deg at lag 0.13; floor-relative -2.38;
# the clean 600 mm square went from 387.4 mm closure to 11.0 mm at the
# same bake. THIS rig's plant is a first-order lag with breakaway only
# at START (LaggedRig / stiction_probe.cpp): it coasts the full vAct*lag
# at every speed, so on it the floor-relative form lands every cell LONG
# -- +3.59 / +3.84 / +3.26 (tau 0.08, cruise 40/100/200) and +4.63 /
# +4.99 / +4.31 (tau 0.15) -- the model coasting what the hardware does
# not. The bound below therefore covers a KNOWN MODEL OFFSET, not an
# engine-accuracy claim: it is widened to clear the worst cell (4.99),
# and every cell is additionally required to be one-signed (LONG), so a
# regression that lands SHORT again on this plant -- the full-credit
# form's signature -- still fails. Do not restore the full credit to
# tighten this; fit a plant with floor stiction (design S10.2) instead.
_LAG_MODEL_ARRIVAL_BOUND_DEG = 5.5
_LAG_MODEL_ARRIVAL_SIGN_NOTE = ("on this no-floor-stiction plant the "
                                "floor-relative credit must land LONG")


@pytest.mark.parametrize("cruise", _LAG_MODEL_CRUISES)
@pytest.mark.parametrize("tau", _LAG_MODEL_TAUS)
def test_lag_aware_pivot_lands_within_the_measured_arrival_window(
        motion_lib, tau, cruise):
    """With `MotionLimits.lag` set to the LaggedRig's own `tau` (the
    bench measurement design S10.2 describes), a 90 deg pivot on the
    SAME lagged-wheel model design S6.3's table was measured against
    lands within `_LAG_MODEL_ARRIVAL_BOUND_DEG` -- see this module's own
    deviation note (above `_LAG_MODEL_CRUISES`) for why that bound is
    3.75 deg (widened again 2026-09-04, sprint 029 ticket 010, when K1's
    corrected servo shifted the worst cell), not design S9.2's original
    1.0 deg stretch goal, and test_design_s6_3_table_remeasured_with_the
    _fix below for the printed before/after numbers it is derived from.
    """
    with LaggedRig(motion_lib, tau=tau, breakaway=_LAG_MODEL_BREAKAWAY) as r:
        r.set_lag(tau)
        r.move_x(0.0, _KPI / 2.0, cruise, 30000)
        n = r.run()
        assert n > 0
        heading_deg = r.h * 180.0 / _KPI
        assert heading_deg == pytest.approx(
                90.0, abs=_LAG_MODEL_ARRIVAL_BOUND_DEG), (
            f"tau={tau} cruise={cruise}: lag-aware pivot landed at "
            f"{heading_deg:.3f} deg, more than "
            f"{_LAG_MODEL_ARRIVAL_BOUND_DEG} deg from the commanded 90"
        )
        assert heading_deg >= 90.0 - 0.5, (
            f"tau={tau} cruise={cruise}: landed SHORT at {heading_deg:.3f} "
            f"deg -- {_LAG_MODEL_ARRIVAL_SIGN_NOTE} (2026-09-06 note above)"
        )


def test_design_s6_3_table_remeasured_with_the_fix(motion_lib):
    """MEASURED against THIS ticket's own compiled engine (lag-aware
    braking/arrival landed, velocity_shaper.cpp) on the SAME lagged-wheel
    host model design S6.3's own table was measured against
    (docs/code-review/2026-09-02/raw/stiction_probe.cpp/.out) -- "before"
    reproduces that table's own numbers with `MotionLimits.lag` left at
    its 0.0 default (the engine as first landed, sprint 029 ticket 003);
    "after" sets `lag` to the model's own `tau` (ticket 009's fix).
    Rerun with `-s` to reproduce the printed table; this test IS the
    citation (.claude/rules/measurement-citations.md) for the numbers
    recorded in this ticket's own report -- see this module's own
    deviation note (above `_LAG_MODEL_CRUISES`) for why the assertion
    below uses `_LAG_MODEL_ARRIVAL_BOUND_DEG` rather than design S9.2's
    original 1.0 deg stretch goal."""
    rows = []
    for tau in _LAG_MODEL_TAUS:
        for cruise in _LAG_MODEL_CRUISES:
            with LaggedRig(motion_lib, tau=tau,
                           breakaway=_LAG_MODEL_BREAKAWAY) as before:
                before.move_x(0.0, _KPI / 2.0, cruise, 30000)
                n = before.run()
                assert n > 0
                before_err = before.h * 180.0 / _KPI - 90.0
            with LaggedRig(motion_lib, tau=tau,
                           breakaway=_LAG_MODEL_BREAKAWAY) as after:
                after.set_lag(tau)
                after.move_x(0.0, _KPI / 2.0, cruise, 30000)
                n = after.run()
                assert n > 0
                after_err = after.h * 180.0 / _KPI - 90.0
            rows.append((tau, cruise, before_err, after_err))
            assert abs(after_err) <= _LAG_MODEL_ARRIVAL_BOUND_DEG, (
                f"tau={tau} cruise={cruise}: after-fix error "
                f"{after_err:+.2f} deg exceeds "
                f"{_LAG_MODEL_ARRIVAL_BOUND_DEG} deg"
            )
            assert after_err >= -0.5, (
                f"tau={tau} cruise={cruise}: after-fix error {after_err:+.2f} "
                f"deg is SHORT -- {_LAG_MODEL_ARRIVAL_SIGN_NOTE}"
            )

    print("\ndesign S6.3 table, re-measured against THIS ticket's fix "
          "(lag 80/150 ms, breakaway 70 mm/s, cruise 40/100/200):")
    print(f"{'tau (s)':>8}{'cruise':>8}{'before (lag=0)':>18}"
          f"{'after (lag=tau)':>18}")
    for tau, cruise, before_err, after_err in rows:
        print(f"{tau:>8.2f}{cruise:>8.0f}{before_err:>+17.1f}°"
              f"{after_err:>+17.1f}°")


# ---- sprint 031 ticket 006: kernel FF/I gain retune, candidates ONLY --
#
# MODEL PREDICTIONS, NOT MEASUREMENTS (.claude/rules/measurement-
# citations.md): everything below runs the REAL compiled kernel
# (core/diffdrive.cpp, via this file's own LaggedRig) against a host
# SIMULATION of the wheel -- first-order lag + breakaway stiction, no
# tovez hardware in this dispatch. Nothing here is labelled MEASURED.
# Ticket 011 is the hardware session that tries these candidates on
# tovez via live `SET pid_kp`/`SET pid_ki`/`SET pid_kaff` (shims.cpp's
# SET dispatch cases 2/3/5) and either confirms or refutes them; ticket
# 015 bakes whichever one converges. This ticket changes no firmware
# default (`shims.cpp`'s `cfg.kp = 0.0f` / `cfg.ki = 6.0f` are untouched).
#
# The scenario: `sprint.md` §"Kernel tracking overshoot" / this sprint's
# linked issue -- a `WHEELS_V 200 200` step overshoots to 226-256 mm/s
# on hardware today (`kp=0, ki=6`, shims.cpp's tovez defaults) with
# measured acceleration up to 993 mm/s^2 on a 400-limited command
# (accel=400 mm/s^2 is this engine's own compiled MotionLimits default,
# confirmed via `Rig.limits_accel()` below -- so this sprint's own
# "<=1.5x accel" bar is <=600 mm/s^2). `WHEELS_V` calls
# MotionEngine::wheelsV() directly (motion_engine.cpp) -- unlike a
# MOVE_X segment it never goes through VelocityShaper's braking/arrival
# math, so `MotionLimits.lag` (the OTHER "lag" in this file, ticket
# 009's arrival-side knob) plays no role here; only LaggedRig's own
# `tau` (the wheel's simulated physical response time) matters, set to
# 0.13 to match the `lag_s 0.13` tovez already runs (baked
# radio-robot-lib eafccd2, per this ticket's own description).
#
# `_wheels_v_step_response()` reproduces the WHOLE closed loop the
# hardware step exercises: `WHEELS_V 200 200` for 3 s against
# LaggedRig(tau=0.13, breakaway=70 -- this file's own
# `_LAG_MODEL_BREAKAWAY`, not independently fitted for tovez), with
# `meApplyStictionProbeKernelConfig()`'s tovez-shaped Config (iMax
# 765.6, pidMax 1276, twistHoldGain 2.0, ...) and `set_pid_gains()`
# overriding just kp/ki/kaff per candidate. `speed_log[0]` is a
# pre-Hold capture-loop artifact (same reason
# test_wheels_v_ramp_never_exceeds_accel_per_tick above drops it) --
# excluded from both the peak and the per-tick acceleration series.
#
# A BARE LaggedRig(tau=0.13, breakaway=70) has NO per-wheel gain
# mismatch (gain_left == gain_right == 1.0, its own default) and no
# wheelGain/wheelIntercept miscalibration (Config defaults, unset by
# this file's Rig) -- so a candidate with ki=0 "settles" on this model
# with near-zero steady-state error almost by construction: there is
# nothing modeled for an integrator to correct. That is a known gap,
# not an oversight -- `reports/tovez-wheel-velocity-pid-20260828.md`
# reports the robot's real per-wheel feedforward calibration is
# `wheel_gain_left 0.80` vs `wheel_gain_right 0.9567` (already what the
# firmware's own `correctedCommand()`/`wheelGain[]` is FOR, so most of
# that spread is presumably already compensated -- using it directly as
# an uncorrected physical mismatch would double-count the calibration).
# `_ASYM_GAIN_LEFT`/`_ASYM_GAIN_RIGHT` below inject a much smaller,
# explicitly HYPOTHESIZED residual (a plausible leftover after
# calibration, not itself measured) via LaggedRig's own
# `gain_left`/`gain_right` (ticket 010's per-wheel-gain lag model) --
# just enough that a ki=0 candidate's steady-state bias becomes visible
# and rankable, without pretending to know the REAL residual. Ticket
# 011 measures the real one; if it turns out much larger than this
# hypothesis, re-running this sweep with the measured value is the
# right way to extend it (this test's own docstring says so again).
_ASYM_GAIN_LEFT = 0.97   # [1] HYPOTHESIZED residual per-wheel mismatch,
_ASYM_GAIN_RIGHT = 1.02  # [1] NOT measured -- see module comment above.

_GAIN_RETUNE_LAG_S = 0.13  # [s] tovez's baked wheel lag, radio-robot-lib eafccd2
_GAIN_RETUNE_CRUISE = 200.0     # [mm/s] the sprint's own step-response scenario
_GAIN_RETUNE_DURATION_MS = 3000
_GAIN_RETUNE_PEAK_BOUND = 210.0      # [mm/s] this sprint's own G3-peak/G5 bar
_GAIN_RETUNE_ACCEL_BOUND = 600.0     # [mm/s^2] 1.5 x accel(400) -- same bar


def _wheels_v_step_response(motion_lib, kp, ki, kaff,
                            gain_left=1.0, gain_right=1.0):
    """Runs a `WHEELS_V 200 200` step against LaggedRig(tau=0.13) with
    the given candidate gains, returning (peak_speed, peak_accel,
    settle_left, settle_right) -- see the module comment above this
    function for what is and is not modeled. `peak_speed`/`peak_accel`
    are the worst of either wheel's own signed physical speed
    (`velocity_log_left`/`_right` -- the LAGGED, physically-realized
    speed, not the commanded reference); `settle_left`/`_right` are
    each wheel's speed at the end of the 3 s window, for ranking
    candidates by residual steady-state bias."""
    with LaggedRig(motion_lib, tau=_GAIN_RETUNE_LAG_S,
                   breakaway=_LAG_MODEL_BREAKAWAY,
                   gain_left=gain_left, gain_right=gain_right) as r:
        r.set_pid_gains(kp, ki, kaff)
        r.wheels_v(_GAIN_RETUNE_CRUISE, _GAIN_RETUNE_CRUISE,
                  _GAIN_RETUNE_DURATION_MS)
        n_ticks = int(_GAIN_RETUNE_DURATION_MS / TICK_MS)
        left, right = [], []
        for _ in range(n_ticks):
            r.tick()
            left.append(abs(r.velocity_log_left[-1]))
            right.append(abs(r.velocity_log_right[-1]))
        # Drop the pre-Hold artifact tick (see this function's own
        # docstring / the module comment's citation of the identical
        # drop in test_wheels_v_ramp_never_exceeds_accel_per_tick).
        left, right = left[1:], right[1:]
        dt = TICK_MS / 1000.0
        accel_left = max((b - a) / dt for a, b in zip(left, left[1:]))
        accel_right = max((b - a) / dt for a, b in zip(right, right[1:]))
        peak = max(max(left), max(right))
        peak_accel = max(accel_left, accel_right)
        return peak, peak_accel, left[-1], right[-1]


# Ranked candidates from this ticket's own sweep (a wider grid than
# this, kp in [0, 0.2] step 0.025, ki in [0, 3] step 0.5, kaff in
# [0, 0.1] step 0.05, run against `_wheels_v_step_response` with the
# hypothesized asymmetry above, ranked by steady-state bias then peak
# acceleration then peak speed) -- reproduce with the same grid to
# extend it. "today" is `shims.cpp`'s own tovez default, included for
# comparison, not a candidate. See this module's own docstring above
# for what "MODEL PREDICTION" means here.
_GAIN_RETUNE_CANDIDATES = [
    # label,        kp,    ki,   kaff
    ("today (kp=0, ki=6)", 0.0, 6.0, 0.0),
    ("candidate 1", 0.0, 0.5, 0.10),
    ("candidate 2", 0.075, 0.5, 0.05),
    ("candidate 3", 0.10, 0.0, 0.0),
]


def test_kernel_ff_i_gain_retune_candidates(motion_lib):
    """Sprint 031 ticket 006's own deliverable: prints and checks the
    ranked candidate table (see the module comment above this section
    for the full methodology and its citations). "today" is expected to
    OVERSHOOT the bar (reproducing, at model scale, the sprint's own
    hardware finding of 226-256 mm/s / up to 993 mm/s^2 -- this model's
    own "today" row is a PREDICTION that happens to land inside that
    measured range, not a re-measurement of it); every candidate is
    asserted to hold both this sprint's own bars, since narrowing the
    hardware search to sets the model has already ruled the peak/accel
    bars against is the whole point of running this sweep before ticket
    011's live session."""
    rows = []
    for label, kp, ki, kaff in _GAIN_RETUNE_CANDIDATES:
        peak, accel, settle_left, settle_right = _wheels_v_step_response(
            motion_lib, kp, ki, kaff,
            gain_left=_ASYM_GAIN_LEFT, gain_right=_ASYM_GAIN_RIGHT)
        rows.append((label, kp, ki, kaff, peak, accel, settle_left,
                     settle_right))

    print(f"\nsprint 031 ticket 006 -- MODEL PREDICTIONS, not measured "
          f"(LaggedRig tau={_GAIN_RETUNE_LAG_S}, hypothesized asymmetry "
          f"{_ASYM_GAIN_LEFT}/{_ASYM_GAIN_RIGHT}):")
    print(f"{'label':>22}{'kp':>7}{'ki':>7}{'kaff':>7}{'peak':>9}"
          f"{'accel':>9}{'settleL':>9}{'settleR':>9}")
    for label, kp, ki, kaff, peak, accel, sl, sr in rows:
        print(f"{label:>22}{kp:>7.3f}{ki:>7.2f}{kaff:>7.2f}{peak:>9.1f}"
              f"{accel:>9.1f}{sl:>9.1f}{sr:>9.1f}")

    today_label, _, _, _, today_peak, today_accel, _, _ = rows[0]
    assert today_peak > _GAIN_RETUNE_PEAK_BOUND, (
        f"{today_label}: model predicts peak {today_peak:.1f} mm/s -- "
        "expected it to reproduce the sprint's own overshoot finding, "
        "not clear the bar; if this model change made 'today' pass, the "
        "model no longer reproduces the problem this ticket is tuning"
    )

    for label, kp, ki, kaff, peak, accel, _sl, _sr in rows[1:]:
        assert peak <= _GAIN_RETUNE_PEAK_BOUND, (
            f"{label} (kp={kp}, ki={ki}, kaff={kaff}): model predicts "
            f"peak {peak:.1f} mm/s, above the {_GAIN_RETUNE_PEAK_BOUND} "
            "mm/s bar -- not a viable candidate for ticket 011"
        )
        assert accel <= _GAIN_RETUNE_ACCEL_BOUND, (
            f"{label} (kp={kp}, ki={ki}, kaff={kaff}): model predicts "
            f"peak accel {accel:.1f} mm/s^2, above the "
            f"{_GAIN_RETUNE_ACCEL_BOUND} mm/s^2 bar -- not a viable "
            "candidate for ticket 011"
        )


# ---- pivot 90 deg lands within 0.5 deg, at cruise 60/100/200 --------


@pytest.mark.parametrize("cruise", [60.0, 100.0, 200.0])
def test_pivot_90_lands_within_half_degree(motion_lib, cruise):
    with Rig(motion_lib) as r:
        r.move_x(0.0, _KPI / 2.0, cruise, 30000)
        n = r.run()
        assert n > 0
        heading_deg = r.h * 180.0 / _KPI
        assert heading_deg == pytest.approx(90.0, abs=0.5), (
            f"cruise {cruise}: pivot landed at {heading_deg:.3f} deg, "
            "more than 0.5 deg from the commanded 90 -- design S9.2's "
            "own acceptance bound"
        )


# ---- no negative duty on the forward wheel during a pivot -----------


@pytest.mark.parametrize("cruise", [60.0, 100.0, 200.0])
@pytest.mark.parametrize("rotation_sign", [1.0, -1.0])
def test_pivot_forward_wheel_never_goes_negative(
        motion_lib, cruise, rotation_sign):
    """Review MK-02 / design S4.5 K1's own concern (E3d in
    docs/code-review/2026-09-02/raw/profile_probe.cpp): the twist-hold
    servo correcting the SLAVE wheel during a pivot must never push it
    briefly negative -- for rotation > 0 (CCW) the RIGHT wheel is the
    one that should only ever move forward (motion_engine.cpp's
    beginSegment(): `right = distTarget + yawTarget`, `distTarget == 0`
    for a pure pivot, so `right` carries yawTarget's own sign); for
    rotation < 0 (CW) it is the LEFT wheel
    (`left = distTarget - yawTarget`). test_profile_probe_kernel.py
    already promotes this exact scenario (E3d, CCW only) through the
    REAL kernel as its own dedicated test; this generalizes the check
    to both pivot directions via the host-simulated ideal-wheel Rig."""
    with Rig(motion_lib) as r:
        r.move_x(0.0, rotation_sign * _KPI / 2.0, cruise, 30000)
        forward_log = r.duty_log_right if rotation_sign > 0 else r.duty_log_left
        n = r.run()
        assert n > 0
        min_forward_duty = min(forward_log) if forward_log else 0.0
        assert min_forward_duty >= -1e-3, (
            f"cruise {cruise}, rotation_sign {rotation_sign:+.0f}: the "
            f"forward wheel's own duty went as low as "
            f"{min_forward_duty:.4f} -- must never go negative during a "
            "pivot (review MK-02 / design S4.5 K1)"
        )


# ---- arc endpoint within 2 mm of the constant-curvature geometry ----


def test_arc_endpoint_matches_the_constant_radius_geometry(motion_lib):
    """A blended moveX() segment (design S4.3/S6.2) commands velocity
    and twist in a FIXED ratio for its whole duration
    (`velocity = (distTarget/dominant)*step.vCmd`,
    `twist = (yawTarget/dominant)*step.vCmd`, motion_engine.cpp) --
    so the path is a true constant-curvature arc of radius
    R = distance/rotation (trackWidth cancels out of the ratio exactly,
    see this test's own derivation below), landing at
    (R*sin(rotation), R*(1-cos(rotation))) in the body frame it
    started in. For distance=300mm, rotation=45deg (matches design
    S10.1's own bench gate G2, `MOVE_X 300 785 100 8000`): R =
    300/(pi/4) = 381.97 mm, endpoint (270.1, 111.9) -- design S9.2's
    own "arc endpoint within 2 mm" bound, checked here against ideal
    wheels (no camera, no bench slip) rather than G2's 5 mm bench
    tolerance."""
    distance, rotation, cruise = 300.0, _KPI / 4.0, 100.0
    radius = distance / rotation
    expected_x = radius * math.sin(rotation)
    expected_y = radius * (1.0 - math.cos(rotation))

    with Rig(motion_lib) as r:
        r.move_x(distance, rotation, cruise, 30000)
        n = r.run()
        assert n > 0
        assert r.x == pytest.approx(expected_x, abs=2.0), (
            f"arc endpoint x={r.x:.2f} vs expected {expected_x:.2f} mm"
        )
        assert r.y == pytest.approx(expected_y, abs=2.0), (
            f"arc endpoint y={r.y:.2f} vs expected {expected_y:.2f} mm"
        )
        heading_deg = r.h * 180.0 / _KPI
        assert heading_deg == pytest.approx(45.0, abs=0.5)


# ---- straight peak speed within 5% of cruise -------------------------


@pytest.mark.parametrize("cruise", [100.0, 200.0, 400.0])
def test_straight_peak_speed_within_5_percent_of_cruise(motion_lib, cruise):
    with Rig(motion_lib) as r:
        r.set_v_max(1000.0)  # nothing here should clip against vMax
        r.move_x(600.0, 0.0, cruise, 30000)
        n = r.run()
        assert n > 0
        peak = max(r.speed_log)
        assert peak <= cruise * 1.05, (
            f"cruise {cruise}: peak speed {peak:.1f} mm/s exceeds "
            f"cruise + 5% ({cruise * 1.05:.1f})"
        )


# ---- WHEELS_V never steps more than accel*dt above the floor --------


def test_wheels_v_ramp_never_exceeds_accel_per_tick(motion_lib):
    """`set wheel speeds` (WHEELS_V 200 200, design S9.2's own phrase
    for the block-palette verb wheelsV() implements): every tick's
    commanded speed rises by at most `accel * dt` over the previous one
    -- the shaper's own rate limit (velocity_shaper.cpp:
    `vUp = vPrev + lim.accel * dt`), never a bigger jump. Unlike a
    Segment (design S6.1's own "from rest the first command is the
    floor, a step, deliberately"), a continuous Hold's own `remain` is
    the unbounded `-1` sentinel (design S5), which GATES OFF the floor
    clamp entirely (velocity_shaper.cpp: `if (remain >= 0.0f && vNext <
    floor) ...`) -- so WHEELS_V ramps from 0 via plain `accel*dt` per
    tick, with no floor step at all; only the RATE LIMIT and the
    no-overshoot bound are this test's own claims."""
    with Rig(motion_lib) as r:
        accel = r.limits_accel()
        r.wheels_v(200.0, 200.0, 5000)

        speeds = []
        for _ in range(30):
            r.tick()
            speeds.append(r.speed_log[-1])
        # Rig.tick()'s very first call reads back whatever duty was
        # staged BEFORE this loop ran (design S6.5's lazy start: a
        # fresh Hold issues no drive() of its own at wheelsV() call
        # time) -- 0.0, a capture-loop artifact one tick before the
        # Hold's own first service() call ever runs, not a real
        # commanded speed. Drop it.
        speeds = speeds[1:]

        dt = TICK_MS / 1000.0
        for prev, nxt in zip(speeds, speeds[1:]):
            step = nxt - prev
            assert step <= accel * dt + 1.0, (
                f"WHEELS_V speed stepped by {step:.2f} mm/s in one tick, "
                f"more than accel*dt ({accel * dt:.2f}) -- speeds: {speeds}"
            )
        assert max(speeds) <= 210.0, (
            f"WHEELS_V(200, 200) overshot: peak {max(speeds):.1f} mm/s, "
            "above the 210 mm/s bound (design S10.1 gate G5)"
        )
        assert speeds[-1] == pytest.approx(200.0, abs=1.0), (
            f"WHEELS_V(200, 200) had not reached its steady-state 200 "
            f"mm/s by tick 29: {speeds[-1]:.1f}"
        )


# ---- design S7's own "after" measurement, recorded here -------------


def test_design_s7_after_measurement_600mm_cruise_200(motion_lib):
    """Records design S7's own "after" column claim for its
    representative case: "a 600 mm leg at cruise 200 is 3.36 s today
    and ~3.3 s after". MEASURED against THIS ticket's own compiled
    engine, host simulation, ideal wheels: this test IS the capture --
    rerun `uv run pytest tests/host/test_profile_probe.py::test_design_s7_after_measurement_600mm_cruise_200 -q -s`
    to reproduce the printed line below (measurement-citations.md: the
    artifact this citation names is this test file itself, at this
    ticket's own commit)."""
    with Rig(motion_lib) as r:
        r.set_v_max(1000.0)
        r.move_x(600.0, 0.0, 200.0, 30000)
        n = r.run()
        assert n > 0
        duration_s = n * (TICK_MS / 1000.0)
        travelled = math.hypot(r.x, r.y)
        print(
            f"\ndesign S7 after-measurement: 600mm @ cruise 200 -- "
            f"{n} ticks, {duration_s:.2f} s, travelled {travelled:.2f} mm, "
            f"peak {max(r.speed_log):.1f} mm/s"
        )
        # design S7's own claim: "~3.3 s after" (vs. "3.36 s today").
        assert duration_s == pytest.approx(3.3, abs=0.3), (
            f"measured {duration_s:.2f} s -- design S7's own 'after' "
            "column claims ~3.3 s for this leg; if this drifts, update "
            "S7's own table alongside this test, not just the assertion"
        )
        assert travelled == pytest.approx(600.0, abs=3.0)
