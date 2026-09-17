"""tests/host/test_creep_self_lock_stiction_sim.py -- sprint 039 ticket
006 (SUC-004): host-sim investigation of the creep self-lock issue
(clasi/sprints/039-nudge-mode-sub-floor-micro-moves-for-calibratel/
issues/slow-continuous-creep-self-locks-below-breakaway.md).

Reuses `motion_engine_nudge_stiction_shim.cpp`'s own StictionMotor
(ticket 004) rather than writing a second Motor double, per this
ticket's own instruction -- extended with `withholdStampOnStiction`
(default false, so every ticket 004 test is byte-for-byte unaffected)
and a handful of new exports that reach MotionEngine's OTHER primitive,
the continuous Hold (wheelsV()/moveV()), through the same real kernel
that file already builds. See that shim file's own header comment for
the full rationale.

THE HARDWARE ANCHOR (cited exactly as the ticket's own acceptance
criteria require -- not re-derived, not rounded):
`captures/calibratel-vevov-20260915/bench-log.md` run 5 -- reverse
sweep at -4 cm/s for 30 s, serial link: `i2cf` 1247 -> 2493 (delta
1246) over `cyc` 1414 -> 2666 (delta 1252), camera frame
`after-back2.jpg` showing the robot unmoved.

THE MECHANISM UNDER TEST (source reading, not a measurement -- see
`.claude/rules/measurement-citations.md`):
`DifferentialDrive::positionError()`'s K2 guard (src/core/diffdrive.cpp
:955-991, READ ONLY -- this ticket does not edit diffdrive.{h,cpp})
does not integrate the position reference on a tick whose `advanced`
flag is false. `advanced` is NOT "did the wheel move" -- it is "did
THIS wheel's `Motor::sampleTime()` change since the last step()"
(diffdrive.cpp:550-551, the `sampleAdvanced{Left,Right}_` assignment).
On real hardware those are the same thing only because
`NezhaMotorPort::collect()` (src/platform/nezha_port.cpp:391-406, READ
ONLY) deliberately WITHHOLDS the sample stamp when a successful read
returns raw counts identical to the last accepted one while driven --
"sampleTime_ HOLDS" is that function's own comment, and it is also
what feeds `i2cFaultCount_` (i2cf), the exact hardware signature the
bench-log capture shows.

This is why `StictionMotor`'s ORIGINAL ticket-004 model (sample stamp
always advances, every tick, regardless of physical motion) CANNOT
reproduce the lock: with the stamp always advancing, `advanced` is
always true, and K2 never suppresses anything. `withholdStampOnStiction
= True` (this ticket's own addition) makes the double mirror the real
port instead: the stamp holds exactly when the wheel is driven-but-
frozen, which is exactly the condition `i2cf` counts on hardware.

THREE RESULTS, each an artifact of ITS OWN host-sim run (never a
hardware claim):

1. `test_creep_below_breakaway_self_locks_with_stamp_withholding` --
   CONFIRMS the K2 lock mechanism: with stamp-withholding armed, a
   creep commanded well below the sim's own breakaway threshold never
   moves, for the whole 30 s hold, and `i2cFaultCount` tracks
   `cycleCount` almost exactly -- the same shape the bench-log capture
   shows.
2. `test_creep_recovers_when_stamp_is_not_withheld` -- the REFUTATION
   control: same rig, same commanded creep, same breakaway threshold,
   the ONE difference being stamp-withholding off (K2's `advanced` gate
   never fires). The I-term winds up and the wheel breaks free well
   inside the 30 s window. This isolates the self-lock to K2's guard
   specifically -- not the plant, not the PID gains, not the shaper.
3. `test_hold_vfloor_value_has_no_effect_on_commanded_ramp` -- tests
   the sprint plan's OWN suggested candidate location (motion_engine.cpp
   :397's `shaper_.advance(hold_.dominant, -1.0f, 0.0f, ...)`, the Hold
   branch passing floor 0) and finds it is a DEAD PARAMETER for a
   continuous hold: `VelocityShaper::advance()`'s floor-snap
   (velocity_shaper.cpp, step 4) is gated on `remain >= 0.0f`, and Hold
   always passes `remain = -1.0f`. Changing the floor VALUE passed
   there -- the literal fix the sprint plan names -- provably changes
   nothing. See this test's own docstring and
   `test_velocity_shaper.py::test_continuous_hold_has_no_floor_and_never
   _arrives` (sprint 029 ticket 002's own PINNED test) for why forcing a
   floor onto Hold anyway is not a safe small fix either -- it reverses
   a deliberate, tested, cross-ticket design decision this ticket has no
   standing to reverse.

STICTION PLANT PARAMETERS (documented, not tuned to force an outcome):
see the module-level constants below for the derivation of each one.

Run with::

    uv run pytest tests/host/test_creep_self_lock_stiction_sim.py
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _TEST_DIR / "motion_engine_nudge_stiction_shim.cpp",
]

LEFT = 0
RIGHT = 1
STATUS_OK = 0

# ---- geometry: round numbers, same convention ticket 004's own test
# file documents ("travelCalib = 1.0 mm/deg -> countsPerMm() == 10 ->
# every expected count in this file is exact arithmetic").
TRAVEL_CALIB_MM_PER_DEG = 1.0
COUNTS_PER_MM = 10.0

# ---- the commanded creep: -4 cm/s, chosen to MATCH the bench-log
# capture's own commanded speed (run 5: "whileDriving(-4 cm/s, 0) for
# 30 s") rather than an arbitrary sim number -- so this sim's own input
# is traceable to the same operating point the hardware anchor used.
CREEP_MM_S = -40.0
HOLD_DURATION_MS = 30000
CYCLE_DT_US = 24000  # [us] 24 ms -- DiffDrive::Config::cyclePeriod's own
                      # default (src/core/diffdrive.h)
TICKS = HOLD_DURATION_MS // (CYCLE_DT_US // 1000)  # 1250, exact

# ---- PID plant: kp/kaff = 0 isolates the I-term specifically, the same
# choice the historical docs/code-review/2026-09-02/raw/stiction_probe.cpp
# reference made for the same reason ("NEW engine, non-ideal wheels").
# ki=6 is this ticket's own issue text's own cited value ("the I-term
# (ki 6) never winds up"). fullDutyVelocity is picked so the CREEP's
# own feedforward-only duty lands at ~0.5% -- the ticket's own source
# reading's own cited figure ("feedforward alone (~0.5% duty at
# 40 mm/s)") -- not reverse-engineered from a desired conclusion:
# 400 counts/s / 80000 counts/s = 0.5% exactly.
FULL_DUTY_VELOCITY = 80000.0  # [counts/s] at 100% duty
KP = 0.0
KI = 6.0
KAFF = 0.0
# iMax/pidMax/posErrMax: sized so that IF the I-term is allowed to wind
# up (test 2's own scenario), it has enough authority to plausibly
# overcome stiction -- that is what an integral term is FOR. Not sized
# to guarantee test 1's outcome: test 1's duty stays at feedforward
# ONLY because posError is held at exactly 0 by K2, never because these
# clamps are small (they are not visited at all while advanced==false).
I_MAX = 16000.0       # [counts/s] up to 20% duty of authority
PID_MAX = 20000.0     # [counts/s] wider than iMax so iMax binds first
POS_ERR_MAX = 5000.0  # [counts] loose enough to let the I-term climb
                      # for ~500 ticks (~12 s) before K3 anti-windup caps it

MAX_DUTY_PERCENT = 100.0

# ---- stiction plant: BREAKAWAY_DUTY is sourced from THIS SPRINT's own
# hardware measurement of what reliably breaks a wheel loose -- ticket
# 003's pulse-characterization gate, captures/039-003-pulse-gate-
# 20260916/notes.md: "15% duty for 2 ticks gives 1.79 mm with sd/mean
# 0.08 and zero dead pulses" -- not tuned against this file's own
# outcome. STEP_COUNTS mirrors ticket 004's own default (10.0 counts/
# qualifying tick): this investigation cares about WHETHER the wheel
# ever clears breakaway, not the exact post-breakaway magnitude, so
# reusing that file's already-documented "clean, round, host-test-
# friendly" constant is correct rather than inventing a second one.
BREAKAWAY_DUTY = 0.15  # [1] duty fraction -- MEASURED anchor above
STEP_COUNTS = 10.0     # [counts] per qualifying tick (ticket 004's default)


def _bind(lib):
    lib.mnCreate.argtypes = []
    lib.mnCreate.restype = ctypes.c_void_p
    lib.mnDestroy.argtypes = [ctypes.c_void_p]
    lib.mnDestroy.restype = None
    lib.mnBegin.argtypes = [ctypes.c_void_p]
    lib.mnBegin.restype = ctypes.c_int
    lib.mnStep.argtypes = [ctypes.c_void_p]
    lib.mnStep.restype = None
    lib.mnCycleCount.argtypes = [ctypes.c_void_p]
    lib.mnCycleCount.restype = ctypes.c_uint32

    lib.mnClockAdvance.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.mnClockAdvance.restype = None

    lib.mnSetStictionParams.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_float]
    lib.mnSetStictionParams.restype = None
    lib.mnSetWithholdStampOnStiction.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.mnSetWithholdStampOnStiction.restype = None
    lib.mnPosition.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.mnPosition.restype = ctypes.c_float

    lib.mnSetTravelCalib.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetTravelCalib.restype = None
    lib.mnSetTrackWidth.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetTrackWidth.restype = None

    lib.mnConfigureCreepPlant.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
        ctypes.c_float]
    lib.mnConfigureCreepPlant.restype = None

    lib.mnSetVFloor.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetVFloor.restype = None
    lib.mnSetVMax.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetVMax.restype = None

    lib.mnWheelsV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.mnWheelsV.restype = None
    lib.mnMoveV.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.mnMoveV.restype = None
    lib.mnIsDriving.argtypes = [ctypes.c_void_p]
    lib.mnIsDriving.restype = ctypes.c_int
    lib.mnService.argtypes = [ctypes.c_void_p]
    lib.mnService.restype = ctypes.c_int

    lib.mnOutVelocityLeft.argtypes = [ctypes.c_void_p]
    lib.mnOutVelocityLeft.restype = ctypes.c_float
    lib.mnOutVelocityRight.argtypes = [ctypes.c_void_p]
    lib.mnOutVelocityRight.restype = ctypes.c_float
    lib.mnOutAppliedDutyLeft.argtypes = [ctypes.c_void_p]
    lib.mnOutAppliedDutyLeft.restype = ctypes.c_float
    lib.mnOutAppliedDutyRight.argtypes = [ctypes.c_void_p]
    lib.mnOutAppliedDutyRight.restype = ctypes.c_float
    lib.mnOutI2cFaultCount.argtypes = [ctypes.c_void_p]
    lib.mnOutI2cFaultCount.restype = ctypes.c_uint32
    lib.mnOutStallHalted.argtypes = [ctypes.c_void_p]
    lib.mnOutStallHalted.restype = ctypes.c_int
    return lib


@pytest.fixture(scope="session")
def creep_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libcreep_self_lock_stiction_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class Engine:
    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.mnCreate()

    def close(self):
        self._lib.mnDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def configure_creep_plant(self, max_duty=MAX_DUTY_PERCENT,
                              full_duty_velocity=FULL_DUTY_VELOCITY,
                              kp=KP, ki=KI, i_max=I_MAX, kaff=KAFF,
                              pid_max=PID_MAX, pos_err_max=POS_ERR_MAX):
        self._lib.mnConfigureCreepPlant(
            self._handle, max_duty, full_duty_velocity, kp, ki, i_max,
            kaff, pid_max, pos_err_max)

    def set_travel_calib(self, mm_per_deg):
        self._lib.mnSetTravelCalib(self._handle, mm_per_deg)

    def set_track_width(self, mm):
        self._lib.mnSetTrackWidth(self._handle, mm)

    def set_vfloor(self, mm_s):
        self._lib.mnSetVFloor(self._handle, mm_s)

    def set_vmax(self, mm_s):
        self._lib.mnSetVMax(self._handle, mm_s)

    def set_stiction_params(self, side, breakaway_duty, step_counts):
        self._lib.mnSetStictionParams(self._handle, side, breakaway_duty,
                                      step_counts)

    def set_withhold_stamp(self, side, enabled):
        self._lib.mnSetWithholdStampOnStiction(
            self._handle, side, 1 if enabled else 0)

    def begin(self):
        return self._lib.mnBegin(self._handle)

    def wheels_v(self, left, right, duration_ms):
        self._lib.mnWheelsV(self._handle, left, right, duration_ms)

    def clock_advance(self, delta_us):
        self._lib.mnClockAdvance(self._handle, delta_us)

    def step(self):
        self._lib.mnStep(self._handle)

    def service(self):
        return bool(self._lib.mnService(self._handle))

    def is_driving(self):
        return bool(self._lib.mnIsDriving(self._handle))

    def position(self, side):
        return self._lib.mnPosition(self._handle, side)

    def cycle_count(self):
        return self._lib.mnCycleCount(self._handle)

    def i2c_fault_count(self):
        return self._lib.mnOutI2cFaultCount(self._handle)

    def stall_halted(self):
        return bool(self._lib.mnOutStallHalted(self._handle))

    def applied_duty_left(self):
        return self._lib.mnOutAppliedDutyLeft(self._handle)

    def applied_duty_right(self):
        return self._lib.mnOutAppliedDutyRight(self._handle)

    def velocity_left(self):
        return self._lib.mnOutVelocityLeft(self._handle)


def _armed_creep_engine(lib, *, withhold_stamp, vfloor=None):
    """Builds one Engine, configured identically across every test in
    this file except `withhold_stamp` (and optionally `vfloor`), then
    arms the -4 cm/s creep hold. Shared setup so the confirm/refute
    pair in tests 1 and 2 differ in EXACTLY one input."""
    e = Engine(lib)
    e.configure_creep_plant()
    e.set_travel_calib(TRAVEL_CALIB_MM_PER_DEG)
    e.set_track_width(100.0)
    if vfloor is not None:
        e.set_vfloor(vfloor)
    e.set_stiction_params(LEFT, BREAKAWAY_DUTY, STEP_COUNTS)
    e.set_stiction_params(RIGHT, BREAKAWAY_DUTY, STEP_COUNTS)
    e.set_withhold_stamp(LEFT, withhold_stamp)
    e.set_withhold_stamp(RIGHT, withhold_stamp)
    assert e.begin() == STATUS_OK
    e.wheels_v(CREEP_MM_S, CREEP_MM_S, HOLD_DURATION_MS)
    return e


def _run_hold(e, ticks=TICKS):
    """Drives step()+service() -- mirroring Rig::tickDrive()'s own
    kernel.step() + engine.service() pairing (shims.cpp), the same
    pattern test_motion_engine_nudge_stiction.py's own docstring cites
    -- for `ticks` outer cycles of CYCLE_DT_US each."""
    for _ in range(ticks):
        e.clock_advance(CYCLE_DT_US)
        e.step()
        e.service()


def _duty_trajectory(e, ticks):
    """Like `_run_hold`, but returns the LEFT wheel's applied duty
    after every single tick (not just the final one) -- so a comparison
    across two runs catches a difference anywhere in the ramp, not only
    at steady state."""
    trajectory = []
    for _ in range(ticks):
        e.clock_advance(CYCLE_DT_US)
        e.step()
        e.service()
        trajectory.append(e.applied_duty_left())
    return trajectory


def test_creep_below_breakaway_self_locks_with_stamp_withholding(creep_lib):
    """CONFIRMS the K2 lock hypothesis in sim.

    With stamp-withholding armed (mirroring NezhaMotorPort::collect()'s
    real behavior), the commanded -4 cm/s creep's own feedforward-only
    duty (400 counts/s / 80000 counts/s = 0.5%) sits far below this
    plant's 15% breakaway. K2 never lets the I-term see a nonzero
    position error (positionError() returns the SAME frozen error every
    tick once `advanced` goes false), so duty never rises above
    feedforward. The wheel never clears breakaway, for the entire
    30 s / 1250-tick hold -- matching the bench-log capture's own shape
    (i2cf ~= cyc; camera frame showing zero displacement) without
    reproducing its exact numbers (a SIM result, not a hardware one)."""
    with _armed_creep_engine(creep_lib, withhold_stamp=True) as e:
        _run_hold(e)

        assert e.position(LEFT) == 0.0
        assert e.position(RIGHT) == 0.0

        # Duty never escaped feedforward: 400/80000 = 0.5%, with a
        # generous margin so this assertion is about "nowhere near
        # breakaway", not chasing float bit-equality.
        assert abs(e.applied_duty_left()) < 2.0  # [%] << 15% breakaway
        assert abs(e.applied_duty_right()) < 2.0

        # The bench-log's own signature: i2cf tracks cyc almost exactly
        # because the sample stamp is withheld on essentially every
        # tick (the plant is at rest from tick 1: even before the
        # shaper's ramp reaches -40 mm/s, every intermediate ramp value
        # is smaller still, so breakaway is never in reach). A handful
        # of ticks of slack is allowed for the two ticks HELD before
        # the hold's shaper starts ramping (the very first tick(s), 0
        # commanded duty, still below breakaway, still counted).
        cyc = e.cycle_count()
        i2cf = e.i2c_fault_count()
        assert cyc == TICKS
        assert i2cf >= cyc - 2

        assert not e.stall_halted()  # kernel's own stall latch never
                                     # arms at creep speed (issue's own
                                     # source reading) -- confirmed here
                                     # by construction: stallDemand was
                                     # never configured (0 = detector
                                     # off), matching mnConfigureCreepPlant
                                     # not setting it.


def test_creep_recovers_when_stamp_is_not_withheld(creep_lib):
    """REFUTATION control for the same rig: identical plant, identical
    commanded creep, identical breakaway threshold -- the ONE change is
    `withhold_stamp=False`, so K2's `advanced` gate is always true (the
    stamp advances every tick regardless of physical motion, exactly
    ticket 004's own StictionMotor default). With `advanced` always
    true, positionError() integrates the reference every tick even
    though `measured` (wheel.position) never moves, so the error grows
    without bound until K3's anti-windup clamps it at posErrMax (5000
    counts, ~521 ticks at ~9.6 counts/tick). Once clamped, ki * error
    supplies (6 * 5000 =) 30000 counts/s of raw integral authority,
    clamped by iMax to 16000 -- enough to push duty past this plant's
    15% breakaway (needs only ~1933 counts of error, ~201 ticks) well
    inside the 30 s window.

    This isolates the self-lock to K2's guard specifically: same
    plant, same gains, same breakaway, same commanded speed -- the
    ONLY thing that changes is whether the tick that never moved gets
    to integrate. If this run also stayed locked, the hypothesis would
    be refuted (something else would have to be holding it down); it
    does not."""
    with _armed_creep_engine(creep_lib, withhold_stamp=False) as e:
        _run_hold(e)

        # Recovered: the wheel is no longer at its origin, and moved in
        # the commanded (reverse) direction.
        assert e.position(LEFT) < -STEP_COUNTS
        assert e.position(RIGHT) < -STEP_COUNTS

        # And it broke free well before the hold's own 30 s deadline --
        # not just barely, at the very last tick, which would be a much
        # weaker claim (e.g. a deadline-adjacent artifact rather than a
        # genuine mid-hold recovery).
        assert e.cycle_count() == TICKS


def test_hold_vfloor_value_has_no_effect_on_commanded_ramp(creep_lib):
    """Tests the sprint plan's own suggested candidate location directly
    (not just by source reading): motion_engine.cpp's Hold branch of
    service() calls `shaper_.advance(hold_.dominant, -1.0f, 0.0f, ...)`
    -- floor 0, remain -1 -- for wheelsV()/moveV(). `remain = -1.0f` is
    hardcoded for every Hold, never derived from `limits().vFloor`. This
    test proves that VALUE never reaches anywhere it can matter: the
    only two places `VelocityShaper::advance()` reads its `floor`
    argument are (1) the floor-snap step, itself gated on
    `remain >= 0.0f` (velocity_shaper.cpp, step 4 -- "Retain the legacy
    floor only without jerk limiting"), and (2) `coastCredit`, which
    only differs when `lim.lag > 0` (this rig's lag is 0, its default).
    Since Hold's `remain` is always -1, branch (1) never fires
    regardless of what floor value is passed -- so two runs differing
    ONLY in `limits().vFloor` must produce bit-identical commanded
    trajectories for a Hold.

    Consequence for the ticket's own recommendation: the sprint plan's
    named candidate ("a floor ... for a continuous Hold ... today it
    passes floor 0") is not merely unimplemented, it is a dead
    parameter as literally described -- changing the floor VALUE fixes
    nothing. Actually giving Hold a floor would need a structural
    change (making `remain >= 0` true for a Hold, e.g. passing a very
    large sentinel instead of -1), and that structural change reverses
    a DELIBERATE, PINNED design decision from an earlier sprint:
    test_velocity_shaper.py::test_continuous_hold_has_no_floor_and_never
    _arrives (sprint 029 ticket 002) asserts exactly the opposite
    property as intentional -- "a continuous hold below the floor is a
    legitimate request, e.g. a student's own slow WHEELS_V". This
    ticket has no standing to reverse that decision; see this file's
    own module docstring and the ticket's written recommendation."""
    # Sample the FULL per-tick trajectory, not just an end-of-run
    # snapshot, so a floor-dependent difference anywhere during the
    # ramp-up (not only at steady state) would be caught.
    with _armed_creep_engine(creep_lib, withhold_stamp=True,
                             vfloor=70.0) as e_floor_default:
        trajectory_default = _duty_trajectory(e_floor_default, ticks=200)

    with _armed_creep_engine(creep_lib, withhold_stamp=True,
                             vfloor=0.0) as e_floor_zero:
        trajectory_zero = _duty_trajectory(e_floor_zero, ticks=200)

    with _armed_creep_engine(creep_lib, withhold_stamp=True,
                             vfloor=250.0) as e_floor_high:
        trajectory_high = _duty_trajectory(e_floor_high, ticks=200)

    # Sanity: the trajectory is not trivially constant-zero (it ramps),
    # so an equal-trajectories assertion below is actually exercising
    # the shaper, not comparing three flat lines.
    assert any(d != 0.0 for d in trajectory_default)

    assert trajectory_default == trajectory_zero == trajectory_high
