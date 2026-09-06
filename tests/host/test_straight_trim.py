"""tests/host/test_straight_trim.py -- sprint 031 ticket 019, the host
harness proof for `straight_trim` (src/core/diffdrive.h/.cpp's
Config::straightTrim, wire ordinal 38, wire_adapter.cpp's kFields).

docs/sprint-031-postmortem.md §2.2, MEASURED tovez 2026-09-05
(captures/session-b-20260905/discriminator-20260905/legs.json,
correcting the original ticket's "purely encoder-invisible" premise):
tovez's forward legs curve by a per-robot amount that splits roughly
in half between two components --

  - a GROUND-side wheel-radius/scrub mismatch the encoders can never
    see (encoder twist stays ~0 while the ground heading drifts), and
  - a mismatch the encoders DO see, but that a proportional-only twist
    hold (gain 4 [1/s]) leaves as steady-state error against a constant
    disturbance.

`straight_trim` is a single per-robot bias on the twist-hold
REFERENCE (not the encoder feedback itself), sized empirically from a
camera-truthed warm run, that cancels the TOTAL in steady state under
BOTH components at once: it deliberately drives the encoders to twist
by the fraction that cancels the invisible half, and the resulting
nonzero target also relieves the proportional hold's own residual on
the visible half. This file only proves the mechanism against the
GROUND-side (encoder-invisible) component -- that is the half no
`twist_hold_gain` retune could ever reach (2.2's whole point), and the
one component a host-only simulation (no real encoder-visible
mismatch source exists here) can actually inject. The magnitude used
below (1.1%, 114.2 mm track, 600 mm leg, ~3.4 deg) matches the
postmortem's own tovez G3 numbers so the "~3.4 deg" acceptance
criterion is a real, citable target rather than an arbitrary one --
the constant itself is NOT baked into firmware anywhere; default stays
0 (ticket 019 is explicit that baking a robot's own value is a
separate, hardware-acceptance step).

Reuses tests/host/test_kernel_harness.py's `kernel_lib` fixture/Kernel
wrapper (same compiled shim, diffdrive.cpp + kernel_shim.cpp) for tests
1-3, the same "thin subclass" pattern test_kernel_reference_handling.py's
own RefKernel already uses, and tests/host/test_wire_motion_verbs.py's
`wa`/`motion_verb_lib` fixtures (the REAL WireAdapter over a REAL
kernel) for test 4's wire round trip -- no shim additions needed there,
since `straight_trim` reaches the kernel through the SAME generic
kFields/setKernelValue()/getConfigValue() path `twist_hold_gain` already
does (wire_adapter.cpp's onSet()/onGet()), not a per-field forward like
`default_cruise`/`rotational_slip`.

Run with::

    uv run pytest tests/host/test_straight_trim.py
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
from test_wire_motion_verbs import (  # noqa: F401 -- wa/motion_verb_lib re-exported
    _ack,
    motion_verb_lib,
    wa,
)

_DT_S = 0.024   # [s] one kernel cycle -- matches Config::cyclePeriod's
                #   own 24 ms default, same convention
                #   test_kernel_reference_handling.py's own _DT_S uses.
_STEP_US = int(_DT_S * 1e6)

# Plant/leg parameters -- chosen to match docs/sprint-031-postmortem.md
# §2.2's own tovez G3 numbers (114.2 mm track, 600 mm legs, 100 mm/s
# cruise, 1.1% mismatch, ~3.4 deg drift) so the "~3.4 deg"/"<0.3 deg"
# acceptance thresholds are the real cited numbers, not arbitrary ones.
# Units: this file treats "counts" and "mm" as the same numeraire
# throughout (the kernel itself is unit-agnostic -- see diffdrive.h's
# own "[counts/s]" comments -- so nothing below actually depends on a
# real countsPerMm conversion; test_kernel_harness.py's own smoke test
# does the same thing).
_TRACK_WIDTH_MM = 114.2
_LEG_MM = 600.0
_CRUISE_MM_S = 100.0
_MISMATCH = 0.011              # [1] 1.1%, postmortem §2.2's own number
_FULL_DUTY_VELOCITY = 2000.0   # [counts/s] well above cruise + any trim
_MOTOR_TAU_S = 0.05            # [s] first-order per-wheel motor time
                               #   constant -- fast relative to the
                               #   twist-hold gain's own 1/4 = 0.25 s,
                               #   so the closed loop stays well damped.
_TWIST_HOLD_GAIN = 4.0         # [1/s] matches ticket 019's own
                               #   correction note ("a proportional-only
                               #   hold at gain 4").
_LEG_TICKS = round((_LEG_MM / _CRUISE_MM_S) / _DT_S)  # 250, 6.0 s exactly


def _bind_straight_trim(lib):
    """Attach ctypes argtypes/restype for kdSetStraightTrim -- the one
    kernel_shim.cpp export this ticket adds. test_kernel_harness's own
    _bind() does not know about it, so this extends the SAME lib object
    that fixture returns, same convention
    test_kernel_reference_handling.py's own _bind_reference_handling()
    uses."""
    lib.kdSetStraightTrim.argtypes = [ctypes.c_void_p, ctypes.c_float]
    lib.kdSetStraightTrim.restype = None
    return lib


@pytest.fixture(scope="session")
def trim_kernel_lib(kernel_lib):
    return _bind_straight_trim(kernel_lib)


class TrimKernel(Kernel):
    """Adds straight_trim's own setter -- the one knob
    test_kernel_harness.py's own Kernel wrapper does not expose yet."""

    def set_straight_trim(self, value):
        self._lib.kdSetStraightTrim(self._handle, value)

    def set_twist_hold_gain(self, value):
        self._lib.kdSetTwistHoldGain(self._handle, value)


def _drive_straight_leg(k, *, ground_gain_left=1.0, ground_gain_right=1.0,
                        base_us=1_000_000):
    """The plant-in-the-loop straight leg (docs/sprint-031-postmortem.md
    §1a): each tick, take the two staged duties, integrate a per-wheel
    FIRST-ORDER motor (identical gain/time-constant both sides) into
    ENCODER counts and `arm_motor_sample` them -- this is what the
    kernel's own twist-hold feedback sees, and it carries NO ground-
    radius information at all, by construction (both wheels' shaft
    dynamics are driven by the same `_MOTOR_TAU_S`/`_FULL_DUTY_VELOCITY`
    model). Separately, integrate GROUND travel per wheel, where
    `ground_gain_left`/`ground_gain_right` model a ground-side wheel-
    radius/scrub mismatch the encoder never sees. Ground heading is
    `(groundR - groundL) / trackWidth` (postmortem §1a's own formula).

    Returns (encoder_twist_counts, ground_heading_deg, mean_shaft_counts).
    """
    now_us = base_us
    k.set_clock(now_us)
    shaft_left = shaft_right = 0.0
    ground_left = ground_right = 0.0
    vel_left = vel_right = 0.0
    k.arm_motor_sample(LEFT, position=0.0, sample_time_us=now_us)
    k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=now_us)
    k.step()  # baseline sample -- velocity stays 0 until a second one

    assert k.drive(_CRUISE_MM_S, 0.0, 60_000) == STATUS_OK

    for _ in range(_LEG_TICKS):
        duty_left = k.motor_last_staged_duty(LEFT)
        duty_right = k.motor_last_staged_duty(RIGHT)
        vel_left += ((duty_left * _FULL_DUTY_VELOCITY - vel_left) /
                    _MOTOR_TAU_S * _DT_S)
        vel_right += ((duty_right * _FULL_DUTY_VELOCITY - vel_right) /
                     _MOTOR_TAU_S * _DT_S)
        shaft_left += vel_left * _DT_S
        shaft_right += vel_right * _DT_S
        ground_left += vel_left * ground_gain_left * _DT_S
        ground_right += vel_right * ground_gain_right * _DT_S
        now_us += _STEP_US
        k.set_clock(now_us)
        k.arm_motor_sample(LEFT, position=shaft_left, sample_time_us=now_us)
        k.arm_motor_sample(RIGHT, position=shaft_right, sample_time_us=now_us)
        k.step()

    encoder_twist = 0.5 * (shaft_right - shaft_left)
    ground_heading_deg = (
        (ground_right - ground_left) / _TRACK_WIDTH_MM
    ) * (180.0 / 3.141592653589793)
    mean_shaft = 0.5 * (shaft_left + shaft_right)
    return encoder_twist, ground_heading_deg, mean_shaft


def test_1_ground_mismatch_is_encoder_invisible_with_trim_zero(
        trim_kernel_lib):
    """The mechanism proof (docs/sprint-031-postmortem.md §2.2): with a
    1.1% ground-radius mismatch injected on the left wheel and
    straight_trim left at its default 0, the ENCODER twist stays ~0
    (twist hold has nothing to correct -- both wheels are commanded and
    driven identically in shaft/encoder space) while the GROUND heading
    drifts by ~3.4 deg over the 600 mm leg -- the postmortem's own
    tovez G3 number. This is why retuning twist_hold_gain (sprint 031
    tickets 012/015) could never fix this half of the curvature: the
    error twist hold measures is genuinely zero."""
    with TrimKernel(trim_kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
        k.set_twist_hold_gain(_TWIST_HOLD_GAIN)
        assert k.begin() == STATUS_OK

        encoder_twist, ground_heading_deg, _ = _drive_straight_leg(
            k, ground_gain_left=1.0 + _MISMATCH, ground_gain_right=1.0)

        assert encoder_twist == pytest.approx(0.0, abs=1e-3), (
            f"encoder twist {encoder_twist:.6f} counts -- twist hold "
            "should see NOTHING to correct when the mismatch is purely "
            "ground-side (both wheels driven identically in shaft "
            "space)"
        )
        # Sign follows which wheel the mismatch was injected on (here,
        # left gains ground travel, so the heading term below comes out
        # negative) -- the mechanism proof only cares about magnitude.
        assert abs(ground_heading_deg) == pytest.approx(3.4, abs=0.5), (
            f"ground heading {ground_heading_deg:.3f} deg -- expected "
            "~3.4 deg magnitude (docs/sprint-031-postmortem.md §2.2's "
            "own tovez G3 number for a 1.1% mismatch over a 600 mm leg "
            "on a 114.2 mm track)"
        )


def test_2_matching_straight_trim_cancels_the_ground_heading_drift(
        trim_kernel_lib):
    """With the SAME 1.1% ground mismatch as test 1, a matching
    straight_trim (found by two probe runs and linear interpolation --
    the reference straight_trim biases is a LINEAR term, so two points
    determine the zero-crossing exactly, no hand-derived closed-form
    constant needed) brings ground heading at the end of the same leg
    under 0.3 deg (postmortem §3, P2's own acceptance bar)."""
    def heading_at(trim):
        with TrimKernel(trim_kernel_lib) as k:
            k.set_max_duty(100.0)
            k.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
            k.set_twist_hold_gain(_TWIST_HOLD_GAIN)
            k.set_straight_trim(trim)
            assert k.begin() == STATUS_OK
            _, ground_heading_deg, _ = _drive_straight_leg(
                k, ground_gain_left=1.0 + _MISMATCH, ground_gain_right=1.0)
            return ground_heading_deg

    heading_0 = heading_at(0.0)
    probe_trim = 0.01  # [1] arbitrary nonzero probe point
    heading_probe = heading_at(probe_trim)

    # ground_heading(trim) is affine in trim (straight_trim enters the
    # kernel only through a linear reference-integrator term, and
    # nothing in this leg ever saturates a rail/headroom clamp at these
    # small magnitudes) -- two points fix the line exactly.
    slope = (heading_probe - heading_0) / probe_trim
    assert slope != 0.0, "probe trim had no effect -- wiring is broken"
    matching_trim = -heading_0 / slope

    heading_corrected = heading_at(matching_trim)
    assert abs(heading_corrected) < 0.3, (
        f"straight_trim={matching_trim:.6f}: ground heading "
        f"{heading_corrected:.4f} deg -- expected < 0.3 deg "
        "(docs/sprint-031-postmortem.md §3, P2's own bar)"
    )


def test_3_zero_mismatch_zero_trim_leaves_the_leg_straight(
        trim_kernel_lib):
    """No regression on a matched robot (postmortem §3, P2): with no
    ground mismatch and straight_trim at its default 0, ground heading
    stays under 0.05 deg over the leg."""
    with TrimKernel(trim_kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(_FULL_DUTY_VELOCITY)
        k.set_twist_hold_gain(_TWIST_HOLD_GAIN)
        assert k.begin() == STATUS_OK

        encoder_twist, ground_heading_deg, _ = _drive_straight_leg(
            k, ground_gain_left=1.0, ground_gain_right=1.0)

        assert encoder_twist == pytest.approx(0.0, abs=1e-3)
        assert abs(ground_heading_deg) < 0.05, (
            f"ground heading {ground_heading_deg:.4f} deg on a matched "
            "robot with trim 0 -- expected < 0.05 deg (no regression)"
        )


def test_4_straight_trim_wire_field_round_trips(wa):
    """`straight_trim` is settable/gettable via the wire's own SET/GET
    verbs -- the same generic kFields/setKernelValue()/getConfigValue()
    path (ordinal 38) `twist_hold_gain` (ordinal 7) already reaches,
    unlike `default_cruise`/`rotational_slip`'s own dedicated Rig/
    MotionEngine forwards -- so no wire_motion_verb_shim.cpp addition
    is needed here, only the REAL WireAdapter + kernel `wa` fixture
    test_wire_motion_verbs.py already provides. Mirrors that file's own
    test_rotational_slip_wire_field_round_trips_and_reaches_effective_track_width
    in shape."""
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK

    # Default is 0 (no behavior change until a robot's own value is
    # baked separately -- this ticket bakes nothing).
    wa.feed(b"GET straight_trim #1\n")
    reply = wa.take_sink()
    prefix = _ack(1) + b"get straight_trim "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)

    new_trim = 0.0055  # deliberately nonzero and non-default
    wa.feed(f"SET straight_trim {new_trim} #2\n".encode())
    assert wa.take_sink() == _ack(2)

    wa.feed(b"GET straight_trim #3\n")
    reply = wa.take_sink()
    prefix = _ack(3) + b"get straight_trim "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(new_trim, abs=1e-3)

    # Unlike default_cruise/rotational_slip's own ">0, else keep"
    # sentinel validation, straight_trim's sign is meaningful (it
    # cancels a mismatch that can run either way) -- 0 is a real,
    # settable value here, not a silently-ignored no-op.
    wa.feed(b"SET straight_trim 0 #4\n")
    assert wa.take_sink() == _ack(4)
    wa.feed(b"GET straight_trim #5\n")
    reply = wa.take_sink()
    prefix = _ack(5) + b"get straight_trim "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3)

    # Also a negative value round-trips (sign is meaningful).
    wa.feed(f"SET straight_trim {-new_trim} #6\n".encode())
    assert wa.take_sink() == _ack(6)
    wa.feed(b"GET straight_trim #7\n")
    reply = wa.take_sink()
    prefix = _ack(7) + b"get straight_trim "
    assert reply.startswith(prefix)
    assert float(reply[len(prefix):]) == pytest.approx(-new_trim, abs=1e-3)
