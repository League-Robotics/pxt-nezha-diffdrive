"""tests/tools/test_radio_address.py -- pins `tools/radio_address.py`
against `docs/radio-addressing.md` (normative) and its machine-readable
companion `docs/radio-address-vectors.json`.

**Why this exists.** Sprint 025 ticket 001 -- see
`clasi/sprints/025-derive-radio-channel-and-group-from-the-micro-bit-
board-name/tickets/001-radio-address-reference-implementation-and-
full-space-digest-tests.md`. This is the foundation ticket: three
sibling repos (this one, microbit-radio-relay, radio-robot-lib) each
carry their own implementation of the same base-5 codebook, cross-
verified only by digest -- if this test suite is wrong, nothing else
catches it, because everything downstream trusts these two numbers.

**Two digests, asserted both, in priority order.** D2
(`conformance_sha256`) is the PRIMARY gate: its canonical form's last
two columns are always `n`, which forces `decode()`
(`name_to_index`) and `reverse()` (the module's private
`_address_to_index`, reached through `address_to_name`) to run on
every line. D1 (`full_space_sha256`) covers only the forward map
(`encode`/`addr`) and is measured (`docs/radio-addressing.md` "Two
digests, and which one is the gate") to come out byte-identical even
with `decode`/`reverse` both broken -- so it is asserted too, not as
redundant coverage (it's a strict subset of D2's) but as a BISECTOR: a
D2 failure alongside a D1 pass localises the fault to `decode`/
`reverse` rather than the forward map, which no single digest can do
alone. Do not drop either.

All digest and range constants are read from
`docs/radio-address-vectors.json` at test time, never hardcoded here
a second time -- a second copy is a second thing that can drift, and
that failure mode has already bitten this project twice (see the
vectors file's own `$comment` and `docs/radio-addressing.md`'s
maintainer's note).

Run with::

    uv run pytest tests/tools/test_radio_address.py -v
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

import pytest

# tests/tools/test_radio_address.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
_VECTORS_PATH = _REPO_ROOT / 'docs' / 'radio-address-vectors.json'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import radio_address  # noqa: E402  (path must be set up first)


@pytest.fixture(scope='module')
def vectors():
    """The normative machine-readable contract, loaded once. Every
    constant asserted below (digests, ranges, the fleet table, the
    reject/normalize-equivalent lists) comes from this fixture --
    never a second hardcoded copy."""
    return json.loads(_VECTORS_PATH.read_text())


def _canonical(lines):
    return ''.join(lines)


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# --- D2: primary conformance digest (the gate) -----------------------------

def test_d2_conformance_digest_is_the_primary_gate(vectors):
    """Build D2's canonical form ("<name>,<channel>,<group>,<decode(name)>,
    <reverse(channel,group)>\\n" for n=0..3124) via `radio_address.
    conformance_dump()` -- the SAME function the module's own `--dump
    conformance` CLI flag calls -- and assert its sha256 equals
    `$.properties.conformance_sha256`. The last two columns are always
    n, so this is the one digest that cannot pass on a forward-only
    implementation: it forces `decode()` and `reverse()` to run."""
    lines = list(radio_address.conformance_dump())
    assert len(lines) == 3125
    digest = _sha256(_canonical(lines))
    assert digest == vectors['properties']['conformance_sha256'], (
        'D2 mismatch -- the PRIMARY conformance gate. decode() is the '
        'production path (what a relay\'s "!N <name>" executes on every '
        'command); a mismatch here means decode() or reverse() is wrong, '
        'even if D1 below passes. See docs/radio-addressing.md '
        '"Two digests, and which one is the gate."')


# --- D1: full-space digest, retained as a bisector --------------------------

def test_d1_full_space_digest_is_a_bisector_not_a_substitute(vectors):
    """Build D1's canonical form ("<name>,<channel>,<group>\\n" for
    n=0..3124) via `radio_address.full_space_dump()` and assert its
    sha256 equals `$.properties.full_space_sha256`. D1 never calls
    decode() or reverse() -- MEASURED 2026-08-30 (per the vectors
    file's own `full_space_sha256_note`) that a build with both those
    functions deliberately broken still produces a byte-identical D1.
    So this assertion alone proves nothing D2 doesn't; it is kept so
    that a D2 failure alongside a D1 pass narrows the fault to
    decode/reverse rather than the forward map -- do not delete this
    test as "redundant with D2."""
    lines = list(radio_address.full_space_dump())
    assert len(lines) == 3125
    digest = _sha256(_canonical(lines))
    assert digest == vectors['properties']['full_space_sha256'], (
        'D1 mismatch -- this covers only encode()/addr() (the forward '
        'map), so a failure here means the forward map itself is wrong, '
        'not merely decode()/reverse().')


def test_d1_canonical_form_is_not_the_reversed_encoder_digest(vectors):
    """The endianness trap (docs/radio-addressing.md "Endianness, and
    why the obvious test misses it"): base-5 conversion naturally
    emits the LEAST significant digit first, but the name is
    big-endian. A little-endian encoder still produces 3125
    well-formed, regex-passing, distinct names -- just in the wrong
    order -- so nothing about the shape of the output looks broken.
    `$.properties.endianness_probe.reversed_encoder_digest` is D1's
    canonical form under exactly that bug; assert this implementation
    does NOT reproduce it.

    zuzuz, tatat, zotoz, pipip and zavaz are all digit-palindromes and
    are IDENTICAL under both digit orderings, so they cannot detect
    this on their own (see test_endianness_probe_vectors_are_not_
    palindromes below for the two that can: zuzuv and zotuz)."""
    lines = list(radio_address.full_space_dump())
    digest = _sha256(_canonical(lines))
    reversed_digest = vectors['properties']['endianness_probe'][
        'reversed_encoder_digest']
    assert digest != reversed_digest, (
        'digest matches the published REVERSED (little-endian) encoder '
        'value -- the base-5 digit loop runs in the wrong order. Reverse '
        'it; do not patch around the symptom.')


# --- Every row in $.vectors round-trips -------------------------------------

def test_every_vector_row_round_trips(vectors):
    """Every row in `$.vectors[]`: `name_to_index` matches the row's
    `n`, `name_to_address` matches its `channel`/`group`, and (unless
    the row is `evidence: "label-only"`, i.e. togov -- never confirmed
    on silicon) `address_to_name` recovers the row's `name`."""
    for row in vectors['vectors']:
        name, n = row['name'], row['n']
        channel, group = row['channel'], row['group']
        assert radio_address.name_to_index(name) == n, (
            f'name_to_index({name!r}) should be {n}')
        assert radio_address.name_to_address(name) == (channel, group), (
            f'name_to_address({name!r}) should be ({channel}, {group})')
        if row['evidence'] != 'label-only':
            assert radio_address.address_to_name(channel, group) == name, (
                f'address_to_name({channel}, {group}) should be {name!r}')


def test_silicon_vectors_device_id_mod_3125_equals_n(vectors):
    """All 7 rows with `evidence: "silicon"` (measured 2026-08-29 across
    the fleet, per docs/radio-addressing.md) satisfy
    `device_id % 3125 == n` -- the whole scheme rests on this identity,
    since a board's name IS `device_id % 3125` read out of silicon."""
    silicon_rows = [r for r in vectors['vectors']
                     if r['evidence'] == 'silicon']
    assert len(silicon_rows) == 7, (
        'expected exactly 7 silicon-evidenced rows in the fleet table')
    for row in silicon_rows:
        assert row['device_id'] % 3125 == row['n'], (
            f"{row['name']}: device_id {row['device_id']} % 3125 != n "
            f"{row['n']}")


# --- $.reject -----------------------------------------------------------

def test_reject_list_all_raise(vectors):
    """Every entry in `$.reject[]` raises on `name_to_address`."""
    for bad in vectors['reject']:
        with pytest.raises(ValueError):
            radio_address.name_to_address(bad)


def test_gauti_specifically_is_rejected():
    """`gauti` is called out by name in the ticket: a real hostname on
    this rig that LOOKS like a micro:bit name (5 letters, alternating
    consonant/vowel shape) until position 2 is checked -- 'u' is a
    VOWEL, but position 2 requires a consonant (zvgpt). A regex that
    only checked length and alternation, not the specific alphabet per
    position, would wrongly accept it."""
    assert not radio_address._ACCEPT_RE.match('gauti')
    with pytest.raises(ValueError):
        radio_address.name_to_address('gauti')
    with pytest.raises(ValueError):
        radio_address.name_to_index('gauti')


# --- Malformed vs. unknown: opposite failure directions ----------------

@pytest.mark.parametrize('bad', ['robot1', 'gauti', 'vevo', 'aeiou', ''])
def test_malformed_names_must_raise(bad):
    """MALFORMED (outside `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` after
    normalize) MUST RAISE -- never hash, truncate, or default. Per
    `docs/radio-addressing.md` "A non-CVCVC name has no address":
    inventing an address for a name that has none is precisely the
    silent-failure class this scheme exists to remove."""
    with pytest.raises(ValueError):
        radio_address.name_to_address(bad)
    with pytest.raises(ValueError):
        radio_address.name_to_index(bad)


def test_vevovv_and_tovezz_from_the_reject_list_also_raise(vectors):
    """Wrong-length variants from `$.reject[]` (one letter too many),
    covered separately from the parametrized malformed set above so
    both the ticket's literal examples and the vectors file's own
    reject list are exercised."""
    assert 'vevovv' in vectors['reject']
    assert 'TOVEZZ' in vectors['reject']
    with pytest.raises(ValueError):
        radio_address.name_to_address('vevovv')
    with pytest.raises(ValueError):
        radio_address.name_to_address('TOVEZZ')


def test_well_formed_but_unknown_name_is_accepted():
    """WELL-FORMED BUT UNKNOWN (a valid CVCVC name no board currently
    uses, e.g. `pipip`) MUST BE ACCEPTED and return 51/90. The address
    layer does not know which boards exist and must not pretend to --
    that is the deploy-time silicon gate's job (sprint 025 ticket 003).
    Pinning this directly guards against a later reader "hardening"
    the rejection and breaking tune-to-whatever-I-name."""
    assert radio_address.name_to_address('pipip') == (51, 90)
    # and the reverse holds too: 51/90 derives pipip, not an error.
    assert radio_address.address_to_name(51, 90) == 'pipip'


# --- $.normalize_equivalent ----------------------------------------------

def test_normalize_equivalent_pairs(vectors):
    """Every key/value pair in `$.normalize_equivalent` (e.g. `VEVOV`
    and ` vevov ` both) normalizes to produce the same index/address
    as its target name."""
    for variant, target in vectors['normalize_equivalent'].items():
        assert radio_address.name_to_index(variant) == \
            radio_address.name_to_index(target), (
                f'{variant!r} should normalize the same as {target!r}')
        assert radio_address.name_to_address(variant) == \
            radio_address.name_to_address(target)


def test_vevov_and_gauti_style_variants_normalize_to_3743():
    """Concrete pin for the normalize_equivalent case named in the
    ticket: 'VEVOV' and ' vevov ' both -> 37/43 (vevov's real, silicon
    -measured address)."""
    assert radio_address.name_to_address('VEVOV') == (37, 43)
    assert radio_address.name_to_address(' vevov ') == (37, 43)
    assert radio_address.name_to_address('vevov') == (37, 43)


# --- Injectivity, full space ------------------------------------------------

def test_injectivity_all_3125_names_produce_distinct_pairs():
    """`name_to_address` over all 3125 valid names produces 3125
    distinct (channel, group) pairs -- a corollary of the D2/D1
    digests, pinned directly here too as a cheap, independent check
    that doesn't depend on either digest being right."""
    pairs = set()
    for n in range(3125):
        name = radio_address.index_to_name(n)
        addr = radio_address.name_to_address(name)
        assert addr not in pairs, f'{name!r} collides with an earlier name'
        pairs.add(addr)
    assert len(pairs) == 3125


def test_125_names_per_channel_25_names_per_group():
    """Exactly 125 names per channel (25 distinct channels) and 25
    names per group (125 distinct groups: the 9 groups 1..9 plus the
    116 groups 11..126)."""
    channel_counts = Counter()
    group_counts = Counter()
    for n in range(3125):
        channel, group = radio_address.name_to_address(
            radio_address.index_to_name(n))
        channel_counts[channel] += 1
        group_counts[group] += 1
    assert len(channel_counts) == 25
    assert all(count == 125 for count in channel_counts.values())
    assert len(group_counts) == 125
    assert all(count == 25 for count in group_counts.values())


# --- Ranges ------------------------------------------------------------

def test_ranges_over_the_full_space(vectors):
    """Channels 25..73, all odd; groups 1..126; never channel 3, 4, 7;
    never group 0 or 10 -- checked over the whole 3125-name space, not
    just the tabulated rows."""
    reserved_channels = set(vectors['reserved']['channels_never_emitted'])
    reserved_groups = set(vectors['reserved']['groups_never_emitted'])
    assert reserved_channels == {3, 4, 7}
    assert reserved_groups == {0, 10}
    for n in range(3125):
        channel, group = radio_address.name_to_address(
            radio_address.index_to_name(n))
        assert channel % 2 == 1, f'channel {channel} is not odd'
        assert 25 <= channel <= 73, f'channel {channel} out of range'
        assert channel not in reserved_channels
        assert 1 <= group <= 126, f'group {group} out of range'
        assert group not in reserved_groups


# --- Round-trip identity, full space ----------------------------------------

def test_round_trip_identity_over_all_3125_names():
    """`address_to_name(name_to_address(name)) == name` for every one
    of the 3125 valid names."""
    for n in range(3125):
        name = radio_address.index_to_name(n)
        channel, group = radio_address.name_to_address(name)
        assert radio_address.address_to_name(channel, group) == name


def test_endianness_probe_vectors_are_not_palindromes():
    """zuzuv (n=1) and zotuz (n=225) are the two published vectors
    (`$.properties.endianness_probe` names zotuz; zuzuv is vector n=1
    in `$.vectors[]`) that a digit-palindrome sample set misses.
    Unlike zuzuz/tatat/zotoz/pipip/zavaz -- all digit-palindromes,
    identical under either digit ordering -- these two are asymmetric
    and fail loudly against a little-endian encoder (zuzuv would
    reverse to vuzuz, zotuz to zutoz). Round-trip both explicitly,
    beyond the whole-space loop above."""
    assert radio_address.index_to_name(1) == 'zuzuv'
    assert radio_address.name_to_index('zuzuv') == 1
    assert radio_address.index_to_name(225) == 'zotuz'
    assert radio_address.name_to_index('zotuz') == 225
    for name in ('zuzuv', 'zotuz'):
        addr = radio_address.name_to_address(name)
        assert radio_address.address_to_name(*addr) == name


# --- The --dump CLI matches the library functions it wraps -----------------

def test_dump_cli_conformance_matches_the_library_digest(vectors):
    """`--dump conformance` on the command line must produce exactly
    what `conformance_dump()` produces in-process -- the whole point
    of exposing this as a documented function AND a CLI flag is that
    a sibling repo's checker can hash a plain stdout capture instead
    of needing sha256 (or Python) itself. Guards the CLI wiring
    against silently diverging from the library function it's meant
    to wrap."""
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / 'radio_address.py'),
         '--dump', 'conformance'],
        capture_output=True, text=True, check=True)
    digest = _sha256(result.stdout)
    assert digest == vectors['properties']['conformance_sha256']


# --- Malformed name regex sanity (pin the pattern text itself) -------------

def test_accept_pattern_matches_the_published_regex(vectors):
    """The compiled validation regex's pattern text matches
    `$.algorithm.accept` byte for byte -- a drift guard, since the
    regex is transcribed by hand into this module rather than loaded
    from the vectors file (loading executable-shaped strings out of
    JSON is worse than a second copy, not better)."""
    assert radio_address._ACCEPT_RE.pattern == vectors['algorithm']['accept']
    assert isinstance(re.compile(vectors['algorithm']['accept']), type(
        radio_address._ACCEPT_RE))
