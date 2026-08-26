"""tests/host/test_heading_wrap.py -- host test for src/core/heading_wrap.h's
wrapRadians() (sprint 006 ticket 004,
clasi/issues/otos-seed-heading-clamp.md / code review KERN-05: seeding
the OTOS with |heading| > 180 deg silently CLAMPED instead of wrapping,
up to ~170 deg of seed error).

**Why this is the only host-testable proxy for the fix.** `otos_port.h`
includes pxt.h unconditionally, so `OtosPort` -- the actual call site
(`OtosPort::setPose()`, src/platform/otos_port.cpp) -- cannot be compiled into
any host test at all. `heading_wrap.h` carries the one piece of that
fix's logic that CAN be: the pure wrap math. This suite exercises it
directly (`headingWrapWrapRadians()`) and also proves the exact LSB
round trip the real register write would produce
(`headingWrapRoundTripLsb()`, mirroring `OtosPort::writePoseMm()`'s
quantization field-for-field -- see heading_wrap_shim.cpp). Wiring the
wrap into `OtosPort::setPose()` itself is review-verified only.

Run with::

    uv run pytest tests/host/test_heading_wrap.py
"""

import ctypes
import math
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

_SHIM_SOURCES = [_TEST_DIR / "heading_wrap_shim.cpp"]

# otos_port.h's kHdgRadPerLsb -- one LSB, in degrees -- duplicated here
# purely to size the round-trip quantization tolerance in this test's
# own assertions (not to reimplement the quantizer: that lives in
# heading_wrap_shim.cpp, mirroring OtosPort::writePoseMm() exactly).
_ONE_LSB_DEG = 0.00549


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libheading_wrap_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.headingWrapWrapRadians.argtypes = [ctypes.c_float]
    loaded.headingWrapWrapRadians.restype = ctypes.c_float
    loaded.headingWrapRoundTripLsb.argtypes = [ctypes.c_float]
    loaded.headingWrapRoundTripLsb.restype = ctypes.c_float
    return loaded


def _deg2rad(deg):
    return deg * math.pi / 180.0


def _rad2deg(rad):
    return rad * 180.0 / math.pi


# (input degrees, expected wrapped degrees) -- independently re-derived
# (not copied from the implementation), covering the exact cases the
# ticket and code review name plus the boundary/multiples-of-360/
# negative-wrap sweep the ticket's own direction calls for.
_WRAP_CASES = [
    # The ticket's and KERN-05's own named cases.
    (350.0, -10.0),
    (-350.0, 10.0),
    (720.0, 0.0),
    (-720.0, 0.0),
    # Zero and small values (sanity: unaffected by wrap).
    (0.0, 0.0),
    (1.0, 1.0),
    (-1.0, -1.0),
    (90.0, 90.0),
    (-90.0, -90.0),
    (179.0, 179.0),
    (-179.0, -179.0),
    # Multiples of 360 -- must collapse to exactly 0.
    (360.0, 0.0),
    (-360.0, 0.0),
    (1080.0, 0.0),  # 3 * 360
    (-1080.0, 0.0),
    # Just past +/-180 -- wraps to the OPPOSITE sign, close to the
    # opposite boundary. This is the exact region where wrapping and
    # clamping diverge most sharply from each other.
    (181.0, -179.0),
    (-181.0, 179.0),
    (180.01, -179.99),
    (-180.01, 179.99),
    # Multiples of 360 offset from the boundary.
    (540.0, 180.0),  # 360 + 180
    (-540.0, 180.0),  # -360 - 180
]


@pytest.mark.parametrize("deg_in,deg_expected", _WRAP_CASES, ids=[
    f"{d[0]}deg" for d in _WRAP_CASES
])
def test_wrap_radians_matches_correctly_wrapped_equivalent(
    lib, deg_in, deg_expected
):
    """wrapRadians() must match the independently-computed correctly-
    wrapped equivalent, not the old clamp-to-+/-179.89deg behavior."""
    got = lib.headingWrapWrapRadians(ctypes.c_float(_deg2rad(deg_in)))
    assert _rad2deg(got) == pytest.approx(deg_expected, abs=1e-3)


def test_wrap_radians_stays_in_range_over_a_wide_sweep(lib):
    """Every wrapped result must land in (-pi, pi] over a wide sweep of
    inputs, including many multiples of 2*pi and many odd multiples of
    pi -- never outside the range, and never exactly -pi."""
    kPi = math.pi
    for deg in range(-2000, 2001, 7):  # odd step avoids only ever
        rad = _deg2rad(float(deg))     # landing on nice round numbers
        wrapped = lib.headingWrapWrapRadians(ctypes.c_float(rad))
        assert -kPi < wrapped <= kPi + 1e-4, (
            f"deg={deg} rad={rad} wrapped={wrapped} out of (-pi, pi]"
        )
        assert wrapped != pytest.approx(-kPi, abs=1e-6), (
            f"deg={deg} wrapped to -pi; canonical representative must "
            f"be +pi"
        )


# ---- LSB round-trip: proves what the real register write would do ----

@pytest.mark.parametrize("deg_in,deg_expected", [
    (350.0, -10.0),
    (-350.0, 10.0),
    (720.0, 0.0),
    (-720.0, 0.0),
    (90.0, 90.0),
    (-90.0, -90.0),
])
def test_round_trip_lsb_matches_real_register_write(lib, deg_in, deg_expected):
    """headingWrapRoundTripLsb() mirrors OtosPort::writePoseMm()'s exact
    quantization (wrap -> lroundf into LSB units -> clamp -> back to
    float) -- this proves the actual LSB round trip the real chip
    register write would produce for a seed heading outside +/-180 deg,
    not just the pre-quantization wrap value. Tolerance is a few LSBs
    (~0.00549 deg each) to absorb float32 rounding."""
    got = lib.headingWrapRoundTripLsb(ctypes.c_float(_deg2rad(deg_in)))
    assert _rad2deg(got) == pytest.approx(deg_expected, abs=3 * _ONE_LSB_DEG)


def test_round_trip_lsb_at_exact_180_boundary_still_reads_179_89(lib):
    """The ticket's own called-out boundary case: exactly +/-180 deg
    (+/-pi) wraps to the canonical +pi representative, but the chip's
    int16 register (full scale +/-pi, one LSB ~0.00549 deg) cannot
    represent +pi exactly -- it lands one LSB outside the representable
    range and OtosPort::writePoseMm()'s pre-existing x/y-style clamp
    still catches it, exactly as it did before this fix. This is NOT a
    regression: it is the documented, measured hardware behavior
    ("180 deg reads back as 179.89 deg") that wrapping and clamping
    happen to agree on at this one exact boundary -- the bug this
    ticket fixes is for headings BEYOND +/-180 deg (see the 350 deg
    case above), not at exactly +/-180 deg."""
    for deg_in in (180.0, -180.0):
        got = lib.headingWrapRoundTripLsb(ctypes.c_float(_deg2rad(deg_in)))
        assert _rad2deg(got) == pytest.approx(179.89, abs=0.01)


def test_round_trip_lsb_never_exceeds_int16_range(lib):
    """No input, however large, should quantize outside the chip's
    representable +/-32767 LSB range once wrapped first."""
    kOneLsbRad = _deg2rad(_ONE_LSB_DEG)
    kMaxRad = 32767 * kOneLsbRad
    for deg in (-100000.0, -3600.0, -365.0, 365.0, 3600.0, 100000.0):
        got = lib.headingWrapRoundTripLsb(ctypes.c_float(_deg2rad(deg)))
        assert -kMaxRad - 1e-3 <= got <= kMaxRad + 1e-3
