"""tests/host/test_radio_address_derivation.py -- host test for
src/comms/radio_transport.h's deriveRadioAddress() and
selectRadioGroup() (sprint 025 ticket 002,
derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md).

**Why this is the only host-testable proxy for the fix.**
radio_transport.cpp includes pxt.h (uBit.radio, microbit_friendly_name()),
so RadioTransport::ensureRadioReady() itself -- the actual call site --
cannot be compiled into any host test at all (src/DESIGN.md S1's
layering table). radio_transport.h, unlike its .cpp, has no CODAL
dependency (only <cstddef>/<cstdint>), so deriveRadioAddress() and
selectRadioGroup() -- the two pieces of this ticket that ARE pure logic
-- can be. Wiring them into ensureRadioReady() (reading
microbit_friendly_name(), respecting groupOverridden_, and the
enable/band/group/power call order) is review-verified only -- see
radio_transport.cpp's ensureRadioReady() for that wiring.

**D1, not D2 -- and why.** docs/radio-addressing.md publishes two
digests over the full 3125-name space: D1 (`full_space_sha256`,
forward-only -- encode + addr) and D2 (`conformance_sha256`, which
additionally forces decode() and reverse() to run and hashes their
output -- the PRIMARY conformance gate for an implementation that has
both directions). This ticket's C++ implements only the forward
direction: deriveRadioAddress() maps a name to a (channel, group)
pair. There is no C++ `reverse()` (pair -> name/index) in this ticket's
scope -- that direction belongs to `!N?` readback and diagnostics,
which no acceptance criterion here asks for -- so a D2 dump (whose
last column is `reverse(channel, group)`) cannot be produced from this
shim at all. Per docs/radio-addressing.md's own "Dump protocol", an
implementation that only has the forward direction emits v1 and is
checked against D1; that is what this suite does. This means D1's
usual caveat applies at the protocol level: it does not, on its own,
prove a SEPARATELY exposed `decode()` is correct. In THIS
implementation there is no separate decode() to be wrong out from
under it, though: deriveRadioAddress() has exactly one code path from
`name` to `(channel, group)`, and that path computes the base-5 index
`n` from `name` (the decode step) before deriving the pair from it --
there is no addr()-only fast path that could bypass a broken decode
and still pass D1. So this suite's D1 check does fully exercise this
file's own name-to-address logic across the whole 3125-name space; it
is D1 (not D2) only because this ticket never implements reverse(),
not because decode() is untested here.

Run with::

    uv run pytest tests/host/test_radio_address_derivation.py -v
"""

import ctypes
import hashlib
import json
import pathlib
import sys

import pytest

from test_kernel_harness import compile_shared_lib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent
_TOOLS_DIR = _REPO_ROOT / "tools"
_VECTORS_PATH = _REPO_ROOT / "docs" / "radio-address-vectors.json"

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import radio_address  # noqa: E402  (path must be set up first)

_SHIM_SOURCES = [_TEST_DIR / "radio_address_shim.cpp"]

# Legacy fallback pair deriveRadioAddress() must write on ANY
# validation failure -- the fixed values radio_transport.h used before
# this function existed (radio_transport.h's kTransmitPower/kChannel
# block, pre-sprint-025).
_LEGACY_FALLBACK_CHANNEL = 4
_LEGACY_FALLBACK_GROUP = 10


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    lib_path = compile_shared_lib(
        tmp_path_factory,
        sources=_SHIM_SOURCES,
        include_dirs=[_SRC_DIR, _TEST_DIR],
        out_name="libradio_address_shim.so",
    )
    loaded = ctypes.CDLL(str(lib_path))
    loaded.radioAddressDerive.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8),
    ]
    loaded.radioAddressDerive.restype = ctypes.c_int
    loaded.radioAddressSelectGroup.argtypes = [
        ctypes.c_int,
        ctypes.c_uint8,
        ctypes.c_uint8,
    ]
    loaded.radioAddressSelectGroup.restype = ctypes.c_uint8
    return loaded


@pytest.fixture(scope="module")
def vectors():
    """The normative machine-readable contract, loaded once. Every
    digest/reject/normalize-equivalent value asserted below comes from
    this fixture -- never a second hardcoded copy (per
    .claude/rules/measurement-citations.md's sibling principle for
    citations: a duplicated constant is a second thing that can
    drift)."""
    return json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


def _derive(lib, name):
    """Call the shim's deriveRadioAddress() wrapper. Returns
    (valid, channel, group)."""
    channel = ctypes.c_uint8(0)
    group = ctypes.c_uint8(0)
    encoded = None if name is None else name.encode("utf-8")
    valid = lib.radioAddressDerive(
        encoded, ctypes.byref(channel), ctypes.byref(group)
    )
    return bool(valid), channel.value, group.value


# ---------------------------------------------------------------------------
# Full-space digest: the primary proof this C++ implementation matches
# docs/radio-addressing.md across all 3125 names, not just the sampled
# rows below.
# ---------------------------------------------------------------------------


def test_full_space_d1_digest_matches_the_published_full_space_sha256(
    lib, vectors
):
    """For n = 0..3124, encode n to its name in Python
    (radio_address.index_to_name -- the reference `encode`), derive
    that name's (channel, group) through the C++ shim, and hash the D1
    canonical form '<name>,<channel>,<group>\\n'. Must equal
    docs/radio-address-vectors.json's $.properties.full_space_sha256 --
    proof by digest that this C++ header's deriveRadioAddress()
    reproduces the SAME map as the Python reference and the spec, over
    the entire name space, not merely the handful of names exercised
    by the other tests in this file."""
    lines = []
    for n in range(3125):
        name = radio_address.index_to_name(n)
        valid, channel, group = _derive(lib, name)
        assert valid, (
            f"deriveRadioAddress() rejected {name!r} (n={n}), a name "
            f"generated by the reference encoder -- every well-formed "
            f"CVCVC name must be accepted"
        )
        lines.append(f"{name},{channel},{group}\n")

    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    expected = vectors["properties"]["full_space_sha256"]
    assert digest == expected, (
        f"full-space D1 digest mismatch: got {digest}, expected "
        f"{expected} (docs/radio-address-vectors.json's "
        f"$.properties.full_space_sha256). If this instead equals "
        f"$.properties.endianness_probe.reversed_encoder_digest "
        f"({vectors['properties']['endianness_probe']['reversed_encoder_digest']}), "
        f"deriveRadioAddress()'s base-5 combination is little-endian -- "
        f"it must treat name[0] as the MOST significant digit."
    )


def test_full_space_digest_is_not_the_reversed_encoder_fault_digest(
    lib, vectors
):
    """Belt-and-suspenders on the endianness trap specifically: even
    if some future edit changed both digests in lockstep (making the
    equality check above vacuously pass), independently confirm this
    build's digest does NOT match the published little-endian-encoder
    fault digest."""
    lines = []
    for n in range(3125):
        name = radio_address.index_to_name(n)
        _, channel, group = _derive(lib, name)
        lines.append(f"{name},{channel},{group}\n")
    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    reversed_digest = vectors["properties"]["endianness_probe"][
        "reversed_encoder_digest"
    ]
    assert digest != reversed_digest


# ---------------------------------------------------------------------------
# Endianness probes named explicitly in docs/radio-addressing.md --
# digit-palindrome names (zuzuz, tatat, zotoz, pipip, zavaz) cannot
# catch a reversed decoder; zuzuv (n=1) and zotuz (n=225) can.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 225], ids=["zuzuv-n1", "zotuz-n225"])
def test_endianness_probe_names_match_the_python_reference(lib, n):
    """zuzuv (n=1, reverses to vuzuz) and zotuz (n=225, reverses to
    zutoz) are the two published non-palindrome probes. Confirms the
    C++ shim's output for each equals radio_address.py's own
    name_to_address() -- an independent, per-name check alongside the
    full-space digest above."""
    name = radio_address.index_to_name(n)
    expected_channel, expected_group = radio_address.name_to_address(name)
    valid, channel, group = _derive(lib, name)
    assert valid
    assert (channel, group) == (expected_channel, expected_group)


def test_zotuz_specifically_is_channel_25_group_11():
    """Worked-example sanity check, independent of the fixtures above:
    zotuz decodes to n=225 (docs/radio-addressing.md's own worked
    example); channel = 25 + 2*(225%25) = 25, group = 1 + 225//25 = 10,
    bumped to 11 since group 10 is reserved."""
    assert radio_address.name_to_address("zotuz") == (25, 11)


# ---------------------------------------------------------------------------
# Rejection: the legacy fallback pair, never an arbitrary or
# zero-initialized value.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["gauti", "vevo", "vevovv", "aeiou", "TOVEZZ"],
)
def test_rejected_names_from_the_vectors_file_get_the_legacy_fallback_pair(
    lib, vectors, name
):
    """Every name in $.reject[] must be rejected (valid=False) AND
    still write the legacy fallback pair (channel 4, group 10) --
    never a zero-initialized or arbitrary value a caller that ignores
    the return code could act on."""
    assert name in vectors["reject"], (
        f"{name!r} is not actually in this vectors file's reject "
        f"list -- test fixture drifted from docs/radio-address-vectors.json"
    )
    valid, channel, group = _derive(lib, name)
    assert valid is False
    assert (channel, group) == (
        _LEGACY_FALLBACK_CHANNEL,
        _LEGACY_FALLBACK_GROUP,
    )


def test_empty_string_from_the_reject_list_gets_the_legacy_fallback_pair(lib):
    """"" is in $.reject[] too, but pytest.mark.parametrize's id
    generation makes an empty-string case easy to misread in test
    output, so it gets its own named test."""
    valid, channel, group = _derive(lib, "")
    assert valid is False
    assert (channel, group) == (
        _LEGACY_FALLBACK_CHANNEL,
        _LEGACY_FALLBACK_GROUP,
    )


def test_null_name_gets_the_legacy_fallback_pair(lib):
    """A null `name` (never produced by microbit_friendly_name() on
    real hardware, but not undefined behavior here either) must be
    treated exactly like any other malformed input."""
    valid, channel, group = _derive(lib, None)
    assert valid is False
    assert (channel, group) == (
        _LEGACY_FALLBACK_CHANNEL,
        _LEGACY_FALLBACK_GROUP,
    )


def test_well_formed_but_unknown_name_is_accepted(lib):
    """pipip is well-formed CVCVC with no board actually using it --
    docs/radio-addressing.md's "A non-CVCVC name has no address"
    section is explicit that malformed and merely-unknown are
    different verdicts: this must NOT be rejected."""
    valid, _channel, _group = _derive(lib, "pipip")
    assert valid


# ---------------------------------------------------------------------------
# Normalization: whitespace-trimmed and case-folded variants of the
# same name must derive identically.
# ---------------------------------------------------------------------------


def test_normalize_equivalent_pairs_derive_identically(lib, vectors):
    """$.normalize_equivalent maps raw inputs (e.g. "VEVOV", "
    vevov ") to their normalized form ("vevov"). Both the raw and
    normalized spellings must derive to the exact same (channel,
    group) pair, and both must be accepted."""
    for raw, normalized in vectors["normalize_equivalent"].items():
        valid_raw, channel_raw, group_raw = _derive(lib, raw)
        valid_norm, channel_norm, group_norm = _derive(lib, normalized)
        assert valid_raw and valid_norm, (
            f"{raw!r} / {normalized!r} should both be accepted"
        )
        assert (channel_raw, group_raw) == (channel_norm, group_norm), (
            f"{raw!r} derived {(channel_raw, group_raw)}, but its "
            f"normalized form {normalized!r} derived "
            f"{(channel_norm, group_norm)}"
        )


# ---------------------------------------------------------------------------
# selectRadioGroup(): the groupOverridden_ contract ensureRadioReady()
# consults. Not covered by RadioTransport itself (pxt.h-bound, cannot
# be host-compiled), but this is the pure decision logic the class
# delegates to -- see radio_transport.h's own doc comment on
# selectRadioGroup() and setGroup().
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overridden,stored,derived,expected",
    [
        (0, 10, 43, 43),  # never overridden: derived default wins
        (1, 10, 43, 10),  # explicit setGroup(10) call: stored wins
        (1, 200, 1, 200),  # explicit override still wins even if group=1
        (0, 0, 1, 1),  # never overridden, stored is the placeholder 0
    ],
    ids=[
        "not-overridden-uses-derived",
        "overridden-uses-stored",
        "overridden-uses-stored-regardless-of-value",
        "not-overridden-ignores-placeholder-stored",
    ],
)
def test_select_radio_group_override_contract(
    lib, overridden, stored, derived, expected
):
    got = lib.radioAddressSelectGroup(overridden, stored, derived)
    assert got == expected
