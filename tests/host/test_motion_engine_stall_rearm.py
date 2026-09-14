"""tests/host/test_motion_engine_stall_rearm.py -- a stall stops only the
command it happened in.

Before 2026-09-13 the kernel's stall halt (DifferentialDrive's
stallHalted_) was sticky: once a move stalled, the kernel forced neutral
on every later command until something called clearStallLatch(), so
every later Drive/Move block was silently ignored until the micro:bit was
reset. Stakeholder direction: a stall should stop the move that stalled,
the next move should try again, and the stall should stay readable until
the wheels actually turn.

MotionEngine now re-arms the kernel's halt at every public command entry
point and keeps its own sticky report (stallReported()): set when the
halt is published, cleared on the first service() tick of a later command
that measures either wheel above the kernel's stall speed. A stall also
ends a continuous hold, the same way it already ended a Segment.

src/core/diffdrive.{h,cpp} stays vendored and unmodified: this only uses
its existing setStall()/clearStallLatch()/Output.stallHalted surface.

Run with::

    uv run pytest tests/host/test_motion_engine_stall_rearm.py
"""

STATUS_OK = 0
FULL_DUTY_VELOCITY = 5000.0  # [counts/s]

STALL_SPEED = 50.0    # [counts/s] "still" at or below this
STALL_DEMAND = 200.0  # [counts/s] "demanding" above this
STALL_WINDOW = 500.0  # [ms]

TICK_MS = 24
LONG_TIMEOUT_MS = 30_000
START_MS = 1000  # never 0 -- updateLatch()'s own `since == 0` sentinel


class Engine:
    """Thin wrapper around one meCreate()/meDestroy() handle, with a
    fake clock and fake encoders the test advances tick by tick."""

    def __init__(self, lib):
        self._lib = lib
        self._h = lib.meCreate()
        self.now_ms = START_MS
        self.position = [0.0, 0.0]  # [counts] fake encoder positions

    def close(self):
        self._lib.meDestroy(self._h)
        self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def ready(self):
        self._lib.meSetMaxDuty(self._h, 100.0)
        self._lib.meSetFullDutyVelocity(self._h, FULL_DUTY_VELOCITY)
        self._lib.meSetStall(self._h, STALL_SPEED, STALL_DEMAND, STALL_WINDOW)
        assert self._lib.meBegin(self._h) == STATUS_OK
        self._lib.meClockSetNow(self._h, self.now_ms * 1000)

    def tick(self, counts_per_tick=0.0):
        """One control cycle in the order tickDrive() runs it: advance the
        clock, arm this cycle's encoder reads, kernel step(), then the
        engine's service(). counts_per_tick > 0 makes both wheels turn."""
        self.now_ms += TICK_MS
        self._lib.meClockSetNow(self._h, self.now_ms * 1000)
        for side in (0, 1):
            self.position[side] += counts_per_tick
            self._lib.meMotorArmPosition(self._h, side, self.position[side],
                                         self.now_ms * 1000)
        self._lib.meStep(self._h)
        return bool(self._lib.meServiceMove(self._h))

    def move_x(self, distance=1000.0, cruise=100.0):
        self._lib.meMoveX(self._h, distance, 0.0, cruise, LONG_TIMEOUT_MS)

    def wheels_v(self, left=100.0, right=100.0, duration_ms=60_000):
        self._lib.meWheelsV(self._h, left, right, duration_ms)

    def stall_halted(self):
        return bool(self._lib.meOutStallHalted(self._h))

    def stall_reported(self):
        return bool(self._lib.meStallReported(self._h))

    def clear_stall_report(self):
        self._lib.meClearStallReport(self._h)

    def is_driving(self):
        return bool(self._lib.meIsDriving(self._h))

    def staged_duty(self, side):
        return self._lib.meMotorLastStagedDuty(self._h, side)


def _tick_until_ended(e, max_ticks=200, counts_per_tick=0.0):
    """Tick until service() reports the command over; return tick count."""
    for n in range(1, max_ticks + 1):
        if not e.tick(counts_per_tick):
            return n
    raise AssertionError(f"command still active after {max_ticks} ticks")


def _stall_a_move(e):
    """Start a move whose wheels never turn and run it until the stall
    ends it. Leaves the engine with the kernel halt set and reported."""
    e.move_x()
    ticks = _tick_until_ended(e)
    assert e.stall_halted(), "sanity: the move should have ended on the stall"
    assert e.stall_reported()
    # 500 ms window at 24 ms/tick, plus the ramp to the demand threshold
    assert 20 <= ticks <= 40, f"stall ended the move after {ticks} ticks"


def test_a_stall_ends_the_move_and_is_reported(motion_lib):
    with Engine(motion_lib) as e:
        e.ready()
        assert not e.stall_reported()
        _stall_a_move(e)
        assert not e.is_driving()


def test_the_next_move_is_not_blocked_by_an_earlier_stall(motion_lib):
    """The bug this file exists for: before the fix, the kernel stayed
    forced-neutral and this second move never staged any duty."""
    with Engine(motion_lib) as e:
        e.ready()
        _stall_a_move(e)

        e.move_x()
        assert e.tick(), "the new move must run, not end on the old stall"
        assert not e.stall_halted(), "a new command re-arms the kernel halt"
        for _ in range(5):
            assert e.tick()
        assert e.staged_duty(0) > 0.0 and e.staged_duty(1) > 0.0, (
            "the new move must actually drive the motors")
        # No wheel motion measured yet, so the report still stands.
        assert e.stall_reported()


def test_the_report_clears_once_a_later_move_turns_the_wheels(motion_lib):
    with Engine(motion_lib) as e:
        e.ready()
        _stall_a_move(e)

        e.move_x()
        # ~833 counts/s, well above STALL_SPEED
        for _ in range(4):
            assert e.tick(counts_per_tick=20.0)
        assert not e.stall_reported()
        assert not e.stall_halted()


def test_a_still_jammed_motor_stalls_again_on_the_next_move(motion_lib):
    """Re-arming must not remove the protection: a wheel that still does
    not turn trips the detector again after its own window."""
    with Engine(motion_lib) as e:
        e.ready()
        _stall_a_move(e)

        e.move_x()
        ticks = _tick_until_ended(e)
        assert e.stall_halted()
        assert e.stall_reported()
        assert 20 <= ticks <= 40


def test_a_stall_ends_a_continuous_hold(motion_lib):
    """setWheelSpeeds()/driveTwist() holds used to sit halted for their
    whole lease with isDriving() true, so a `while (driveTick())` loop
    spun over a stopped robot. A stall now ends the hold."""
    with Engine(motion_lib) as e:
        e.ready()
        e.wheels_v()
        ticks = _tick_until_ended(e)
        assert e.stall_halted()
        assert e.stall_reported()
        assert not e.is_driving()
        assert ticks <= 40


def test_a_hold_after_a_stall_drives_again(motion_lib):
    with Engine(motion_lib) as e:
        e.ready()
        _stall_a_move(e)

        e.wheels_v()
        for _ in range(6):
            assert e.tick(counts_per_tick=20.0)
        assert not e.stall_halted()
        assert not e.stall_reported()
        assert e.staged_duty(0) > 0.0


def test_clear_stall_report(motion_lib):
    with Engine(motion_lib) as e:
        e.ready()
        _stall_a_move(e)
        e.clear_stall_report()
        assert not e.stall_reported()
