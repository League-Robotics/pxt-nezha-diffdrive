"""tests/host/test_kernel_reference_handling.py -- host coverage for the
four kernel patches (K1-K4, sprint 029 ticket 001, design
docs/design/motion-profile-unification.md §4.5) to
src/core/diffdrive.{h,cpp}'s reference integrators:

  K1 -- the twist-hold reference integrates the POST-floor half-
        differential, not lambda*cmd.twist from before applySpeedFloor()
        ever touched it (review MK-02).
  K2 -- positionError() does not advance a wheel's position reference on
        a tick whose sample did not advance (review MK-03).
  K3 -- positionError() clamps the STORED reference to posErrMax of the
        measured position, not just the value it returns (anti-windup).
  K4 -- rearmReferences(), a deferred request (same shape as
        rebasePosition()) that disarms both position references and the
        twist reference at the start of the next step().

Reuses tests/host/test_kernel_harness.py's kernel_lib fixture and its
Kernel wrapper (same compiled shim, diffdrive.cpp + kernel_shim.cpp --
this file does not invent a second shim) rather than re-implementing the
compile/bind plumbing. RefKernel below is a thin subclass adding the
K1/K3/K4 diagnostic accessors kernel_shim.cpp now exports
(kdTwistReferenceCounts/kdTwistReferenceArmed/kdPositionReferenceCounts/
kdRearmReferences) plus a couple of raw passthroughs the base Kernel
class doesn't wrap yet -- the same "thin subclass" pattern
test_frozen_encoder_hold.py's own _EncoderKernel already uses.

Run with::

    uv run pytest tests/host/test_kernel_reference_handling.py
"""

import ctypes

import pytest

from test_kernel_harness import (  # noqa: F401 -- kernel_lib re-exported as a fixture
    LEFT,
    RIGHT,
    STATUS_OK,
    Kernel,
    kernel_lib,
)

_DT_S = 0.024  # [s] one kernel cycle -- matches Config::cyclePeriod's own
               # 24 ms default; DifferentialDrive::step() derives its own
               # dt from measured clock deltas, so every helper below
               # advances the fake clock by exactly this much per tick.
_STEP_US = int(_DT_S * 1e6)


def _bind_reference_handling(lib):
    """Attach ctypes argtypes/restype for the K1/K3/K4 diagnostic
    exports kernel_shim.cpp adds in this ticket -- test_kernel_harness's
    own _bind() does not know about them, so this extends the SAME lib
    object that fixture returns rather than re-binding everything."""
    lib.kdRearmReferences.argtypes = [ctypes.c_void_p]
    lib.kdRearmReferences.restype = None
    lib.kdTwistReferenceCounts.argtypes = [ctypes.c_void_p]
    lib.kdTwistReferenceCounts.restype = ctypes.c_float
    lib.kdTwistReferenceArmed.argtypes = [ctypes.c_void_p]
    lib.kdTwistReferenceArmed.restype = ctypes.c_int
    lib.kdPositionReferenceCounts.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdPositionReferenceCounts.restype = ctypes.c_float
    return lib


@pytest.fixture(scope="session")
def ref_kernel_lib(kernel_lib):
    return _bind_reference_handling(kernel_lib)


class RefKernel(Kernel):
    """Adds the K1/K3/K4 diagnostic accessors plus a few raw
    passthroughs (applied-duty readback, the FakeMotor collect-failure
    knob, ki/iMax/pidMax/speedFloor/posErrMax setters) that
    test_kernel_harness.py's own Kernel wrapper does not expose yet --
    all of them thin calls to symbols kernel_shim.cpp already binds."""

    def rearm_references(self):
        self._lib.kdRearmReferences(self._handle)

    def twist_reference_counts(self):
        return self._lib.kdTwistReferenceCounts(self._handle)

    def twist_reference_armed(self):
        return bool(self._lib.kdTwistReferenceArmed(self._handle))

    def position_reference_counts(self, left_wheel):
        return self._lib.kdPositionReferenceCounts(
            self._handle, 1 if left_wheel else 0)

    def motor_set_collect_succeeds(self, side, succeeds):
        self._lib.kdMotorSetCollectSucceeds(
            self._handle, side, 1 if succeeds else 0)

    def out_applied_duty(self, side):
        fn = (self._lib.kdOutAppliedDutyLeft if side == LEFT
              else self._lib.kdOutAppliedDutyRight)
        return fn(self._handle) * 0.01  # [%] -> [-1, 1] fraction

    def set_ki(self, value):
        self._lib.kdSetKi(self._handle, value)

    def set_imax(self, value):
        self._lib.kdSetIMax(self._handle, value)

    def set_pid_max(self, value):
        self._lib.kdSetPidMax(self._handle, value)

    def set_speed_floor(self, value):
        self._lib.kdSetSpeedFloor(self._handle, value)

    def set_position_error_max(self, value):
        self._lib.kdSetPositionErrorMax(self._handle, value)

    def set_twist_hold_gain(self, value):
        self._lib.kdSetTwistHoldGain(self._handle, value)


def _drive_ideal_wheels(k, base_us, velocity, twist, ticks,
                        full_duty_velocity, freeze_tick_left=-1):
    """Steps the kernel `ticks` times over FakeMotor ports whose next
    sample is armed, each tick, from the PREVIOUS tick's own staged
    duty -- an ideal (zero-lag, zero-modeling-error) wheel that always
    lands exactly where the kernel just commanded it. Mirrors
    docs/code-review/2026-09-02/raw/profile_probe.cpp's own Rig::tick()
    with tauS == 0.

    `freeze_tick_left`: if >= 0, LEFT's collect is made to fail on that
    0-indexed tick only (profile_probe.cpp's own `freezeTick` pattern,
    E5) -- the wheel's TRUE position keeps advancing that tick (nothing
    stops it physically moving); only the SENSOR READ for that one tick
    is discarded, exactly like a stale I2C collect, and the cached
    sample catches up in one jump on the next tick whose collect
    succeeds.

    Returns (now_us, pos_left, pos_right, duties, twist_refs, pos_refs)
    -- duties/twist_refs/pos_refs are one entry per tick, read back
    immediately after that tick's own step().
    """
    now_us = base_us
    pos_left = pos_right = 0.0
    k.set_clock(now_us)
    k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
    k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
    k.step()  # baseline sample -- velocity stays 0 until a second one

    assert k.drive(velocity, twist, 30_000) == STATUS_OK

    duties = []
    twist_refs = []
    pos_refs = []
    for i in range(ticks):
        now_us += _STEP_US
        duty_left = k.motor_last_staged_duty(LEFT)
        duty_right = k.motor_last_staged_duty(RIGHT)
        pos_left += duty_left * full_duty_velocity * _DT_S
        pos_right += duty_right * full_duty_velocity * _DT_S
        k.set_clock(now_us)
        k.arm_motor_sample(LEFT, position=pos_left, sample_time_us=now_us)
        k.arm_motor_sample(RIGHT, position=pos_right, sample_time_us=now_us)
        freeze_this_tick = i == freeze_tick_left
        if freeze_this_tick:
            k.motor_set_collect_succeeds(LEFT, False)
        k.step()
        if freeze_this_tick:
            k.motor_set_collect_succeeds(LEFT, True)
        duties.append((k.motor_last_staged_duty(LEFT),
                       k.motor_last_staged_duty(RIGHT)))
        twist_refs.append(k.twist_reference_counts())
        pos_refs.append(k.position_reference_counts(True))
    return now_us, pos_left, pos_right, duties, twist_refs, pos_refs


# ---------------------------------------------------------------------
# K1 -- post-floor twist-hold reference
# ---------------------------------------------------------------------


def test_k1_floored_twist_reference_tracks_post_floor_half_differential(
        ref_kernel_lib):
    """A floored pivot: commanded twist (100 counts/s) is well under the
    speed floor (400 counts/s), so applySpeedFloor() rescales both
    wheels up to the floor every tick. Before this ticket's fix,
    twistRef_.reference integrated the PRE-floor `lambda*cmd.twist`
    (100 counts/s), while the wheels actually ran at the floored ~400
    counts/s -- the reference fell behind, the error went negative, and
    trim braked the turn (MEASURED -11% reverse duty on a cruise-100
    pivot, review MK-02). With the fix, the reference is reconstructed
    here from the OBSERVED post-floor duty each tick; if it still
    integrated the pre-floor command this equality would fail by
    roughly the floor's ~4x amplification factor, not by rounding.
    """
    with RefKernel(ref_kernel_lib) as k:
        fdv = 2000.0    # [counts/s] wheel rate at 100% duty
        twist = 100.0   # [counts/s] commanded -- well under the floor
        v_min = 400.0   # [counts/s] speed floor; binds against `twist`
        ticks = 40

        k.set_max_duty(100.0)
        k.set_full_duty_velocity(fdv)
        k.set_speed_floor(v_min)
        k.set_twist_hold_gain(2.0)
        assert k.begin() == STATUS_OK

        _, _, _, duties, twist_refs, _ = _drive_ideal_wheels(
            k, base_us=1_000_000, velocity=0.0, twist=twist, ticks=ticks,
            full_duty_velocity=fdv)

        expected = 0.0
        for duty_left, duty_right in duties:
            expected += 0.5 * (duty_right - duty_left) * fdv * _DT_S

        assert twist_refs[-1] == pytest.approx(expected, rel=1e-3, abs=1e-2)

        # The observable per the ticket/design: the servo must not brake
        # the faster (right) wheel -- no negative right duty at any
        # tick once the floor has bound.
        assert all(duty_right >= -1e-6 for _, duty_right in duties), (
            "right wheel duty went negative -- K1 regression "
            f"(duties={duties})"
        )
        # And the floor really did bind (otherwise this test would pass
        # trivially without exercising K1 at all).
        assert abs(duties[-1][1]) * fdv > twist * 2


# ---------------------------------------------------------------------
# K2 -- stale-tick freeze
# ---------------------------------------------------------------------


def test_k2_frozen_sample_leaves_reference_unchanged_and_does_not_kick_duty(
        ref_kernel_lib):
    """Reproduces profile_probe.cpp's own E5 scenario (300 mm/s-scale
    cruise, kp == 0 so the position I-term is the only feedback path)
    with LEFT's collect failing for exactly one tick after settling.
    Before the fix, positionError() advanced ref.reference by
    speed*dt on the tick immediately after the freeze even though
    wheel.position had not moved (the sample was still the pre-freeze
    cached value), injecting one tick's worth of phantom position error
    and stepping duty toward the rail (MEASURED 35.3 -> 41.3%, review
    MK-03). With the fix, that tick's `advanced` flag is false (the
    PREVIOUS tick's own collect failed), so positionError() returns the
    unchanged error instead.
    """
    with RefKernel(ref_kernel_lib) as k:
        fdv = 10795.0   # [counts/s] matches profile_probe.cpp's kFullDuty
        cruise = 300.0  # [counts/s] matches profile_probe.cpp's E5 cruise

        k.set_max_duty(100.0)
        k.set_full_duty_velocity(fdv)
        k.set_ki(6.0)
        k.set_imax(765.6)
        k.set_pid_max(1276.0)
        # posErrMax stays 0 (unclamped) -- isolate K2 from K3's own
        # clamp so this test is about the reference-advance guard alone.
        assert k.begin() == STATUS_OK

        settle_ticks = 40  # let the position I-term reach steady state
        freeze_at = settle_ticks  # freeze the tick right after settling
        _, _, _, duties, _, pos_refs = _drive_ideal_wheels(
            k, base_us=1_000_000, velocity=cruise, twist=0.0,
            ticks=settle_ticks + 3, full_duty_velocity=fdv,
            freeze_tick_left=freeze_at)

        duty_before = duties[freeze_at - 1][0]
        duty_frozen_tick = duties[freeze_at][0]     # the freeze itself
        duty_after = duties[freeze_at + 1][0]        # E5's own kick site

        ref_frozen_tick = pos_refs[freeze_at]
        ref_after = pos_refs[freeze_at + 1]

        # The freeze tick itself is unaffected (it still reads the last
        # good, pre-freeze sample) -- sanity check that settling really
        # reached steady state before asserting anything about the kick.
        assert duty_frozen_tick == pytest.approx(duty_before, abs=5e-3)

        # K2's own assertion: the reference the tick immediately after
        # the freeze sees is UNCHANGED from the freeze tick itself.
        assert ref_after == pytest.approx(ref_frozen_tick, abs=1e-6)

        # And the observable the ticket names: duty does not jump. The
        # historical, unfixed magnitude was ~+6 duty points (35.3 ->
        # 41.3%, i.e. +0.06 in this [-1, 1] fraction); require the jump
        # stay under a tenth of that.
        assert abs(duty_after - duty_frozen_tick) < 0.006, (
            f"duty stepped after the frozen tick: {duty_frozen_tick} -> "
            f"{duty_after} -- K2 regression"
        )


# ---------------------------------------------------------------------
# K3 -- anti-windup
# ---------------------------------------------------------------------


def test_k3_anti_windup_bounds_the_stored_reference_backlog(ref_kernel_lib):
    """Stands in for the design's "a 50 mm lag yields a reference
    backlog of exactly posErrMax" (§9.3 item 3, §4.5 K3) using the
    kernel's own unit (counts -- diffdrive.cpp never sees mm) instead of
    a motion_engine countsPerMm() conversion that is irrelevant to this
    file. The wheel is held stalled (a REAL stall: position genuinely
    does not move, sampleTime advances every tick -- not a collect
    failure, K2's own scenario) for many ticks while a nonzero speed is
    commanded, then released. Before the fix only the RETURNED error was
    clamped to posErrMax; the stored ref.reference itself accumulated
    without bound and discharged that backlog once the wheel could move
    again (the movex-end-bump-is-i-term-stall memory). With the fix the
    stored reference itself never runs more than posErrMax ahead of the
    measured position, at every tick, during the stall AND the release.
    """
    with RefKernel(ref_kernel_lib) as k:
        fdv = 2000.0
        cruise = 300.0       # [counts/s] commanded
        pos_err_max = 100.0  # [counts] deliberately far below the raw
                             # backlog the stall below would otherwise
                             # accumulate

        k.set_max_duty(100.0)
        k.set_full_duty_velocity(fdv)
        k.set_position_error_max(pos_err_max)
        # kp/ki/iMax stay 0 -- this test reads the stored reference
        # directly via the accessor, no PID path needed to expose it.
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()

        assert k.drive(cruise, 0.0, 30_000) == STATUS_OK

        now_us = base_us
        stall_ticks = 60
        for _ in range(stall_ticks):
            now_us += _STEP_US
            k.set_clock(now_us)
            k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
            k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
            k.step()
            backlog = k.position_reference_counts(True) - k.motor_position(LEFT)
            assert backlog <= pos_err_max + 1e-3, (
                f"stored reference backlog {backlog} exceeded posErrMax "
                f"{pos_err_max} during the stall -- K3 regression"
            )

        # The scenario is a real test of the clamp, not a no-op: without
        # K3 the raw (unclamped) integral would have reached several
        # multiples of posErrMax.
        raw_unclamped = cruise * stall_ticks * _DT_S
        assert raw_unclamped > 3 * pos_err_max
        assert k.position_reference_counts(True) == pytest.approx(
            pos_err_max, rel=1e-3)

        # Release: the wheel starts moving at the commanded speed. The
        # backlog invariant must keep holding as it catches up.
        pos = 0.0
        for _ in range(20):
            now_us += _STEP_US
            pos += cruise * _DT_S
            k.set_clock(now_us)
            k.arm_motor_sample(LEFT, position=pos, sample_time_us=now_us)
            k.arm_motor_sample(RIGHT, position=pos, sample_time_us=now_us)
            k.step()
            backlog = k.position_reference_counts(True) - k.motor_position(LEFT)
            assert backlog <= pos_err_max + 1e-3, (
                f"stored reference backlog {backlog} exceeded posErrMax "
                f"{pos_err_max} during release -- K3 regression"
            )


# ---------------------------------------------------------------------
# K4 -- rearmReferences()
# ---------------------------------------------------------------------


def test_k4_rearm_references_zeroes_twist_error_on_the_next_tick(
        ref_kernel_lib):
    """Builds up a real twist-hold reference over many ticks of a
    pivot, then calls rearmReferences() and steps once more with the
    SAME command still active. Because maxDuty's rail is nowhere near
    saturated here, lambdaEnabled defaults false so lambda_ == 1.0
    exactly -- so with the reference freshly re-anchored (twistError ==
    0 on entry to this tick, since origin == current position and
    reference == 0), the ONLY thing left to integrate this tick is that
    tick's own post-floor half-differential: reference == twist * dt
    exactly. If rearm had NOT zeroed the twist error, trim would be
    nonzero and this exact-value assertion would fail.
    """
    with RefKernel(ref_kernel_lib) as k:
        fdv = 2000.0
        twist = 50.0  # [counts/s] small -- stays well off the duty rail

        k.set_max_duty(100.0)
        k.set_full_duty_velocity(fdv)
        k.set_twist_hold_gain(2.0)
        # vMin stays 0 -- isolate K4 from K1's floor interaction.
        assert k.begin() == STATUS_OK

        now_us, pos_left, pos_right, duties, twist_refs, _ = (
            _drive_ideal_wheels(k, base_us=1_000_000, velocity=0.0,
                                twist=twist, ticks=20,
                                full_duty_velocity=fdv))

        # Confirm the reference genuinely accumulated something to lose
        # -- otherwise "zero after rearm" would be a no-op assertion.
        pre_rearm_reference = twist_refs[-1]
        assert abs(pre_rearm_reference) > 1e-3

        k.rearm_references()
        now_us += _STEP_US
        duty_left, duty_right = duties[-1]
        pos_left += duty_left * fdv * _DT_S
        pos_right += duty_right * fdv * _DT_S
        k.set_clock(now_us)
        k.arm_motor_sample(LEFT, position=pos_left, sample_time_us=now_us)
        k.arm_motor_sample(RIGHT, position=pos_right, sample_time_us=now_us)
        k.step()

        assert k.twist_reference_armed()
        assert k.twist_reference_counts() == pytest.approx(
            twist * _DT_S, rel=1e-3)
        assert abs(k.twist_reference_counts()) < abs(pre_rearm_reference)


def test_k4_rearm_references_zeroes_position_references_too(ref_kernel_lib):
    """The position references disarm on rearmReferences() as well, not
    just the twist reference -- design §4.5 K4 names all three
    (posRefLeft_/Right_, twistRef_). A large backlog built up under K3's
    clamp (posErrMax) collapses to exactly 0 the step after rearm:
    positionError()'s own "just (re)armed" branch (pre-existing,
    unchanged by this ticket -- the same branch a first-ever call or a
    rebasePosition() takes) returns 0.0 and sets reference = 0.0f
    without integrating that same tick, unlike the twist-hold block
    (which unconditionally integrates after the floor regardless of
    whether it just re-armed). K4's contribution is only that
    rearmReferences() gets `armed` to false in the first place.
    """
    with RefKernel(ref_kernel_lib) as k:
        fdv = 2000.0
        cruise = 300.0
        pos_err_max = 100.0

        k.set_max_duty(100.0)
        k.set_full_duty_velocity(fdv)
        k.set_position_error_max(pos_err_max)
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()
        assert k.drive(cruise, 0.0, 30_000) == STATUS_OK

        now_us = base_us
        for _ in range(40):
            now_us += _STEP_US
            k.set_clock(now_us)
            k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
            k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
            k.step()

        pre_rearm_backlog = k.position_reference_counts(True) - k.motor_position(LEFT)
        assert pre_rearm_backlog == pytest.approx(pos_err_max, rel=1e-3)

        k.rearm_references()
        now_us += _STEP_US
        # The wheel is still at position 0 -- rearm re-anchors origin
        # there, so a fresh, well-behaved reference starts from 0 too.
        k.set_clock(now_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
        k.step()

        post_rearm_backlog = k.position_reference_counts(True) - k.motor_position(LEFT)
        assert post_rearm_backlog == pytest.approx(0.0, abs=1e-3)
        assert post_rearm_backlog < pre_rearm_backlog
