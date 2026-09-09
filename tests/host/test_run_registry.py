"""tests/host/test_run_registry.py -- the mirror FUNCS discloses.

**What this table is for.** This repo's runnable surface is the
cleartext ``RUN:<name>[:<arg>...]`` carve-out, dispatched by name
against handlers a block program bound with ``onRun()`` -- a table that
lives in TypeScript and differs per program. Nothing in C++ could see
it, so the v6 ``FUNCS`` verb had nothing to enumerate.
``src/comms/run_registry.h`` is the C++ mirror ``onRun()`` publishes
into as it binds, and ``WireAdapter`` reads back out.

**The rule that shapes it.** A listing that quietly disagrees with what
dispatch will actually do is worse than no listing -- it is the "host
reads a short allowlist as the whole allowlist" failure the protocol's
FUNCS section refuses. So: registration is idempotent by name,
truncation is preferred to refusal, and a full table SATURATES with a
visible count rather than evicting an entry that is still dispatchable.

Run with::

    uv run pytest tests/host/test_run_registry.py
"""
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

# The shim's own test instantiation: RunRegistry<4, 8, 12>. Small enough
# that the overflow and truncation edges are reachable in a few calls,
# with the name and signature cells sized differently so a test can
# tell which limit clipped what (the firmware's own default is 24/64).
_SLOTS = 4
_BYTES = 8
_SIG_BYTES = 12


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    loaded = ctypes.CDLL(str(compile_shared_lib(
        tmp_path_factory,
        sources=[_TEST_DIR / "run_registry_shim.cpp"],
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="librun_registry_shim.so",
    )))
    loaded.rrNew.restype = ctypes.c_void_p
    loaded.rrFree.argtypes = [ctypes.c_void_p]
    loaded.rrFree.restype = None
    loaded.rrAdd.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    loaded.rrAdd.restype = ctypes.c_int
    loaded.rrCount.argtypes = [ctypes.c_void_p]
    loaded.rrCount.restype = ctypes.c_int
    loaded.rrName.argtypes = [ctypes.c_void_p, ctypes.c_int]
    loaded.rrName.restype = ctypes.c_char_p
    loaded.rrSignature.argtypes = [ctypes.c_void_p, ctypes.c_int]
    loaded.rrSignature.restype = ctypes.c_char_p
    loaded.rrOverflowCount.argtypes = [ctypes.c_void_p]
    loaded.rrOverflowCount.restype = ctypes.c_uint
    loaded.rrFind.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    loaded.rrFind.restype = ctypes.c_int
    return loaded


class Registry:
    """Thin wrapper around one rrNew()/rrFree() handle, mirroring
    test_run_queue.py's own harness shape."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.rrNew()

    def add(self, name: bytes, signature: bytes = b"") -> bool:
        return bool(self._lib.rrAdd(self._handle, name, signature))

    def count(self) -> int:
        return self._lib.rrCount(self._handle)

    def name(self, index: int) -> bytes:
        return self._lib.rrName(self._handle, index)

    def signature(self, index: int) -> bytes:
        return self._lib.rrSignature(self._handle, index)

    def overflow_count(self) -> int:
        return self._lib.rrOverflowCount(self._handle)

    def find(self, name: bytes) -> int:
        return self._lib.rrFind(self._handle, name)

    def close(self):
        self._lib.rrFree(self._handle)


@pytest.fixture
def reg(lib):
    r = Registry(lib)
    yield r
    r.close()


def test_a_fresh_registry_is_empty(reg):
    """The state a program that bound no onRun() handlers leaves behind
    -- and the state FUNCS answers with no lines at all. Zero is a valid
    answer, not an uninitialised one."""
    assert reg.count() == 0
    assert reg.overflow_count() == 0


def test_names_are_stored_and_read_back_in_registration_order(reg):
    """Registration order is the listing order, so a program's FUNCS
    output reads in the order its handlers were bound rather than in
    some rearranged one an operator cannot predict."""
    assert reg.add(b"tour", b"i->v")
    assert reg.add(b"pivot", b"d->v")
    assert reg.count() == 2
    assert reg.name(0) == b"tour"
    assert reg.signature(0) == b"i->v"
    assert reg.name(1) == b"pivot"


def test_an_empty_signature_is_stored_as_empty_not_refused(reg):
    """"No signature" is the normal case for this repo -- run.ts's
    onRun() block has one fixed calling convention, so it publishes
    every name with an empty signature. execFuncs omits the field
    entirely for these."""
    assert reg.add(b"tour", b"")
    assert reg.count() == 1
    assert reg.signature(0) == b""


def test_an_empty_name_is_refused_and_is_not_an_overflow(reg):
    """An empty name is not ADDRESSABLE -- no RUN: line could reach it
    -- so it is not a registration at all. Deliberately not counted as
    an overflow: overflowCount() means "the table was full", and
    conflating the two would make a program with one bad name look like
    one with a truncated listing."""
    assert not reg.add(b"", b"int->void")
    assert reg.count() == 0
    assert reg.overflow_count() == 0


def test_re_registering_a_name_updates_it_rather_than_duplicating(reg):
    """A block program may legally bind two handlers to one name --
    run.ts dispatches to BOTH -- but the listing enumerates addressable
    NAMES, not handler bindings, so the name must appear exactly once.
    A duplicate row would tell a host there are two callable things when
    there is one."""
    assert reg.add(b"tour", b"")
    assert reg.add(b"tour", b"i->v")
    assert reg.count() == 1
    assert reg.name(0) == b"tour"
    assert reg.signature(0) == b"i->v"


def test_an_overlong_name_is_truncated_rather_than_dropped(reg):
    """Truncation beats refusal here: a name too long for a cell is
    still a name the TypeScript dispatcher will answer to, so half of it
    in the listing beats none. (The wire's own sanitize/truncate pass in
    execFuncs is a separate, later defence -- this one is about the
    table's own fixed cells.)"""
    assert reg.add(b"a" * 40, b"s" * 40)
    assert reg.count() == 1
    assert reg.name(0) == b"a" * (_BYTES - 1)
    assert reg.signature(0) == b"s" * (_SIG_BYTES - 1)


def test_the_signature_cell_is_wider_than_the_name_cell(reg):
    """A signature is a declaration the host parses --
    `(dist:number,speed:number=60)` -- not a short token like a name, so
    it gets its own, larger cell (run_registry.h's SigBytes; 64 in the
    firmware, 12 here). A declaration that would not fit a name cell
    must come back intact from the signature cell, punctuation and all."""
    sig = b"(a:n,b=6)"  # 9 bytes: over the 8-byte name cell, under the 12-byte signature cell
    assert len(sig) > _BYTES - 1
    assert reg.add(b"move", sig)
    assert reg.signature(0) == sig
    # Re-declaring updates in place (run.ts's runSignature() after onRun()).
    assert reg.add(b"move", b"()")
    assert reg.count() == 1
    assert reg.signature(0) == b"()"


def test_an_empty_re_registration_keeps_the_declared_signature(reg):
    """runSignature() may run BEFORE the onRun() it describes, and
    onRun() always registers with "". Measured on gopiv 2026-09-09:
    `clear` and `diag`, declared above their onRun() lines, listed bare
    while every name declared below its onRun() kept its signature. An
    empty signature on a known name is "no opinion", never "erase"."""
    assert reg.add(b"clear", b"()")
    assert reg.add(b"clear", b"")
    assert reg.add(b"clear", None)
    assert reg.count() == 1
    assert reg.signature(0) == b"()"


def test_the_table_saturates_and_counts_rather_than_evicting(reg):
    """The failure mode that matters. A ring that overwrote the oldest
    entry would make FUNCS list a table that no longer matches what
    dispatch does -- names silently missing from an allowlist. Dropping
    the NEWEST and counting it keeps every listed name true, and
    overflowCount() is what tells a reader the listing is partial."""
    for i in range(_SLOTS):
        assert reg.add(f"n{i}".encode(), b"")
    assert reg.count() == _SLOTS
    assert reg.overflow_count() == 0

    assert not reg.add(b"extra", b"")
    assert reg.count() == _SLOTS
    assert reg.overflow_count() == 1
    # Every earlier name survived, unchanged.
    assert [reg.name(i) for i in range(_SLOTS)] == [
        f"n{i}".encode() for i in range(_SLOTS)
    ]
    assert reg.find(b"extra") == -1


def test_re_registering_an_existing_name_works_even_when_full(reg):
    """The dedupe check runs BEFORE the capacity check, so a program
    that rebinds a name it already registered does not spuriously
    overflow a full table."""
    for i in range(_SLOTS):
        assert reg.add(f"n{i}".encode(), b"")
    assert reg.add(b"n0", b"i->v")
    assert reg.count() == _SLOTS
    assert reg.overflow_count() == 0
    assert reg.signature(0) == b"i->v"


def test_non_printable_bytes_are_dropped_from_both_fields(reg):
    """The alphabet rule RunBridge applies to a payload, applied to the
    table's own cells: an entry may be wrong, but it may never be
    unprintable.

    MEASURED gopiv 2026-09-07, fw 1.20260907.1 over the farm USB serial
    daemon: every line came back as `funcs <name> \\xef\\xbf\\xbdc` --
    two junk bytes where the omitted signature belonged, because
    `MSTR()` on a zero-length PXT String does not yield a clean "".
    shims.cpp's registerRunName no longer asks that question of
    ManagedString, and this filter means the answer could not have
    reached the wire even if it did."""
    assert reg.add(b"to\x01ur", b"i\x7f->v")
    assert reg.name(0) == b"tour"
    assert reg.signature(0) == b"i->v"


def test_a_signature_of_only_junk_becomes_empty_not_a_dangling_field(reg):
    """The exact gopiv shape: a signature that is ENTIRELY non-printable
    must sanitize to "", so execFuncs omits the field rather than
    emitting `funcs tour ` with a trailing separator and garbage."""
    assert reg.add(b"tour", b"\x01\x02\x1f")
    assert reg.signature(0) == b""


def test_out_of_range_reads_return_empty_never_null(reg):
    """The never-null contract Wire::Adapter documents for runName()/
    runSignature(): the caller hands these straight to a string API, so
    a null would be a crash rather than an empty listing entry."""
    assert reg.add(b"tour", b"")
    for index in (-1, 1, 99):
        assert reg.name(index) == b""
        assert reg.signature(index) == b""


def test_find_locates_a_registered_name(reg):
    assert reg.add(b"tour", b"")
    assert reg.add(b"pivot", b"")
    assert reg.find(b"pivot") == 1
    assert reg.find(b"nope") == -1
