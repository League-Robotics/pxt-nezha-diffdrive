"""tests/host/test_cutebot_actuation_policy.py -- pure-function
coverage for `diffDrive::CutebotActuationPolicy::decide()`
(src/platform/cutebot_actuation_policy.h/.cpp, sprint 040 ticket 004),
exercised with ZERO I2C, `CutebotDevice`, or board in the link -- the
same isolation `MotionLimits`/`VelocityShaper` already get, per this
sprint's own Design Rationale ("CutebotActuationPolicy as a pure
function, not a stateful method on CutebotDevice").

See `test_cutebot_hybrid_actuation.py` for the device-level integration
this class feeds into (frame choice actually shipped, the neutral
two-frame exception, `appliedDuty()` reporting, the sim's own onboard
loop) and `test_cutebot_port.py` for the raw-PWM path this ticket does
not touch.

SOURCE READING, not MEASURED: the hysteresis band (design doc S3.D's
own illustrative 220/180 numbers around a 200 mm/s floor) is a POLICY
CHOICE, not a bench-tuned constant -- see cutebot_actuation_policy.h's
own header comment.

Run with::

    uv run pytest tests/host/test_cutebot_actuation_policy.py
"""

import ctypes
import pathlib
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_HERE = pathlib.Path(__file__).resolve().parent

_SOURCES = [
    _HERE / "cutebot_actuation_policy_shim.cpp",
    _SRC_DIR / "platform" / "cutebot_actuation_policy.cpp",
]

# VelocityShaper::Phase's own declaration order (velocity_shaper.h).
PHASE_ACCEL = 0
PHASE_CRUISE = 1
PHASE_BRAKE = 2

FLOOR = 200.0  # mm/s -- upper threshold 220, lower 180 (mode 1)


def _compile(tmp_path_factory):
    build_dir = tmp_path_factory.mktemp("cutebot_actuation_policy_build")
    lib_path = build_dir / "libcutebotactuationpolicy.so"
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
    F = ctypes.c_float
    I = ctypes.c_int
    f.capDecide.argtypes = [I, F, F, F, F, I, I, I, F, ctypes.POINTER(I)]
    f.capDecide.restype = I
    return f


def decide(lib, prev_engaged, mode, tap_left, tap_right, phase=PHASE_CRUISE,
          neutral=False, floor=FLOOR, duty_left=0.0, duty_right=0.0):
    """Returns (chose_onboard: bool, new_engaged: bool)."""
    engaged_out = ctypes.c_int(0)
    frame = lib.capDecide(
        1 if prev_engaged else 0, duty_left, duty_right,
        tap_left, tap_right, phase, 1 if neutral else 0, mode, floor,
        ctypes.byref(engaged_out),
    )
    return bool(frame), bool(engaged_out.value)


# ---------------------------------------------------------------------
# Mode 0: always PWM, unconditionally.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("tap_left,tap_right,phase", [
    (0.0, 0.0, PHASE_ACCEL),
    (300.0, 300.0, PHASE_CRUISE),   # well above the floor
    (-300.0, -300.0, PHASE_CRUISE),
    (500.0, 500.0, PHASE_BRAKE),
])
def test_mode0_always_ships_pwm(lib, tap_left, tap_right, phase):
    for prev_engaged in (False, True):
        onboard, engaged = decide(lib, prev_engaged, 0, tap_left, tap_right, phase)
        assert onboard is False
        assert engaged is False


def test_mode0_ignores_a_zero_floor_too(lib):
    onboard, engaged = decide(lib, False, 0, 300.0, 300.0, PHASE_CRUISE, floor=0.0)
    assert onboard is False
    assert engaged is False


# ---------------------------------------------------------------------
# Mode 1: threshold with hysteresis -- three regions.
# ---------------------------------------------------------------------

def test_mode1_engages_at_upper_threshold(lib):
    onboard, engaged = decide(lib, False, 1, 220.0, 220.0)  # floor*1.1
    assert (onboard, engaged) == (True, True)


def test_mode1_does_not_engage_just_below_upper_threshold(lib):
    onboard, engaged = decide(lib, False, 1, 219.0, 219.0)
    assert (onboard, engaged) == (False, False)


def test_mode1_stays_engaged_through_the_gap(lib):
    onboard, engaged = decide(lib, True, 1, 200.0, 200.0)  # between 180 and 220
    assert (onboard, engaged) == (True, True)


def test_mode1_releases_at_lower_threshold(lib):
    onboard, engaged = decide(lib, True, 1, 180.0, 180.0)  # floor*0.9
    assert (onboard, engaged) == (False, False)


def test_mode1_stays_released_just_above_lower_threshold_if_not_engaged(lib):
    # Not yet engaged, and below the UPPER threshold -- must not engage
    # just because it is above the lower one (that would collapse the
    # hysteresis band to a single crossing value).
    onboard, engaged = decide(lib, False, 1, 200.0, 200.0)
    assert (onboard, engaged) == (False, False)


def test_mode1_full_engage_stay_release_sequence(lib):
    """The three-region proof as one continuous run, threading engaged
    state exactly as CutebotDevice::serviceCycle() would tick to tick."""
    engaged = False
    onboard, engaged = decide(lib, engaged, 1, 210.0, 210.0)
    assert (onboard, engaged) == (False, False)  # below upper -- not yet
    onboard, engaged = decide(lib, engaged, 1, 225.0, 225.0)
    assert (onboard, engaged) == (True, True)    # at/above upper -- engage
    onboard, engaged = decide(lib, engaged, 1, 190.0, 190.0)
    assert (onboard, engaged) == (True, True)    # in the gap -- stays
    onboard, engaged = decide(lib, engaged, 1, 170.0, 170.0)
    assert (onboard, engaged) == (False, False)  # at/below lower -- release


# ---------------------------------------------------------------------
# Mode 2: plateau-only -- engage at cruise, release at first brake.
# ---------------------------------------------------------------------

def test_mode2_does_not_engage_during_accel(lib):
    onboard, engaged = decide(lib, False, 2, 300.0, 300.0, PHASE_ACCEL)
    assert (onboard, engaged) == (False, False)


def test_mode2_engages_at_cruise(lib):
    onboard, engaged = decide(lib, False, 2, 300.0, 300.0, PHASE_CRUISE)
    assert (onboard, engaged) == (True, True)


def test_mode2_releases_at_first_brake_tick(lib):
    onboard, engaged = decide(lib, True, 2, 300.0, 300.0, PHASE_BRAKE)
    assert (onboard, engaged) == (False, False)


def test_mode2_accel_after_engaged_holds_engagement(lib):
    """A documented, deliberate choice (cutebot_actuation_policy.cpp's
    own comment): kAccel neither engages nor releases an already-
    engaged run -- only kBrake releases."""
    onboard, engaged = decide(lib, True, 2, 300.0, 300.0, PHASE_ACCEL)
    assert (onboard, engaged) == (True, True)


# ---------------------------------------------------------------------
# Both-wheels eligibility gate -- applies ahead of BOTH modes 1 and 2.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("mode", [1, 2])
@pytest.mark.parametrize("tap_left,tap_right", [
    (250.0, 50.0),   # one above floor, one strictly under it
    (50.0, 250.0),   # the other way around
    (0.0, 50.0),     # one exactly 0, one nonzero-under-floor
    (50.0, 0.0),
])
def test_both_wheels_gate_forces_pwm(lib, mode, tap_left, tap_right):
    onboard, engaged = decide(lib, False, mode, tap_left, tap_right, PHASE_CRUISE)
    assert (onboard, engaged) == (False, False)


@pytest.mark.parametrize("mode", [1, 2])
def test_both_wheels_gate_forces_release_even_if_previously_engaged(lib, mode):
    onboard, engaged = decide(lib, True, mode, 250.0, 50.0, PHASE_CRUISE)
    assert (onboard, engaged) == (False, False)


def test_mode1_never_engages_from_a_standing_stop(lib):
    """0/0 passes the both-wheels gate (design doc: "0 allowed"), but
    mode 1's own threshold never engages from zero -- minMag is always
    0, which never reaches the upper threshold."""
    onboard, engaged = decide(lib, False, 1, 0.0, 0.0, PHASE_CRUISE)
    assert (onboard, engaged) == (False, False)


def test_mode2_engages_at_cruise_even_at_exactly_zero(lib):
    """0/0 passes the both-wheels gate (design doc: "0 allowed"), and
    mode 2's engagement rule looks at PHASE alone once eligible -- a
    cruise tick engages even at this degenerate zero-speed edge case.
    (In practice a genuine stop is delivered as onNeutral(), not
    onDrive() with kCruise, so this combination is not expected to
    occur on a real drive -- it is tested here because decide() itself
    has no way to know that, and must still answer SOMETHING coherent
    with its own stated rules.)"""
    onboard, engaged = decide(lib, False, 2, 0.0, 0.0, PHASE_CRUISE)
    assert (onboard, engaged) == (True, True)


# ---------------------------------------------------------------------
# A neutral tick forces PWM unconditionally, ahead of every other
# check, and resets engagement -- mode and setpoint magnitude included.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("mode", [1, 2])
def test_neutral_forces_pwm_even_if_previously_engaged(lib, mode):
    onboard, engaged = decide(lib, True, mode, 300.0, 300.0, PHASE_CRUISE,
                              neutral=True)
    assert (onboard, engaged) == (False, False)


# ---------------------------------------------------------------------
# An out-of-range mode falls back to PWM, the same "unrecognized field
# is silently inert" shape the rest of this codebase's config surface
# uses.
# ---------------------------------------------------------------------

def test_out_of_range_mode_falls_back_to_pwm(lib):
    onboard, engaged = decide(lib, True, 3, 300.0, 300.0, PHASE_CRUISE)
    assert (onboard, engaged) == (False, False)


# ---------------------------------------------------------------------
# kernelDuty is part of decide()'s own signature (cutebot_actuation_
# policy.h's own comment on why) but must not influence the decision --
# two calls that differ ONLY in duty must agree.
# ---------------------------------------------------------------------

def test_kernel_duty_does_not_influence_the_decision(lib):
    a = decide(lib, False, 1, 225.0, 225.0, duty_left=0.9, duty_right=0.9)
    b = decide(lib, False, 1, 225.0, 225.0, duty_left=-0.9, duty_right=0.0)
    assert a == b
