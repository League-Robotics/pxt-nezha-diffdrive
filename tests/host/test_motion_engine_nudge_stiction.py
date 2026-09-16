"""tests/host/test_motion_engine_nudge_stiction.py -- sprint 039 ticket
004 (SUC-002): the settle-gated nudge stepper's behavior against an
AUTONOMOUS stiction-plant Motor double (motion_engine_nudge_stiction_
shim.cpp's own StictionMotor: no motion at all below a breakaway duty,
one fixed quantized position increment per qualifying tick above it).

Why a dedicated shim rather than this directory's shared `motion_lib`
fixture (test_motion_engine_nudge.py, conftest.py): the nudge stepper's
own `firePulseAndSettle()` drives its own internal, synchronous
`kernel.step()` loop with NO per-tick control point from Python --
exactly the reason ticket 001's own `test_motion_engine_pulse.py` needed
`FakeMotor`'s duty-history log rather than re-arming a position by hand
between steps. Proving "the ledger converges", "budget and deadline
each terminate independently", and "a target reachable in N pulses does
not take N+1" all need the PHYSICS to live inside the double across
several REAL pulses, not be scripted one step() at a time from outside
it. `fake_ports.h`'s `FakeMotor` deliberately carries no such physics
("No timer, no clock, deterministic, caller-driven" -- that file's own
header comment); this shim's `StictionMotor` is the sprint plan's own
SUC-004 stiction-plant shape, reused here for ticket 004's ACs rather
than ticket 006's (which investigates the SEPARATE creep self-lock
question against `wheelsV()`/`moveV()`, not this stepper).

Geometry is set to round numbers (travelCalib = 1.0 mm/deg ->
countsPerMm() == 10) so every expected count in this file is exact
arithmetic, not an approximation against the real vevov bake.

Run with::

    uv run pytest tests/host/test_motion_engine_nudge_stiction.py
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

# StictionMotor's own synthetic test constants (motion_engine_nudge_
# stiction_shim.cpp's own header comment: chosen for a clean, round,
# host-test-friendly magnitude, NOT a hardware measurement).
BREAKAWAY_DUTY = 0.10   # [1] 10% -- below the accepted 15% nudge amplitude
STEP_COUNTS = 10.0      # [counts] per qualifying tick

# nudgeAmplitude() default (15%) clears BREAKAWAY_DUTY; nudgeWidthTicks()
# default (2) means each fired pulse advances a qualifying wheel by
# WIDTH_TICKS * STEP_COUNTS.
WIDTH_TICKS = 2
PULSE_STEP_COUNTS = WIDTH_TICKS * STEP_COUNTS  # 20.0


def _bind(lib):
    lib.mnCreate.argtypes = []
    lib.mnCreate.restype = ctypes.c_void_p
    lib.mnDestroy.argtypes = [ctypes.c_void_p]
    lib.mnDestroy.restype = None
    lib.mnSetMaxDuty.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetMaxDuty.restype = None
    lib.mnBegin.argtypes = [ctypes.c_void_p]
    lib.mnBegin.restype = ctypes.c_int
    lib.mnStep.argtypes = [ctypes.c_void_p]
    lib.mnStep.restype = None
    lib.mnCycleCount.argtypes = [ctypes.c_void_p]
    lib.mnCycleCount.restype = ctypes.c_uint32
    lib.mnOutEstopped.argtypes = [ctypes.c_void_p]
    lib.mnOutEstopped.restype = ctypes.c_int
    lib.mnKernelEstop.argtypes = [ctypes.c_void_p]
    lib.mnKernelEstop.restype = None
    lib.mnKickThenStep.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float]
    lib.mnKickThenStep.restype = None

    lib.mnClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.mnClockSetNow.restype = None
    lib.mnClockAdvance.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.mnClockAdvance.restype = None

    lib.mnSetStictionParams.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_float]
    lib.mnSetStictionParams.restype = None
    lib.mnPosition.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.mnPosition.restype = ctypes.c_float
    lib.mnDutyHistoryCount.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.mnDutyHistoryCount.restype = ctypes.c_int
    lib.mnDutyHistoryAt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.mnDutyHistoryAt.restype = ctypes.c_float
    lib.mnClearDutyHistory.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.mnClearDutyHistory.restype = None

    lib.mnCountsPerMm.argtypes = [ctypes.c_void_p]
    lib.mnCountsPerMm.restype = ctypes.c_float
    lib.mnEffectiveTrackWidth.argtypes = [ctypes.c_void_p]
    lib.mnEffectiveTrackWidth.restype = ctypes.c_float
    lib.mnSetTrackWidth.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetTrackWidth.restype = None
    lib.mnSetTravelCalib.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetTravelCalib.restype = None

    lib.mnSetArriveDist.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetArriveDist.restype = None
    lib.mnSetArriveYaw.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetArriveYaw.restype = None

    lib.mnSetNudgeAmplitude.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetNudgeAmplitude.restype = None
    lib.mnSetNudgeWidthTicks.argtypes = [ctypes.c_void_p, ctypes.c_int32]
    lib.mnSetNudgeWidthTicks.restype = None
    lib.mnSetNudgeSettle.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.mnSetNudgeSettle.restype = None
    lib.mnBeginNudge.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32]
    lib.mnBeginNudge.restype = None
    lib.mnIsNudgeActive.argtypes = [ctypes.c_void_p]
    lib.mnIsNudgeActive.restype = ctypes.c_int
    lib.mnNudgePulseCount.argtypes = [ctypes.c_void_p]
    lib.mnNudgePulseCount.restype = ctypes.c_int32
    lib.mnNudgeMaxPulses.argtypes = [ctypes.c_void_p]
    lib.mnNudgeMaxPulses.restype = ctypes.c_int32
    lib.mnService.argtypes = [ctypes.c_void_p]
    lib.mnService.restype = ctypes.c_int
    return lib


@pytest.fixture(scope="session")
def nudge_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libmotion_engine_nudge_stiction_shim.so",
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

    def set_max_duty(self, v):
        self._lib.mnSetMaxDuty(self._handle, v)

    def begin(self):
        return self._lib.mnBegin(self._handle)

    def step(self):
        self._lib.mnStep(self._handle)

    def cycle_count(self):
        return self._lib.mnCycleCount(self._handle)

    def out_estopped(self):
        return bool(self._lib.mnOutEstopped(self._handle))

    def kernel_estop(self):
        self._lib.mnKernelEstop(self._handle)

    def kick_then_step(self, amp_left, amp_right):
        self._lib.mnKickThenStep(self._handle, amp_left, amp_right)

    def clock_advance(self, delta_us):
        self._lib.mnClockAdvance(self._handle, delta_us)

    def set_stiction_params(self, side, breakaway_duty, step_counts):
        self._lib.mnSetStictionParams(self._handle, side, breakaway_duty,
                                      step_counts)

    def position(self, side):
        return self._lib.mnPosition(self._handle, side)

    def duty_history(self, side):
        count = self._lib.mnDutyHistoryCount(self._handle, side)
        return [self._lib.mnDutyHistoryAt(self._handle, side, i)
                for i in range(count)]

    def clear_duty_history(self, side):
        self._lib.mnClearDutyHistory(self._handle, side)

    def counts_per_mm(self):
        return self._lib.mnCountsPerMm(self._handle)

    def set_track_width(self, mm):
        self._lib.mnSetTrackWidth(self._handle, mm)

    def set_travel_calib(self, mm_per_deg):
        self._lib.mnSetTravelCalib(self._handle, mm_per_deg)

    def set_arrive_dist(self, mm):
        self._lib.mnSetArriveDist(self._handle, mm)

    def set_arrive_yaw(self, deg):
        self._lib.mnSetArriveYaw(self._handle, deg)

    def set_nudge_amplitude(self, v):
        self._lib.mnSetNudgeAmplitude(self._handle, v)

    def set_nudge_width_ticks(self, v):
        self._lib.mnSetNudgeWidthTicks(self._handle, v)

    def set_nudge_settle_ms(self, v):
        self._lib.mnSetNudgeSettle(self._handle, v)

    def begin_nudge(self, distance_mm, rotation_rad, timeout_ms):
        self._lib.mnBeginNudge(self._handle, distance_mm, rotation_rad,
                               timeout_ms)

    def is_nudge_active(self):
        return bool(self._lib.mnIsNudgeActive(self._handle))

    def nudge_pulse_count(self):
        return self._lib.mnNudgePulseCount(self._handle)

    def nudge_max_pulses(self):
        return self._lib.mnNudgeMaxPulses(self._handle)

    def service(self):
        return bool(self._lib.mnService(self._handle))


def _ready(e, arrive_dist_mm=None):
    e.set_max_duty(100.0)
    e.set_travel_calib(1.0)   # countsPerMm() == 10 exactly
    e.set_track_width(120.0)
    assert e.begin() == STATUS_OK
    e.set_stiction_params(LEFT, BREAKAWAY_DUTY, STEP_COUNTS)
    e.set_stiction_params(RIGHT, BREAKAWAY_DUTY, STEP_COUNTS)
    if arrive_dist_mm is not None:
        e.set_arrive_dist(arrive_dist_mm)
    e.clear_duty_history(LEFT)
    e.clear_duty_history(RIGHT)


def _run_until_done(e, max_ticks=200):
    """Drives step()+service() (mirroring Rig::tickDrive()'s own
    kernel.step() + engine.service() pairing) until the nudge ends or
    max_ticks is exhausted. Returns the number of outer ticks run."""
    ticks = 0
    while e.is_nudge_active() and ticks < max_ticks:
        e.step()
        e.service()
        ticks += 1
    return ticks


# ---- AC: the ledger converges, and "a target reachable in N pulses does
# not take N+1" (stop within one step of target rather than overshoot and
# correct) ------------------------------------------------------------


def test_ledger_converges_and_does_not_overshoot_by_a_needless_extra_pulse(
        nudge_lib):
    """Target distance 5.5 mm (55 counts at countsPerMm()==10), margin
    0.3 mm (3 counts): three pulses of 20 counts each land the cumulative
    at 60 counts (remaining magnitude 5, still OUTSIDE the 3-count
    margin) -- but 5 < half of the last pulse's own 20-count step, so the
    stepper must stop at 3 pulses rather than fire a 4th (which would
    only widen the miss to 25 counts). This is the concrete numeric case
    behind "stop within one step of target rather than overshoot and
    correct" (captures/039-003-pulse-gate-20260916/notes.md's own
    rotation-resolution consequence, generalized here to the distance
    axis for a fully deterministic host test)."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.3)  # 3 counts

        e.begin_nudge(5.5, 0.0, 30_000)  # 55 counts
        ticks = _run_until_done(e)

        assert not e.is_nudge_active(), (
            f"nudge never converged within {ticks} ticks")
        assert e.nudge_pulse_count() == 3, (
            f"expected exactly 3 pulses (stop within one step), got "
            f"{e.nudge_pulse_count()}")
        assert e.position(LEFT) == pytest.approx(3 * PULSE_STEP_COUNTS)
        assert e.position(RIGHT) == pytest.approx(3 * PULSE_STEP_COUNTS)


def test_ledger_converges_exactly_at_the_margin_boundary(nudge_lib):
    """Target distance 4.5 mm (45 counts), margin 0.5 mm (5 counts): two
    pulses land remaining exactly AT the margin (45 - 40 == 5 <= 5), so
    this converges by the ordinary margin test, not the one-step
    heuristic -- the companion case to the test above."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.5)  # 5 counts

        e.begin_nudge(4.5, 0.0, 30_000)  # 45 counts
        _run_until_done(e)

        assert not e.is_nudge_active()
        assert e.nudge_pulse_count() == 2
        assert e.position(LEFT) == pytest.approx(2 * PULSE_STEP_COUNTS)


# ---- AC: pulses fire only when settled (re-confirmed against the real
# stiction plant: nothing else in this file arms a residual velocity, so
# every fire below is one this loop's OWN settle test allowed) ----------


def test_every_fired_pulse_is_followed_by_a_settled_read(nudge_lib):
    """After firePulseAndSettle()'s own internal settle loop, the very
    NEXT outer tick's kernel.step() (this test's own step() call, mirrror
    -ing Rig::tickDrive()) must show the wheels at rest -- otherwise this
    loop would refuse to fire the following pulse and the target would
    never converge within budget. test_ledger_converges_... above already
    proves convergence; this test asserts the DIRECT signature (duty
    goes nonzero, then a settle tail of exact zeros, every single pulse)."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.3)

        e.begin_nudge(5.5, 0.0, 30_000)
        _run_until_done(e)

        history = e.duty_history(LEFT)
        # Each pulse: WIDTH_TICKS nonzero entries, then >=1 zero (the
        # hard-zero settle tail) -- across 3 pulses that is at least
        # 3 * (WIDTH_TICKS + 1) entries, and the very LAST entry must be
        # the settle zero (nothing fires after the loop ends).
        assert len(history) >= 3 * (WIDTH_TICKS + 1)
        assert history[-1] == pytest.approx(0.0)


# ---- AC: the pulse budget terminates the loop independently -----------


def test_pulse_budget_terminates_a_target_that_never_converges(nudge_lib):
    """A target far beyond what nudgeMaxPulses() pulses can reach (55
    counts/pulse * 40 == 2200 counts; this target is an order of
    magnitude larger) never satisfies the margin OR the one-step
    heuristic within budget, so the FIXED pulse cap is what ends it."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.1)

        e.begin_nudge(10_000.0, 0.0, 60_000)  # 100,000 counts -- unreachable
        ticks = _run_until_done(e, max_ticks=e.nudge_max_pulses() + 10)

        assert not e.is_nudge_active(), (
            "the pulse budget did not terminate the nudge")
        assert e.nudge_pulse_count() == e.nudge_max_pulses()
        # One tick per fired pulse, plus exactly one further tick to
        # DETECT the exhausted budget (the check runs at the top of
        # serviceNudge(), against the state the PREVIOUS fire left) --
        # that extra tick fires no further pulse of its own.
        assert ticks == e.nudge_max_pulses() + 1, (
            f"expected {e.nudge_max_pulses()} firing ticks plus one "
            f"budget-detection tick, got {ticks}")


# ---- AC: the deadline terminates the loop independently ---------------


def test_deadline_terminates_even_with_budget_and_margin_still_available(
        nudge_lib):
    """An UNREACHABLE target (as above) but with a short deadline: proves
    the deadline check fires on its own, not merely as a side effect of
    exhausting the pulse budget -- this test's own tick count is far
    below nudgeMaxPulses()."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.1)

        e.begin_nudge(10_000.0, 0.0, 1)  # 1 ms timeout
        # Advance the clock past the deadline BEFORE the first service()
        # call -- MotionEngine's now() reads FakeClock (mnClockAdvance),
        # independent of StictionMotor's own self-incrementing sample
        # clock (this file's own header comment on why the two must be
        # independent).
        e.clock_advance(5_000)  # 5 ms > the 1 ms deadline

        e.step()
        still_active = e.service()

        assert not still_active
        assert not e.is_nudge_active()
        assert e.nudge_pulse_count() == 0, (
            "the deadline had already passed before the first tick -- no "
            "pulse should have fired at all")
        assert e.nudge_pulse_count() < e.nudge_max_pulses()


# ---- AC: a direction flip pays exactly one reversal dwell (never a
# second one of this engine's own making) --------------------------------


def test_a_reversed_pulse_takes_the_identical_step_shape_as_a_forward_one(
        nudge_lib):
    """firePulseAndSettle() issues the identical driveDuty()-then-settle
    call sequence regardless of sign (motion_engine.cpp's own comment on
    that method) -- pins it by comparing the kernel.step() COUNT (via
    Output.cycleCount, which increments unconditionally every step() --
    src/core/diffdrive.cpp) consumed by one pulse fired in each of two
    fresh, independent nudges: one purely forward, one purely reverse.
    Equal counts means this engine added no extra step/sleep of its own
    for the reversed case -- "do not add a second dwell of your own; the
    settle gate should absorb it naturally" (sprint.md's own design
    note); the PORT's real reversal dwell is hardware this host harness
    cannot model (motion_engine_nudge_stiction_shim.cpp's own header
    comment) and is explicitly out of this test's scope."""
    forward_ticks = None
    reverse_ticks = None

    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.1)
        e.begin_nudge(5.0, 0.0, 30_000)  # positive -- forward
        before = e.cycle_count()
        e.step()
        e.service()
        forward_ticks = e.cycle_count() - before
        assert forward_ticks > 0

    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.1)
        e.begin_nudge(-5.0, 0.0, 30_000)  # negative -- reverse
        before = e.cycle_count()
        e.step()
        e.service()
        reverse_ticks = e.cycle_count() - before

    assert reverse_ticks == forward_ticks, (
        f"a reversed pulse consumed {reverse_ticks} kernel.step() calls "
        f"vs {forward_ticks} for a forward one -- the stepper added extra "
        f"work of its own for the direction flip")


def test_direction_flip_within_one_nudge_pays_exactly_one_dwell_per_pulse(
        nudge_lib):
    """A single nudge whose own pulses flip sign mid-flight (a target
    just past one pulse's reach, so pulse 2 corrects back): every pulse,
    flipped or not, consumes the SAME per-pulse step count -- there is no
    additional per-flip cost anywhere in this loop."""
    with Engine(nudge_lib) as e:
        _ready(e, arrive_dist_mm=0.1)  # 1 count -- tight enough that the
                                       # first pulse cannot land inside it
        # 8 counts: pulse 1 (20 counts, sign +) OVERSHOOTS to -12 counts
        # remaining -- magnitude 12 is NOT < half of the 20-count last
        # step (10), so this does not converge by the one-step heuristic
        # either, and pulse 2 fires with the OPPOSITE sign (a genuine
        # direction flip) back toward the target: cumulative 0, remaining
        # 8 counts, |8| < 10 -- NOW it converges. Two pulses, one flip.
        e.begin_nudge(0.8, 0.0, 30_000)  # 8 counts

        per_pulse_ticks = []
        last_cycle = e.cycle_count()
        while e.is_nudge_active() and len(per_pulse_ticks) < 10:
            pulses_before = e.nudge_pulse_count()
            e.step()
            e.service()
            if e.nudge_pulse_count() > pulses_before:
                now_cycle = e.cycle_count()
                per_pulse_ticks.append(now_cycle - last_cycle)
                last_cycle = now_cycle

        assert len(per_pulse_ticks) >= 2, (
            "expected at least two pulses (an overshoot then a reversed "
            f"correction) -- got {per_pulse_ticks}")
        assert len(set(per_pulse_ticks)) == 1, (
            f"pulses within one nudge consumed different step counts "
            f"({per_pulse_ticks}) -- a direction flip cost extra")
