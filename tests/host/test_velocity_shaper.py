"""tests/host/test_velocity_shaper.py -- sprint 029 ticket 002 (motion
profile unification, docs/design/motion-profile-unification.md S4.2/
S6.1/S9.1): the new `diffDrive::VelocityShaper` and `diffDrive::
MotionLimits` objects, in isolation -- neither is wired into
MotionEngine yet (that is ticket 003), so this suite exercises them
directly through velocity_shaper_shim.cpp, the same "opaque handle plus
free functions" shape every other host shim in this directory uses
(see e.g. emit_queue_shim.cpp).

Covers design S9.1's five VelocityShaper properties (from rest the
first command is the floor; accel never exceeds `accel` above the
floor; decel never exceeds `decel`; with `jerk` set the commanded
acceleration never steps by more than `jerk*dt`; `arriving` fires
exactly when `remain <= v*dt + stop`), plus the two properties the
ticket's own acceptance criteria add (continuous hold has no floor and
no arrival; a `target` change mid-run is slewed toward, not stepped
to) and a minimal smoke test of MotionLimits's "positive, else keep"
setters and its two axis-unit conversion helpers (design S6.2).

Run with::

    uv run pytest tests/host/test_velocity_shaper.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "velocity_shaper_shim.cpp",
]

# MotionLimits field order, mirrored exactly by vsAdvance()'s trailing
# arguments and by _DEFAULT_LIMITS below -- see velocity_shaper_shim.cpp's
# own comment ("assembles the struct here, in DECLARATION order").
_LIMIT_FIELDS = (
    "accel", "decel", "jerk", "vMax", "omegaMax", "vFloor", "omegaFloor",
    "stopDistance", "arriveDist", "arriveYaw",
)


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libvelocity_shaper_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))

    loaded.vsNew.argtypes = []
    loaded.vsNew.restype = ctypes.c_void_p
    loaded.vsFree.argtypes = [ctypes.c_void_p]
    loaded.vsFree.restype = None
    loaded.vsReset.argtypes = [ctypes.c_void_p]
    loaded.vsReset.restype = None
    loaded.vsAdvance.argtypes = (
        [ctypes.c_void_p] + [ctypes.c_float] * 15 + [ctypes.POINTER(ctypes.c_int)]
    )
    loaded.vsAdvance.restype = ctypes.c_float
    loaded.vsVelocity.argtypes = [ctypes.c_void_p]
    loaded.vsVelocity.restype = ctypes.c_float
    loaded.vsAcceleration.argtypes = [ctypes.c_void_p]
    loaded.vsAcceleration.restype = ctypes.c_float

    loaded.mlNew.argtypes = []
    loaded.mlNew.restype = ctypes.c_void_p
    loaded.mlFree.argtypes = [ctypes.c_void_p]
    loaded.mlFree.restype = None
    for name in (
        "mlSetAccel", "mlSetDecel", "mlSetJerk", "mlSetVMax", "mlSetOmegaMax",
        "mlSetVFloor", "mlSetOmegaFloor", "mlSetStopDistance",
        "mlSetArriveDist", "mlSetArriveYaw",
    ):
        fn = getattr(loaded, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_float]
        fn.restype = None
    for name in (
        "mlAccel", "mlDecel", "mlJerk", "mlVMax", "mlOmegaMax", "mlVFloor",
        "mlOmegaFloor", "mlStopDistance", "mlArriveDist", "mlArriveYaw",
    ):
        fn = getattr(loaded, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float
    loaded.mlOmegaFloorAsWheelSpeed.argtypes = [ctypes.c_void_p, ctypes.c_float]
    loaded.mlOmegaFloorAsWheelSpeed.restype = ctypes.c_float
    loaded.mlOmegaMaxAsWheelSpeed.argtypes = [ctypes.c_void_p, ctypes.c_float]
    loaded.mlOmegaMaxAsWheelSpeed.restype = ctypes.c_float

    return loaded


class Limits:
    """A plain Python mirror of MotionLimits' field defaults (design
    S4.1) -- passed straight through to vsAdvance() as fifteen trailing
    floats. A test overrides only the fields it cares about via
    `Limits(**overrides)`."""

    def __init__(self, accel=400.0, decel=400.0, jerk=0.0, vMax=250.0,
                 omegaMax=0.0, vFloor=70.0, omegaFloor=20.0,
                 stopDistance=0.0, arriveDist=1.0, arriveYaw=0.3):
        self.accel = accel
        self.decel = decel
        self.jerk = jerk
        self.vMax = vMax
        self.omegaMax = omegaMax
        self.vFloor = vFloor
        self.omegaFloor = omegaFloor
        self.stopDistance = stopDistance
        self.arriveDist = arriveDist
        self.arriveYaw = arriveYaw

    def as_args(self):
        return [getattr(self, f) for f in _LIMIT_FIELDS]


class Shaper:
    """Thin Pythonic wrapper around one vsNew()/vsFree() handle, same
    habit test_kernel_harness.py's own Kernel wrapper follows."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.vsNew()

    def close(self):
        self._lib.vsFree(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def reset(self):
        self._lib.vsReset(self._handle)

    def advance(self, target, remain, floor, cap, dt, lim):
        arriving = ctypes.c_int(0)
        vcmd = self._lib.vsAdvance(
            self._handle, target, remain, floor, cap, dt,
            *lim.as_args(), ctypes.byref(arriving)
        )
        return vcmd, bool(arriving.value)

    @property
    def velocity(self):
        return self._lib.vsVelocity(self._handle)

    @property
    def acceleration(self):
        return self._lib.vsAcceleration(self._handle)


# ---- VelocityShaper -------------------------------------------------------


def test_first_command_from_rest_is_the_floor(lib):
    """design S6.1's own named property: "From rest, the first command
    is the floor -- a step, deliberately." A fresh shaper (v=0) given a
    large target/remain must command exactly vFloor on its very first
    tick, not an accel-ramped value below it."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, vFloor=70.0)
        vcmd, arriving = vs.advance(
            target=200.0, remain=1000.0, floor=lim.vFloor, cap=1e9,
            dt=0.024, lim=lim,
        )
        assert vcmd == pytest.approx(70.0)
        assert vs.velocity == pytest.approx(70.0)
        assert not arriving


def test_accel_never_exceeds_the_limit_above_the_floor(lib):
    """Once a run is above the floor, every tick's speed increase must
    be bounded by `accel*dt` (design S6.1 step 2). The very first tick
    (0 -> floor) is EXCLUDED by construction -- it is a deliberate step,
    per the property above, not a rate-limited ramp."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, jerk=0.0, vMax=250.0,
                      vFloor=70.0)
        dt = 0.02
        remain = 2000.0  # far from arrival -- isolates the accel ramp
        prev_v = None
        for _ in range(60):
            vcmd, arriving = vs.advance(
                target=200.0, remain=remain, floor=lim.vFloor, cap=1e9,
                dt=dt, lim=lim,
            )
            assert not arriving
            if prev_v is not None and prev_v >= lim.vFloor:
                assert vcmd - prev_v <= lim.accel * dt + 1e-4
            prev_v = vcmd
            remain -= vcmd * dt


def test_decel_never_exceeds_the_limit(lib):
    """A sudden ceiling drop (a `SET v_max`/`cap` change mid-segment,
    design S6.1's own "target can change mid-segment" note) must slew
    DOWN no faster than `decel*dt` per tick, symmetric to the accel
    test above."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=300.0, jerk=0.0, vFloor=0.0)
        dt = 0.02
        # Ramp up to cruise first (remain kept huge so the braking plan
        # never binds -- this test is about the rate limiter's decel
        # branch only, not the arrival braking plan).
        v = 0.0
        for _ in range(40):
            v, _ = vs.advance(
                target=200.0, remain=1e6, floor=0.0, cap=1e9, dt=dt, lim=lim,
            )
        assert v == pytest.approx(200.0, abs=1.0)

        # Now drop the ceiling hard and confirm every tick's decrease
        # is bounded by decel*dt.
        prev_v = v
        for _ in range(30):
            vcmd, _ = vs.advance(
                target=10.0, remain=1e6, floor=0.0, cap=1e9, dt=dt, lim=lim,
            )
            assert prev_v - vcmd <= lim.decel * dt + 1e-4
            prev_v = vcmd


def test_jerk_bounds_the_change_in_commanded_acceleration(lib):
    """design S6.1 step 3: with `jerk` set, the commanded acceleration
    must never step by more than `jerk*dt` per tick, and (the a^2/(2j)
    anticipation term's whole point) the ramp must not overshoot its
    cap. `floor=0` here deliberately removes the floor's own
    unconditional override from this trace, so every observed
    acceleration step is attributable to the jerk limiter alone (the
    floor-crossing tick is excluded the same way in the two tests
    above)."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, jerk=800.0, vFloor=0.0)
        dt = 0.02
        target = 200.0
        prev_a = 0.0
        peak_v = 0.0
        for _ in range(80):
            vcmd, arriving = vs.advance(
                target=target, remain=1e6, floor=0.0, cap=1e9, dt=dt,
                lim=lim,
            )
            a = vs.acceleration
            assert abs(a - prev_a) <= lim.jerk * dt + 1e-3
            prev_a = a
            peak_v = max(peak_v, vcmd)
        # The anticipation term's job: the ramp settles at the cap
        # without ever overshooting it.
        assert peak_v <= target + 1e-2
        assert vs.velocity == pytest.approx(target, abs=1.0)


def test_arrival_fires_exactly_when_predicted_by_the_stop_condition(lib):
    """design S6.3: `arriving = remain >= 0 and remain <= vNext*dt +
    stopDistance` -- tested here not by re-deriving the formula but by
    running a full simulated approach (ideal wheels: `remain -=
    vcmd*dt` each tick, the same assumption every host test in this
    tree makes for a probe run) and checking the EXACT postcondition
    against the shim's own returned `(vcmd, arriving)` on every single
    tick, not just at the boundary."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, jerk=0.0, vFloor=70.0,
                      stopDistance=5.0)
        dt = 0.02
        remain = 500.0
        saw_arrival = False
        for _ in range(2000):
            vcmd, arriving = vs.advance(
                target=200.0, remain=remain, floor=lim.vFloor, cap=1e9,
                dt=dt, lim=lim,
            )
            expected = remain <= vcmd * dt + lim.stopDistance + 1e-6
            assert arriving == expected, (
                f"remain={remain} vcmd={vcmd} stop={lim.stopDistance} "
                f"dt={dt} arriving={arriving} expected={expected}"
            )
            if arriving:
                saw_arrival = True
                break
            remain -= vcmd * dt
        assert saw_arrival, "shaper never arrived over 2000 simulated ticks"


def test_continuous_hold_has_no_floor_and_never_arrives(lib):
    """`remain < 0` means "no displacement bound" (continuous drive --
    wheelsV/driveTwist, design S6.1's remain<0 branch): the floor must
    NOT apply (a continuous hold below the floor is a legitimate
    request, e.g. a student's own slow WHEELS_V), and `arriving` must
    never fire since there is no target to arrive at."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, jerk=0.0, vFloor=70.0,
                      stopDistance=5.0)
        dt = 0.02
        # From rest, ramping toward a target BELOW the floor: with
        # remain>=0 the floor would force this up to 70; with remain<0
        # it must not.
        vcmd, arriving = vs.advance(
            target=30.0, remain=-1.0, floor=lim.vFloor, cap=1e9, dt=dt,
            lim=lim,
        )
        assert vcmd < lim.vFloor
        assert not arriving

        # Run it out to cruise and confirm arriving stays false the
        # whole time, however long it runs.
        for _ in range(200):
            vcmd, arriving = vs.advance(
                target=30.0, remain=-1.0, floor=lim.vFloor, cap=1e9, dt=dt,
                lim=lim,
            )
            assert not arriving
        assert vcmd == pytest.approx(30.0, abs=0.5)


def test_target_change_mid_run_is_slewed_not_stepped(lib):
    """design S6.1: "`target` can change mid-segment ...: the rate
    limiter simply slews toward the new value." A live SET v_max (or a
    supervisory re-solve) must never appear as an instantaneous jump in
    vCmd -- every post-change tick's delta stays bounded by
    accel/decel*dt, the same bound the ramp-up tests above check,
    exercised here specifically across a target change rather than
    from a fixed target throughout."""
    with Shaper(lib) as vs:
        lim = Limits(accel=400.0, decel=400.0, jerk=0.0, vFloor=0.0)
        dt = 0.02
        v = 0.0
        for _ in range(30):
            v, _ = vs.advance(
                target=200.0, remain=-1.0, floor=0.0, cap=1e9, dt=dt, lim=lim,
            )
        assert v == pytest.approx(200.0, abs=1.0)

        # target drops hard, mid-run -- must slew, not step.
        prev_v = v
        first_post_change_v, _ = vs.advance(
            target=50.0, remain=-1.0, floor=0.0, cap=1e9, dt=dt, lim=lim,
        )
        assert prev_v - first_post_change_v <= lim.decel * dt + 1e-4
        assert first_post_change_v != pytest.approx(50.0)

        for _ in range(30):
            v, _ = vs.advance(
                target=50.0, remain=-1.0, floor=0.0, cap=1e9, dt=dt, lim=lim,
            )
        assert v == pytest.approx(50.0, abs=1.0)


# ---- MotionLimits -----------------------------------------------------


class MLimits:
    """Thin Pythonic wrapper around one mlNew()/mlFree() handle."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.mlNew()

    def close(self):
        self._lib.mlFree(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


@pytest.mark.parametrize("field,default", [
    ("Accel", 400.0), ("Decel", 400.0), ("Jerk", 0.0), ("VMax", 250.0),
    ("OmegaMax", 0.0), ("VFloor", 70.0), ("OmegaFloor", 20.0),
    ("StopDistance", 0.0), ("ArriveDist", 1.0), ("ArriveYaw", 0.3),
])
def test_defaults_match_design_s4_1(lib, field, default):
    """Every field's default matches design S4.1's own struct listing
    verbatim -- the fleet bake this ticket must not silently change."""
    with MLimits(lib) as ml:
        assert getattr(lib, f"ml{field}")(ml._handle) == pytest.approx(default)


@pytest.mark.parametrize("field,requires_strictly_positive", [
    ("Accel", True), ("Decel", True), ("Jerk", False), ("VMax", True),
    ("OmegaMax", False), ("VFloor", False), ("OmegaFloor", False),
    ("StopDistance", False), ("ArriveDist", True), ("ArriveYaw", True),
])
def test_setters_are_positive_else_keep(lib, field, requires_strictly_positive):
    """Every setter accepts a valid new value and silently keeps the
    prior one on an invalid input -- MotionEngine::setRotationalSlip()'s
    own validation style (motion_engine.h). `jerk`/`omegaMax`/`vFloor`/
    `omegaFloor`/`stopDistance` additionally accept exactly 0.0 (each is
    its own documented "off"/"none" default, design S4.1); the rest
    require a strictly positive value."""
    with MLimits(lib) as ml:
        getter = getattr(lib, f"ml{field}")
        setter = getattr(lib, f"mlSet{field}")

        setter(ml._handle, 123.5)
        assert getter(ml._handle) == pytest.approx(123.5)

        setter(ml._handle, -1.0)
        assert getter(ml._handle) == pytest.approx(123.5)  # kept

        if requires_strictly_positive:
            setter(ml._handle, 0.0)
            assert getter(ml._handle) == pytest.approx(123.5)  # kept
        else:
            setter(ml._handle, 0.0)
            assert getter(ml._handle) == pytest.approx(0.0)  # 0 accepted


def test_axis_unit_conversions_match_design_s6_2_worked_example(lib):
    """design S6.2's own worked example, at trackWidth b=120mm: `omegaFloor`
    20 deg/s -> 21 mm/s per wheel; `omegaMax` 90 deg/s -> 94 mm/s per
    wheel. Both are the design doc's own stated numbers, re-derived here
    from the formula (omega * pi/180 * b/2), not copied as magic
    constants."""
    with MLimits(lib) as ml:
        lib.mlSetOmegaFloor(ml._handle, 20.0)
        lib.mlSetOmegaMax(ml._handle, 90.0)

        floor_speed = lib.mlOmegaFloorAsWheelSpeed(ml._handle, 120.0)
        max_speed = lib.mlOmegaMaxAsWheelSpeed(ml._handle, 120.0)

        assert floor_speed == pytest.approx(20.0 * 3.14159265358979323846 / 180.0 * 60.0)
        assert floor_speed == pytest.approx(20.94, abs=0.05)
        assert max_speed == pytest.approx(90.0 * 3.14159265358979323846 / 180.0 * 60.0)
        assert max_speed == pytest.approx(94.25, abs=0.05)
