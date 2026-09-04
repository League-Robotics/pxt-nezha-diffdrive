"""tests/host/test_config_descriptor_table.py -- sprint 029 ticket 004,
extended by ticket 009's own `lag` row (design docs/design/motion-profile-unification.md S4.7/S9.5's own test
list, item 5): the ONE descriptor table replacing the three parallel
switches for the shaping fields (review CO-05, scoped to this design).

Two things this file exists to prove, against the REAL WireAdapter +
the real shims.cpp test doubles (wire_motion_verb_shim.cpp), not a
mock:

1. Every wire name in design S4.7's table (`v_floor`, `stop_distance`,
   `accel`, `decel`, `v_max`, `jerk`, `omega_max`, `omega_floor`,
   `arrive_dist`, `arrive_yaw`) round-trips through SET/GET, landing on
   the REAL `MotionLimits` object `MotionEngine::limits()` (not a
   shadow/mock copy) -- see test_get_set_sweeps_every_kfields_entry_
   without_overflow (test_wire_motion_verbs.py) for the fuller sweep
   over EVERY kFields entry, not just these ten; this file is the
   FOCUSED, single-purpose test the design's own S9.5 test list names.
2. The NINE removed names (the eight ordinals design S4.7 marks
   "removed" -- brake_frac, dist_taper, yaw_taper, dist_floor,
   turn_floor, ramp_ms, plateau_min_s, profile_exit -- plus the three
   RENAMED-away old names speed_floor/pivot_overrun/max_yaw_rate, which
   must ALSO now be unknown, not just their new names newly known)
   answer `err 1` (`Wire::Result::kUnknown`) on BOTH GET and SET, for
   one release, per design S4.7: "a stale bench script fails loudly
   instead of silently setting nothing."

Also covers K5 (design S4.5): `SET v_floor <x>` writes ONLY
`MotionLimits::vFloor` -- the kernel's own `Config::vMin` stays pinned
at 0 forever (`shims.cpp`'s `ensure()`, its own `Config` seed comment).

Same two-handle-shim convention as test_wire_motion_verbs.py (see that
file's own header comment for the full rationale) -- this file compiles
its OWN copy of the same six sources into a separate shared library
(`libconfig_descriptor_table_shim.so`) rather than importing that
file's fixtures, since pytest fixtures do not cross test-file
boundaries without a shared conftest.py, and this repo has none under
tests/host/. Only the `wa`-shaped surface (WireHandler + the REAL
WireAdapter + a REAL DiffDrive kernel/MotionEngine over FakeMotor) is
needed here -- the `wv`/WireMockAdapter surface is not exercised by
this file at all.

Run with::

    uv run pytest tests/host/test_config_descriptor_table.py
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
    _SRC_DIR / "comms" / "wire_handler.cpp",
    _SRC_DIR / "comms" / "wire_adapter.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
]

# Wire::DoneReason's DECLARATION-ORDER ordinal (wire_handler.h) -- only
# DONE_NONE is ever reachable through a fresh handle with no motion ever
# armed, which is all this file's own acks need.
DONE_NONE = 0
_DONE_REASON_NAME = {DONE_NONE: "none"}


def _ack(n, last_done=0, reason=DONE_NONE):
    return f"ack {n} {last_done} {_DONE_REASON_NAME[reason]}\n".encode()


def _err(code, id_):
    return f"err {code} #{id_}\n".encode()


# resultCode(Wire::Result::kUnknown) (wire_handler.cpp) -- the ONE error
# code both a decode failure and a merits rejection like an unknown
# field name share; see wire_adapter.cpp's onGet()/onSet() and
# wire_handler.cpp's execGet()/execSet() for the exact path an unknown
# name takes to get here (findField() returns nullptr; onGet() answers
# `false`, onSet() answers `Wire::Result::kUnknown` -- both turned into
# this same `err 1` by execGet()/execSet()).
ERR_UNKNOWN = 1


def _bind(lib):
    """Attach ctypes argtypes/restype for only the WaHandle (wa*)
    surface this file actually calls -- a small subset of
    test_wire_motion_verbs.py's own _bind(), which additionally covers
    the wv* (WireMockAdapter) surface this file never touches."""
    lib.waCreate.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.waCreate.restype = ctypes.c_void_p
    lib.waDestroy.argtypes = [ctypes.c_void_p]
    lib.waDestroy.restype = None
    lib.waFeed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waFeed.restype = None
    lib.waSinkLength.argtypes = [ctypes.c_void_p]
    lib.waSinkLength.restype = ctypes.c_int
    lib.waSinkRead.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waSinkRead.restype = ctypes.c_int
    lib.waSinkClear.argtypes = [ctypes.c_void_p]
    lib.waSinkClear.restype = None
    # this ticket (K5): direct kernel Config::vMin readback -- see its
    # own doc comment in wire_motion_verb_shim.cpp for why
    # getConfigValue(8) cannot be used for this any more.
    lib.waKernelVMin.argtypes = [ctypes.c_void_p]
    lib.waKernelVMin.restype = ctypes.c_float
    return lib


@pytest.fixture(scope="session")
def descriptor_table_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libconfig_descriptor_table_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class WireAdapterHandle:
    """Minimal Pythonic wrapper around one waCreate()/waDestroy() handle
    -- the REAL WireAdapter over a REAL kernel/FakeMotor pair. A smaller
    surface than test_wire_motion_verbs.py's own WireAdapterHandle
    (feed/take_sink/kernel_v_min only); this file needs no motion-verb
    or diag-override setup."""

    def __init__(self, lib, name=b"testbot", serial=b"SN001",
                 drivetrain=b"diffdrive", profile=b"nezha2",
                 version=b"6.0.0"):
        self._lib = lib
        self._name, self._serial = name, serial
        self._drivetrain, self._profile, self._version = (
            drivetrain, profile, version,
        )
        self._handle = lib.waCreate(name, serial, drivetrain, profile,
                                     version)

    def close(self):
        self._lib.waDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def feed(self, data: bytes):
        self._lib.waFeed(self._handle, data, len(data))

    def take_sink(self) -> bytes:
        length = self._lib.waSinkLength(self._handle)
        if length == 0:
            return b""
        buf = ctypes.create_string_buffer(length)
        n = self._lib.waSinkRead(self._handle, buf, length)
        assert n == length
        data = buf.raw[:length]
        self._lib.waSinkClear(self._handle)
        return data

    @property
    def kernel_v_min(self) -> float:
        return self._lib.waKernelVMin(self._handle)


@pytest.fixture
def wa(descriptor_table_lib):
    with WireAdapterHandle(descriptor_table_lib) as w:
        yield w


# Design S4.7's own wire-name table, exactly: {name: (ordinal, value)}.
# Values are inside each field's own documented/validated range
# (motion_limits.h's "positive, else keep"/"'>=0', else keep" setters)
# and deliberately NOT any field's shipped default -- a round trip that
# silently no-ops (validation rejecting the SET) would then show up as
# a mismatch against the field's real default instead of passing by
# coincidence.
_DESIGN_TABLE_FIELDS = {
    "accel": 500.0,          # ordinal 19, [mm/s^2], default 400
    "decel": 700.0,          # ordinal 20, [mm/s^2], default 400
    "v_max": 300.0,          # ordinal 21, [mm/s], default 250
    "jerk": 4000.0,          # ordinal 28, [mm/s^3], default 0
    "omega_max": 90.0,       # ordinal 30, [deg/s], default 0
    "v_floor": 120.0,        # ordinal 8, [mm/s], default 70
    "omega_floor": 25.0,     # ordinal 34, [deg/s], default 20
    "stop_distance": 3.7,    # ordinal 18, [mm], default 0
    "arrive_dist": 2.5,      # ordinal 35, [mm], default 1.0
    "arrive_yaw": 0.6,       # ordinal 36, [deg], default 0.3
    "lag": 0.08,             # ordinal 37, [s], default 0 (ticket 009)
}

# The eight ordinals design S4.7 marks "removed" outright (no
# MotionLimits equivalent, no row in wire_adapter.cpp's kFields at all).
_REMOVED_NAMES = (
    "brake_frac", "dist_taper", "yaw_taper", "dist_floor", "turn_floor",
    "ramp_ms", "plateau_min_s", "profile_exit",
)

# The three OLD names design S4.7 renamed away from -- same ordinal,
# different wire name now, so the OLD name must ALSO be unknown (not
# just newly reachable under its new name).
_RENAMED_AWAY_NAMES = ("speed_floor", "pivot_overrun", "max_yaw_rate")


@pytest.mark.parametrize("name,value", sorted(_DESIGN_TABLE_FIELDS.items()))
def test_design_table_field_round_trips(wa, name, value):
    """Every wire name in design S4.7's table SET/GETs through the REAL
    WireAdapter, landing on the REAL MotionEngine::limits() -- not a
    mock, not a shadow copy. Proves the descriptor table (shims.cpp's
    kLimitsFields) actually routes each name to the field the design
    names, not merely that SOME value comes back."""
    wa.feed(f"SET {name} {value} #1\n".encode())
    assert wa.take_sink() == _ack(1), f"{name}: SET was not acked cleanly"

    wa.feed(f"GET {name} #2\n".encode())
    reply = wa.take_sink()
    prefix = _ack(2) + f"get {name} ".encode()
    assert reply.startswith(prefix), (name, reply)
    got = float(reply[len(prefix):])
    assert got == pytest.approx(value, rel=1e-3, abs=1e-3), (
        f"{name}: SET {value}, GET read back {got} -- the descriptor "
        f"table routed this name to the wrong field, or not at all"
    )


def test_v_floor_writes_motion_limits_not_kernel_v_min(wa):
    """K5 (design S4.5, S8): `v_floor` (ordinal 8) writes ONLY
    MotionLimits::vFloor now -- the kernel's own Config::vMin, which
    ordinal 8 used to reach (the old `speed_floor` name), stays pinned
    at its compiled-in 0 forever. This is the one field in the
    descriptor table whose ORDINAL survived a full reinterpretation
    (kernel servo concept -> profile concept, design S3), so it gets
    its own dedicated proof beyond the generic round-trip sweep above:
    a round trip alone cannot distinguish 'wrote MotionLimits::vFloor'
    from 'wrote both' or 'wrote the kernel field under a new name'."""
    assert wa.kernel_v_min == pytest.approx(0.0)
    wa.feed(b"SET v_floor 250.0 #1\n")
    assert wa.take_sink() == _ack(1)
    # The kernel's own vMin must not have moved even though v_floor
    # (MotionLimits::vFloor) very much did -- see the round-trip test
    # above for proof that side did land.
    assert wa.kernel_v_min == pytest.approx(0.0), (
        "SET v_floor reached the kernel's own Config::vMin -- K5 (design "
        "S4.5) requires it stay pinned at 0; the profile floor lives on "
        "MotionLimits now, not the kernel servo."
    )


@pytest.mark.parametrize("name", sorted(_REMOVED_NAMES))
def test_removed_name_get_answers_err_1(wa, name):
    """Design S4.7: a removed ordinal's wire name answers `err 1`
    (ERR_UNKNOWN) on GET -- not a silent 0, not a decode failure. The
    ack still fires (the line arrived and decoded fine; this is a
    MERITS rejection, same class as any other unrecognized field
    name -- wire_handler.cpp's execGet())."""
    wa.feed(f"GET {name} #1\n".encode())
    assert wa.take_sink() == _ack(1) + _err(ERR_UNKNOWN, 1), (
        f"{name}: removed ordinal's GET did not answer err 1 -- design "
        f"S4.7 requires a stale bench script to fail loudly here"
    )


@pytest.mark.parametrize("name", sorted(_REMOVED_NAMES))
def test_removed_name_set_answers_err_1(wa, name):
    """Design S4.7: a removed ordinal's wire name answers `err 1` on
    SET too -- the write is REFUSED, not silently accepted-and-
    discarded (the pre-ticket-004 behavior this ticket closes: SET used
    to ack normally against a harmless shims.cpp no-op case)."""
    wa.feed(f"SET {name} 1.0 #1\n".encode())
    assert wa.take_sink() == _ack(1) + _err(ERR_UNKNOWN, 1), (
        f"{name}: removed ordinal's SET did not answer err 1 -- a stale "
        f"bench script would silently set nothing and never know"
    )


@pytest.mark.parametrize("name", sorted(_RENAMED_AWAY_NAMES))
def test_renamed_away_old_name_get_answers_err_1(wa, name):
    """The OLD name of a renamed ordinal (speed_floor/pivot_overrun/
    max_yaw_rate) must be unknown too -- the rename genuinely replaced
    the wire name, it did not just add an alias alongside the old one."""
    wa.feed(f"GET {name} #1\n".encode())
    assert wa.take_sink() == _ack(1) + _err(ERR_UNKNOWN, 1), (
        f"{name}: still answers on GET -- the rename to its design S4.7 "
        f"replacement name did not actually retire this old wire name"
    )


@pytest.mark.parametrize("name", sorted(_RENAMED_AWAY_NAMES))
def test_renamed_away_old_name_set_answers_err_1(wa, name):
    wa.feed(f"SET {name} 1.0 #1\n".encode())
    assert wa.take_sink() == _ack(1) + _err(ERR_UNKNOWN, 1), (
        f"{name}: still answers on SET -- the rename to its design S4.7 "
        f"replacement name did not actually retire this old wire name"
    )


def test_bare_get_dump_never_lists_a_removed_or_renamed_away_name(wa):
    """A bare `GET #<id>` dump (wire_adapter.cpp's fieldName()/
    fieldCount(), walked by wire_handler.cpp's execGet()) must never
    offer a removed or renamed-away name for discovery -- the field
    list itself, not just a targeted GET/SET, must reflect the current
    table."""
    wa.feed(b"GET #1\n")
    reply = wa.take_sink()
    body = reply[len(_ack(1)):]
    names = {
        line.split(b" ")[1].decode()
        for line in body.split(b"\n") if line.startswith(b"get ")
    }
    stale = names & (set(_REMOVED_NAMES) | set(_RENAMED_AWAY_NAMES))
    assert not stale, (
        f"bare GET dump still lists retired name(s): {sorted(stale)}"
    )
    for name in _DESIGN_TABLE_FIELDS:
        assert name in names, (
            f"bare GET dump is missing design S4.7 table field {name!r}"
        )
