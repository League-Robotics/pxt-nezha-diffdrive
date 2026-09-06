"""tests/host/test_odometry.py -- host test for src/motion/odometry.h's
Odometry (sprint 033 ticket 002, closes
odometry-object-and-kernel-rearm-references.md).

**What this covers.** Odometry is the dead-reckoned pose that used to be
five loose `Rig` fields, a free `odomUpdate()` over them, a separate
read-only `EncoderPoseSource` adapter bound to them by `const float&`,
and a rebase-epoch guard -- all in `shims.cpp`, which includes `pxt.h`
and can therefore never be compiled into a host test at all. Nothing
about that math was host-testable before this ticket; as one
host-portable object it is, and this file exercises it directly:

  1. a known wheel-count path integrated through `Odometry::update()`,
     matched against the PRE-REFACTOR `odomUpdate()` output (below);
  2. the rebase-epoch guard -- a changed `positionEpochLeft/Right` must
     re-anchor the wheel baseline and HOLD the frame, not integrate the
     kernel's intentional position discontinuity as motion.

**Where the expected numbers come from.** They are NOT hand-derived from
the formula and they are not this implementation's own output recorded
after the fact. Before the math was moved, `odomUpdate()`'s body was
transcribed VERBATIM out of `src/shims.cpp` at commit 822a8a5 (lines
343-379, the last commit before this ticket) into a standalone C++11
program over a plain struct standing in for `Rig`'s five odometry
fields, compiled with the same `float` arithmetic, and run over exactly
the `_WHEEL_PATH` below with exactly `_TRAVEL_CALIB`/`_TRACK_WIDTH`/
`_ROTATIONAL_SLIP`. Its printed frames are `_GOLDEN_FRAMES`. That
program is reproduced by `_reference_integrate()` below -- a Python
transcription of the same pre-refactor body, asserted against the same
goldens by `test_reference_transcription_reproduces_the_captured_
goldens`, so the two independent statements of "what the old code did"
have to agree with each other before either is used to judge the new
code. A future edit to `Odometry::update()`'s math fails against the
goldens whether or not anyone remembers to update the transcription.

Run with::

    uv run pytest tests/host/test_odometry.py
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
    _TEST_DIR / "odometry_shim.cpp",
]

# Geometry the goldens were captured with. Deliberately set explicitly
# rather than inherited from MotionEngine's per-robot defaults, so a
# later bake change cannot silently move this file's expected numbers.
_TRAVEL_CALIB = 0.8      # [mm/deg] -> countsPerMm = 10 / 0.8 = 12.5
_TRACK_WIDTH = 114.4     # [mm]
_ROTATIONAL_SLIP = 1.0   # [1] -> effectiveTrackWidth == trackWidth

# The known wheel path: (positionLeft, positionRight) in [counts], all at
# epoch (0, 0). At 12.5 counts/mm the legs are, in order: prime, 100 mm
# straight, an arc (+40 mm left wheel / +120 mm right), 100 mm straight
# on the new heading, an arc back the other way (+80 / +40), then 50 mm
# of reverse on both wheels.
_WHEEL_PATH = [
    (0.0, 0.0),
    (1250.0, 1250.0),
    (1750.0, 2750.0),
    (3000.0, 4000.0),
    (4000.0, 4500.0),
    (3375.0, 3875.0),
]

# Frame after each _WHEEL_PATH sample: (x [mm], y [mm], heading [rad]).
# Captured from the pre-refactor odomUpdate() -- see the module docstring.
_GOLDEN_FRAMES = [
    (0.0, 0.0, 0.0),
    (100.0, 0.0, 0.0),
    (175.159409, 27.4055481, 0.699300706),
    (251.68866, 91.7738113, 0.699300706),
    (303.623871, 121.819359, 0.349650353),
    (256.649231, 104.690887, 0.349650353),
]

# float32 math on the C++ side vs float64 in the Python transcription --
# the goldens are printed to 9 significant digits, so this is the
# agreement a correct move must produce, and is far tighter than any
# change to the integration itself could hide inside.
_REL = 1e-6
_ABS = 1e-4


def _reference_integrate(path, primed_state=None):
    """Python transcription of the PRE-REFACTOR `odomUpdate()` body
    (`src/shims.cpp` at commit 822a8a5) -- the epoch guard, the
    counts->mm divide, the midpoint-heading integration, in that order.
    `path` is a list of (positionLeft, positionRight, epochLeft,
    epochRight). Returns the list of (x, y, heading) frames, one per
    sample.
    """
    counts_per_mm = 10.0 / _TRAVEL_CALIB
    track_width = _TRACK_WIDTH / _ROTATIONAL_SLIP
    x, y, heading = primed_state or (0.0, 0.0, 0.0)
    pos_left = pos_right = 0.0
    epoch_left = epoch_right = 0
    primed = False
    frames = []
    for position_left, position_right, out_epoch_left, out_epoch_right in path:
        rebased = primed and (out_epoch_left != epoch_left
                              or out_epoch_right != epoch_right)
        if not primed or rebased:
            pos_left, pos_right = position_left, position_right
            epoch_left, epoch_right = out_epoch_left, out_epoch_right
            primed = True
            frames.append((x, y, heading))
            continue
        d_left = (position_left - pos_left) / counts_per_mm
        d_right = (position_right - pos_right) / counts_per_mm
        pos_left, pos_right = position_left, position_right
        epoch_left, epoch_right = out_epoch_left, out_epoch_right
        d_center = 0.5 * (d_left + d_right)
        d_heading = (d_right - d_left) / track_width
        mid_heading = heading + 0.5 * d_heading
        x += d_center * math.cos(mid_heading)
        y += d_center * math.sin(mid_heading)
        heading += d_heading
        frames.append((x, y, heading))
    return frames


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libodometry_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.odoCreate.argtypes = []
    loaded.odoCreate.restype = ctypes.c_void_p
    loaded.odoDestroy.argtypes = [ctypes.c_void_p]
    loaded.odoDestroy.restype = None
    loaded.odoSetGeometry.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ]
    loaded.odoSetGeometry.restype = None
    loaded.odoCountsPerMm.argtypes = [ctypes.c_void_p]
    loaded.odoCountsPerMm.restype = ctypes.c_float
    loaded.odoEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    loaded.odoEffectiveTrackWidth.restype = ctypes.c_float
    loaded.odoUpdate.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float,
        ctypes.c_uint32, ctypes.c_uint32,
    ]
    loaded.odoUpdate.restype = None
    loaded.odoReset.argtypes = [ctypes.c_void_p]
    loaded.odoReset.restype = None
    loaded.odoSeed.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
    ]
    loaded.odoSeed.restype = None
    for name in ("odoX", "odoY", "odoHeading", "odoPoseSourceX"):
        fn = getattr(loaded, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float
    return loaded


class Odometry:
    """Thin Pythonic wrapper around one odoCreate()/odoDestroy() handle,
    mirroring test_encoder_glitch_armor.py's own Armor wrapper. Geometry
    is armed to this file's fixed bake on construction."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.odoCreate()
        lib.odoSetGeometry(self._handle, _TRAVEL_CALIB, _TRACK_WIDTH,
                           _ROTATIONAL_SLIP)

    def close(self):
        self._lib.odoDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def update(self, position_left, position_right, epoch_left=0,
               epoch_right=0):
        self._lib.odoUpdate(self._handle, position_left, position_right,
                            epoch_left, epoch_right)

    def reset(self):
        self._lib.odoReset(self._handle)

    def seed(self, x, y, heading):
        self._lib.odoSeed(self._handle, x, y, heading)

    def frame(self):
        return (self._lib.odoX(self._handle), self._lib.odoY(self._handle),
                self._lib.odoHeading(self._handle))

    def pose_source_x(self):
        return self._lib.odoPoseSourceX(self._handle)

    def counts_per_mm(self):
        return self._lib.odoCountsPerMm(self._handle)

    def effective_track_width(self):
        return self._lib.odoEffectiveTrackWidth(self._handle)


def _assert_frame(actual, expected):
    for got, want in zip(actual, expected):
        assert got == pytest.approx(want, rel=_REL, abs=_ABS)


# ---- the two statements of the pre-refactor behavior must agree -------

def test_reference_transcription_reproduces_the_captured_goldens():
    """The Python transcription of the pre-refactor body and the C++
    capture of that same body (`_GOLDEN_FRAMES`) must produce the same
    frames -- otherwise neither can be trusted to judge the new code.
    This test touches no C++ at all."""
    path = [(left, right, 0, 0) for left, right in _WHEEL_PATH]
    for got, want in zip(_reference_integrate(path), _GOLDEN_FRAMES):
        _assert_frame(got, want)


# ---- AC: a known wheel path matches the pre-refactor odomUpdate() -----

def test_geometry_is_read_from_the_engine(lib):
    """Odometry integrates with the engine's geometry, read fresh on
    every update() -- not a snapshot of its own. This pins the two
    numbers the goldens were captured with, so a failure below can be
    read as a math change rather than a geometry surprise."""
    with Odometry(lib) as odom:
        assert odom.counts_per_mm() == pytest.approx(12.5)
        assert odom.effective_track_width() == pytest.approx(_TRACK_WIDTH)


def test_known_wheel_path_matches_pre_refactor_odom_update(lib):
    """The ticket's headline acceptance criterion: integrate the known
    wheel-count path through Odometry::update() and match the frames the
    pre-refactor free function produced for the same path, sample by
    sample (not just at the end -- a compensating pair of errors would
    survive an end-state-only check)."""
    with Odometry(lib) as odom:
        for (position_left, position_right), golden in zip(_WHEEL_PATH,
                                                           _GOLDEN_FRAMES):
            odom.update(position_left, position_right)
            _assert_frame(odom.frame(), golden)


def test_first_update_primes_without_integrating(lib):
    """The very first sample has no prior sample to be a continuation of
    -- it anchors the wheel baseline and leaves the frame alone, however
    far from zero the encoders happen to be. Without this, a robot whose
    counters are already at 50,000 would teleport 4 m on its first pose
    read."""
    with Odometry(lib) as odom:
        odom.update(50_000.0, -37_500.0)
        _assert_frame(odom.frame(), (0.0, 0.0, 0.0))
        # ...and the NEXT sample integrates the delta from THAT anchor,
        # not from zero: +1250 counts on both wheels == 100 mm straight.
        odom.update(51_250.0, -36_250.0)
        _assert_frame(odom.frame(), (100.0, 0.0, 0.0))


def test_repeated_identical_sample_is_a_no_op(lib):
    """update() diffs against the last Output it consumed, so a tick
    with no new encoder movement changes nothing -- this is what makes
    tickDrive()'s unconditional per-tick call safe (src/DESIGN.md S9)."""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.update(1250.0, 1250.0)
        before = odom.frame()
        for _ in range(5):
            odom.update(1250.0, 1250.0)
        _assert_frame(odom.frame(), before)


def test_pure_pivot_translates_nothing(lib):
    """Equal and opposite wheel travel is a pivot in place: heading
    changes by 2 * d / b, x/y do not move. (dCenter == 0 kills both
    trig terms regardless of the midpoint heading, so this holds
    exactly, not approximately.)"""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.update(-625.0, 625.0)  # -50 mm left, +50 mm right
        x, y, heading = odom.frame()
        assert x == pytest.approx(0.0, abs=1e-6)
        assert y == pytest.approx(0.0, abs=1e-6)
        assert heading == pytest.approx(100.0 / _TRACK_WIDTH, rel=_REL)


# ---- AC: the rebase-epoch guard ---------------------------------------

@pytest.mark.parametrize("epoch_left,epoch_right", [
    (1, 1),  # both wheels re-anchored (what kernel.rebasePosition() does)
    (1, 0),  # left only
    (0, 1),  # right only
])
def test_changed_position_epoch_holds_the_frame(lib, epoch_left, epoch_right):
    """SET rebase -> kernel.rebasePosition() re-anchors positionLeft/
    positionRight to a new software zero at the kernel's next step(): an
    intentional discontinuity, not motion. A changed epoch on EITHER
    wheel must therefore re-anchor this object's own baseline and hold
    the frame. Without the guard, the sample below (a ~4000-count jump
    back to zero) would integrate as a ~320 mm phantom leg."""
    with Odometry(lib) as odom:
        for position_left, position_right in _WHEEL_PATH:
            odom.update(position_left, position_right)
        before = odom.frame()

        odom.update(0.0, 0.0, epoch_left, epoch_right)
        _assert_frame(odom.frame(), before)

        # The baseline moved with the rebase: the next sample integrates
        # against the post-rebase counts, so +625 counts on both wheels
        # is 50 mm of ordinary straight travel on the held heading.
        odom.update(625.0, 625.0, epoch_left, epoch_right)
        x, y, heading = odom.frame()
        assert heading == pytest.approx(before[2], rel=_REL, abs=_ABS)
        assert x == pytest.approx(before[0] + 50.0 * math.cos(before[2]),
                                  rel=_REL, abs=_ABS)
        assert y == pytest.approx(before[1] + 50.0 * math.sin(before[2]),
                                  rel=_REL, abs=_ABS)


def test_unchanged_epoch_does_not_hold_the_frame(lib):
    """The negative control for the guard above: the SAME jump back to
    zero counts, with the epochs left alone, is treated as ordinary
    (implausible, but ordinary) wheel motion and integrated. This is
    what proves the hold is caused by the epoch change and not by
    something incidental about the sample itself."""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.update(1250.0, 1250.0)
        odom.update(0.0, 0.0)
        _assert_frame(odom.frame(), (0.0, 0.0, 0.0))


def test_epoch_guard_matches_the_pre_refactor_reference(lib):
    """The whole path plus a rebase and a following leg, checked against
    the pre-refactor transcription rather than against hand-reasoning --
    the guard's exact interaction with priming and baselining is what
    this ticket folded INTO the class, so it gets the same
    match-the-old-code treatment as the integration math."""
    path = [(left, right, 0, 0) for left, right in _WHEEL_PATH]
    path += [(0.0, 0.0, 1, 1), (625.0, 625.0, 1, 1)]
    expected = _reference_integrate(path)
    with Odometry(lib) as odom:
        for (position_left, position_right, epoch_left,
             epoch_right), want in zip(path, expected):
            odom.update(position_left, position_right, epoch_left,
                        epoch_right)
            _assert_frame(odom.frame(), want)


# ---- reset()/seed(): the frame writers --------------------------------

def test_reset_zeroes_the_frame_without_disturbing_the_baseline(lib):
    """resetPose()/SET rebase's own shape: the caller calls update()
    first (consuming pending deltas), then reset(). The wheel baseline is
    deliberately untouched, so the next sample integrates from where the
    encoders actually are rather than replaying the discarded motion."""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.update(1250.0, 1250.0)
        odom.reset()
        _assert_frame(odom.frame(), (0.0, 0.0, 0.0))
        odom.update(2500.0, 2500.0)  # another 100 mm on the same wheels
        _assert_frame(odom.frame(), (100.0, 0.0, 0.0))


def test_seed_declares_the_frame_verbatim(lib):
    """seedPose()/v6 SEED: the declared pose is stored exactly as given,
    including an unwrapped heading well outside (-pi, pi] -- Odometry
    does NOT share OtosPort's wrap convention (motion_engine.h's
    PoseSource comment)."""
    with Odometry(lib) as odom:
        odom.seed(-250.5, 812.25, 4.0 * math.pi)
        x, y, heading = odom.frame()
        assert x == pytest.approx(-250.5)
        assert y == pytest.approx(812.25)
        assert heading == pytest.approx(4.0 * math.pi, rel=_REL)


def test_integration_continues_from_a_seeded_frame(lib):
    """A seed is a new origin for the SAME integration -- the next
    wheel delta is folded into the seeded frame, at the seeded heading."""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.seed(10.0, 20.0, math.pi / 2.0)
        odom.update(1250.0, 1250.0)  # 100 mm straight, now heading +y
        x, y, heading = odom.frame()
        assert x == pytest.approx(10.0, abs=1e-3)
        assert y == pytest.approx(120.0, abs=1e-3)
        assert heading == pytest.approx(math.pi / 2.0, rel=_REL)


# ---- Odometry IS the PoseSource ---------------------------------------

def test_reads_through_the_pose_source_interface_agree(lib):
    """Odometry implements PoseSource directly (no adapter object in
    between, which is the cohesion this ticket bought): a read through a
    `const PoseSource&` -- the exact form MotionEngine::goToW() takes --
    must return the same frame the concrete reads do."""
    with Odometry(lib) as odom:
        odom.update(0.0, 0.0)
        odom.update(1250.0, 1250.0)
        assert odom.pose_source_x() == pytest.approx(odom.frame()[0])
