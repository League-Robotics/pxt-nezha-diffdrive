---
id: '006'
title: "Cross-repo conformance interop \u2014 dump entry point and foreign-dump checker"
status: in-progress
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Cross-repo conformance interop — dump entry point and foreign-dump checker

## Description

Ticket 001 landed `tools/radio_address.py` and 23 passing tests (commit
`bf0633f`), proving this repo's addressing scheme agrees with the SPEC.
It does not let anyone check that this repo agrees with the RELAY — the
original stakeholder ask ("a test proving all three repos generate
name<->(channel,group) identically"). **Verified 2026-08-30**: running
`microbit-radio-relay`'s comparator against this worktree reports
`no tools/radio-address-dump` and `RESULT: DISAGREEMENT` or failure,
while its own two implementations (relay python, relay firmware-cpp)
both report `a1069d8503f83873`. This repo is currently invisible to the
cross-repo comparison.

This ticket closes that gap: an executable entry point the relay's
comparator can discover and run, plus a `--check` mode on
`tools/radio_address.py` that can validate a dump from ANY
implementation — including ticket 002's C++ firmware, which has no
sha256 of its own and participates in conformance only by having its
dump validated by this checker.

**Should land before or alongside ticket 002.** Ticket 002's firmware
derivation has no independent way to prove conformance — a language
with no sha256 participates in the cross-repo scheme by producing a
dump and having this ticket's checker validate it against D1/D2. If
ticket 002 lands first with nothing to validate its dump against, its
conformance is unverified until this ticket catches up.

## Acceptance Criteria

### 1. `tools/radio-address-dump` — protocol v1 entry point

- [x] `tools/radio-address-dump` exists, is executable, and is at the
      exact path the relay's comparator discovers implementations by.
- [x] `--list` prints the implementation ids this entry point can dump.
- [x] `<id>` prints the 3-column canonical form
      `"<name>,<channel>,<group>\n"` for `n = 0..3124`, in order, to
      stdout.
- [x] Exit code 3 means the requested id is unavailable.
- [x] It calls `tools/radio_address.py`'s `full_space_dump()` — it MUST
      NOT reimplement the encode/decode/addr/reverse arithmetic. There
      must not be a second implementation of the map in this repo.
- [x] `pxt-nezha-diffdrive-4f` has a verified 70-line version of this
      script that drops in as-is — ask the team-lead for it before
      writing one from scratch.
- [x] Acceptance: the relay's comparator run goes three-way green (relay
      python, relay firmware-cpp, this repo) instead of reporting a
      missing dump.

### 2. `--check` mode on `tools/radio_address.py` — validate a FOREIGN dump

- [x] `tools/radio_address.py --check <file>` (or equivalent — stdin is
      also acceptable) reads a dump produced by ANOTHER implementation
      and validates it. Today the CLI only EMITS (`--dump
      conformance|full-space`); nothing here validates a dump from
      outside this module, including the C++ firmware and MakeCode
      static-TypeScript implementations arriving in ticket 002.
- [x] Distinguishes v1 (3 columns, digests to D1) from v2 (5 columns,
      digests to D2) by counting columns, per
      `docs/radio-address-vectors.json`'s `$.properties.dump_protocol`.
- [x] On success, reports which protocol version and which digest
      matched.
- [x] On failure, the diagnostics ARE the feature — a bare "mismatch" is
      not acceptable output. It must:
  - [x] Compare the dump's digest against
        `$.properties.endianness_probe.reversed_encoder_digest`
        (`52ea4a6e6124cdebbb56639d21db15b48f95d54aeb38ce93f7df9e7f9fbeb8dc`)
        and, if it matches, report "little-endian ENCODER" by name —
        the D1 (3-column) reversed-encoder fault.
  - [x] Compare the dump's digest against
        `$.properties.conformance_sha256_broken_decode.digest`
        (`5acfd688ee679d4ce56d5e686ae9b3931cf8d570cca250111f685e1f867fe6c9`)
        and, if it matches, report "little-endian DECODER" by name —
        the D2 (5-column) broken-decode fault (`encode`, `addr`,
        `reverse` all correct; only `decode` reads `name[0]` as least
        significant).
  - [x] When neither published fault digest matches, find and report the
        FIRST differing line by content — the name at that line, not
        only "digest mismatch" or a byte offset. Diff the foreign dump
        against this module's own `conformance_dump()`/`full_space_dump()`
        line-by-line (matching column count) to locate it.
  - [x] When a reported channel is 3, 4, or 7, or a reported group is 0
        or 10, explain the reserved-value collision concretely by name —
        in particular, a mapping that emits channel 3 collides with
        getez, which `.claude/rules/playfield-testing.md` forbids
        retuning (`torture:8760`'s relay pool depends on getez staying on
        channel 3).
- [x] Acceptance: feeding the checker a dump from a deliberately
      little-endian encoder reports "little-endian ENCODER"; feeding it
      a dump from a deliberately little-endian decoder (with encode/addr/
      reverse correct) reports "little-endian DECODER"; feeding it a
      dump with one row's channel forced to 3 names getez by name in the
      diagnostic.

### 3. Reverse-address rejection tests

- [x] Ticket 001's suite (`tests/tools/test_radio_address.py`) has 8
      `pytest.raises` cases and all of them reject malformed NAMES.
      Nothing asserts that `address_to_name` rejects an address the
      forward map never produces — the half of the inverse ticket 002's
      firmware will need to implement, and it needs pinning here first.
- [x] Add `pytest.raises(ValueError)` cases to
      `tests/tools/test_radio_address.py` for `address_to_name`:
  - [x] `(26, 1)` — even channel (channels are always odd, 25..73).
  - [x] `(23, 1)` — below the channel floor (25).
  - [x] `(75, 1)` — above the channel ceiling (73).
  - [x] `(25, 0)` — reserved group 0 (MakeCode's unconfigured default).
  - [x] `(25, 10)` — reserved group 10 (the relay's `!C` button space).
  - [x] `(25, 127)` — above the group ceiling (126).

### 4. Regenerate the diagnostic-constant tests, don't assert-not-equal

- [x] The landed
      `test_d1_canonical_form_is_not_the_reversed_encoder_digest` (ticket
      001) asserts the reference implementation's D1 does NOT equal
      `52ea4a6e...`. That proves the reference is unbroken; it does NOT
      prove `52ea4a6e...` still describes the fault it names — replace
      the published constant with garbage and this test still passes.
      This is a defect per `docs/radio-addressing.md`'s stated
      principle that "a diagnostic constant must name its exact fault."
- [x] Add a test that constructs a deliberately little-endian ENCODER
      (digit loop reversed, everything else correct) inline, builds D1's
      three-column canonical form from it, and asserts the digest
      equals `52ea4a6e6124cdebbb56639d21db15b48f95d54aeb38ce93f7df9e7f9fbeb8dc`
      exactly — regenerating the published broken digest from the fault
      it claims to describe.
- [x] Add a test that constructs a deliberately little-endian DECODER
      (`encode`, `addr`, `reverse` all correct; only `decode` reads
      `name[0]` as least-significant) inline, builds D2's five-column
      canonical form from it, and asserts the digest equals
      `5acfd688ee679d4ce56d5e686ae9b3931cf8d570cca250111f685e1f867fe6c9`
      exactly.
- [x] Both new tests double as fixtures for the `--check` mode's
      diagnostics (item 2 above) — the same two broken implementations
      are what the `--check` acceptance tests should feed the checker.

## Implementation Plan

### Approach

Work item 1 first (the entry point) — it is the smallest and unblocks
the relay-side three-way comparison immediately, even before `--check`
exists. Ask the team-lead for `pxt-nezha-diffdrive-4f`'s verified
70-line version before writing one from scratch; adapt it to call
`full_space_dump()` (or `conformance_dump()`, if the relay's actual
comparator expects v2 — confirm against its documented contract before
finalizing) from `tools/radio_address.py` rather than reimplementing
the map.

Work item 4 (regenerate, don't assert-not-equal) can be done in
parallel with item 1 — it only touches
`tests/tools/test_radio_address.py` and needs no new files. Build the
two broken implementations (local to the test module, never exported)
by copying `index_to_name`/`name_to_index`/`_address_to_index` and
reversing the digit loop / swapping the read order — the same
technique ticket 001's Implementation Plan already describes for
constructing a reversed encoder produces both fixtures item 4 needs.

Work item 3 (reverse-rejection tests) is a small, independent addition
to the same test file — six new `pytest.raises` cases against
`address_to_name`, using the boundary values already established in
`_address_to_index`'s docstring (odd 25..73, group 1..9 or 11..126).

Work item 2 (`--check` mode) depends on nothing else in this ticket but
benefits from items 3 and 4 landing first, since the reserved-value
rejection tests and the two broken-implementation fixtures are exactly
what the `--check` acceptance tests (feeding it bad dumps) exercise.
Implement the line-by-line diff against this module's own dump as a
plain generator comparison — correctness first, then simplify if it's
slow.

### Files to Create

- `tools/radio-address-dump` — protocol v1 entry point (executable,
  no file extension, at the exact path the relay's comparator expects).

### Files to Modify

- `tools/radio_address.py` — add `--check` mode (and its diagnostic
  helpers) to the existing `argparse` CLI in `_main()`, alongside the
  existing `--dump` flag. Keep the diagnostic logic in importable
  functions rather than buried in `_main()`, the same way
  `conformance_dump()`/`full_space_dump()` are already separated from
  the CLI wrapper — a future caller (or a test) may want to call the
  checker directly on an in-memory dump rather than through a file.
- `tests/tools/test_radio_address.py` — add: six reverse-rejection
  cases (item 3), two regenerate-from-fault tests replacing the
  assert-not-equal pattern (item 4), and `--check` mode tests (item 2)
  that exercise both the little-endian-encoder and little-endian-decoder
  diagnostics plus the reserved-channel-3/getez explanation.

### Testing Plan

- **Existing tests to run**: `uv run pytest tests/tools/test_radio_address.py -v`
  — must stay green; this ticket only adds coverage, it does not change
  `name_to_index`/`index_to_name`/`name_to_address`/`address_to_name`.
- **New tests**: described in Acceptance Criteria items 2-4 above, all
  in `tests/tools/test_radio_address.py`.
- **Verification command**: `uv run pytest tests/tools/test_radio_address.py -v`
- **Acceptance criterion beyond pytest**: the relay comparator run
  (`microbit-radio-relay`'s cross-repo comparator, run against this
  worktree) is green three-way — relay python, relay firmware-cpp, and
  this repo all report the same digest, instead of this repo reporting
  `no tools/radio-address-dump`.

### Documentation Updates

None required — `docs/radio-addressing.md`'s "Dump protocol" section
already documents v1/v2 and the digest table; this ticket implements
against it and does not change the contract. If the relay's comparator
turns out to expect a CLI shape different from what's described above
(discovered during implementation), update this ticket's Acceptance
Criteria to match reality rather than silently deviating, and flag it
to the team-lead.
