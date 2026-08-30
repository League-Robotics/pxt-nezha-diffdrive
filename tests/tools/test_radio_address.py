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


# --- Regenerating the diagnostic-constant digests from their exact fault ---
#
# `test_d1_canonical_form_is_not_the_reversed_encoder_digest` (ticket 001)
# asserted this reference's D1 does NOT equal `52ea4a6e...`. That proves
# the reference is unbroken; it does NOT prove `52ea4a6e...` still
# describes the fault it names -- replace the published constant with
# garbage and that test still passes. Per docs/radio-addressing.md's
# stated principle ("a diagnostic constant must name its exact fault"),
# the two tests below REGENERATE each published fault digest from a
# deliberately broken implementation of the exact bug it claims to
# describe, built locally by copying `index_to_name`/`name_to_index`/
# `_address_to_index` and reversing the digit loop / swapping the read
# order -- ticket 001's Implementation Plan already describes this
# technique for constructing a reversed encoder. Neither broken
# implementation is exported; both double as fixtures for the --check
# mode diagnostics tests further down.

def _little_endian_index_to_name(n):
    """A deliberately BROKEN `index_to_name` (`encode`): the digit
    loop runs LEAST-significant-first instead of counting down from
    the most significant position -- copied from
    `radio_address.index_to_name` with only the loop direction
    changed. This is the fault docs/radio-addressing.md's
    "Endianness" section describes: base-5 conversion naturally
    emits the least-significant digit first, so a naive port gets
    this backwards."""
    if not (0 <= n <= 3124):
        raise ValueError(f'index out of range 0..3124: {n!r}')
    digits = [0, 0, 0, 0, 0]
    for p in range(5):  # BUG: should count down, 4..0
        digits[p] = n % 5
        n //= 5
    return ''.join(radio_address._alphabet(p)[digits[p]] for p in range(5))


def _little_endian_full_space_line(n):
    """D1's three-column canonical form for index `n`, built with the
    broken encoder above for the NAME column only. `channel`/`group`
    still come from the real, correct `name_to_address`/`index_to_name`
    -- per docs/radio-addressing.md's "Two digests" table, D1 covers
    `encode` (n -> name, broken here) AND `addr` (n -> pair, still
    correct), so only the name column should move."""
    channel, group = radio_address.name_to_address(
        radio_address.index_to_name(n))
    return f'{_little_endian_index_to_name(n)},{channel},{group}\n'


def test_little_endian_encoder_regenerates_the_published_d1_fault_digest(
        vectors):
    """Build D1's canonical form (n=0..3124) using ONLY the broken,
    least-significant-first encoder above for the name column, and
    assert its digest equals exactly
    `$.properties.endianness_probe.reversed_encoder_digest`
    (`52ea4a6e...`) -- regenerating the published constant from the
    fault it claims to describe, not merely asserting the reference
    avoids it."""
    lines = [_little_endian_full_space_line(n) for n in range(3125)]
    digest = _sha256(_canonical(lines))
    assert digest == vectors['properties']['endianness_probe'][
        'reversed_encoder_digest']


def _little_endian_name_to_index(name):
    """A deliberately BROKEN `name_to_index` (`decode`): reads
    `name[0]` as the LEAST significant base-5 digit instead of the
    MOST -- copied from `radio_address.name_to_index` with only the
    digit-read order swapped (position 4 first, position 0 last).
    `encode`, `addr` and `reverse` are all correct; only this
    function is wrong -- the exact fault
    `$.properties.conformance_sha256_broken_decode` names."""
    norm = radio_address._normalize(name)
    if not radio_address._ACCEPT_RE.match(norm):
        raise ValueError(
            f'not a valid micro:bit name after normalize: {name!r}')
    n = 0
    for p in range(4, -1, -1):  # BUG: should count up, 0..4
        n = n * 5 + radio_address._alphabet(p).index(norm[p])
    return n


def _little_endian_conformance_line(n):
    """D2's five-column canonical form for index `n`, built with the
    broken decoder above for column 4 ONLY. `name`/`channel`/`group`
    (correct `encode`/`addr`) and column 5 (correct `reverse`, via
    `radio_address._address_to_index`) are untouched -- only
    `decode(name)` is wrong."""
    name = radio_address.index_to_name(n)
    channel, group = radio_address.name_to_address(name)
    decoded = _little_endian_name_to_index(name)
    reversed_n = radio_address._address_to_index(channel, group)
    return f'{name},{channel},{group},{decoded},{reversed_n}\n'


def test_little_endian_decoder_regenerates_the_published_d2_fault_digest(
        vectors):
    """Build D2's canonical form (n=0..3124) using ONLY the broken,
    name[0]-is-least-significant decoder above for column 4, and
    assert its digest equals exactly
    `$.properties.conformance_sha256_broken_decode.digest`
    (`5acfd688...`) -- regenerating the published constant from the
    fault it claims to describe. This is the fault D1 (3 columns)
    cannot see at all, per docs/radio-addressing.md's "Two digests"
    section -- only D2's `decode(name)` column exercises it."""
    lines = [_little_endian_conformance_line(n) for n in range(3125)]
    digest = _sha256(_canonical(lines))
    assert digest == vectors['properties'][
        'conformance_sha256_broken_decode']['digest']


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


# --- Reverse-address rejection: address_to_name only accepts what the
# forward map can produce ------------------------------------------------
#
# All 8 `pytest.raises` cases landed by ticket 001 reject malformed
# NAMES. Nothing pinned that `address_to_name` rejects an ADDRESS the
# forward map never produces -- the half of the inverse ticket 002's
# firmware independently implements, and it needs pinning here first.

@pytest.mark.parametrize('channel,group,why', [
    (26, 1, 'even channel (channels are always odd, 25..73)'),
    (23, 1, 'below the channel floor (25)'),
    (75, 1, 'above the channel ceiling (73)'),
    (25, 0, "reserved group 0 (MakeCode's unconfigured default)"),
    (25, 10, "reserved group 10 (the relay's !C button space)"),
    (25, 127, 'above the group ceiling (126)'),
])
def test_address_to_name_rejects_addresses_the_forward_map_never_produces(
        channel, group, why):
    with pytest.raises(ValueError):
        radio_address.address_to_name(channel, group)


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


# --- --check: validate a FOREIGN dump ---------------------------------------
#
# `tools/radio_address.py --check` is what makes ticket 002's C++
# firmware (and any other language with no sha256 of its own)
# participate in cross-repo conformance: it produces a dump, and this
# checker validates it against D1/D2. The diagnostics ARE the feature
# per the ticket -- a bare "mismatch" sends the next reader on a
# six-variant reconstruction hunt, so every failure mode below asserts
# on the SPECIFIC named diagnostic, not merely that `problems` is
# non-empty.

def test_check_dump_accepts_this_reference_own_v1_dump_with_a_protocol_note(
        vectors):
    """A conformant v1 (3-column) dump reports which protocol version
    and which digest matched, per the ticket's "On success" acceptance
    criterion -- and, since v1 cannot exercise decode()/reverse(), a
    note saying so rather than a bare CONFORMANT that overstates what
    was checked."""
    text = _canonical(radio_address.full_space_dump())
    problems, notes = radio_address.check_dump(text)
    assert problems == []
    assert any(note.startswith('protocol v1') for note in notes)
    assert any(vectors['properties']['full_space_sha256'] in note
               for note in notes)
    assert any('cannot' in note.lower() for note in notes), (
        'a v1 pass must say it could not check decode()/reverse()')


def test_check_dump_accepts_this_reference_own_v2_dump_with_a_protocol_note(
        vectors):
    """A conformant v2 (5-column) dump reports protocol v2 and the D2
    digest that matched."""
    text = _canonical(radio_address.conformance_dump())
    problems, notes = radio_address.check_dump(text)
    assert problems == []
    assert any(note.startswith('protocol v2') for note in notes)
    assert any(vectors['properties']['conformance_sha256'] in note
               for note in notes)


def test_check_dump_reports_little_endian_encoder_by_name():
    """Feeding the checker a dump from a deliberately little-endian
    encoder (the D1/v1 fixture from the regeneration tests above)
    must report "little-endian ENCODER" -- the ticket's first
    --check acceptance scenario."""
    text = _canonical(
        _little_endian_full_space_line(n) for n in range(3125))
    problems, notes = radio_address.check_dump(text)
    assert any('LITTLE-ENDIAN ENCODER' in p for p in problems), problems


def test_check_dump_reports_little_endian_decoder_by_name():
    """Feeding the checker a dump from a deliberately little-endian
    decoder (encode/addr/reverse correct; the D2/v2 fixture from the
    regeneration tests above) must report "little-endian DECODER" --
    the ticket's second --check acceptance scenario."""
    text = _canonical(
        _little_endian_conformance_line(n) for n in range(3125))
    problems, notes = radio_address.check_dump(text)
    assert any('LITTLE-ENDIAN DECODER' in p for p in problems), problems


def test_check_dump_names_getez_when_a_row_channel_is_forced_to_3():
    """Feeding the checker a dump with one row's channel forced to the
    reserved value 3 must name getez concretely in the diagnostic --
    the ticket's third --check acceptance scenario. Channel 3 is the
    legacy fleet convention getez sits on; .claude/rules/
    playfield-testing.md forbids retuning it because the torture:8760
    relay pool depends on getez staying there."""
    lines = list(radio_address.full_space_dump())
    parts = lines[0].rstrip('\n').split(',')
    parts[1] = '3'
    lines[0] = ','.join(parts) + '\n'
    problems, notes = radio_address.check_dump(_canonical(lines))
    assert any('getez' in p for p in problems), problems
    assert any('reserved channel(s) [3]' in p for p in problems), problems


def test_check_dump_names_the_relay_c_group_when_a_row_group_is_forced_to_10():
    """A row's group forced to the reserved value 10 (the relay's !C
    button space) is explained concretely, not just flagged."""
    lines = list(radio_address.full_space_dump())
    parts = lines[1].rstrip('\n').split(',')
    parts[2] = '10'
    lines[1] = ','.join(parts) + '\n'
    problems, notes = radio_address.check_dump(_canonical(lines))
    assert any('!C' in p for p in problems), problems


def test_check_dump_reports_first_differing_line_by_name_when_no_known_fault_matches():
    """When neither published fault digest matches, the checker finds
    and reports the FIRST differing line by content -- the name at
    that line -- not only a hash or a byte offset. Corrupting a
    single row (rather than reproducing a whole-space bug) cannot
    coincidentally hit either published diagnostic digest."""
    lines = list(radio_address.full_space_dump())
    # zuzuv (n=1) mangled into a name nothing else in the dump uses.
    lines[1] = 'zuzuv,29,1\n'  # correct channel for n=1 is 27, not 29
    problems, notes = radio_address.check_dump(_canonical(lines))
    assert any('first differing line is 2 (n=1)' in p and 'zuzuv' in p
               for p in problems), problems


def test_check_dump_rejects_wrong_line_count():
    """A dump with too few or too many lines is flagged structurally,
    independent of the digest mismatch it also produces."""
    lines = list(radio_address.full_space_dump())[:100]
    problems, notes = radio_address.check_dump(_canonical(lines))
    assert any('expected 3125 lines, got 100' in p for p in problems), (
        problems)


def test_check_dump_distinguishes_v1_from_v2_by_column_count(vectors):
    """Column count alone -- not a flag, not a filename -- decides
    which protocol (and therefore which published digest) a dump is
    checked against, per `$.properties.dump_protocol`."""
    v1_problems, v1_notes = radio_address.check_dump(
        _canonical(radio_address.full_space_dump()))
    v2_problems, v2_notes = radio_address.check_dump(
        _canonical(radio_address.conformance_dump()))
    assert v1_problems == [] and v2_problems == []
    assert any('v1' in n for n in v1_notes)
    assert any('v2' in n for n in v2_notes)


# --- --check: CLI wiring ----------------------------------------------------

def test_check_cli_exits_zero_on_a_conformant_dump(tmp_path, vectors):
    dump_path = tmp_path / 'mine.txt'
    dump_path.write_text(_canonical(radio_address.full_space_dump()))
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / 'radio_address.py'),
         '--check', str(dump_path)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'CONFORMANT' in result.stdout


def test_check_cli_reads_stdin_with_a_dash_and_exits_nonzero_on_mismatch():
    broken = _canonical(
        _little_endian_full_space_line(n) for n in range(3125))
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / 'radio_address.py'), '--check', '-'],
        input=broken, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'LITTLE-ENDIAN ENCODER' in result.stderr


# --- tools/radio-address-dump: the cross-repo entry point ------------------

def test_radio_address_dump_entry_point_list_reports_python():
    """`--list` must print at least the `python` implementation id --
    the entry point the relay's comparator discovers by path and
    then dumps by id."""
    result = subprocess.run(
        [str(_TOOLS_DIR / 'radio-address-dump'), '--list'],
        capture_output=True, text=True, check=True)
    assert 'python' in result.stdout.split()


def test_radio_address_dump_entry_point_python_matches_full_space_dump(
        vectors):
    """`radio-address-dump python`'s stdout is byte-identical to
    `full_space_dump()`'s own output (protocol v1, D1) -- it MUST
    call the library function, not reimplement the map."""
    result = subprocess.run(
        [str(_TOOLS_DIR / 'radio-address-dump'), 'python'],
        capture_output=True, text=True, check=True)
    assert result.stdout == _canonical(radio_address.full_space_dump())
    assert _sha256(result.stdout) == vectors['properties'][
        'full_space_sha256']


def test_radio_address_dump_entry_point_unknown_id_is_not_exit_0():
    """An id `--list` never printed must not report success -- the
    comparator would otherwise treat an empty/garbage dump as a real
    implementation."""
    result = subprocess.run(
        [str(_TOOLS_DIR / 'radio-address-dump'), 'bogus'],
        capture_output=True, text=True)
    assert result.returncode != 0


def test_radio_address_dump_entry_point_output_checks_out(vectors):
    """End-to-end: the entry point's own output, piped through
    `--check`, is itself CONFORMANT -- the actual path the relay's
    comparator (and this ticket's acceptance criterion) exercises."""
    dump = subprocess.run(
        [str(_TOOLS_DIR / 'radio-address-dump'), 'python'],
        capture_output=True, text=True, check=True)
    problems, notes = radio_address.check_dump(dump.stdout)
    assert problems == [], problems
