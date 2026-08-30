#!/usr/bin/env python3
"""Radio addressing: a board's name IS its address.

Reference implementation of `docs/radio-addressing.md` (normative) --
five-letter micro:bit name <-> (radio channel, radio group). Pure
functions only: no I/O, no board access, no third-party imports.
`tools/make_deploy.py`, `tools/robotlink.py`, `tools/wire_acceptance.py`
(sprint 025 tickets 003-004) import from this module; the firmware host
test (ticket 002) asserts against the same digests
`tests/tools/test_radio_address.py` proves here.

## The map

Positions 0, 2, 4 are consonants (`zvgpt`); positions 1, 3 are vowels
(`uoiea`). A name's index into its position's alphabet is that
position's base-5 digit. `name[0]` is the MOST significant digit,
`name[4]` the LEAST -- **big-endian**. Base-5 conversion naturally
emits the least-significant digit first, so a naive port gets this
backwards and produces 3125 well-formed, regex-passing, distinct names
in the wrong order, with no error to see (`docs/radio-addressing.md`
"Endianness, and why the obvious test misses it"). `zuzuv` (n=1) and
`zotuz` (n=225) are the published probes that catch it -- every other
tabulated vector is a digit-palindrome and passes identically under
both orderings.

## Naming vs. the spec's prose terms

The spec (and the two digests below) talk about four operations:
`encode` (n -> name), `decode` (name -> n), `addr` (n -> pair) and
`reverse` (pair -> n). This module exposes the four functions the
ticket asks for instead -- `name_to_index` is `decode`, `index_to_name`
is `encode`, `name_to_address` composes `decode`+`addr`, and
`address_to_name` composes `reverse`+`encode`. The bare `reverse`
(pair -> n, no encode step) exists here too, as `_address_to_index`,
because the D2 conformance dump needs it directly -- see below.

## Two digests, and which one is the gate

`docs/radio-address-vectors.json` publishes two sha256 digests over
the full 3125-name space:

- **D1** (`$.properties.full_space_sha256`) -- canonical form
  `"<name>,<channel>,<group>\n"` for `n = 0..3124`. Covers `encode`
  and `addr` only; it never calls `decode` or `reverse`. A build with
  both of those broken produces a byte-identical D1 (measured
  2026-08-30) -- so D1 alone proves nothing about the production path
  (`decode` is what a relay's `!N <name>` runs on every command).
- **D2** (`$.properties.conformance_sha256`) -- canonical form
  `"<name>,<channel>,<group>,<decode(name)>,<reverse(channel,group)>\n"`.
  The last two columns are always `n`, which forces `decode` and
  `reverse` to run and hashes their output. **This is the primary
  conformance gate.**

Both are asserted in the test suite: D1 is not redundant coverage (it
is a strict subset of D2's), it is a *bisector* -- D2 failing while D1
still passes localises the fault to `decode`/`reverse` rather than the
forward map, which is the only way to tell those two failure modes
apart from test output alone.

`conformance_dump()` / `full_space_dump()` below generate exactly
these two canonical forms, and are the single implementation the CLI's
`--dump` flag and the test suite both call -- see the module's own
"Verify your implementation against the whole space, not the sampled
rows" note in `docs/radio-addressing.md`, and the ticket's request for
a checker that can conformance-test the C++/static-TypeScript sibling
implementations against D2 without needing sha256 in either language.

Usage as a CLI (emits a canonical form to stdout, for conformance
checking against $.properties.conformance_sha256 / full_space_sha256):

  python3 tools/radio_address.py --dump conformance
  python3 tools/radio_address.py --dump full-space

Or validates a dump captured from ANOTHER implementation -- C++
firmware, MakeCode static TypeScript, or a sibling repo's own port --
telling v1 (3 columns, digests to D1) and v2 (5 columns, digests to
D2) apart by counting columns (`docs/radio-addressing.md`'s "Dump
protocol"). See `check_dump()` below for what a failure reports:

  tools/radio-address-dump python | python3 tools/radio_address.py --check -
  python3 tools/radio_address.py --check their-dump.txt
"""
import pathlib
import re

# positions 0, 2, 4
CONSONANTS = 'zvgpt'
# positions 1, 3
VOWELS = 'uoiea'

# ASCII whitespace only (`docs/radio-addressing.md` "normalize: trim
# ASCII whitespace") -- deliberately not `str.strip()`'s default,
# which also strips non-ASCII Unicode whitespace.
_ASCII_WHITESPACE = ' \t\n\r\v\f'

_ACCEPT_RE = re.compile(r'^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$')

# n's valid range: base-5, 5 digits -> 5**5 - 1.
_MAX_INDEX = 5 ** 5 - 1


def _alphabet(position):
    """The codebook alphabet for a 0-indexed name position: consonants
    at 0/2/4, vowels at 1/3."""
    return CONSONANTS if position % 2 == 0 else VOWELS


def _normalize(name):
    """Trim ASCII whitespace and map `A`-`Z` to `a`-`z` -- ASCII-only,
    deliberately not `str.lower()` (which also folds non-ASCII
    case pairs the spec never mentions)."""
    trimmed = name.strip(_ASCII_WHITESPACE)
    return ''.join(
        chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in trimmed)


def name_to_index(name):
    """`decode`: five-letter micro:bit name -> its base-5 index
    `n` (0..3124), big-endian (`name[0]` most significant).

    Raises `ValueError` if `name`, after normalizing, does not match
    `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` -- a non-CVCVC name has no
    address (`docs/radio-addressing.md` "A non-CVCVC name has no
    address"); this must never fall back to a hash, a default, or a
    truncation. A well-formed name that no current board happens to
    use is NOT an error here -- this layer does not know which boards
    exist (that is the deploy-time silicon gate's job).
    """
    norm = _normalize(name)
    if not _ACCEPT_RE.match(norm):
        raise ValueError(
            f'not a valid micro:bit name after normalize: {name!r} '
            f'(must match {_ACCEPT_RE.pattern!r})')
    n = 0
    for p in range(5):
        n = n * 5 + _alphabet(p).index(norm[p])
    return n


def index_to_name(n):
    """`encode`: base-5 index `n` (0..3124) -> its five-letter name,
    big-endian (most significant digit first, at position 0).

    Raises `ValueError` if `n` is outside 0..3124.
    """
    if not isinstance(n, int) or isinstance(n, bool) or not (0 <= n <= _MAX_INDEX):
        raise ValueError(f'index out of range 0..{_MAX_INDEX}: {n!r}')
    digits = [0, 0, 0, 0, 0]
    for p in range(4, -1, -1):
        digits[p] = n % 5
        n //= 5
    return ''.join(_alphabet(p)[digits[p]] for p in range(5))


def name_to_address(name):
    """`decode` + `addr`: five-letter micro:bit name -> `(channel,
    group)`. Raises `ValueError` per `name_to_index`'s rules.

    `channel = 25 + 2 * (n % 25)` (25..73 odd, inclusive -- 25 IS a
    valid channel, per `docs/radio-addressing.md` "Channel 25 is
    inclusive"). `group = 1 + (n // 25)`, then `group += 1` if
    `group >= 10` -- this closes the gap at group 10, which
    `microbit-radio-relay`'s `!C` button space reserves.
    """
    n = name_to_index(name)
    channel = 25 + 2 * (n % 25)
    group = 1 + (n // 25)
    if group >= 10:
        group += 1
    return channel, group


def _address_to_index(channel, group):
    """`reverse`: `(channel, group)` -> `n`, with no `encode` step --
    used directly by `address_to_name` and by the D2 conformance dump,
    which needs the bare index (see module docstring).

    Raises `ValueError` if `channel` is not odd in 25..73, or `group`
    is not in 1..9 or 11..126 (0 and 10 are reserved and never
    emitted -- see `docs/radio-addressing.md` "Why those five values
    are reserved").
    """
    if channel % 2 == 0 or not (25 <= channel <= 73):
        raise ValueError(
            f'channel must be odd and in 25..73: {channel!r}')
    if group == 0 or group == 10 or not (1 <= group <= 126):
        raise ValueError(
            f'group must be in 1..9 or 11..126: {group!r}')
    g = group - 1 if group > 10 else group
    return 25 * (g - 1) + (channel - 25) // 2


def address_to_name(channel, group):
    """`reverse` + `encode`: `(channel, group)` -> the five-letter name
    that derives it. Raises `ValueError` per `_address_to_index`'s
    range checks."""
    return index_to_name(_address_to_index(channel, group))


def conformance_line(n):
    """One line of D2's canonical form for index `n`:
    `"<name>,<channel>,<group>,<decode(name)>,<reverse(channel,group)>\\n"`.
    The last two columns are always `n` itself -- every line forces
    `name_to_index` (decode) and `_address_to_index` (reverse) to run
    and hashes their output, which is what makes D2 (unlike D1) prove
    the production `decode` path is correct.
    """
    name = index_to_name(n)
    channel, group = name_to_address(name)
    decoded = name_to_index(name)
    reversed_n = _address_to_index(channel, group)
    return f'{name},{channel},{group},{decoded},{reversed_n}\n'


def conformance_dump():
    """Yield D2's canonical-form lines for `n = 0..3124` in order.
    Concatenated and sha256'd, this must equal
    `docs/radio-address-vectors.json`'s `$.properties.conformance_sha256`
    -- the primary conformance gate. This is the one function the
    `--dump conformance` CLI flag and the test suite both call, so a
    checker in a sibling repo can hash a plain stdout capture instead
    of needing sha256 (or this module) in its own language.
    """
    for n in range(_MAX_INDEX + 1):
        yield conformance_line(n)


def full_space_line(n):
    """One line of D1's canonical form for index `n`:
    `"<name>,<channel>,<group>\\n"`. Forward-only -- never calls
    `name_to_index` or `_address_to_index` -- see module docstring on
    why D1 alone is not a conformance proof."""
    name = index_to_name(n)
    channel, group = name_to_address(name)
    return f'{name},{channel},{group}\n'


def full_space_dump():
    """Yield D1's canonical-form lines for `n = 0..3124` in order.
    Concatenated and sha256'd, this must equal
    `docs/radio-address-vectors.json`'s `$.properties.full_space_sha256`.
    Retained as a bisector alongside `conformance_dump()`, not as a
    substitute for it -- see module docstring."""
    for n in range(_MAX_INDEX + 1):
        yield full_space_line(n)


# --- --check: validate a FOREIGN dump ---------------------------------

# tools/radio_address.py -> tools -> repo root -> docs/...
_VECTORS_PATH = (pathlib.Path(__file__).resolve().parent.parent
                  / 'docs' / 'radio-address-vectors.json')

_NAME_SPACE = _MAX_INDEX + 1  # 3125
_RESERVED_GROUP = 10
# Channels 3 and 4 are the legacy hand-allocated fleet convention --
# getez sits on 3, and .claude/rules/playfield-testing.md forbids
# retuning it (the torture:8760 relay pool depends on getez staying
# there). Channel 7 + group 0 is MakeCode's unconfigured default;
# group 10 is microbit-radio-relay's !C button space.
_RESERVED_CHANNELS = (3, 4, 7)


def load_digests(path=None):
    """The published digest constants `check_dump()` compares a
    foreign dump against, read from `docs/radio-address-vectors.json`
    -- never hardcoded here a second time (see the vectors file's own
    `$comment` and this module's "Two digests" docstring section).
    `path` overrides the default location, mainly for tests."""
    import json
    props = json.loads(
        pathlib.Path(path or _VECTORS_PATH).read_text(encoding='utf-8')
    )['properties']
    return {
        'd1': props['full_space_sha256'],
        'd2': props['conformance_sha256'],
        'little_endian_encoder':
            props['endianness_probe']['reversed_encoder_digest'],
        'little_endian_decoder':
            props['conformance_sha256_broken_decode']['digest'],
    }


def _digest_of(text):
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _expected_line(n, columns):
    """The reference's own line for index `n`, at the same column
    count as the foreign dump being checked -- `conformance_line`
    (5 columns) or `full_space_line` (3), never a third
    reimplementation of either."""
    return (conformance_line(n) if columns == 5
            else full_space_line(n)).rstrip('\n')


def check_dump(text, digests=None):
    """Validate a conformance dump captured from ANY OTHER
    implementation -- C++ firmware, MakeCode static TypeScript, or a
    sibling repo's own port -- against this module's reference output
    and the digests published in `docs/radio-address-vectors.json`.

    Distinguishes protocol v1 (3 columns, `<name>,<channel>,<group>`,
    digests to D1) from v2 (5 columns, digests to D2) purely by
    COUNTING COLUMNS on the first line -- per
    `docs/radio-addressing.md`'s "Dump protocol" section, never by a
    flag or a filename.

    Pure function over `text` (and the loaded `digests`, so a test can
    pass a fixture instead of reading the real vectors file off disk).
    Returns `(problems, notes)`. `problems` empty means the dump
    conforms. `notes` records what protocol was detected and, on
    success, which digest matched -- and for a v1 dump, that it
    cannot prove the inverse (`decode`/`reverse`) is correct, since a
    clean v1 pass that implied otherwise would overstate what was
    checked (see this module's "Two digests, and which one is the
    gate" docstring section).

    On failure the diagnostics ARE the feature: a digest matching a
    published broken-implementation fault is named by that fault
    rather than reported as an opaque mismatch, the first differing
    line is quoted by name (not a byte offset), and any reserved
    channel/group value present is explained concretely -- including
    that channel 3 collides with getez, which
    `.claude/rules/playfield-testing.md` forbids retuning because the
    `torture:8760` relay pool depends on getez staying there.
    """
    digests = digests or load_digests()
    problems, notes = [], []

    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()  # the dump contract's trailing newline
    if not lines:
        return (['dump is empty -- expected 3125 lines, one per name'],
                 notes)

    columns = lines[0].count(',') + 1
    if columns not in (3, 5):
        return ([f'lines have {columns} columns; expected 3 (protocol '
                  'v1, digests to D1) or 5 (protocol v2, digests to '
                  'D2) -- see docs/radio-addressing.md "Dump '
                  'protocol"'], notes)
    notes.append(f'protocol v{1 if columns == 3 else 2} '
                 f'({columns} columns), {len(lines)} lines')
    if columns == 3:
        notes.append(
            'v1 digests to D1, which CANNOT detect a broken decode() '
            'or reverse() -- a little-endian decoder is wrong on 3000 '
            'of 3125 names and produces a byte-identical v1 dump. '
            'Emit v2 to have the inverse actually checked.')

    if len(lines) != _NAME_SPACE:
        problems.append(
            f'expected {_NAME_SPACE} lines, got {len(lines)} -- the '
            'dump is every name for n = 0..3124 in order, one per '
            'line')

    body = ''.join(line + '\n' for line in lines)
    actual = _digest_of(body)
    expected = digests['d2'] if columns == 5 else digests['d1']
    if actual == expected:
        notes.append(
            f'digest {actual} matches published '
            f'{"D1 full_space_sha256" if columns == 3 else "D2 conformance_sha256"}')
    else:
        if columns == 5 and actual == digests['little_endian_decoder']:
            problems.append(
                'this is the LITTLE-ENDIAN DECODER digest: decode() '
                'reads name[0] as the LEAST significant base-5 digit; '
                'it must be the MOST significant. Wrong on 3000 of '
                '3125 names, and INVISIBLE to a v1 dump -- decode() '
                'is the production path, what "!N <name>" runs on '
                'every command.')
        elif columns == 3 and actual == digests['little_endian_encoder']:
            problems.append(
                'this is the LITTLE-ENDIAN ENCODER digest: the '
                'encoder emits base-5 digits least-significant-first, '
                'so name[0] carries the wrong digit. Reverse the '
                'digit order. (Palindromes -- zuzuz, tatat, zavaz -- '
                'are identical either way, which is why a spot check '
                'misses it.)')
        elif columns == 5 and _digest_of(''.join(
                ','.join(line.split(',')[:3]) + '\n'
                for line in lines)) == digests['d1']:
            problems.append(
                f'D2 {actual} != {expected}, but D1 over the first '
                'three columns MATCHES: the forward map is correct '
                'and the fault is in decode() or reverse() -- columns '
                '4 and 5.')
        else:
            problems.append(f'digest {actual} != {expected}')

    for index, line in enumerate(lines[:_NAME_SPACE]):
        expected_line = _expected_line(index, columns)
        if line != expected_line:
            problems.append(
                f'first differing line is {index + 1} (n={index}): '
                f'got {line!r}, expected {expected_line!r}')
            break

    # Structural checks, independent of the digest, so a failing
    # implementation gets a diagnosis rather than one opaque hash.
    malformed = inverse = bad_channel = bad_group = 0
    seen_channels, seen_groups, seen_names = set(), set(), set()
    for line in lines:
        parts = line.split(',')
        if len(parts) != columns:
            malformed += 1
            continue
        try:
            name = parts[0]
            channel, group = int(parts[1]), int(parts[2])
            inverse_columns = [int(p) for p in parts[3:]]
        except ValueError:
            malformed += 1
            continue
        seen_names.add(name)
        seen_channels.add(channel)
        seen_groups.add(group)
        if channel % 2 == 0 or not (25 <= channel <= 73):
            bad_channel += 1
        if group == 0 or group == _RESERVED_GROUP or not (1 <= group <= 126):
            bad_group += 1
        try:
            n = name_to_index(name)
        except ValueError:
            malformed += 1
            continue
        if any(value != n for value in inverse_columns):
            inverse += 1

    if malformed:
        problems.append(f'{malformed} line(s) malformed or carrying a '
                        'name outside the codebook')
    if inverse:
        problems.append(
            f'{inverse} line(s) where decode(name) or reverse(channel, '
            'group) does not equal n -- the inverse directions '
            'disagree with the forward map')
    if bad_channel:
        problems.append(f'{bad_channel} line(s) have a channel outside '
                        'the odd 25..73 range')
    if bad_group:
        problems.append(f'{bad_group} line(s) have a group outside '
                        '1..9 / 11..126')
    if len(seen_names) != len(lines):
        problems.append(f'names are not distinct: {len(seen_names)} '
                        f'unique across {len(lines)} lines')
    forbidden_channels = sorted(set(_RESERVED_CHANNELS) & seen_channels)
    if forbidden_channels:
        problems.append(
            f'emits reserved channel(s) {forbidden_channels}: 3 and 4 '
            "are the legacy fleet convention (getez sits on 3, and "
            '.claude/rules/playfield-testing.md forbids retuning it '
            '-- the torture:8760 relay pool depends on getez staying '
            "there), 7 is MakeCode's unconfigured default")
    forbidden_groups = sorted({0, _RESERVED_GROUP} & seen_groups)
    if forbidden_groups:
        problems.append(
            f'emits reserved group(s) {forbidden_groups}: 0 is '
            "MakeCode's unconfigured default, 10 is the relay's !C "
            'button space')
    return problems, notes


def _main():
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description='Radio addressing reference implementation '
                     '(docs/radio-addressing.md). Emits a canonical '
                     'form for n=0..3124 to stdout, for conformance '
                     'checking against docs/radio-address-vectors.json, '
                     'or validates a dump from ANOTHER implementation.')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        '--dump', choices=('conformance', 'full-space'),
        help='conformance = D2, 5 columns (name,channel,group,decode,'
             'reverse), the primary conformance gate. full-space = D1, '
             '3 columns (name,channel,group), forward-only, a bisector.')
    mode.add_argument(
        '--check', metavar='FILE',
        help="validate a foreign implementation's dump ('-' for "
             'stdin) against this reference and the published '
             'digests. Accepts v1 (3 columns) or v2 (5 columns), told '
             'apart by column count.')
    args = ap.parse_args()

    if args.dump:
        dump = conformance_dump if args.dump == 'conformance' else full_space_dump
        sys.stdout.writelines(dump())
        return

    text = (sys.stdin.read() if args.check == '-'
            else pathlib.Path(args.check).read_text(encoding='utf-8'))
    problems, notes = check_dump(text)
    for note in notes:
        print(f'note: {note}')
    if not problems:
        print('CONFORMANT')
        return
    print('NOT CONFORMANT:', file=sys.stderr)
    for problem in problems:
        print(f'  - {problem}', file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    _main()
