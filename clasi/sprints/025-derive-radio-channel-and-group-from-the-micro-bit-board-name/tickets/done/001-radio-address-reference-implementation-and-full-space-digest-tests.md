---
id: '001'
title: Radio address reference implementation and full-space digest tests
status: done
use-cases: []
depends-on: []
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Radio address reference implementation and full-space digest tests

## Description

Create the pure-Python reference implementation of the radio addressing
scheme from `docs/radio-addressing.md`, plus its test suite. This is the
foundation ticket: `make_deploy.py`, `robotlink.py`, and `wire_acceptance.py`
(tickets 003-004) all import from this module, and the firmware host test
(ticket 002) asserts against the same digest this ticket's test proves.

No I/O, no board access, no host tool changes in this ticket — pure
functions only.

## Acceptance Criteria

- [x] `tools/radio_address.py` exists with four pure functions and no I/O:
      `name_to_index(name) -> int`, `index_to_name(n) -> str`,
      `name_to_address(name) -> (channel, group)`,
      `address_to_name(channel, group) -> str`.
- [x] Normalization: trims ASCII whitespace, maps `A-Z` to `a-z`, before
      validation.
- [x] Validation: rejects (raises `ValueError`) anything not matching
      `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` after normalization.
- [x] Encoding is big-endian: `name[0]` is the most significant base-5
      digit, `name[4]` the least — per `docs/radio-addressing.md`
      "Endianness" section. `n = 0; for p in 0..4: n = n*5 +
      index_in_alphabet(name[p])`.
- [x] `channel = 25 + 2 * (n % 25)`; `group = 1 + (n / 25)`, then `group += 1`
      if `group >= 10`.
- [x] `tools/radio_address.py` can emit D2's five-column conformance
      canonical form to stdout — for `n = 0..3124` in order, one line
      `"<name>,<channel>,<group>,<decode(name)>,<reverse(channel,group)>\n"`
      — via e.g. a `--dump` CLI flag or a documented function the test suite
      and CLI both call. This is the shared "conformance dump" contract:
      pxt-nezha-diffdrive-4f is drafting a checker that hashes and validates
      one implementation's stdout dump against D2, so the C++ firmware and
      static-TypeScript implementations can conform without sha256 in
      either language. This ticket owns that checker; the draft is inbound
      from -4f — ask the team-lead for it rather than writing one from
      scratch.
- [x] `tests/tools/test_radio_address.py` asserts, in this priority order:
  - [x] **D2 — primary conformance digest.** Build the canonical form for
        `n = 0..3124` in order, one line
        `"<name>,<channel>,<group>,<decode(name)>,<reverse(channel,group)>\n"`
        (UTF-8) — the last two columns are always `n`, which forces
        `decode()` and `reverse()` to run — concatenate, sha256, and assert
        it equals `docs/radio-address-vectors.json`'s
        `$.properties.conformance_sha256`
        (`f10db38bb3cdd2c5e15e69384f8633ff315876615f65bec8d4660e2012867657`).
        This is the primary conformance gate. `decode()` is the production
        path — it is what the relay's `!N <name>` executes on every
        command — and D2 is the only digest that exercises it.
  - [x] **D1 — full-space digest, retained as a bisector.** Build the
        canonical form for `n = 0..3124` in order, one line
        `"<name>,<channel>,<group>\n"` (UTF-8), concatenate, sha256, and
        assert it equals `$.properties.full_space_sha256`
        (`a1069d8503f83873ab79b97c063ff95f300b34a35a03d83848888cc361bbde31`).
        D1 covers only `encode(n->name)` and `addr(n->pair)` — it never
        calls `decode()` or `reverse()`. **Measured 2026-08-30**: a build
        with `decode()` and `reverse()` both deliberately broken produces a
        byte-identical D1; the same build fails D2 loudly
        (`2e4e9013…`). Do not drop this assertion as "redundant with D2" —
        D1's coverage is a strict subset of D2's, so on its own it proves
        nothing D2 doesn't, but asserting both means a D2 failure alongside
        a D1 pass localises the fault to `decode`/`reverse` rather than the
        forward map, which is the only way to tell the two failure modes
        apart from test output alone.
  - [x] Every row in `$.vectors[]` round-trips exactly: `name_to_address`
        matches the row's `channel`/`group`, and `address_to_name` matches
        the row's `name` (skip rows with `evidence: "label-only"` for
        `address_to_name` since `togov` has no confirming silicon read —
        the row is still valid for the forward direction).
  - [x] Every entry in `$.reject[]` raises on `name_to_address`.
  - [x] **Malformed vs. unknown — both directions, both tested.** These fail
        silently in opposite directions, so neither can stand in for the
        other:
        - MALFORMED (outside `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$` after
          normalize) **MUST RAISE** — never hash, truncate, or default.
          Test rejects at least `"gauti"` (a real hostname on this rig
          that looks like a micro:bit name until you check position 2),
          `"robot1"`, `"vevo"`, `"vevovv"`, `"aeiou"`, and `""`.
        - WELL-FORMED BUT UNKNOWN (a valid CVCVC name no board currently
          uses, e.g. `"pipip"`) **MUST BE ACCEPTED** and return `51/90`.
          The address layer does not know which boards exist and must not
          pretend to — that is the deploy-time silicon gate's job (ticket
          003). Pin this with an explicit test, or a later reader
          "hardens" the rejection and breaks tune-to-whatever-I-name.
  - [x] Every key/value pair in `$.normalize_equivalent` (e.g. `"VEVOV"` and
        `" vevov "` both normalize to produce the same address as
        `"vevov"`).
  - [x] Injectivity: `name_to_address` over all 3125 valid names produces
        3125 distinct `(channel, group)` pairs (this is a corollary of the
        digest test but pin it directly too — a cheap, independent check).
  - [x] `address_to_name(name_to_address(name)) == name` for a spot sample
        including `zuzuv` (n=1) and `zotuz` (n=225) specifically — these are
        the two vectors published in `$.properties.endianness_probe` and
        the issue text precisely because they are *not* digit-palindromes.
        Do not rely solely on `zuzuz`/`tatat`/`zotoz`/`pipip`/`zavaz` for
        endianness coverage — per `docs/radio-addressing.md` "Endianness,
        and why the obvious test misses it", all five are digit-palindromes
        and pass identically under a reversed (little-endian) encoder. If
        the primary digest test ever fails, compare it against
        `$.properties.endianness_probe.reversed_encoder_digest`
        (`52ea4a6e6124cdebbb56639d21db15b48f95d54aeb38ce93f7df9e7f9fbeb8dc`)
        as the first diagnostic step — a match there means the digit order
        is reversed, not that the algorithm is otherwise wrong.

## Implementation Plan

### Approach

Port the pseudocode in `docs/radio-addressing.md` directly — it is already
expressed as non-negative integer arithmetic with no shifts, no `%` on
negatives, no BigInt, so the port is close to line-for-line. Load
`docs/radio-address-vectors.json` once (module-level constant path, resolved
relative to the repo root the same way other `tools/*.py` scripts locate
`docs/`) inside the test file, not the library module — the library stays
pure and dependency-free; only the test needs the fixture.

Write the D2 conformance-digest test first (per `docs/radio-addressing.md`
"Two digests, and which one is the gate," D2 is the primary conformance
gate) — it will fail loudly and unambiguously (digest mismatch) before any
of the smaller assertions are even reached, and getting it green first is
the fastest path to a correct implementation, since D2 forces `decode()`
and `reverse()` to run and so cannot pass on a forward-only implementation.
Add the D1 full-space-digest assertion alongside it, not instead of it —
D1 is retained as a bisector, not dropped as redundant (see the Acceptance
Criteria note on why a byte-identical D1 does not imply a correct
`decode`/`reverse`). If D1 produces
`52ea4a6e6124cdebbb56639d21db15b48f95d54aeb38ce93f7df9e7f9fbeb8dc` instead of
the expected value, the encoder is little-endian — reverse the digit loop,
do not add a workaround. (That published reversed-encoder value is for D1's
three-column canonical form specifically; a reversed encoder still fails D2,
just not against that exact constant, since D2's canonical form has two more
columns.)

### Files to Create

- `tools/radio_address.py` — the four pure functions.
- `tests/tools/test_radio_address.py` — the test suite described above.

### Files to Modify

None. This ticket only adds new files.

### Testing Plan

- **New tests**: `tests/tools/test_radio_address.py` (this ticket's own
  suite, described in Acceptance Criteria).
- **Verification command**: `uv run pytest tests/tools/test_radio_address.py -v`
- No existing tests are touched by this ticket, so no regression run beyond
  the module's own new suite is required here (the ticket-004 rule to run
  the full suite once applies only if working out-of-process; on this sprint
  branch the full suite runs once at `close_sprint`).

### Documentation Updates

None — `docs/radio-addressing.md` and `docs/radio-address-vectors.json` are
already normative and committed; this ticket implements against them and
does not change them.
