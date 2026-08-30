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
"""
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


def _main():
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description='Radio addressing reference implementation '
                     '(docs/radio-addressing.md). Emits a canonical '
                     'form for n=0..3124 to stdout, for conformance '
                     'checking against docs/radio-address-vectors.json.')
    ap.add_argument(
        '--dump', choices=('conformance', 'full-space'), required=True,
        help='conformance = D2, 5 columns (name,channel,group,decode,'
             'reverse), the primary conformance gate. full-space = D1, '
             '3 columns (name,channel,group), forward-only, a bisector.')
    args = ap.parse_args()

    dump = conformance_dump if args.dump == 'conformance' else full_space_dump
    sys.stdout.writelines(dump())


if __name__ == '__main__':
    _main()
