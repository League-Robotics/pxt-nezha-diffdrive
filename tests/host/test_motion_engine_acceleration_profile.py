"""tests/host/test_motion_engine_acceleration_profile.py -- the
cross-cutting acceptance proof, in host simulation, that the unified
`VelocityShaper`'s constant-acceleration/deceleration kinematic core
(design docs/design/motion-profile-unification.md S4.2/S6.1) and the
distance-chosen default-cruise resolver (S8) actually deliver what the
issue that originally motivated this file claimed, end to end. No
hardware is involved: this file ticks the REAL `MotionEngine::service()`
(motion_engine.cpp, unmodified) at a realistic 24 ms cadence and
integrates each wheel's position from the ACTUAL last-staged duty -- the
same technique test_motion_engine_deadline_boundary.py's own
`_drive_to_completion()` uses, reimplemented independently here (no
cross-file import) so this file has no coupling to either.

REWRITTEN this ticket (design S9: "pins the algorithm this design
removes"). The pre-unification engine had a LEGACY/SHAPED toggle
(`aAccelMmS2_ == 0.0` selected a `remain/distTaper_` + `elapsed/rampMs_`
formula instead of constant-a kinematics) plus `brakeFrac_`,
`distTaper_`/`yawTaper_`, `distFloor_`/`turnFloor_`, and
`profileExitMmS_` -- thirteen fields this ticket deletes outright
(motion_engine.h's own field list, pre-ticket). None of that survives:
`VelocityShaper::advance()` (velocity_shaper.h/.cpp, ticket 002) is the
ONLY shaping code left, it runs unconditionally, and its braking window
is always the kinematic `v^2/(2*decel)`, never a fixed-count taper. So
the tests this file used to carry for the legacy branch, the
distTaper_-ceiling regression, the yawTaper_-vs-kinematics split, and
profileExitMmS_'s glide-vs-floor behaviour are gone along with the code
they pinned -- there is no longer a second code path, or a fixed-count
window, or a profile-exit toggle, for any of them to guard. What
remains, updated for the new engine's own knobs
(`limits().setAccel()`/`setDecel()`/`setVMax()`, exposed here as
`meLimitsSetAccel`/`meLimitsSetDecel`/`meLimitsSetVMax`):

  1. The central claim, now unconditional: measured deceleration
     (mm/s^2) is CONSTANT across commanded cruise speeds once `decel`
     is configured (`test_decel_is_constant_across_cruise_speeds`) --
     where the pre-unification legacy formula demanded a v^2-growing
     deceleration instead (measured, before that work landed, from this
     same compiled engine: 105/516/2449/5081 mm/s^2 at cruise
     100/200/400/600, captures/motion-profile-probe-20260901/
     measured.txt -- restated here as historical context, not
     reproducible any more: `decel` can no longer be driven to 0.0 --
     motion_limits.h's "positive, else keep" setter -- so that v^2-growing
     branch is not just unused, it is unreachable).
  2. accel and decel still shape independently.
  3. `defaultCruiseForDistance()` still never asks a leg to brake harder
     than it was configured to.
  4. A pure pivot still resolves a real, positive default speed instead
     of being refused, driven end to end (not just at the resolver
     level -- test_motion_engine_default_cruise_for_distance.py already
     covers that).

Fit methodology: `_fit_decel_regression()` walks backward from the end
of a trace, first collapsing any trailing FLAT run (the floor-clamped
crawl every taper ends in, not part of the sqrt(remain) physics), then
fitting a least-squares slope over just the segment that is still
strictly decreasing tick to tick -- the actual v = sqrt(2*decel*remain)
segment. (The old two-point "from 90% of peak" fitter this file also
carried is gone with the legacy negative control it existed to match
apples-to-apples.)

Every capture below drops the FINAL sampled tick before any per-tick
decel analysis: that sample's own "velocity" is read back from
`motor_last_staged_duty()` AFTER `service()` has already declared the
move over, so for a move that completes by reaching its target (rather
than by exhausting max_ticks) it reflects the post-completion command,
not a real commanded braking event on the way there.

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
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_shim.cpp",
]

LEFT = 0
RIGHT = 1

# Same rationale as the other multi-tick host tests in this directory:
# large enough that every cruise used below (capped at 350 mm/s) stays
# well under the fullDutyVelocity rail, so no assertion here is
# secretly checking a clamped value.
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

    lib.meLimitsSetAccel.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetAccel.restype = None
    lib.meLimitsSetDecel.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetDecel.restype = None
    lib.meLimitsSetVMax.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.meLimitsSetVMax.restype = None
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

    def set_accel(self, v):
        self._lib.meLimitsSetAccel(self._handle, v)

    def set_decel(self, v):
        self._lib.meLimitsSetDecel(self._handle, v)

    def set_v_max(self, v):
        self._lib.meLimitsSetVMax(self._handle, v)

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
    move starts (setting limits() directly via MotionEngine's own C++
    setters, already exported by motion_engine_shim.cpp -- no wire
    layer needed for this). Ticks the real service() at TICK_MS
    cadence, integrating each wheel's encoder position from the actual
    last-staged duty -- see this file's own header comment for the full
    rationale. Returns a _Trace; `completed` is False if `max_ticks`
    was exhausted without the move going inactive, which a caller must
    treat as "did not land", not as a real completion."""
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


def _fit_decel_regression(rows, drop_last=1, flat_eps=1e-3, eps=1e-6):
    """See this file's own header comment for the rationale. Walks
    backward from the end (after dropping `drop_last` trailing
    sample(s)), first locating a trailing FLAT run (the floor-clamped
    crawl, values equal within `flat_eps`) and EXCLUDING every repeat of
    it from the fit -- only the single sample where the decreasing run
    first reaches the floor stays in -- then extending the segment's own
    start further back while STRICTLY decreasing (`eps` guards against
    float noise at an otherwise-flat sample being misread as a one-off
    decrease). Fits a least-squares slope of v(t) over just that
    strictly-decreasing tail, with the floor's own flat repeats excluded.
    A fixed `v_floor` (this engine's own floor, unlike the old
    fraction-of-cruise one) leaves less headroom above the floor at a
    LOW cruise, so the floor-clamped tail can be a large fraction of a
    short braking window -- letting it back into the regression (as an
    earlier version of this helper did, by slicing to the end of `rows`
    instead of to this boundary) drags the fitted slope toward 0.
    Returns (decel_mm_s2, peak_mm_s, n_samples_in_fit)."""
    usable = rows[:len(rows) - drop_last] if drop_last else rows
    v = [r[1] for r in usable]
    t = [r[0] for r in usable]
    pk = max(v)
    n_total = len(v)
    start = n_total - 1
    while start > 0 and abs(v[start - 1] - v[start]) < flat_eps:
        start -= 1
    # `start` now marks the FIRST sample of the trailing flat run (the
    # floor-clamped crawl) -- exclude every REPEAT of it from the fit
    # itself, not just from the search for where the decreasing run
    # starts. The two-step walk above only used the flat run to find
    # this boundary; the segment sliced below used to run all the way
    # to the end of `usable`, silently pulling the whole flat tail back
    # into the least-squares fit and dragging its slope toward 0 --
    # exactly the discrepancy a low cruise close to `v_floor` (a small
    # decel headroom, a long floor crawl) exposes. `end` pins the
    # segment to stop at the one sample where the decreasing run
    # actually reaches the floor.
    end = start + 1
    while start > 0 and v[start - 1] > v[start] + eps:
        start -= 1
    seg_t = t[start:end]
    seg_v = v[start:end]
    n = len(seg_t)
    if n < 2:
        return 0.0, pk, n
    mean_t = sum(seg_t) / n
    mean_v = sum(seg_v) / n
    num = sum((ti - mean_t) * (vi - mean_v) for ti, vi in zip(seg_t, seg_v))
    den = sum((ti - mean_t) ** 2 for ti in seg_t)
    slope_per_ms = num / den if den > 0 else 0.0
    return -slope_per_ms * 1000.0, pk, n


def _fit_accel(rows):
    """(peak - floor) / (t_peak - t_floor) mm/s^2, the ramp's own slope
    from the shaper's first real command up to peak. `rows[0]` is a
    lazy-start ARTIFACT of `_run_move()`'s own capture loop (design
    S6.5): its `v == 0.0` at t == TICK_MS reflects nothing having been
    staged yet before the loop's first iteration, one tick before the
    segment's own first service() call ever runs -- not a real
    commanded speed. `rows[1]` is the segment's own genuine first
    command (the floor, design S6.1's "a step, deliberately"), so the
    ramp's fit baseline starts there, not at `rows[0]`."""
    v = [r[1] for r in rows]
    t = [r[0] for r in rows]
    pk = max(v)
    i_pk = v.index(pk)
    return (v[i_pk] - v[1]) / max((t[i_pk] - t[1]) / 1000.0, 1e-3)


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


# ---- AC: constant decel across cruise -------------------------------

_DECEL_TEST = 300.0  # [mm/s^2] arbitrary but well-resolved test value


def test_decel_is_constant_across_cruise_speeds(motion_lib):
    """The central claim, now unconditional (there is no more legacy
    branch to opt out of it): with `decel` configured, measured
    deceleration on a 1000 mm leg stays within 20% of the configured
    value across cruise 100/200/350 -- in stark contrast to the
    pre-unification legacy formula's v^2-growing demand this file used
    to reproduce as a negative control (105/516/2449/5081 mm/s^2 at
    cruise 100/200/400/600, captures/motion-profile-probe-20260901/
    measured.txt). That control cannot be reproduced against this
    engine any more: `decel` cannot be driven to 0.0 through the public
    setter (motion_limits.h's "positive, else keep" pattern), so the
    branch that demanded it is not just unused, it is unreachable."""

    def configure(e):
        e.set_decel(_DECEL_TEST)
        e.set_v_max(1000.0)  # nothing here should clip against vMax

    fits = {}
    for cruise in (100.0, 200.0, 350.0):
        trace = _run_move(motion_lib, 1000.0, 0.0, cruise,
                          configure=configure)
        assert trace.completed
        dec, _pk, n = _fit_decel_regression(trace.rows)
        assert n >= 3, (
            f"cruise {cruise}: decel fit had only {n} samples, too few "
            "to trust"
        )
        fits[cruise] = dec

    for cruise, dec in fits.items():
        assert dec == pytest.approx(_DECEL_TEST, rel=0.20), (
            f"cruise {cruise}: fit decel {dec:.1f} mm/s^2 vs configured "
            f"{_DECEL_TEST} -- fits by cruise: {fits}"
        )

    # The qualitative contrast the AC asks for: nowhere near the old
    # legacy mode's >20x spread across the same cruise sweep.
    assert max(fits.values()) / min(fits.values()) < 1.5


# ---- AC: accel and decel are independently settable/observable ------


def test_varying_accel_alone_leaves_measured_decel_unchanged(motion_lib):
    """Fix decel, vary accel across two well-separated values: the
    measured ACCEL phase must track each configured value, while the
    measured DECEL phase barely moves at all."""
    cruise = 350.0  # well under the duty rail -- no clipping

    def configure(accel):
        def _c(e):
            e.set_accel(accel)
            e.set_decel(_DECEL_TEST)
            e.set_v_max(1000.0)
        return _c

    results = {}
    for accel in (300.0, 900.0):
        trace = _run_move(motion_lib, 1000.0, 0.0, cruise,
                          configure=configure(accel))
        assert trace.completed
        accel_fit = _fit_accel(trace.rows)
        decel_fit, _pk, _n = _fit_decel_regression(trace.rows)
        results[accel] = (accel_fit, decel_fit)

    for accel, (accel_fit, _decel_fit) in results.items():
        assert accel_fit == pytest.approx(accel, rel=0.20)

    decel_300, decel_900 = results[300.0][1], results[900.0][1]
    assert decel_300 == pytest.approx(_DECEL_TEST, rel=0.20)
    assert decel_900 == pytest.approx(_DECEL_TEST, rel=0.20)
    # The independence claim itself: changing accel by 3x must not
    # meaningfully move the measured decel.
    assert abs(decel_300 - decel_900) < 0.15 * _DECEL_TEST


def test_varying_decel_alone_leaves_measured_accel_unchanged(motion_lib):
    """Fix accel, vary decel across two well-separated values: the
    measured DECEL phase must track each configured value, while the
    measured ACCEL phase barely moves at all."""
    cruise = 350.0
    accel_fixed = 500.0

    def configure(decel):
        def _c(e):
            e.set_accel(accel_fixed)
            e.set_decel(decel)
            e.set_v_max(1000.0)
        return _c

    results = {}
    for decel in (150.0, 450.0):
        trace = _run_move(motion_lib, 1000.0, 0.0, cruise,
                          configure=configure(decel))
        assert trace.completed
        accel_fit = _fit_accel(trace.rows)
        decel_fit, _pk, n = _fit_decel_regression(trace.rows)
        assert n >= 3
        results[decel] = (accel_fit, decel_fit)

    for decel, (_accel_fit, decel_fit) in results.items():
        assert decel_fit == pytest.approx(decel, rel=0.20)

    accel_150, accel_450 = results[150.0][0], results[450.0][0]
    assert accel_150 == pytest.approx(accel_fixed, rel=0.05)
    assert accel_450 == pytest.approx(accel_fixed, rel=0.05)
    assert abs(accel_150 - accel_450) < 0.05 * accel_fixed


# ---- AC: v_default(D) monotonicity, v_max ceiling, and braking safety


def test_v_default_monotonic_and_capped_at_v_max(motion_lib):
    """Formula-level check tying this file's own D range (reused by
    the drive-simulation safety test below) to the resolver: resolved
    speed is non-decreasing in D and never exceeds vMax. (The
    resolver's own exhaustive proof already lives in
    test_motion_engine_default_cruise_for_distance.py -- this is a
    narrower, scenario-linked check, not a duplicate of that file.)"""
    v_max = 250.0
    with Engine(motion_lib) as e:
        e.set_decel(_DECEL_TEST)
        e.set_v_max(v_max)

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
    that leg to completion, and confirm the leg's own measured per-tick
    deceleration never dramatically exceeds `decel`. A 1.5x margin is
    used, not 1.0x: a first-order (explicit-Euler) simulation of a
    v=sqrt(2*decel*remain) curve, sampled every 24 ms, systematically
    over-estimates the instantaneous slope near the low end of the
    curve (the "knee" close to the floor speed) -- measured up to
    ~1.31x here even down at D=20 mm, never higher. This is a property
    of the DISCRETE SIMULATION's own resolution, not of the engine: see
    this file's header comment on why the final tick is dropped before
    this check."""

    def configure(e):
        e.set_decel(_DECEL_TEST)
        e.set_v_max(250.0)

    for d in (20.0, 50.0, 100.0, 300.0, 800.0, 2000.0, 5000.0):
        with Engine(motion_lib) as e:
            _ready(e)
            configure(e)
            v_default = e.default_cruise_for_distance(d)
        assert v_default > 0.0

        trace = _run_move(motion_lib, d, 0.0, v_default, configure=configure)
        assert trace.completed
        worst = _worst_tick_decel(trace.rows, drop_last=1)
        assert worst <= _DECEL_TEST * 1.5, (
            f"D={d}: worst per-tick decel {worst:.1f} mm/s^2 exceeds "
            f"1.5x the configured {_DECEL_TEST} mm/s^2"
        )


# ---- AC: pure pivots resolve a sane default and are not refused -----


def test_pure_pivot_default_cruise_completes_and_is_not_refused(motion_lib):
    """A pure pivot (distance == 0, rotation != 0) must resolve a real,
    positive default cruise from its own wheel travel and must actually
    DRIVE to completion when that default is used as the commanded
    cruise -- not stall, not get refused as a zero-magnitude/zero-cruise
    no-op. (test_motion_engine_default_cruise_for_distance.py already
    covers the resolver in isolation; this is the end-to-end drive.)"""
    rotation_rad = math.radians(90.0)

    def configure(e):
        e.set_decel(_DECEL_TEST)
        e.set_v_max(250.0)

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
