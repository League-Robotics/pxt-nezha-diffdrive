"""tests/host/test_motor_wiring.py -- the decision behind the
`configure motor` block (src/core/motor_wiring.h).

THE BUG THIS EXISTS FOR. configureMotor() (shims.cpp) shipped on
2026-09-12 refusing any request that named the port the OTHER wheel was
on, to keep the pair from ever sharing one motor:

    if (port == other.wiredPort()) return;   // would strand a wheel

With the shipped defaults (left M1, right M2) that rejected BOTH lines of
the swap a mirror-wired robot needs --

    configureMotor(Left,  M2, Reversed)   # right is on M2 -> returned
    configureMotor(Right, M1, Forward)    # left  is on M1 -> returned

-- so the block did nothing at all, in silence. And because the refusal
came before `fwdSign` was read, changing the direction dropdown did
nothing either, which is how it presented: "I can swap them from both
forward to both reversed and Tovez still goes backwards."

It reached a robot because nothing could test it: shims.cpp includes
pxt.h and cannot be host-compiled. Hence motor_wiring.h, which holds the
decision as a pure function, and hence this file.

THE RULE NOW: naming the other wheel's port is a SWAP, not an error --
the two exchange ports, each keeping its own direction. The pair is
never left sharing a port, and no request is ever silently refused
except an out-of-range one, which changes nothing at all.
"""

import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

_SHIM_SOURCES = [_TEST_DIR / "motor_wiring_shim.cpp"]

# shims.cpp's Rig literals: the wiring a board runs before any
# `configure motor` call. Left on M1 reversed, right on M2 forward.
DEFAULT_LEFT = (1, -1)
DEFAULT_RIGHT = (2, 1)

# tovez's measured wiring (radio-robot-lib config/robots/tovez.json,
# geometry.firmware_bake.motors): left on port 2, right on port 1.
TOVEZ_LEFT = (2, -1)
TOVEZ_RIGHT = (1, 1)


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libmotor_wiring_shim.so",
    )
    handle = ctypes.CDLL(str(lib_path))
    handle.motorWiringApply.restype = None
    handle.motorWiringApply.argtypes = [ctypes.c_int] * 6 + [
        ctypes.POINTER(ctypes.c_int)
    ] * 4
    handle.motorWiringPortValid.restype = ctypes.c_int
    handle.motorWiringPortValid.argtypes = [ctypes.c_int]
    handle.motorWiringSignValid.restype = ctypes.c_int
    handle.motorWiringSignValid.argtypes = [ctypes.c_int]
    return handle


def apply(lib, target, other, request):
    """Resolve one request; returns (target, other) as (port, sign) pairs."""
    out = [ctypes.c_int(0) for _ in range(4)]
    lib.motorWiringApply(
        target[0], target[1], other[0], other[1], request[0], request[1],
        *[ctypes.byref(o) for o in out],
    )
    return (out[0].value, out[1].value), (out[2].value, out[3].value)


# ---- the regression itself -------------------------------------------

def test_naming_the_other_wheels_port_swaps_rather_than_refusing(lib):
    """The exact call that used to be a silent no-op."""
    target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, TOVEZ_LEFT)
    assert target == TOVEZ_LEFT, "left must take M2 -- this used to return"
    assert other == TOVEZ_RIGHT, "right must move to the vacated M1"


def test_the_two_line_tovez_swap_lands_on_tovez_wiring(lib):
    """Both lines of the documented tovez setup, in order, from defaults."""
    left, right = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, TOVEZ_LEFT)
    # Second line names the RIGHT side, so target/other change places.
    right, left = apply(lib, right, left, TOVEZ_RIGHT)
    assert (left, right) == (TOVEZ_LEFT, TOVEZ_RIGHT)


def test_one_line_is_enough_and_the_second_is_a_no_op(lib):
    """A swap is fully expressed by naming ONE side; the other line
    confirms rather than re-swaps. A second call that re-swapped would
    put the robot back where it started -- the failure mode a
    swap-on-collision rule could plausibly have introduced."""
    left, right = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, TOVEZ_LEFT)
    right_again, left_again = apply(lib, right, left, TOVEZ_RIGHT)
    assert (left_again, right_again) == (left, right)


def test_direction_only_change_is_applied(lib):
    """Keeping the port and flipping the sign must actually flip it --
    the half of the block that looked inert because the refusal came
    before the sign was read."""
    target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, (1, 1))
    assert target == (1, 1)
    assert other == DEFAULT_RIGHT


def test_both_sides_reversed_keeps_both_ports(lib):
    """"Both forward -> both reversed", the other thing tried against the
    broken build. Ports stay; only signs move."""
    left, right = apply(lib, (1, 1), (2, 1), (1, -1))
    right, left = apply(lib, right, left, (2, -1))
    assert left == (1, -1)
    assert right == (2, -1)


# ---- the invariant the old guard was protecting ----------------------

def test_the_pair_never_shares_a_port(lib):
    """Over every reachable request from every legal starting pair."""
    for tp in range(1, 5):
        for op in range(1, 5):
            if tp == op:
                continue  # not a state the pair can be in
            for rp in range(1, 5):
                for rs in (1, -1):
                    target, other = apply(lib, (tp, -1), (op, 1), (rp, rs))
                    assert target[0] != other[0], (
                        f"({tp},{op}) + request port {rp} -> both on "
                        f"{target[0]}"
                    )


def test_moving_to_a_free_port_leaves_the_other_wheel_alone(lib):
    """Only a genuine collision moves the other wheel."""
    target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, (3, 1))
    assert target == (3, 1)
    assert other == DEFAULT_RIGHT


def test_the_other_wheel_keeps_its_own_direction_through_a_swap(lib):
    """A swap exchanges PORTS. The displaced wheel's sign is its own and
    must survive -- taking the requester's sign would silently reverse a
    wheel nobody asked about."""
    target, other = apply(lib, (1, -1), (2, 1), (2, -1))
    assert target == (2, -1)
    assert other == (1, 1), "right kept +1 and moved to M1"


# ---- refusal is reserved for genuinely invalid requests --------------

@pytest.mark.parametrize("port", [0, 5, -1, 99])
def test_out_of_range_port_changes_nothing(lib, port):
    target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, (port, 1))
    assert (target, other) == (DEFAULT_LEFT, DEFAULT_RIGHT)


@pytest.mark.parametrize("sign", [0, 2, -2])
def test_out_of_range_sign_changes_nothing(lib, sign):
    """Crucially it must not move the OTHER wheel either: applying half
    of a refused request is how both wheels would end up on one port."""
    target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, (2, sign))
    assert (target, other) == (DEFAULT_LEFT, DEFAULT_RIGHT)


def test_validity_helpers_match_the_brick(lib):
    assert [p for p in range(-2, 8) if lib.motorWiringPortValid(p)] == [1, 2, 3, 4]
    assert [s for s in range(-3, 4) if lib.motorWiringSignValid(s)] == [-1, 1]


# ---- idempotence ------------------------------------------------------

def test_feeding_the_result_back_in_changes_nothing(lib):
    """Setup code runs on every boot, and a program may set the same
    wiring twice; neither may ratchet the pair somewhere new."""
    for request in (TOVEZ_LEFT, (3, 1), (1, 1)):
        target, other = apply(lib, DEFAULT_LEFT, DEFAULT_RIGHT, request)
        again_target, again_other = apply(lib, target, other, request)
        assert (again_target, again_other) == (target, other), request
