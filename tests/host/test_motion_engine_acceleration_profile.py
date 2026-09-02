"""tests/host/test_motion_engine_acceleration_profile.py -- the
cross-cutting acceptance proof, in host simulation, that the
constant-acceleration/deceleration kinematic core and the
distance-chosen default-cruise resolver actually deliver what the
underlying issue claims, end to end. No hardware is involved: this
file ticks the REAL `serviceMove()` (motion_engine.cpp, unmodified) at
a realistic 24 ms cadence and integrates each wheel's position from the
ACTUAL last-staged duty -- the same technique
`test_motion_engine_deadline_boundary.py`'s own `_drive_to_completion()`
and `captures/motion-profile-probe-20260901/profile_probe.py` both use,
reimplemented independently here (no cross-file import) so this file
has no coupling to either.

The single most important claim under test: measured deceleration
(mm/s^2) is CONSTANT across commanded cruise speeds once `aDecelMmS2_`
is set, where the shipped legacy formula demands a v^2-growing
deceleration instead (measured, before this work landed, from this
same compiled engine: 105/516/2449/5081 mm/s^2 at cruise 100/200/400/
600 -- captures/motion-profile-probe-20260901/measured.txt). Every test
below either exercises that claim directly or exercises one of the
three supporting claims the issue also makes: accel and decel shape
independently, `defaultCruiseForDistance()` never asks a leg to brake
harder than it was configured to, and a pure pivot resolves a real,
positive default speed instead of being refused.

Fit methodology, and why there are two of them:

  - `_fit_decel_two_point()` mirrors profile_probe.py's own crude
    90%-peak-to-end method exactly, so the legacy negative control
    below can be compared apples-to-apples against the issue's own
    recorded table.
  - `_fit_decel_regression()` is needed for the SHAPED-mode fits: this
    file deliberately sets `distTaper_` far wider than any of these
    legs actually need to brake within (see `_DIST_TAPER_TEST_COUNTS`'s
    own comment), which means a shaped trace's own braking tail is a
    short, genuinely-decelerating segment sitting after a long
    full-speed plateau -- the two-point method's "from 90% of peak"
    definition would instead average over most of that plateau and
    report a near-zero slope. This fit instead walks backward from the
    end of the trace, first collapsing any trailing FLAT run (the
    floor-clamped crawl every taper ends in, not part of the
    sqrt(remain) physics), then fitting a least-squares slope over just
    the segment that is still strictly decreasing tick to tick -- the
    actual v = sqrt(2*aDecelMmS2_*remain) segment.

Every capture below drops the FINAL sampled tick before any per-tick
decel analysis: that sample's own "velocity" is read back from
`motor_last_staged_duty()` AFTER `serviceMove()` has already declared
the move over, so for a move that completes by reaching its target
(rather than by exhausting max_ticks) it reflects the post-completion
command, not a real commanded braking event on the way there.

Run with::

    uv run pytest tests/host/test_motion_engine_acceleration_profile.py
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
    _TEST_DIR / "motion_engine_shim.cpp",
]

LEFT = 0
RIGHT = 1

# Same rationale as the other multi-tick host tests in this directory:
# large enough that every cruise below stays under the fullDutyVelocity
# rail EXCEPT the two high-cruise legacy points (400/600), which the
# issue's own captured table shows clip to the same ~394 mm/s peak --
# reproduced deliberately below as part of matching that table exactly.
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

# docs/design/design.md "Execution model (tick model)" -- the realistic
# control-cycle cadence every multi-tick host test in this directory
# uses.
TICK_MS = 24.0

_MAX_TICKS = 4000


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
    lib.meServiceMove.argtypes = [ctypes.c_void_p]
    lib.meServiceMove.restype = ctypes.c_int
    lib.meWrongWayCount.argtypes = [ctypes.c_void_p]
    lib.meWrongWayCount.restype = ctypes.c_uint32

    lib.meSetAAccelMmS2.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetAAccelMmS2.restype = None
    lib.meSetADecelMmS2.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetADecelMmS2.restype = None
    lib.meSetVMaxMmS.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetVMaxMmS.restype = None
    lib.meSetBrakeFrac.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetBrakeFrac.restype = None
    lib.meSetDistTaper.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meSetDistTaper.restype = None
    lib.meDefaultCruiseForDistance.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meDefaultCruiseForDistance.restype = ctypes.c_float
    lib.meDominantAxisTravelMm.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float,
    ]
    lib.meDominantAxisTravelMm.restype = ctypes.c_float

    return lib


@pytest.fixture(scope="session")
def motion_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_acceleration_profile_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    pared down to this file's own surface."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.meCreate()

    def close(self):
        self._lib.meDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def set_max_duty(self, v):
        self._lib.meSetMaxDuty(self._handle, v)

    def set_full_duty_velocity(self, v):
        self._lib.meSetFullDutyVelocity(self._handle, v)

    def begin(self):
        return self._lib.meBegin(self._handle)

    def step(self):
        self._lib.meStep(self._handle)

    def set_clock(self, now_us):
        self._lib.meClockSetNow(self._handle, now_us)

    def motor_last_staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._handle, side)

    def arm_motor_position_at(self, side, position_counts, sample_time_us):
        self._lib.meMotorArmPosition(
            self._handle, side, position_counts, sample_time_us)

    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.meEffectiveTrackWidth(self._handle)

    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def wrong_way_count(self):
        return self._lib.meWrongWayCount(self._handle)

    def set_a_accel_mm_s2(self, v):
        self._lib.meSetAAccelMmS2(self._handle, v)

    def set_a_decel_mm_s2(self, v):
        self._lib.meSetADecelMmS2(self._handle, v)

    def set_v_max_mm_s(self, v):
        self._lib.meSetVMaxMmS(self._handle, v)

    def set_brake_frac(self, v):
        self._lib.meSetBrakeFrac(self._handle, v)

    def set_dist_taper(self, v):
        self._lib.meSetDistTaper(self._handle, v)

    def default_cruise_for_distance(self, distance_mm):
        return self._lib.meDefaultCruiseForDistance(self._handle, distance_mm)

    def dominant_axis_travel_mm(self, distance_mm, rotation_rad):
        return self._lib.meDominantAxisTravelMm(
            self._handle, distance_mm, rotation_rad)


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == 0  # STATUS_OK
    return FULL_DUTY_VELOCITY


class _Trace:
    def __init__(self, rows, left_counts, right_counts, wrong_way_count,
                completed):
        self.rows = rows  # [(t_ms, mean_speed_mm_s, mean_pos_mm), ...]
        self.left_counts = left_counts
        self.right_counts = right_counts
        self.wrong_way_count = wrong_way_count
        self.completed = completed


def _run_move(motion_lib, distance_mm, rotation_rad, cruise_mm_s,
              timeout_ms=60000, max_ticks=_MAX_TICKS, configure=None):
    """Fresh engine; optional `configure(e)` callback runs BEFORE the
    move starts (setting aAccelMmS2_/aDecelMmS2_/vMaxMmS_/brakeFrac_/
    distTaper_ directly via MotionEngine's own C++ setters, already
    exported by motion_engine_shim.cpp -- no wire layer needed for
    this). Ticks the real serviceMove() at TICK_MS cadence, integrating
    each wheel's encoder position from the actual last-staged duty --
    see this file's own header comment for the full rationale. Returns
    a _Trace; `completed` is False if `max_ticks` was exhausted without
    the move going inactive, which a caller must treat as "did not
    land", not as a real completion."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        if configure:
            configure(e)
        cpm = e.counts_per_mm()
        e.set_clock(0)
        e.move_x(distance_mm, rotation_rad, cruise_mm_s, timeout_ms)
        pos = {LEFT: 0.0, RIGHT: 0.0}
        duty = {
            LEFT: e.motor_last_staged_duty(LEFT),
            RIGHT: e.motor_last_staged_duty(RIGHT),
        }
        t_ms = 0.0
        rows = []
        completed = False
        for _ in range(max_ticks):
            for side in (LEFT, RIGHT):
                pos[side] += duty[side] * fdv * (TICK_MS / 1000.0)
            t_ms += TICK_MS
            us = int(t_ms * 1000.0)
            e.arm_motor_position_at(LEFT, pos[LEFT], us)
            e.arm_motor_position_at(RIGHT, pos[RIGHT], us)
            e.set_clock(us)
            e.step()
            active = e.service_move()
            duty[LEFT] = e.motor_last_staged_duty(LEFT)
            duty[RIGHT] = e.motor_last_staged_duty(RIGHT)
            vl = duty[LEFT] * fdv
            vr = duty[RIGHT] * fdv
            rows.append((
                t_ms,
                0.5 * (vl + vr) / cpm,
                0.5 * (pos[LEFT] + pos[RIGHT]) / cpm,
            ))
            if not active:
                completed = True
                break
        return _Trace(rows, pos[LEFT], pos[RIGHT], e.wrong_way_count(),
                      completed)


# ---- fit methods ----------------------------------------------------


def _fit_decel_two_point(rows):
    """profile_probe.py's own crude method, reproduced exactly: from
    the last sample at/above 90% of peak, to the final sample. Used
    ONLY for the legacy negative control, so that control is comparable
    apples-to-apples against the issue's own recorded table."""
    t = [r[0] for r in rows]
    v = [r[1] for r in rows]
    pk = max(v)
    last90 = max(i for i, s in enumerate(v) if s >= 0.9 * pk)
    dt = (t[-1] - t[last90]) / 1000.0
    dec = (v[last90] - v[-1]) / dt if dt > 0 else float("inf")
    return dec, pk


def _fit_decel_regression(rows, drop_last=1, flat_eps=1e-3, eps=1e-6):
    """See this file's own header comment for why this differs from
    the two-point method above. Walks backward from the end (after
    dropping `drop_last` trailing sample(s) -- see header comment),
    first collapsing a trailing FLAT run (the floor-clamped crawl,
    values equal within `flat_eps`), then extending further back while
    STRICTLY decreasing (`eps` guards against float noise at an
    otherwise-flat sample being misread as a one-off decrease). Fits a
    least-squares slope of v(t) over just that strictly-decreasing
    tail. Returns (decel_mm_s2, peak_mm_s, n_samples_in_fit)."""
    usable = rows[:len(rows) - drop_last] if drop_last else rows
    v = [r[1] for r in usable]
    t = [r[0] for r in usable]
    pk = max(v)
    n_total = len(v)
    start = n_total - 1
    while start > 0 and abs(v[start - 1] - v[start]) < flat_eps:
        start -= 1
    while start > 0 and v[start - 1] > v[start] + eps:
        start -= 1
    seg_t = t[start:]
    seg_v = v[start:]
    n = len(seg_t)
    if n < 2:
        return 0.0, pk, n
    mean_t = sum(seg_t) / n
    mean_v = sum(seg_v) / n
    num = sum((ti - mean_t) * (vi - mean_v) for ti, vi in zip(seg_t, seg_v))
    den = sum((ti - mean_t) ** 2 for ti in seg_t)
    slope_per_ms = num / den if den > 0 else 0.0
    return -slope_per_ms * 1000.0, pk, n


def _worst_tick_decel(rows, drop_last=1):
    """Largest instantaneous (v[i]-v[i+1])/dt across consecutive
    samples, after dropping the trailing `drop_last` sample(s) -- see
    header comment. Only positive (velocity-dropping) deltas count."""
    usable = rows[:len(rows) - drop_last] if drop_last else rows
    worst = 0.0
    for (t0, v0, _), (t1, v1, _) in zip(usable, usable[1:]):
        dt = (t1 - t0) / 1000.0
        if dt <= 0:
            continue
        d = (v0 - v1) / dt
        if d > worst:
            worst = d
    return worst


def _legacy_shadow_straight_trace(distance_mm, cruise_mm_s, cpm,
                                  dist_taper_counts=400.0, ramp_ms=400.0,
                                  dist_floor=0.25, dist_margin=10.0,
                                  tick_ms=TICK_MS, max_ticks=_MAX_TICKS):
    """Independent Python re-derivation of the PRE-SPRINT straight-line
    taper/ramp formula (motion_engine.cpp's `aAccelMmS2_==aDecelMmS2_==
    0.0` branches: `axisScale = remain/distTaper_`,
    `ramp = elapsed/rampMs_`) -- this function never calls into the
    compiled engine. It reproduces the ONE-TICK COMMAND PIPELINE the
    real capture loop (`_run_move()` above) also exhibits: the encoder
    position advances each tick using the duty that was REALIZED by
    the previous tick's `step()` (starting at 0 -- nothing has step()'d
    yet when the move is first issued), while the recorded "velocity"
    for a tick is the duty `step()` just realized THIS tick from
    whatever `serviceMove()` staged one tick earlier (or moveX()'s own
    initial 0.25 scale, for the very first tick) -- so this function's
    own trace can be compared 1:1, tick-by-tick, against a real
    captured trace with no timing-model coupling to the C++ under test.
    Only valid for a cruise that never saturates the duty rail (see the
    caller): this omits the maxDuty clamp on purpose, since a
    representative legacy check does not need it.
    """
    dist_target = distance_mm * cpm
    vel_cmd = math.copysign(cruise_mm_s * cpm, dist_target) if dist_target else 0.0
    staged_scale = 0.25  # moveX()'s own initial arm
    applied_scale = 0.0  # nothing has step()'d yet
    mean_progress = 0.0
    t_ms = 0.0
    rows = []
    for _ in range(max_ticks):
        this_tick_scale = staged_scale  # realized by step() THIS tick
        mean_progress += vel_cmd * applied_scale * (tick_ms / 1000.0)
        t_ms += tick_ms
        q = vel_cmd * this_tick_scale
        remain = abs(dist_target) - abs(mean_progress)
        done = remain <= dist_margin
        rows.append((t_ms, q / cpm, mean_progress / cpm))
        if done:
            break
        taper_scale = remain / dist_taper_counts
        s = taper_scale if taper_scale < 1.0 else 1.0
        if s < dist_floor:
            s = dist_floor
        ramp = t_ms / ramp_ms
        if ramp < dist_floor:
            ramp = dist_floor
        if ramp < s:
            s = ramp
        if s > 1.0:
            s = 1.0
        staged_scale = s
        applied_scale = this_tick_scale
    return rows


# ---- AC: constant decel across cruise, vs. legacy's v^2 growth -------

# The issue's own probe MEASURED this from the compiled engine before
# this sprint's constant-a work landed:
# captures/motion-profile-probe-20260901/measured.txt (1000 mm leg).
_LEGACY_MEASURED_DECEL_MM_S2 = {100: 105.0, 200: 516.0, 400: 2449.0, 600: 5081.0}

_A_DECEL_TEST = 300.0  # [mm/s^2] arbitrary but well-resolved test value

# Deliberately far wider than any leg below needs to physically brake
# within (max needed: v=250 mm/s at aDecelMmS2_=300 needs ~104 mm ==
# ~1320 counts) -- see this file's own header comment on why a wide
# taper window does not distort the shaped-mode fits: the axis-scale
# formula clamps to 1.0 (full speed) until the leg is genuinely within
# braking distance, regardless of how much wider the configured window
# is, so this just guarantees the WINDOW itself is never what gates
# braking -- only the kinematics are under test.
_DIST_TAPER_TEST_COUNTS = 8000.0


def test_legacy_mode_shows_v_squared_growing_decel_across_cruise(motion_lib):
    """Negative control (both for this AC and for "legacy bit-for-bit"
    below): with aAccelMmS2_==aDecelMmS2_==0.0 (the shipped default,
    untouched by this file), a 1000 mm leg at cruise 100/200/400/600
    reproduces the issue's own measured v^2-growing demand within 5%,
    AND grows dramatically (600's demand is tens of times 100's) --
    confirming this file's own harness/fit reproduces the documented
    defect before checking that the new mode fixes it."""
    fits = {}
    for cruise in (100, 200, 400, 600):
        trace = _run_move(motion_lib, 1000.0, 0.0, float(cruise))
        assert trace.completed
        dec, _pk = _fit_decel_two_point(trace.rows)
        fits[cruise] = dec

    for cruise, expected in _LEGACY_MEASURED_DECEL_MM_S2.items():
        assert fits[cruise] == pytest.approx(expected, rel=0.05)

    assert fits[600] / fits[100] > 20.0  # explosive growth, not constant


def test_shaped_mode_decel_is_constant_across_cruise(motion_lib):
    """The central claim: with aDecelMmS2_ set, measured deceleration
    stays within 20% of the configured value across cruise 100/200/
    400/600 on the SAME 1000 mm leg the legacy negative control above
    uses -- in stark contrast to that control's >20x growth."""

    def configure(e):
        e.set_a_decel_mm_s2(_A_DECEL_TEST)
        e.set_dist_taper(_DIST_TAPER_TEST_COUNTS)

    fits = {}
    for cruise in (100, 200, 400, 600):
        trace = _run_move(motion_lib, 1000.0, 0.0, float(cruise),
                          configure=configure)
        assert trace.completed
        dec, _pk, n = _fit_decel_regression(trace.rows)
        assert n >= 3, (
            f"cruise {cruise}: decel fit had only {n} samples, too few "
            "to trust"
        )
        fits[cruise] = dec

    for cruise, dec in fits.items():
        assert dec == pytest.approx(_A_DECEL_TEST, rel=0.20), (
            f"cruise {cruise}: fit decel {dec:.1f} mm/s^2 vs configured "
            f"{_A_DECEL_TEST} -- fits by cruise: {fits}"
        )

    # The qualitative contrast the AC asks for: nowhere near the
    # legacy mode's >20x spread across the same cruise sweep.
    assert max(fits.values()) / min(fits.values()) < 1.5


def test_cruise_400_decel_window_tracks_kinematics_at_default_dist_taper(
        motion_lib):
    """Regression guard for the dist_taper-ceiling defect: at cruise
    400 with `distTaper_` left at its shipped DEFAULT (400 counts,
    ~31.5 mm -- no `set_dist_taper()` call anywhere in this test), the
    braking window must still track `v^2/(2*aDecelMmS2_)` instead of
    being capped by that legacy default. Before the fix, the dist
    axis's shaped-mode branch only engaged once `remain <= distTaper_`,
    so at cruise 400 (needed window ~267 mm, 8.5x the 31.5 mm default)
    the move never entered the constant-a solve at all and stopped in
    a single control tick -- MEASURED on gopiv,
    captures/gopiv-profile-sweep-20260901/sweep_gopiv_shaped.json.
    This test uses the same regression-fit technique as
    test_shaped_mode_decel_is_constant_across_cruise above, but
    deliberately omits that test's own `set_dist_taper(8000)` override
    -- the whole point here is the engine's real, shipped default."""
    cruise = 400.0

    def configure(e):
        e.set_a_decel_mm_s2(_A_DECEL_TEST)
        # distTaper_ deliberately left at its engine default (400
        # counts) -- no set_dist_taper() call. That default is smaller
        # than this cruise's own v^2/(2a) window, which is exactly the
        # defect this test guards against reappearing.

    trace = _run_move(motion_lib, 1000.0, 0.0, cruise, configure=configure)
    assert trace.completed

    dec, pk, n = _fit_decel_regression(trace.rows)
    assert n >= 3, (
        f"decel fit had only {n} samples, too few to trust -- at the "
        "old distTaper_-ceiling defect this collapsed to a single "
        "control tick at cruise 400"
    )
    assert dec == pytest.approx(_A_DECEL_TEST, rel=0.20), (
        f"fit decel {dec:.1f} mm/s^2 vs configured {_A_DECEL_TEST} at "
        f"cruise {cruise} mm/s with distTaper_ at its shipped default -- "
        "if this drifts back toward a v^2-growing legacy-shaped demand, "
        "the dist axis's shaped-mode gate has regressed to depending on "
        "distTaper_ again."
    )

    # Directly check the braking window itself, in mm, against the
    # kinematic prediction v^2/(2a) -- using the MEASURED peak speed
    # `pk` (this cruise clips against the duty rail, per this file's
    # own FULL_DUTY_VELOCITY comment, so the achieved plateau is a bit
    # under the nominal 400 mm/s cruise), not just the fitted decel
    # rate above.
    usable = trace.rows[:-1]  # drop the post-completion final sample
    v = [r[1] for r in usable]
    p = [r[2] for r in usable]
    i_cruise = max(i for i, s in enumerate(v) if s >= 0.99 * pk)
    measured_window_mm = p[-1] - p[i_cruise]
    predicted_window_mm = (pk * pk) / (2.0 * _A_DECEL_TEST)

    assert measured_window_mm == pytest.approx(
        predicted_window_mm, rel=0.25), (
        f"measured braking window {measured_window_mm:.1f} mm vs the "
        f"kinematic prediction v^2/(2a) = {predicted_window_mm:.1f} mm "
        f"(peak speed {pk:.1f} mm/s, aDecelMmS2_={_A_DECEL_TEST}) -- "
        "distTaper_'s shipped default (400 counts, ~31.5 mm) must no "
        "longer cap this window."
    )
    # Explicitly rule out the pre-fix defect shape: a window anywhere
    # near distTaper_'s own ~31.5 mm default would mean the fixed-counts
    # ceiling gate is back.
    assert measured_window_mm > 100.0, (
        f"measured braking window {measured_window_mm:.1f} mm is close "
        "to distTaper_'s old ~31.5 mm ceiling -- the dist axis's "
        "shaped-mode gate looks like it has regressed to depending on "
        "distTaper_ instead of the kinematics."
    )


# ---- AC: accel and decel are independently settable/observable ------


def test_varying_accel_alone_leaves_measured_decel_unchanged(motion_lib):
    """Fix aDecelMmS2_, vary aAccelMmS2_ across two well-separated
    values: the measured ACCEL phase must track each configured value,
    while the measured DECEL phase barely moves at all."""
    cruise = 350.0  # well under the duty rail (~394 mm/s) -- no clipping

    def configure(a_accel):
        def _c(e):
            e.set_a_accel_mm_s2(a_accel)
            e.set_a_decel_mm_s2(_A_DECEL_TEST)
            e.set_dist_taper(_DIST_TAPER_TEST_COUNTS)
        return _c

    results = {}
    for a_accel in (300.0, 900.0):
        trace = _run_move(motion_lib, 1000.0, 0.0, cruise,
                          configure=configure(a_accel))
        assert trace.completed
        v = [r[1] for r in trace.rows]
        t = [r[0] for r in trace.rows]
        pk = max(v)
        i_pk = v.index(pk)
        accel_fit = (v[i_pk] - v[0]) / max((t[i_pk] - t[0]) / 1000.0, 1e-3)
        decel_fit, _pk, _n = _fit_decel_regression(trace.rows)
        results[a_accel] = (accel_fit, decel_fit)

    for a_accel, (accel_fit, _decel_fit) in results.items():
        assert accel_fit == pytest.approx(a_accel, rel=0.20)

    decel_300, decel_900 = results[300.0][1], results[900.0][1]
    assert decel_300 == pytest.approx(_A_DECEL_TEST, rel=0.20)
    assert decel_900 == pytest.approx(_A_DECEL_TEST, rel=0.20)
    # The independence claim itself: changing accel by 3x must not
    # meaningfully move the measured decel.
    assert abs(decel_300 - decel_900) < 0.15 * _A_DECEL_TEST


def test_varying_decel_alone_leaves_measured_accel_unchanged(motion_lib):
    """Fix aAccelMmS2_, vary aDecelMmS2_ across two well-separated
    values: the measured DECEL phase must track each configured value,
    while the measured ACCEL phase barely moves at all."""
    cruise = 350.0
    a_accel_fixed = 500.0

    def configure(a_decel):
        def _c(e):
            e.set_a_accel_mm_s2(a_accel_fixed)
            e.set_a_decel_mm_s2(a_decel)
            e.set_dist_taper(_DIST_TAPER_TEST_COUNTS)
        return _c

    results = {}
    for a_decel in (150.0, 450.0):
        trace = _run_move(motion_lib, 1000.0, 0.0, cruise,
                          configure=configure(a_decel))
        assert trace.completed
        v = [r[1] for r in trace.rows]
        t = [r[0] for r in trace.rows]
        pk = max(v)
        i_pk = v.index(pk)
        accel_fit = (v[i_pk] - v[0]) / max((t[i_pk] - t[0]) / 1000.0, 1e-3)
        decel_fit, _pk, n = _fit_decel_regression(trace.rows)
        assert n >= 3
        results[a_decel] = (accel_fit, decel_fit)

    for a_decel, (_accel_fit, decel_fit) in results.items():
        assert decel_fit == pytest.approx(a_decel, rel=0.20)

    accel_150, accel_450 = results[150.0][0], results[450.0][0]
    assert accel_150 == pytest.approx(a_accel_fixed, rel=0.05)
    assert accel_450 == pytest.approx(a_accel_fixed, rel=0.05)
    assert abs(accel_150 - accel_450) < 0.05 * a_accel_fixed


# ---- AC: v_default(D) monotonicity, v_max ceiling, and braking safety


def test_v_default_monotonic_and_capped_at_v_max(motion_lib):
    """Formula-level check tying this file's own D range (reused by
    the drive-simulation safety test below) to the resolver: resolved
    speed is non-decreasing in D and never exceeds vMaxMmS_. (The
    resolver's own exhaustive proof already lives in
    test_motion_engine_default_cruise_for_distance.py -- this is a
    narrower, scenario-linked check, not a duplicate of that file.)"""
    v_max = 250.0
    with Engine(motion_lib) as e:
        e.set_a_decel_mm_s2(_A_DECEL_TEST)
        e.set_brake_frac(0.375)
        e.set_v_max_mm_s(v_max)

        distances = (20.0, 50.0, 100.0, 300.0, 800.0, 2000.0, 5000.0)
        speeds = [e.default_cruise_for_distance(d) for d in distances]
        for prev, nxt in zip(speeds, speeds[1:]):
            assert nxt >= prev - 1e-6
        for s in speeds:
            assert s <= v_max + 1e-6
        assert speeds[-1] == pytest.approx(v_max)  # 5000 mm clips at the ceiling


def test_v_default_never_demands_harder_braking_than_configured(motion_lib):
    """SUC-003's whole point, proven by actually driving the resolved
    speed rather than trusting the formula alone: for a range of leg
    distances D, resolve cruise = defaultCruiseForDistance(D), drive
    that leg to completion, and confirm the leg's own measured
    per-tick deceleration never dramatically exceeds aDecelMmS2_. A
    1.5x margin is used, not 1.0x: a first-order (explicit-Euler)
    simulation of a v=sqrt(2*a*remain) curve, sampled every 24 ms,
    systematically over-estimates the instantaneous slope near the low
    end of the curve (the "knee" close to the floor speed) -- measured
    up to ~1.31x here even down at D=20 mm, never higher. This is a
    property of the DISCRETE SIMULATION's own resolution, not of the
    engine: see this file's header comment on why the final tick is
    dropped before this check."""

    def configure(e):
        e.set_a_decel_mm_s2(_A_DECEL_TEST)
        e.set_brake_frac(0.375)
        e.set_v_max_mm_s(250.0)
        e.set_dist_taper(_DIST_TAPER_TEST_COUNTS)

    for d in (20.0, 50.0, 100.0, 300.0, 800.0, 2000.0, 5000.0):
        with Engine(motion_lib) as e:
            _ready(e)
            configure(e)
            v_default = e.default_cruise_for_distance(d)
        assert v_default > 0.0

        trace = _run_move(motion_lib, d, 0.0, v_default, configure=configure)
        assert trace.completed
        worst = _worst_tick_decel(trace.rows, drop_last=1)
        assert worst <= _A_DECEL_TEST * 1.5, (
            f"D={d}: worst per-tick decel {worst:.1f} mm/s^2 exceeds "
            f"1.5x the configured {_A_DECEL_TEST} mm/s^2"
        )


# ---- AC: pure pivots resolve a sane default and are not refused -----


def test_pure_pivot_default_cruise_completes_and_is_not_refused(motion_lib):
    """The real defect ticket 002 fixed, guarded here end to end (not
    just at the resolver level -- test_motion_engine_default_cruise_
    for_distance.py already covers that): a pure pivot (distance == 0,
    rotation != 0) must resolve a real, positive default cruise from
    its own wheel travel and must actually DRIVE to completion when
    that default is used as the commanded cruise -- not stall, not get
    refused as a zero-magnitude/zero-cruise no-op."""
    rotation_rad = math.radians(90.0)

    def configure(e):
        e.set_a_decel_mm_s2(_A_DECEL_TEST)
        e.set_brake_frac(0.375)
        e.set_v_max_mm_s(250.0)
        e.set_dist_taper(_DIST_TAPER_TEST_COUNTS)

    with Engine(motion_lib) as e:
        _ready(e)
        configure(e)
        b = e.effective_track_width()
        cpm = e.counts_per_mm()
        d = e.dominant_axis_travel_mm(0.0, rotation_rad)
        v_default = e.default_cruise_for_distance(d)

    assert d > 0.0  # the defect: this used to resolve to 0 for a pivot
    assert v_default > 0.0  # ... which used to refuse the whole move

    trace = _run_move(motion_lib, 0.0, rotation_rad, v_default,
                      configure=configure)

    assert trace.completed  # reached the target, not deadline/max_ticks
    assert trace.wrong_way_count == 0

    expected_yaw_counts = rotation_rad * 0.5 * b * cpm
    measured_yaw_counts = 0.5 * (trace.right_counts - trace.left_counts)
    measured_mean_counts = 0.5 * (trace.right_counts + trace.left_counts)
    # Same margin rationale as test_motion_engine_deadline_boundary.py's
    # own _assert_reached_target(): one tick's worth of floor-rate
    # crawl can overshoot the engine's own completion margin slightly.
    assert measured_yaw_counts == pytest.approx(expected_yaw_counts, abs=40.0)
    assert measured_mean_counts == pytest.approx(0.0, abs=40.0)  # no translation


# ---- AC: legacy mode is bit-for-bit unchanged ------------------------


def test_legacy_mode_matches_independent_reformulation_tick_by_tick(
        motion_lib):
    """The "legacy bit-for-bit" acceptance bar: a representative move
    (600 mm at 200 mm/s -- production tuning, chosen specifically
    because it stays under the duty rail so the independent
    reformulation below does not need to model the maxDuty clamp) in
    legacy mode (aAccelMmS2_==aDecelMmS2_==0.0, untouched by this file)
    must match `_legacy_shadow_straight_trace()`'s own from-scratch
    re-derivation of the pre-sprint `remain/distTaper_` +
    `elapsed/rampMs_` formula, sample for sample, to floating-point
    tolerance -- not the same code path re-run, an independently
    written one."""
    trace = _run_move(motion_lib, 600.0, 0.0, 200.0)
    assert trace.completed

    with Engine(motion_lib) as e:
        cpm = _ready(e) and e.counts_per_mm()

    shadow_rows = _legacy_shadow_straight_trace(600.0, 200.0, cpm)

    assert len(shadow_rows) == len(trace.rows)
    for (t_r, v_r, p_r), (t_s, v_s, p_s) in zip(trace.rows, shadow_rows):
        assert t_r == pytest.approx(t_s, abs=1e-6)
        assert v_r == pytest.approx(v_s, abs=1e-2)
        assert p_r == pytest.approx(p_s, abs=1e-2)
