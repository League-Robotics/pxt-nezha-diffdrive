"""tests/host/test_cutebot_hybrid_actuation.py -- device-level
integration for sprint 040 ticket 004's hybrid actuation path:
`CutebotDevice`'s per-cycle frame choice (via `CutebotActuationPolicy`,
reached through `serviceCycle()`), `CutebotTapAdapter`'s sign-corrected
forwarding, and `sim_cutebot_bus.h`'s simulated `0x80` onboard loop --
over a REAL `CutebotDevice`/`CutebotMotorPort` pair and a simulated
0x10 slave, the same "compile and run the real port" argument
`test_cutebot_port.py` and `sim_nezha_bus.h` both make in their own
header comments.

WHY A SEPARATE FILE FROM `test_cutebot_port.py`. That file proves the
raw-PWM path's own correctness with `onboard_pid` left at its default
0 throughout (ticket 002's scope). This file's job is everything
ticket 004 added on top: one frame per cycle in each mode, the
both-wheels eligibility gate, the documented "neutral while engaged"
two-frame exception, `appliedDuty()` still reporting the kernel's own
request while onboard holds the wheels, and `sim_cutebot_bus.h`'s
onboard-loop clamp/lag model exercised in isolation (bypassing
`CutebotDevice` entirely, via raw frame writes) per this ticket's own
"proving the clamp and lag model in isolation, ahead of ticket 006's
full-tour proof" testing note.

`test_cutebot_actuation_policy.py` is a THIRD file again: the pure
`CutebotActuationPolicy::decide()` function, with zero I2C or
`CutebotDevice` in the link at all.

SOURCE READING, not MEASURED: every wire-protocol assertion here
encodes what `cutebot_port.h`/`cutebot_actuation_policy.h`/
`sim_cutebot_bus.h` all cite as read from ELECFREAKS' own extension or
chosen as this project's own policy; nothing has run on real Cutebot
hardware, and the hysteresis band and the sim's plant constants are
explicitly not measurements (see each source file's own header).

Run with::

    uv run pytest tests/host/test_cutebot_hybrid_actuation.py
"""

import ctypes
import pathlib
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_HERE = pathlib.Path(__file__).resolve().parent

_SOURCES = [
    _HERE / "cutebot_hybrid_shim.cpp",
    _SRC_DIR / "platform" / "cutebot_port.cpp",
    _SRC_DIR / "platform" / "cutebot_actuation_policy.cpp",
]

# VelocityShaper::Phase's own declaration order (velocity_shaper.h).
PHASE_ACCEL = 0
PHASE_CRUISE = 1
PHASE_BRAKE = 2


def _compile(tmp_path_factory):
    build_dir = tmp_path_factory.mktemp("cutebot_hybrid_build")
    lib_path = build_dir / "libcutebothybrid.so"
    objects = []
    for index, source in enumerate(_SOURCES):
        obj = build_dir / f"{source.stem}.{index}.o"
        cmd = ["/usr/bin/c++", "-std=c++11", "-Wall", "-Wextra", "-fPIC",
               "-O0", "-DDIFFDRIVE_HOST_BUILD", "-c"]
        if not source.resolve().is_relative_to(_SRC_DIR.resolve()):
            cmd += ["-I", str(_SRC_DIR), "-I", str(_HERE)]
        cmd += [str(source), "-o", str(obj)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"host compile failed for {source}:\ncommand: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        objects.append(obj)
    link_cmd = (["/usr/bin/c++", "-shared", "-fPIC", "-o", str(lib_path)]
               + [str(o) for o in objects])
    result = subprocess.run(link_cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"host link failed:\ncommand: {' '.join(link_cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return lib_path


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = _compile(tmp_path_factory)
    f = ctypes.CDLL(str(path))
    P = ctypes.c_void_p
    F = ctypes.c_float
    I = ctypes.c_int
    U = ctypes.c_uint
    U64 = ctypes.c_ulonglong

    f.chCreate.argtypes = [F, F, F]; f.chCreate.restype = P
    f.chDestroy.argtypes = [P]; f.chDestroy.restype = None
    f.chBeginBoth.argtypes = [P]; f.chBeginBoth.restype = None
    f.chSetDuty.argtypes = [P, I, F]; f.chSetDuty.restype = None
    f.chCycle.argtypes = [P, U64]; f.chCycle.restype = None
    f.chTapDrive.argtypes = [P, F, F, I]; f.chTapDrive.restype = None
    f.chTapNeutral.argtypes = [P]; f.chTapNeutral.restype = None
    f.chSetOnboardMode.argtypes = [P, I]; f.chSetOnboardMode.restype = I
    f.chOnboardMode.argtypes = [P]; f.chOnboardMode.restype = I
    f.chSetOnboardFloor.argtypes = [P, F]; f.chSetOnboardFloor.restype = I
    f.chOnboardFloor.argtypes = [P]; f.chOnboardFloor.restype = F
    f.chAppliedDuty.argtypes = [P, I]; f.chAppliedDuty.restype = F
    f.chPosition.argtypes = [P, I]; f.chPosition.restype = F
    f.chVelocity.argtypes = [P, I]; f.chVelocity.restype = F
    f.chStepPhysics.argtypes = [P, F]; f.chStepPhysics.restype = None
    f.chFrameCount.argtypes = [P]; f.chFrameCount.restype = U
    f.chOnboardFrameCount.argtypes = [P]; f.chOnboardFrameCount.restype = U
    f.chOnboardActive.argtypes = [P]; f.chOnboardActive.restype = I
    f.chOnboardSetpoint.argtypes = [P, I]; f.chOnboardSetpoint.restype = F
    f.chLastWheelFrame.argtypes = [P, I]; f.chLastWheelFrame.restype = U
    f.chLastOnboardFrame.argtypes = [P, I]; f.chLastOnboardFrame.restype = U
    f.chSimWheelVelocity.argtypes = [P, I]; f.chSimWheelVelocity.restype = F
    f.chWriteRawOnboardFrame.argtypes = [P, U, U, U]
    f.chWriteRawOnboardFrame.restype = None
    f.chWriteRawPwmFrame.argtypes = [P, U, U, U, U]
    f.chWriteRawPwmFrame.restype = None
    return f


class Handle:
    def __init__(self, lib, tau=0.0, breakaway=0.0, duty_vel_max=1000.0):
        self.lib = lib
        self.ptr = lib.chCreate(tau, breakaway, duty_vel_max)

    def close(self):
        self.lib.chDestroy(self.ptr)

    def begin_both(self):
        self.lib.chBeginBoth(self.ptr)

    def set_duty(self, side, duty):
        self.lib.chSetDuty(self.ptr, side, duty)

    def cycle(self, now_us):
        self.lib.chCycle(self.ptr, now_us)

    def tap_drive(self, left, right, phase):
        self.lib.chTapDrive(self.ptr, left, right, phase)

    def tap_neutral(self):
        self.lib.chTapNeutral(self.ptr)

    def set_onboard_mode(self, mode):
        return bool(self.lib.chSetOnboardMode(self.ptr, mode))

    def onboard_mode(self):
        return self.lib.chOnboardMode(self.ptr)

    def set_onboard_floor(self, floor_mm_s):
        return bool(self.lib.chSetOnboardFloor(self.ptr, floor_mm_s))

    def onboard_floor(self):
        return self.lib.chOnboardFloor(self.ptr)

    def applied_duty(self, side):
        return self.lib.chAppliedDuty(self.ptr, side)

    def position(self, side):
        return self.lib.chPosition(self.ptr, side)

    def velocity(self, side):
        return self.lib.chVelocity(self.ptr, side)

    def step_physics(self, dt):
        self.lib.chStepPhysics(self.ptr, dt)

    def frame_count(self):
        return self.lib.chFrameCount(self.ptr)

    def onboard_frame_count(self):
        return self.lib.chOnboardFrameCount(self.ptr)

    def onboard_active(self):
        return bool(self.lib.chOnboardActive(self.ptr))

    def onboard_setpoint(self, side):
        return self.lib.chOnboardSetpoint(self.ptr, side)

    def last_wheel_frame(self):
        return tuple(self.lib.chLastWheelFrame(self.ptr, i) for i in range(4))

    def last_onboard_frame(self):
        return tuple(self.lib.chLastOnboardFrame(self.ptr, i) for i in range(5))

    def sim_wheel_velocity(self, side):
        return self.lib.chSimWheelVelocity(self.ptr, side)

    def write_raw_onboard_frame(self, mag_l, mag_r, dirbits):
        self.lib.chWriteRawOnboardFrame(self.ptr, mag_l, mag_r, dirbits)

    def write_raw_pwm_frame(self, wheel_sel, abs_l, abs_r, dirbits):
        self.lib.chWriteRawPwmFrame(self.ptr, wheel_sel, abs_l, abs_r, dirbits)


@pytest.fixture
def handle(lib):
    h = Handle(lib)
    h.begin_both()
    yield h
    h.close()


# ---------------------------------------------------------------------
# Mode 0: always PWM, one frame per cycle, regardless of the tap.
# ---------------------------------------------------------------------

def test_mode0_ships_pwm_only_even_at_cruise_speed(handle):
    assert handle.onboard_mode() == 0
    handle.tap_drive(300.0, 300.0, PHASE_CRUISE)
    handle.set_duty(0, 0.5)
    handle.set_duty(1, 0.5)
    handle.cycle(now_us=1000)
    assert handle.frame_count() == 1
    assert handle.onboard_frame_count() == 0
    assert handle.onboard_active() is False


# ---------------------------------------------------------------------
# Mode 1: threshold with hysteresis -- engage/stay/release across three
# regions, not a single crossing value.
# ---------------------------------------------------------------------

def test_mode1_hysteresis_engage_stay_release(handle):
    assert handle.set_onboard_mode(1) is True
    assert handle.set_onboard_floor(200.0) is True  # upper 220, lower 180

    def drive_tick(speed, now_us):
        frames_before = handle.frame_count()
        onboard_before = handle.onboard_frame_count()
        handle.tap_drive(speed, speed, PHASE_CRUISE)
        handle.set_duty(0, 0.5)
        handle.set_duty(1, 0.5)
        handle.cycle(now_us)
        return (handle.frame_count() - frames_before,
                handle.onboard_frame_count() - onboard_before)

    # Below the upper threshold: not yet engaged -> PWM.
    pwm_delta, onboard_delta = drive_tick(210.0, 1000)
    assert (pwm_delta, onboard_delta) == (1, 0)
    assert handle.onboard_active() is False

    # At/above the upper threshold: engages -> onboard.
    pwm_delta, onboard_delta = drive_tick(225.0, 2000)
    assert (pwm_delta, onboard_delta) == (0, 1)
    assert handle.onboard_active() is True

    # In the gap between thresholds: STAYS engaged.
    pwm_delta, onboard_delta = drive_tick(190.0, 3000)
    assert (pwm_delta, onboard_delta) == (0, 1)
    assert handle.onboard_active() is True

    # At/below the lower threshold: releases -> PWM.
    pwm_delta, onboard_delta = drive_tick(170.0, 4000)
    assert (pwm_delta, onboard_delta) == (1, 0)
    assert handle.onboard_active() is False


# ---------------------------------------------------------------------
# Mode 2: plateau-only -- engages at cruise, releases at first brake.
# ---------------------------------------------------------------------

def test_mode2_engages_at_cruise_and_releases_at_first_brake(handle):
    assert handle.set_onboard_mode(2) is True

    def drive_tick(phase, now_us):
        handle.tap_drive(300.0, 300.0, phase)
        handle.set_duty(0, 0.5)
        handle.set_duty(1, 0.5)
        handle.cycle(now_us)

    drive_tick(PHASE_ACCEL, 1000)
    assert handle.onboard_active() is False  # still ramping -- PWM

    drive_tick(PHASE_CRUISE, 2000)
    assert handle.onboard_active() is True  # plateau reached -- onboard

    drive_tick(PHASE_CRUISE, 3000)
    assert handle.onboard_active() is True  # stays onboard through cruise

    drive_tick(PHASE_BRAKE, 4000)
    assert handle.onboard_active() is False  # first brake tick -- released


# ---------------------------------------------------------------------
# Both-wheels eligibility gate: one wheel ineligible keeps the WHOLE
# pair on PWM, in every mode.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("mode", [1, 2])
@pytest.mark.parametrize(
    "left,right",
    [
        (250.0, 50.0),   # one above floor, one strictly under it
        (0.0, 50.0),     # one exactly 0, one nonzero-under-floor
    ],
)
def test_both_wheels_gate_keeps_the_pair_on_pwm(handle, mode, left, right):
    assert handle.set_onboard_mode(mode) is True
    handle.tap_drive(left, right, PHASE_CRUISE)
    handle.set_duty(0, 0.5)
    handle.set_duty(1, 0.2)
    handle.cycle(now_us=1000)
    assert handle.onboard_active() is False
    assert handle.frame_count() == 1
    assert handle.onboard_frame_count() == 0


# ---------------------------------------------------------------------
# Neutral while onboard is engaged: BOTH the 0x80 zero and the 0x10
# zero are sent (this ticket's own handoff-bookkeeping requirement).
# ---------------------------------------------------------------------

def test_neutral_while_engaged_sends_both_zero_frames(handle):
    assert handle.set_onboard_mode(1) is True
    handle.tap_drive(300.0, 300.0, PHASE_CRUISE)
    handle.set_duty(0, 0.5)
    handle.set_duty(1, 0.5)
    handle.cycle(now_us=1000)
    assert handle.onboard_active() is True

    frames_before = handle.frame_count()
    onboard_before = handle.onboard_frame_count()
    handle.tap_neutral()
    handle.set_duty(0, 0.0)
    handle.set_duty(1, 0.0)
    handle.cycle(now_us=2000)

    # Both frame counters advanced by exactly one this cycle: the 0x80
    # zero-both AND the 0x10 zero.
    assert handle.frame_count() - frames_before == 1
    assert handle.onboard_frame_count() - onboard_before == 1
    # The last onboard frame shipped was the zero (magnitude 0 both
    # sides) -- not a stale nonzero setpoint.
    mag_l = (handle.last_onboard_frame()[0] << 8) | handle.last_onboard_frame()[1]
    mag_r = (handle.last_onboard_frame()[2] << 8) | handle.last_onboard_frame()[3]
    assert (mag_l, mag_r) == (0, 0)
    # The 0x10 write came LAST (see serviceCycle()'s own comment), so
    # the sim ends this cycle back in PWM mode.
    assert handle.onboard_active() is False


def test_neutral_while_not_engaged_sends_only_the_pwm_zero(handle):
    """The two-frame exception is specifically for a transition OUT of
    an engaged onboard state -- a neutral tick that was never onboard
    to begin with (mode 0, or mode 1/2 never having engaged) behaves
    exactly as ticket 002 left it: one PWM frame."""
    assert handle.set_onboard_mode(1) is True
    handle.tap_drive(50.0, 50.0, PHASE_CRUISE)  # under the floor -- never engages
    handle.set_duty(0, 0.2)
    handle.set_duty(1, 0.2)
    handle.cycle(now_us=1000)
    assert handle.onboard_active() is False

    frames_before = handle.frame_count()
    onboard_before = handle.onboard_frame_count()
    handle.tap_neutral()
    handle.set_duty(0, 0.0)
    handle.set_duty(1, 0.0)
    handle.cycle(now_us=2000)
    assert handle.frame_count() - frames_before == 1
    assert handle.onboard_frame_count() - onboard_before == 0


# ---------------------------------------------------------------------
# appliedDuty() keeps reporting the kernel's OWN requested duty even
# while the onboard loop actually holds the wheels -- design doc S3.D's
# "nothing upstream sees a discontinuity across a handoff".
# ---------------------------------------------------------------------

def test_applied_duty_reports_kernel_request_while_onboard_engaged(handle):
    assert handle.set_onboard_mode(1) is True
    handle.tap_drive(300.0, 300.0, PHASE_CRUISE)
    handle.set_duty(0, 0.3)
    handle.set_duty(1, -0.3)
    handle.cycle(now_us=1000)
    assert handle.onboard_active() is True  # onboard actually shipped
    assert handle.applied_duty(0) == pytest.approx(0.3, abs=1e-6)
    assert handle.applied_duty(1) == pytest.approx(-0.3, abs=1e-6)


# ---------------------------------------------------------------------
# sim_cutebot_bus.h's own onboard-loop model, in isolation: the 200
# mm/s clamp and the first-order lag, driven by RAW frame writes with
# no CutebotDevice/policy in the way at all.
# ---------------------------------------------------------------------

def test_sim_onboard_loop_clamps_nonzero_under_200_and_passes_zero_through(handle):
    # magL=100 (under 200, must clamp UP); magR=0 (must pass through).
    handle.write_raw_onboard_frame(mag_l=100, mag_r=0, dirbits=0)
    assert handle.onboard_setpoint(0) == pytest.approx(200.0)
    assert handle.onboard_setpoint(1) == pytest.approx(0.0)


def test_sim_onboard_loop_ceiling_clamps_above_500(handle):
    handle.write_raw_onboard_frame(mag_l=600, mag_r=0, dirbits=0)
    assert handle.onboard_setpoint(0) == pytest.approx(500.0)


def test_sim_onboard_loop_first_order_lag(lib):
    h = Handle(lib, tau=0.5, breakaway=0.0, duty_vel_max=1000.0)
    try:
        h.begin_both()
        h.write_raw_onboard_frame(mag_l=300, mag_r=0, dirbits=0)  # no clamp
        h.step_physics(dt=0.5)  # a = dt/(tau+dt) = 0.5 -> halfway to 300
        assert h.sim_wheel_velocity(0) == pytest.approx(150.0, abs=1e-3)
    finally:
        h.close()


def test_sim_onboard_loop_direction_bits(handle):
    handle.write_raw_onboard_frame(mag_l=300, mag_r=300, dirbits=0b01)
    assert handle.onboard_setpoint(0) == pytest.approx(-300.0)
    assert handle.onboard_setpoint(1) == pytest.approx(300.0)


# ---------------------------------------------------------------------
# CutebotDevice::writeOnboardFrame()'s own dirbit encoding, for every
# sign combination -- the 0x80 analogue of test_cutebot_port.py's
# test_frame_bytes_for_all_four_sign_combinations() for 0x10.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "left_speed,right_speed,expected_dirbits",
    [
        (250.0, 250.0, 0b00),   # both forward
        (250.0, -250.0, 0b10),  # left forward, right reverse
        (-250.0, 250.0, 0b01),  # left reverse, right forward
        (-250.0, -250.0, 0b11),  # both reverse
    ],
)
def test_onboard_frame_dirbits_for_all_four_sign_combinations(
    handle, left_speed, right_speed, expected_dirbits
):
    assert handle.set_onboard_mode(1) is True
    handle.tap_drive(left_speed, right_speed, PHASE_CRUISE)
    handle.set_duty(0, 0.5)
    handle.set_duty(1, 0.5)
    handle.cycle(now_us=1000)
    assert handle.onboard_active() is True
    mag_l = (handle.last_onboard_frame()[0] << 8) | handle.last_onboard_frame()[1]
    mag_r = (handle.last_onboard_frame()[2] << 8) | handle.last_onboard_frame()[3]
    dirbits = handle.last_onboard_frame()[4]
    assert mag_l == 250 and mag_r == 250
    assert dirbits == expected_dirbits


def test_sim_0x10_write_cancels_onboard_mode(handle):
    handle.write_raw_onboard_frame(mag_l=300, mag_r=300, dirbits=0)
    assert handle.onboard_active() is True
    handle.write_raw_pwm_frame(wheel_sel=2, abs_l=50, abs_r=50, dirbits=0)
    assert handle.onboard_active() is False
