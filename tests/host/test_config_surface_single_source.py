"""tests/host/test_config_surface_single_source.py -- the wire's config
surface is one list, and this file is what makes that true rather than
aspirational.

**What it used to be.** Four lists of the same thing, kept in step by
hand: `wire_adapter.cpp`'s `kFields` (name -> ordinal), `shims.cpp`'s
`setKernelValue()` switch (ordinal -> setter), its `getConfigValue()`
switch (ordinal -> getter), and `blocks/motion.ts`'s `ConfigField` enum
(TypeScript member -> ordinal). They drifted -- `kFields` and
`ConfigField` were not even the same length -- and the visible cost was
a comment in `protocol.h` citing an ordinal from the wrong namespace
entirely.

**What it is now.**

* `src/comms/config_fields.h` -- names, ordinals, units. Included
  directly by `wire_adapter.cpp`, which keeps no copy.
* `src/shims.cpp` -- behaviour, in two tables keyed by ordinal:
  `kLimitsFields` (the ten motion-shaping fields, over `MotionLimits`)
  and `kConfigAccessors` (everything else, one get/set pair per row).
  This half cannot live in the header: every accessor reaches into
  `Rig`, the kernel or the motion engine, so it needs `pxt.h`, and the
  header has to stay host-portable.
* `blocks/motion.ts`'s `ConfigField` -- generated from the header by
  `tools/gen_config_field_enum.py` and committed;
  `tests/tools/test_gen_config_field_enum.py` fails if the checked-in
  enum and a fresh generation disagree.

The split between the header and `shims.cpp` is by portability, not by
preference, and it is the one seam a hand-kept list could creep back
into. That seam is what the source-reading tests below hold shut: the
ordinals the header names and the ordinals `shims.cpp` implements must
be the same set, exactly, in both directions -- and the host test
double must implement that same set, or every compiled wire test in
this directory is exercising a different surface than the robot runs.

The compiled half then proves the surface actually works end to end:
every name in the header round-trips through `SET`/`GET` against the
REAL `WireAdapter`, except the one name documented as write-only.

Same two-handle-shim convention as `test_wire_motion_verbs.py` (see that
file's own header comment) -- its own copy of the shared library, since
pytest fixtures do not cross test-file boundaries without a conftest.py
and this directory has none.

Run with::

    uv run pytest tests/host/test_config_surface_single_source.py
"""

import ctypes
import pathlib
import re

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
_SRC_DIR = _REPO_ROOT / "src"

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _SRC_DIR / "comms" / "wire_handler.cpp",
    _SRC_DIR / "comms" / "wire_adapter.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
]

# The one name that is write-only on the wire: `rebase` has no stored
# value and no latch worth reading back, so WireAdapter::onGet() refuses
# it outright rather than manufacture a 0. Every other name in the table
# answers a GET.
WRITE_ONLY_NAMES = {"rebase"}

# Names whose GET answers a live latch rather than the value just SET --
# write-triggered actions wearing a config field's clothes. A round trip
# through these proves the SET is accepted and the GET is well-formed,
# not that a value survived.
ACTION_NAMES = {"stall_clear", "estop_clear"} | WRITE_ONLY_NAMES

# `lambda_enabled` is a boolean wearing a float's clothes: the setter
# coerces any nonzero to a stored 1.0, so its honest round trip is
# "write 2.0, read 1.0". Every other stored field reads back what it was
# written.
COERCED_READBACK = {"lambda_enabled": 1.0}

DONE_NONE = 0


def _ack(n):
    return f"ack {n} 0 none\n".encode()


def _read(relative):
    return (_SRC_DIR / relative).read_text()


# ---------------------------------------------------------------------------
# Source-reading half: the seam between the header's names and
# shims.cpp's behaviour, and between production and the test double.
# ---------------------------------------------------------------------------


def config_field_rows():
    """[(wire_name, ordinal, unit)] from comms/config_fields.h, in
    declaration order -- which is also the order a bare wire `GET`
    dumps the surface in."""
    text = _read("comms/config_fields.h")
    table = re.search(r"kConfigFields\[\]\s*=\s*\{(.*?)\n\};", text, re.DOTALL)
    assert table, "config_fields.h's kConfigFields[] table was not found"
    rows = re.findall(r'\{"(\w+)",\s*(\d+),\s*"([^"]*)"\}', table.group(1))
    assert rows, "config_fields.h's kConfigFields[] table has no rows"
    return [(name, int(ordinal), unit) for name, ordinal, unit in rows]


def _table_ordinals(text, table_name, row_pattern):
    match = re.search(
        table_name + r"\[\]\s*=\s*\{(.*?)\n\};", text, re.DOTALL
    )
    assert match, f"{table_name}[] was not found"
    ordinals = [int(n) for n in re.findall(row_pattern, match.group(1))]
    assert ordinals, f"{table_name}[] has no rows this test recognizes"
    return ordinals


def shims_limits_ordinals():
    return _table_ordinals(
        _read("shims.cpp"), "kLimitsFields", r"\{(\d+),\s*&MotionLimits::"
    )


def shims_accessor_ordinals():
    return _table_ordinals(
        _read("shims.cpp"),
        "kConfigAccessors",
        r"\{(\d+),\s*&cfgGet\w+,\s*&cfgSet\w+\}",
    )


def double_accessor_ordinals():
    text = (_TEST_DIR / "wire_motion_verb_shim.cpp").read_text()
    return _table_ordinals(
        text, "kWaConfigAccessors", r"\{(\d+),\s*&waGet\w+,\s*&waSet\w+\}"
    )


def double_limits_ordinals():
    """The test double mirrors kLimitsFields as a pair of switches over
    the same ordinals (it writes MotionLimits through the handle's own
    engine rather than through Rig's). Both directions must cover the
    same set, so this reads the setter side and the getter side and
    insists they agree before comparing against production."""
    text = (_TEST_DIR / "wire_motion_verb_shim.cpp").read_text()
    covered = []
    for signature in (
        r"static bool waSetLimitsFieldIfKnown\(int field, float v\) \{(.*?)\n\}",
        r"static bool waGetLimitsFieldIfKnown\(int field, float& out\) \{(.*?)\n\}",
    ):
        match = re.search(signature, text, re.DOTALL)
        assert match, f"wire_motion_verb_shim.cpp: {signature} not found"
        covered.append({int(n) for n in re.findall(r"case (\d+):", match.group(1))})
    assert covered[0] == covered[1], (
        f"the test double's shaping-field SET and GET mirrors cover "
        f"different ordinals: {sorted(covered[0] ^ covered[1])}"
    )
    return covered[0]


def test_config_field_table_has_no_duplicate_name_or_ordinal():
    """A name or ordinal appearing twice in the one table would put the
    surface right back where it started -- two definitions of one field,
    with whichever the linear search hits first silently winning."""
    rows = config_field_rows()
    names = [name for name, _, _ in rows]
    ordinals = [ordinal for _, ordinal, _ in rows]
    assert len(set(names)) == len(names), (
        f"config_fields.h names a field twice: "
        f"{sorted({n for n in names if names.count(n) > 1})}"
    )
    assert len(set(ordinals)) == len(ordinals), (
        f"config_fields.h uses an ordinal twice: "
        f"{sorted({o for o in ordinals if ordinals.count(o) > 1})}"
    )


def test_every_row_carries_a_unit():
    """The unit is the row's own documentation of what the (x1000-scaled)
    wire number means. An empty one is a row nobody finished."""
    missing = [name for name, _, unit in config_field_rows() if not unit.strip()]
    assert not missing, f"config_fields.h rows with no unit: {missing}"


def test_shims_cpp_implements_exactly_the_ordinals_the_table_names():
    """The header's ordinals and shims.cpp's two behaviour tables must
    partition each other exactly.

    * An ordinal in the header with no behaviour is a name the wire
      advertises, acks, and silently drops.
    * An ordinal with behaviour but no header row is unreachable code
      that reads like a live field.
    * An ordinal in BOTH shims.cpp tables is two definitions of one
      field: findLimitsField() runs first, so the accessor row would be
      dead while looking authoritative.
    """
    table = {ordinal for _, ordinal, _ in config_field_rows()}
    limits = set(shims_limits_ordinals())
    accessors = set(shims_accessor_ordinals())

    overlap = limits & accessors
    assert not overlap, (
        f"shims.cpp defines ordinal(s) {sorted(overlap)} in both "
        f"kLimitsFields[] and kConfigAccessors[]."
    )
    assert limits | accessors == table, (
        f"comms/config_fields.h and shims.cpp's behaviour tables have "
        f"diverged.\n"
        f"  named but not implemented: {sorted(table - (limits | accessors))}\n"
        f"  implemented but not named: {sorted((limits | accessors) - table)}"
    )


def test_host_double_covers_the_same_ordinals_as_production():
    """wire_motion_verb_shim.cpp mirrors shims.cpp's config surface for
    every compiled wire test in this directory. If it covers a different
    set of ordinals, those tests pass against a surface the robot does
    not have -- the exact failure mode a test double earns its keep by
    not having."""
    assert set(double_accessor_ordinals()) == set(shims_accessor_ordinals()), (
        f"the test double's kWaConfigAccessors and shims.cpp's "
        f"kConfigAccessors cover different ordinals: "
        f"{sorted(set(double_accessor_ordinals()) ^ set(shims_accessor_ordinals()))}"
    )
    assert double_limits_ordinals() == set(shims_limits_ordinals()), (
        f"the test double's shaping-field mirror and shims.cpp's "
        f"kLimitsFields cover different ordinals: "
        f"{sorted(double_limits_ordinals() ^ set(shims_limits_ordinals()))}"
    )


def test_wire_adapter_keeps_no_second_copy_of_the_name_table():
    """wire_adapter.cpp reads the header; it must not grow its own list
    back. A `{"name", ordinal}`-shaped row anywhere in that file is the
    old `kFields` returning under a new name."""
    text = _read("comms/wire_adapter.cpp")
    code = re.sub(r"//[^\n]*", "", text)
    rows = re.findall(r'\{\s*"(\w+)"\s*,\s*\d+\s*[,}]', code)
    assert not rows, (
        f"wire_adapter.cpp has grown a second name/ordinal table again: "
        f"{rows}. The one list lives in comms/config_fields.h."
    )
    assert '#include "config_fields.h"' in text, (
        "wire_adapter.cpp no longer includes config_fields.h -- it has "
        "to read the table it stopped copying."
    )


# ---------------------------------------------------------------------------
# Compiled half: the surface actually works, end to end, for every name.
# ---------------------------------------------------------------------------


def _bind(lib):
    lib.waCreate.argtypes = [ctypes.c_char_p] * 5
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
    return lib


@pytest.fixture(scope="session")
def config_surface_lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        out_name="libconfig_surface_shim.so",
    )
    return _bind(ctypes.CDLL(str(lib_path)))


class WireAdapterHandle:
    """One waCreate()/waDestroy() handle around the REAL WireAdapter over
    a REAL kernel/FakeMotor pair -- feed/take_sink only."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.waCreate(
            b"testbot", b"SN001", b"diffdrive", b"nezha2", b"6.0.0"
        )

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
        assert self._lib.waSinkRead(self._handle, buf, length) == length
        data = buf.raw[:length]
        self._lib.waSinkClear(self._handle)
        return data


@pytest.fixture
def wa(config_surface_lib):
    with WireAdapterHandle(config_surface_lib) as w:
        yield w


@pytest.mark.parametrize(
    "name,ordinal", [(name, ordinal) for name, ordinal, _ in config_field_rows()]
)
def test_every_table_name_is_reachable_over_the_wire(wa, name, ordinal):
    """Every name the table declares is SET-able through the REAL
    WireAdapter, and every one except the documented write-only field
    answers a well-formed GET. A name that acks a SET and then answers
    `err 1` on GET (or vice versa) is a half-wired ordinal -- which is
    what a hand-kept list produces the moment someone updates one of its
    copies."""
    wa.feed(f"SET {name} 0 #1\n".encode())
    assert wa.take_sink() == _ack(1), f"{name} (ordinal {ordinal}): SET refused"

    wa.feed(f"GET {name} #2\n".encode())
    reply = wa.take_sink()
    if name in WRITE_ONLY_NAMES:
        assert reply.endswith(b"err 1 #2\n"), (
            f"{name} is documented write-only, so GET must refuse it "
            f"exactly the way an unknown name is refused: {reply!r}"
        )
        return
    prefix = _ack(2) + f"get {name} ".encode()
    assert reply.startswith(prefix), (name, reply)
    float(reply[len(prefix):])  # well-formed number, or this raises


@pytest.mark.parametrize(
    "name,ordinal",
    [
        (name, ordinal)
        for name, ordinal, _ in config_field_rows()
        if name not in ACTION_NAMES
    ],
)
def test_every_stored_field_round_trips_its_value(wa, name, ordinal):
    """The stored fields -- everything that is not a write-triggered
    action -- must give back what was written. 2.0 is inside every
    field's own validated range (all of them accept a positive value;
    the "positive, else keep" setters would silently drop a 0 and this
    test would then be reading a default back and calling it a round
    trip)."""
    expected = COERCED_READBACK.get(name, 2.0)
    wa.feed(f"SET {name} 2.0 #1\n".encode())
    assert wa.take_sink() == _ack(1), f"{name}: SET refused"

    wa.feed(f"GET {name} #2\n".encode())
    reply = wa.take_sink()
    prefix = _ack(2) + f"get {name} ".encode()
    assert reply.startswith(prefix), (name, reply)
    got = float(reply[len(prefix):])
    assert got == pytest.approx(expected, abs=1e-3), (
        f"{name} (ordinal {ordinal}) read back {got}, not the {expected} "
        f"its own SET of 2.0 should have stored -- its GET and its SET "
        f"are not addressing the same field."
    )
