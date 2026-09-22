"""tests/host/test_wheel_command_tap.py -- sprint 040 ticket 003:
`src/motion/wheel_command_tap.h` (`diffDrive::WheelCommandTap`), the
optional observer `MotionEngine` notifies with the shaped per-wheel
`(left, right)` mm/s alongside every `kernel_.drive()` call, and
`onNeutral()` alongside every `kernel_.neutral()` call
(docs/design/cutebot-pro-support.md §3.D).

Uses `motion_engine_shim.cpp`'s `FakeWheelCommandTap` (every `Handle`
owns one, but `engine.setWheelCommandTap()` is only ever called through
`meTapInstall()` -- a handle that never calls it is the "no tap"
state), driven through the REAL `MotionEngine::service()`/`beginSegment()`/
`beginNudge()`/`endMove()`/`pulseWheels()`, unmodified.

**What "the tap sees exactly what the kernel receives" means here, and
how it is checked independently of the tap's own arithmetic**: the
kernel is configured exactly as `test_motion_engine_primitives.py`
does it (`setMaxDuty(100)` + `setFullDutyVelocity(fdv)`, every other
`Config` field left at its zero/off default) so `controlStep()` stages
`duty = (velocity - twist or + twist) / fullDutyVelocity` as PURE
feedforward -- no PID/bias/twist-hold contribution. A tick's tap
record is compared against `motor_last_staged_duty(side) * fdv / cpm`,
the wheel's ACTUAL applied mm/s reconstructed from what the kernel
itself staged, not against a second copy of MotionEngine's own
`velocity - twist` / `velocity + twist` arithmetic -- that would only
prove the test and the tap agree with each other, not that either
agrees with the kernel.

**Sign convention** (`docs/design/design.md`'s unit ladder,
`src/core/diffdrive.cpp:605-606`'s own `rawLeft = velocity - twist`,
`rawRight = velocity + twist`, and `test_motion_engine_primitives.py`'s
own pin of the identical decomposition): `notifyDrive()`'s two
arguments are `velocity - twist` (left) and `velocity + twist` (right),
the exact split the kernel performs internally on the SAME
(velocity, twist) mm/s a call site is handing `kernel_.drive()`.

Phase values are `diffDrive::VelocityShaper::Phase`'s declaration
order: 0 = kAccel, 1 = kCruise, 2 = kBrake (velocity_shaper.h).

Run with::

    uv run pytest tests/host/test_wheel_command_tap.py
"""

import math

import pytest


LEFT = 0
RIGHT = 1

STATUS_OK = 0
STATUS_REFUSED_UNCONFIGURED = 1

FULL_DUTY_VELOCITY = 5000.0  # [counts/s]
_DUTY_REL = 1e-4  # same tolerance test_motion_engine_primitives.py uses

PHASE_ACCEL = 0
PHASE_CRUISE = 1
PHASE_BRAKE = 2

TICK_MS = 24.0
_MAX_TICKS = 4000


class Engine:
    """Thin Pythonic wrapper around one meCreate()/meDestroy() handle --
    this file's own subset, same shape as every other
    motion_engine_shim.cpp test file's Engine wrapper."""

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

    # ---- kernel ----
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

    def out_estopped(self):
        return bool(self._lib.meOutEstopped(self._handle))

    def kernel_estop(self):
        self._lib.meKernelEstop(self._handle)

    def set_stall(self, speed, demand, window):
        self._lib.meSetStall(self._handle, speed, demand, window)

    # ---- MotionEngine geometry ----
    def counts_per_mm(self):
        return self._lib.meCountsPerMm(self._handle)

    def set_accel(self, v):
        self._lib.meLimitsSetAccel(self._handle, v)

    def set_decel(self, v):
        self._lib.meLimitsSetDecel(self._handle, v)

    def set_v_max(self, v):
        self._lib.meLimitsSetVMax(self._handle, v)

    # ---- the two primitives + reductions ----
    def wheels_v(self, left, right, duration_ms):
        self._lib.meWheelsV(self._handle, left, right, duration_ms)

    def wheels_x(self, left, right, cruise, timeout_ms):
        self._lib.meWheelsX(self._handle, left, right, cruise, timeout_ms)

    def move_x(self, distance, rotation, cruise, timeout_ms):
        self._lib.meMoveX(self._handle, distance, rotation, cruise,
                          timeout_ms)

    def service_move(self):
        return bool(self._lib.meServiceMove(self._handle))

    def is_move_active(self):
        return bool(self._lib.meIsMoveActive(self._handle))

    def end_move(self):
        self._lib.meEndMove(self._handle)

    def wrong_way_count(self):
        return self._lib.meWrongWayCount(self._handle)

    def pulse_wheels(self, amp_left, amp_right, width_ticks):
        self._lib.mePulseWheels(self._handle, amp_left, amp_right,
                                width_ticks)

    def begin_nudge(self, distance_mm, rotation_rad, timeout_ms):
        self._lib.meBeginNudge(self._handle, distance_mm, rotation_rad,
                               timeout_ms)

    # ---- WheelCommandTap ----
    def tap_install(self):
        self._lib.meTapInstall(self._handle)

    def tap_uninstall(self):
        self._lib.meTapUninstall(self._handle)

    def tap_clear(self):
        self._lib.meTapClear(self._handle)

    def tap_record_count(self):
        return self._lib.meTapRecordCount(self._handle)

    def tap_records(self):
        """Every tap call so far, in order, as
        ("drive", left, right, phase) or ("neutral", None, None, None)."""
        out = []
        for i in range(self.tap_record_count()):
            kind = self._lib.meTapRecordKind(self._handle, i)
            if kind == 0:
                out.append((
                    "drive",
                    self._lib.meTapRecordLeft(self._handle, i),
                    self._lib.meTapRecordRight(self._handle, i),
                    self._lib.meTapRecordPhase(self._handle, i),
                ))
            else:
                out.append(("neutral", None, None, None))
        return out


def _ready(engine):
    engine.set_max_duty(100.0)
    engine.set_full_duty_velocity(FULL_DUTY_VELOCITY)
    assert engine.begin() == STATUS_OK
    return FULL_DUTY_VELOCITY


def _expected_mm_s(duty, fdv, cpm):
    return duty * fdv / cpm


def _run_move_x(motion_lib, distance_mm, cruise_mm_s, timeout_ms=60_000,
                max_ticks=_MAX_TICKS):
    """Ticks the real service() at a realistic cadence, integrating each
    wheel's encoder position from the ACTUAL last-staged duty -- same
    closed-loop technique test_motion_engine_acceleration_profile.py's
    own _run_move() uses (reimplemented independently here, no
    cross-file import, matching this test tree's own convention).
    Returns the ordered list of every tap call across the whole move."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        e.tap_install()
        e.set_clock(0)
        e.move_x(distance_mm, 0.0, cruise_mm_s, timeout_ms)
        pos = {LEFT: 0.0, RIGHT: 0.0}
        duty = {LEFT: 0.0, RIGHT: 0.0}
        t_ms = 0.0
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
            if not active:
                break
        return e.tap_records()


# ---- no tap installed: zero behaviour change -----------------------------


def test_no_tap_installed_records_nothing_and_changes_nothing(motion_lib):
    """A handle that never calls meTapInstall() (every other host test
    file in this shared library, forever) must behave exactly as it did
    before WheelCommandTap existed: the tap log stays empty across a
    real move, and the commanded duty is unaffected -- this IS the
    "byte-identical with no tap installed" acceptance criterion, made
    concrete rather than argued from the null check alone."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.wheels_x(300.0, 300.0, 150.0, 5000)
        e.step()
        e.service_move()
        e.step()
        assert e.motor_last_staged_duty(LEFT) != 0.0, (
            "sanity: the move must actually be commanding something, "
            "else this test cannot distinguish 'no tap' from 'nothing "
            "happened yet'."
        )
        assert e.tap_record_count() == 0


# ---- onDrive() carries the identical numbers the kernel receives --------


def test_ondrive_matches_kernel_for_a_segment_tick(motion_lib):
    """wheelsX() with unequal per-wheel distances (a genuine nonzero
    twist, not just a symmetric straight leg) -- the tap's first onDrive()
    record must reconstruct to the SAME per-wheel mm/s the kernel
    actually staged as duty, independently derived (see this file's own
    header comment)."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        e.tap_install()
        e.wheels_x(300.0, 150.0, 200.0, 60_000)  # unequal -> nonzero twist
        e.step()
        e.service_move()
        e.step()

        expected_left = _expected_mm_s(e.motor_last_staged_duty(LEFT), fdv, cpm)
        expected_right = _expected_mm_s(e.motor_last_staged_duty(RIGHT), fdv, cpm)
        assert expected_left != expected_right, (
            "sanity: an unequal wheelsX() must produce a nonzero twist, "
            "else this test cannot tell left/right apart."
        )

        records = e.tap_records()
        drives = [r for r in records if r[0] == "drive"]
        assert len(drives) == 1
        _, left, right, _phase = drives[0]
        assert left == pytest.approx(expected_left, rel=_DUTY_REL)
        assert right == pytest.approx(expected_right, rel=_DUTY_REL)


def test_ondrive_matches_kernel_for_a_hold_tick(motion_lib):
    """wheelsV() (a continuous hold) with unequal left/right -- same
    independent-reconstruction proof as the segment test above, for the
    OTHER kernel_.drive() call site (motion_engine.cpp's hold branch).
    Unlike a Segment, a fresh hold ramps from v=0 at `accel` with NO
    floor snap (motion_engine.h's own doc comment on wheelsV() / this
    file's own header comment) -- so the clock must actually advance
    (mirroring test_motion_engine_primitives.py's own
    land_steady_state_hold()) for tick 1 to command anything nonzero at
    all."""
    with Engine(motion_lib) as e:
        fdv = _ready(e)
        cpm = e.counts_per_mm()
        e.tap_install()
        e.set_clock(0)
        e.wheels_v(150.0, 50.0, 60_000)
        e.step()
        e.set_clock(1_000_000)  # 1 s later -- past the ramp to full speed
        e.service_move()
        e.step()

        expected_left = _expected_mm_s(e.motor_last_staged_duty(LEFT), fdv, cpm)
        expected_right = _expected_mm_s(e.motor_last_staged_duty(RIGHT), fdv, cpm)
        assert expected_left != expected_right

        drives = [r for r in e.tap_records() if r[0] == "drive"]
        assert len(drives) == 1
        _, left, right, _phase = drives[0]
        assert left == pytest.approx(expected_left, rel=_DUTY_REL)
        assert right == pytest.approx(expected_right, rel=_DUTY_REL)


# ---- onNeutral() on every path that calls kernel_.neutral() -------------


def test_onneutral_on_arrival(motion_lib):
    """A short, CLOSED-LOOP move (encoders driven from the kernel's own
    actual applied duty, not left unarmed) reaches its target and ends
    via step.arriving -- service()'s arrival branch -- and must notify
    onNeutral() there. (An open-loop "no motor position ever armed"
    move, the pattern the deadline/estop/wrongWay tests below use on
    purpose, can NEVER arrive: remain is measured off real encoder
    progress, so it stays at the full target forever and the move can
    only end on its deadline -- see _run_move_x()'s own header comment
    for the closed-loop technique this test needs instead.)"""
    records = _run_move_x(motion_lib, distance_mm=5.0, cruise_mm_s=100.0,
                          timeout_ms=30_000)
    assert records, "expected at least one tap call across the move"
    assert records[-1] == ("neutral", None, None, None)
    assert any(r[0] == "drive" for r in records), (
        "sanity: the move must have actually driven before arriving"
    )


def test_onneutral_on_deadline_expiry(motion_lib):
    """A move whose wheels never turn (no motor position armed) never
    arrives on its own -- it can only end on its own deadline, which
    hits the SAME combined abort branch as wrongWay/stall/estop."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.set_clock(0)
        e.move_x(1000.0, 0.0, 100.0, 100)  # 100 ms deadline
        e.step()
        still_active = e.service_move()
        assert still_active, "sanity: must still be running before the deadline"

        e.set_clock(500_000)  # 500 ms -- well past the 100 ms deadline
        e.step()
        still_active = e.service_move()
        assert not still_active
        assert e.tap_records()[-1] == ("neutral", None, None, None)


def test_onneutral_on_estop(motion_lib):
    """kernel.estop() latched DIRECTLY (never through endMove()) still
    reaches the same abort branch on the very next service() call --
    mirrors test_motion_engine_estop_and_refusal.py's own precedent."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.move_x(1000.0, 0.0, 100.0, 30_000)
        for _ in range(3):
            e.step()
            still_active = e.service_move()
        assert still_active
        assert not e.out_estopped()

        e.kernel_estop()
        e.step()
        assert e.out_estopped()
        still_active = e.service_move()
        assert not still_active
        assert e.tap_records()[-1] == ("neutral", None, None, None)


def test_onneutral_on_refused_drive_segment(motion_lib):
    """maxDuty == 0 refuses every kernel_.drive() call
    (kRefusedUnconfigured) -- service()'s own refusal check must still
    notify onNeutral(), AND the drive() call it was refusing still
    notifies onDrive() first (this call site notifies unconditionally,
    exactly once per kernel_.drive() call, regardless of the Status that
    comes back) -- both fire on the SAME tick."""
    with Engine(motion_lib) as e:
        e.set_max_duty(0.0)
        assert e.begin() == STATUS_REFUSED_UNCONFIGURED
        e.tap_install()

        e.move_x(200.0, 0.0, 100.0, 5000)
        assert e.is_move_active()  # lazy start -- armed, nothing attempted yet

        e.step()
        still_active = e.service_move()
        assert not still_active
        records = e.tap_records()
        assert [r[0] for r in records] == ["drive", "neutral"], records


def test_onneutral_on_refused_drive_hold(motion_lib):
    """Same refusal proof as the segment test above, for the hold
    branch's own separate kernel_.drive() / kernel_.neutral() pair."""
    with Engine(motion_lib) as e:
        e.set_max_duty(0.0)
        assert e.begin() == STATUS_REFUSED_UNCONFIGURED
        e.tap_install()

        e.wheels_v(100.0, 100.0, 5000)
        e.step()
        still_active = e.service_move()
        assert not still_active
        records = e.tap_records()
        assert [r[0] for r in records] == ["drive", "neutral"], records


def test_onneutral_on_wrong_way(motion_lib):
    """A commanded CCW+ pivot that physically measures CW (the opposite
    direction) aborts via wrongWay() -- the same combined abort branch
    the deadline/estop tests above hit -- mirrors
    test_motion_engine_reductions.py's own
    test_move_x_wrong_way_abort_increments_count."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        before = e.wrong_way_count()
        rotation = 90.0 * math.pi / 180.0

        e.move_x(0.0, rotation, 100.0, 5000)
        e.step()
        e.service_move()  # lazy origin capture -- not wrongWay yet
        e.arm_motor_position_at(LEFT, 1000.0, 1_000_000)
        e.arm_motor_position_at(RIGHT, -1000.0, 1_000_000)
        e.step()

        still_active = e.service_move()
        assert not still_active
        assert e.wrong_way_count() == before + 1
        assert e.tap_records()[-1] == ("neutral", None, None, None)


def test_onneutral_on_stall_hold(motion_lib):
    """A continuous hold whose wheels never turn stalls and ends via the
    hold branch's OWN stallHalted check -- a separate call site from the
    segment abort branch above."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.set_stall(50.0, 200.0, 500.0)  # speed, demand, window
        e.tap_install()
        now_ms = 1000
        e.set_clock(now_ms * 1000)
        e.wheels_v(150.0, 150.0, 60_000)

        stalled = False
        for _ in range(80):
            now_ms += int(TICK_MS)
            e.set_clock(now_ms * 1000)
            e.arm_motor_position_at(LEFT, 0.0, now_ms * 1000)
            e.arm_motor_position_at(RIGHT, 0.0, now_ms * 1000)
            e.step()
            if not e.service_move():
                stalled = True
                break
        assert stalled, "sanity: the hold should have stalled"
        assert e.tap_records()[-1] == ("neutral", None, None, None)


def test_onneutral_on_hold_expiry(motion_lib):
    """A hold's own `duration` lease expiring (holdExpired) is a
    separate call site from stall/refusal above."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.set_clock(0)
        e.wheels_v(100.0, 100.0, 200)  # 200 ms lease
        e.step()
        still_active = e.service_move()
        assert still_active

        e.set_clock(500_000)  # past the 200 ms lease
        e.step()
        still_active = e.service_move()
        assert not still_active
        assert e.tap_records()[-1] == ("neutral", None, None, None)


def test_onneutral_on_end_move_cancel(motion_lib):
    """endMove() while a segment is active notifies onNeutral(); calling
    it again (nothing active) must NOT notify a second time -- the `if
    (seg_.active || hold_.active)` guard this call site already has."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.move_x(1000.0, 0.0, 100.0, 30_000)
        assert e.is_move_active()

        e.end_move()
        assert not e.is_move_active()
        assert e.tap_records() == [("neutral", None, None, None)]

        e.tap_clear()
        e.end_move()  # nothing active -- must be a true no-op
        assert e.tap_record_count() == 0


def test_onneutral_on_begin_segment_zero_magnitude(motion_lib):
    """beginSegment()'s own zero-magnitude early return (wheelsX(0, 0,
    ...)) calls kernel_.neutral() SYNCHRONOUSLY, before any service()
    tick -- a call site none of the service()-driven tests above ever
    reach."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.wheels_x(0.0, 0.0, 100.0, 5000)
        assert e.tap_records() == [("neutral", None, None, None)]


def test_onneutral_on_begin_nudge_zero_magnitude(motion_lib):
    """beginNudge()'s own zero-magnitude early return -- the nudge
    analogue of the beginSegment() test above, also synchronous."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.begin_nudge(0.0, 0.0, 5000)
        assert e.tap_records() == [("neutral", None, None, None)]


def test_onneutral_on_pulse_wheels(motion_lib):
    """pulseWheels() -> firePulseAndSettle()'s hard-zero
    (kernel_.neutral()) is a call site none of the move-engine paths
    above reach at all -- widthTicks <= 0 is documented as "a defensive
    no-op, not a refusal" (motion_engine.h), so this proves the neutral
    fires even on the degenerate zero-width pulse."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.pulse_wheels(0.0, 0.0, 0)
        assert e.tap_records() == [("neutral", None, None, None)]


def test_onneutral_on_nudge_convergence(motion_lib):
    """serviceNudge()'s own convergence branch (distConverged and
    yawConverged) -- a target within the default arrival margin,
    encoders unmoved, converges on the FIRST serviceNudge() tick."""
    with Engine(motion_lib) as e:
        _ready(e)
        e.tap_install()
        e.begin_nudge(0.5, 0.0, 5000)  # well under the 1.0 mm arriveDist
        e.step()
        still_active = e.service_move()  # dispatches to serviceNudge()
        assert not still_active
        assert e.tap_records() == [("neutral", None, None, None)]


# ---- Phase: accel -> cruise -> brake -------------------------------------


def test_phase_transitions_accel_cruise_brake_on_a_long_move_x(motion_lib):
    """A move long enough to reach cruise and hold it for a while (600 mm
    at a 200 mm/s ceiling, against the default 400 mm/s^2 accel/decel)
    must show the phase sequence accel -> cruise -> brake, monotonic
    (never regressing from a later phase back to an earlier one, and
    reaching every one of the three at least once)."""
    records = _run_move_x(motion_lib, distance_mm=600.0, cruise_mm_s=200.0)
    phases = [r[3] for r in records if r[0] == "drive"]
    assert phases, "expected at least one onDrive() call across the move"

    assert PHASE_CRUISE in phases, (
        "a 600 mm move at 200 mm/s cruise (vs ~94 mm of combined accel+"
        "brake distance at the default 400 mm/s^2) must reach a genuine "
        "cruise plateau"
    )
    assert PHASE_BRAKE in phases, "the move must brake to a stop somewhere"

    highest_seen = -1
    for p in phases:
        assert p >= highest_seen, (
            f"phase regressed from {highest_seen} back to {p} -- "
            f"full sequence: {phases}"
        )
        highest_seen = p
    assert highest_seen == PHASE_BRAKE


def test_phase_never_reports_cruise_on_a_short_move_with_no_plateau(motion_lib):
    """A move short enough that the brake-to-stop ceiling (vBrake) is
    already below the cruise target on tick 1 -- 20 mm at 200 mm/s vs.
    the default 400 mm/s^2 decel gives vBrake = sqrt(2*400*20) ~= 126
    mm/s < 200 -- must NEVER report kCruise: there is no speed the
    shaper ever settles at and holds, only a truncated ramp straight
    into the brake ceiling."""
    records = _run_move_x(motion_lib, distance_mm=20.0, cruise_mm_s=200.0)
    phases = [r[3] for r in records if r[0] == "drive"]
    assert phases, "expected at least one onDrive() call across the move"
    assert PHASE_CRUISE not in phases, (
        f"a short move with no plateau reported kCruise: {phases}"
    )
