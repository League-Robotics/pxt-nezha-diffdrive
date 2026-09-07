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
    # wire_adapter.cpp's runName()/runSignature() delegate to the shared
    # RunRegistry instance, which lives here -- without this TU the link
    # fails on an undefined diffDrive::runRegistry().
    _SRC_DIR / "comms" / "run_registry.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
]

# The one name that is write-only on the wire: `rebase` has no stored
# value and no latch worth reading back, so WireAdapter::onGet() refuses
# it outright rather than manufacture a 0. Every other name in the table
# answers a GET.
WRITE_ONLY_NAMES = {"rebase"}

# ERR_WRITE_ONLY -- Wire::Result::kWriteOnly's wire code
# (`Wire::kErrWriteOnly`, wire_handler.h). Refusing was always right;
# refusing with ERR_UNKNOWN (1) was the defect, because a field the
# robot itself advertises then answered exactly like a typo.
ERR_WRITE_ONLY = 12

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
        assert reply.endswith(f"err {ERR_WRITE_ONLY} #2\n".encode()), (
            f"{name} is documented write-only, so GET must refuse it with "
            f"the write-only code -- NOT the err 1 a typo gets, which is "
            f"what made an advertised field indistinguishable from a "
            f"misspelled one: {reply!r}"
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


# ---------------------------------------------------------------------------
# The go-to deadline (sprint 033 ticket 004): a field that used to be a
# bespoke, call-scoped slot on the singleton, now one row of the surface
# above. These pin the move itself; the parametrized sweeps above
# already cover it as an ordinary field, which is the whole point.
# ---------------------------------------------------------------------------

GOTO_TIMEOUT_NAME = "goto_timeout"
GOTO_TIMEOUT_ORDINAL = 39


def test_goto_timeout_is_an_ordinary_row_of_the_table():
    """Name, ordinal and unit, in the one table -- not a fifth list, and
    not a fresh use of a retired ordinal."""
    rows = {name: (ordinal, unit) for name, ordinal, unit in config_field_rows()}
    assert GOTO_TIMEOUT_NAME in rows, (
        f"config_fields.h no longer names {GOTO_TIMEOUT_NAME}: {sorted(rows)}"
    )
    ordinal, unit = rows[GOTO_TIMEOUT_NAME]
    assert ordinal == GOTO_TIMEOUT_ORDINAL, (
        f"{GOTO_TIMEOUT_NAME} moved to ordinal {ordinal}; ordinals are a "
        f"wire contract and this one was published as "
        f"{GOTO_TIMEOUT_ORDINAL}."
    )
    assert unit == "ms", f"{GOTO_TIMEOUT_NAME}'s unit reads {unit!r}, not 'ms'"
    assert GOTO_TIMEOUT_ORDINAL in set(shims_accessor_ordinals()), (
        "shims.cpp's kConfigAccessors has no row for the go-to deadline "
        "-- the name would ack a SET and silently drop it."
    )


def test_goto_deadline_is_no_longer_a_bespoke_singleton_field():
    """The storage moved: `Rig::goToDeadline` is what the config
    accessors read and write, and the old private handoff field is gone
    by name as well as by shape. `engineSetGoToDeadline()` still writes
    it -- that shim exists to keep every `//%` shim at <=4 parameters,
    which this ticket did not change -- so the check is that it writes
    the CONFIG-backed field, not a private one of its own."""
    shims = _read("shims.cpp")
    assert "pendingGoToDeadline" not in shims, (
        "shims.cpp still carries the pendingGoToDeadline_ field (or a "
        "comment naming it) -- the go-to deadline now lives in the "
        "config table as Rig::goToDeadline."
    )
    assert re.search(r"^\s*uint32_t goToDeadline = 0;\s*//\s*\[ms\]", shims, re.M), (
        "Rig no longer declares `uint32_t goToDeadline = 0;  // [ms]` -- "
        "the field the goto_timeout accessors are supposed to back."
    )
    assert re.search(r"r\.goToDeadline = static_cast<uint32_t>\(v\)", shims), (
        "cfgSetGoToDeadline() no longer writes Rig::goToDeadline."
    )
    assert re.search(
        r"void engineSetGoToDeadline\(uint32_t timeout\)[^\n]*\n"
        r"\s*ensure\(\)\.goToDeadline = timeout;",
        shims,
    ), (
        "engineSetGoToDeadline() either changed signature or no longer "
        "writes the config-backed Rig::goToDeadline -- the block layer's "
        "pre-arm and the wire's `SET goto_timeout` must reach the same "
        "storage, and motion.ts's callers must not have to change."
    )
    assert re.search(r"engineGoToR\(x, y, cruise, arrive, r\.goToDeadline\)", shims), (
        "engineGoToRArmed() no longer reads the deadline from "
        "Rig::goToDeadline."
    )
    assert re.search(r"void engineSetGoToYawRate\(int yawRate\)", shims), (
        "engineSetGoToYawRate()'s signature changed -- this ticket "
        "moved only the deadline's storage; every TS caller of both "
        "shims stays as it was."
    )


def test_goto_timeout_round_trips_a_real_deadline(wa):
    """A SET/GET round trip through the REAL WireAdapter at a value a
    bench host would actually send. The parametrized sweep above already
    round-trips 2.0 through every stored field; this one uses a
    plausible go-to deadline (4500 ms) so the check also covers the
    x1000 wire scaling at a magnitude the 2.0 case cannot reach."""
    wa.feed(f"SET {GOTO_TIMEOUT_NAME} 4500 #1\n".encode())
    assert wa.take_sink() == _ack(1), "SET goto_timeout refused"

    wa.feed(f"GET {GOTO_TIMEOUT_NAME} #2\n".encode())
    reply = wa.take_sink()
    prefix = _ack(2) + f"get {GOTO_TIMEOUT_NAME} ".encode()
    assert reply.startswith(prefix), reply
    assert float(reply[len(prefix):]) == pytest.approx(4500.0, abs=1e-3), reply


def test_goto_timeout_stores_zero_rather_than_keeping_the_prior_value(wa):
    """0 is a legal deadline (MotionEngine::goToR()'s own "already
    expired"), so this field must NOT take the ">0, else keep" shape
    `default_cruise` uses -- otherwise a GET could not read back a state
    the block layer can actually put the robot in."""
    wa.feed(f"SET {GOTO_TIMEOUT_NAME} 4500 #1\n".encode())
    assert wa.take_sink() == _ack(1)
    wa.feed(f"SET {GOTO_TIMEOUT_NAME} 0 #2\n".encode())
    assert wa.take_sink() == _ack(2)

    wa.feed(f"GET {GOTO_TIMEOUT_NAME} #3\n".encode())
    reply = wa.take_sink()
    prefix = _ack(3) + f"get {GOTO_TIMEOUT_NAME} ".encode()
    assert reply.startswith(prefix), reply
    assert float(reply[len(prefix):]) == pytest.approx(0.0, abs=1e-3), (
        f"goto_timeout kept its prior value through a SET of 0: {reply!r}"
    )
