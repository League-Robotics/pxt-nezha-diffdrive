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

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

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


def _bind(lib):
    lib.meCreate.argtypes = []
    lib.meCreate.restype = ctypes.c_void_p
    lib.meDestroy.argtypes = [ctypes.c_void_p]
    lib.meDestroy.restype = None

    lib.meSetMaxDuty.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetMaxDuty.restype = None
    lib.meSetFullDutyVelocity.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetFullDutyVelocity.restype = None
    lib.meBegin.argtypes = [ctypes.c_void_p]
    lib.meBegin.restype = ctypes.c_int
    lib.meStep.argtypes = [ctypes.c_void_p]
    lib.meStep.restype = None
    lib.meClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.meClockSetNow.restype = None

    lib.meMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.meMotorLastStagedDuty.restype = ctypes.c_float
    lib.meMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.meMotorArmPosition.restype = None

    lib.meCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.meCountsPerMm.restype = ctypes.c_float
    lib.meEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.meEffectiveTrackWidth.restype = ctypes.c_float

    lib.meMoveX.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32,
    ]
    lib.meMoveX.restype = None
    lib.meWheelsV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.meWheelsV.restype = None
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meIsMoveActive.argtypes = [ctypes.c_void_p]
    lib.meIsMoveActive.restype = ctypes.c_int
    lib.meIsDriving.argtypes = [ctypes.c_void_p]
    lib.meIsDriving.restype = ctypes.c_int

    lib.meLimitsAccel.argtypes = [ctypes.c_void_p]
    lib.meLimitsAccel.restype = ctypes.c_float
    lib.meLimitsVFloor.argtypes = [ctypes.c_void_p]
    lib.meLimitsVFloor.restype = ctypes.c_float
    lib.meLimitsSetVMax.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetVMax.restype = None

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_profile_probe_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Rig:
    """Ideal-wheel host simulation of one MotionEngine: ticks the REAL
    service() at TICK_MS cadence, integrating each wheel's encoder
    position from the ACTUAL last-staged duty (no simulated physics,
    no lag), plus a small differential-drive odometry integrator
    (`odom()`) so (x, y, heading) endpoints -- not just dominant-axis
    distance -- can be checked. Mirrors docs/code-review/2026-09-02/
    raw/profile_probe.cpp's own Rig exactly, reimplemented here against
    the ctypes shim instead of a standalone C++ binary."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()
        self._lib.meSetMaxDuty(self._handle, 100.0)
        self._lib.meSetFullDutyVelocity(self._handle, FULL_DUTY_VELOCITY)
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
            self._pos[side] += self._duty[side] * FULL_DUTY_VELOCITY * (
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
        vl = self._duty[LEFT] * FULL_DUTY_VELOCITY / self._cpm
        vr = self._duty[RIGHT] * FULL_DUTY_VELOCITY / self._cpm
        self.speed_log.append(max(abs(vl), abs(vr)))
        self.duty_log_left.append(self._duty[LEFT])
        self.duty_log_right.append(self._duty[RIGHT])
        return active

    def run(self, max_ticks=4000):
        n = 0
        while n < max_ticks and self.is_move_active():
            self.tick()
            n += 1
        return n


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
