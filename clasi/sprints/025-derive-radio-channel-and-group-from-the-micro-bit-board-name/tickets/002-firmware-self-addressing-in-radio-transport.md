---
id: '002'
title: Firmware self-addressing in radio_transport
status: open
use-cases: []
depends-on:
- '001'
github-issue: ''
issue: derive-each-micro-bit-s-radio-channel-group-from-its-five-letter-name.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Firmware self-addressing in radio_transport

## BLOCKER TO CHECK FIRST

There are **uncommitted edits in the MAIN checkout**
(`/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive`, **not** this
worktree) that add a `setChannel()` method with a store-then-apply contract
to `src/comms/radio_transport.h`/`.cpp` (a mutable `channel_` member
defaulting to `kChannel`, a doc comment mirroring `setGroup()`'s, and a
`_K_CHANNEL_RE`-sensitive comment on the `kChannel` line telling
`make_deploy.py` not to reformat it). **Confirmed present** as of this
sprint's planning (verified via `git diff -- src/comms/radio_transport.h` in
the main checkout, 2026-08-30) — this worktree's own copy of the file does
**not** yet have it.

This change is complementary to this ticket, not opposed: a mutable
`channel_` is exactly what derivation needs to write into. But the two
edits must not land blind into the same file. **Before touching
`src/comms/radio_transport.h`/`.cpp`, check with the team-lead** about the
state of that main-checkout change (has it merged into this sprint branch?
is it still pending?). If `setChannel()` has already landed by the time
this ticket is worked, **preserve it verbatim** — same doc comment, same
store-then-apply contract, same `_K_CHANNEL_RE`-sensitive `kChannel` line —
and layer this ticket's derivation underneath it: `channel_`'s *default*
becomes the derived channel instead of `kChannel`, exactly the way
`group_`'s default becomes the derived group below. Do not delete or
restructure `setChannel()` to make room for derivation; the two are meant
to compose.

## Landing Order Constraint (with ticket 003)

**Ticket 003 must land with or before this ticket — never after.**
`tools/make_deploy.py`'s `_inject_radio_channel()` matches the `kChannel`
line via `_K_CHANNEL_RE = r'(static constexpr int kChannel = )\d+(;)'` and
**raises** the moment that regex stops matching. This ticket deletes the
`kChannel` constant the regex matches against; ticket 003 deletes
`_inject_radio_channel()` (and `_K_CHANNEL_RE`) itself. If this ticket's
deletion lands first, every `make_deploy.py` build breaks in between — the
injector still fires, finds no `kChannel` line, and raises. Both tickets'
`depends-on` lists only name `['001']`, so the dependency graph does not
prevent committing them in the wrong order; this note is what does.

## Description

`ensureRadioReady()` (`src/comms/radio_transport.cpp:30`) currently brings
the radio up on a hand-maintained `kChannel` constexpr (deploy-time
text-substituted by `make_deploy.py`'s `_inject_radio_channel()`, retired in
ticket 003) and a baked `group_ = 10` default. This ticket makes the board
derive both from its own name instead: `microbit_friendly_name()` is
already read once, elsewhere, at `Protocol::buildIdentity()`
(`src/comms/protocol.cpp:236`) — this ticket adds a second, independent read
at radio bring-up, per `docs/radio-addressing.md`'s codebook.

The formula's range is not incidental. `channel = 25 + 2*(n%25)` only ever
produces 25-73, and `group = 1 + n/25` (with the `+1` skip past 10) only
ever produces 1-9/11-126 — so this derivation can never emit channel 3, 4,
or 7, nor group 0 or 10, for *any* name (`docs/radio-addressing.md`, "Why
those five values are reserved"). That is what lets a migrated board and
the legacy fleet convention (channel 3/4 + group 10) or MakeCode's
unconfigured default (channel 7 + group 0) coexist with no flag day. The
consequence of *not* reserving them is concrete, not abstract:
microbit-radio-relay's `!N` verb hashes names with a different algorithm
that ignores this reserved set entirely (see ticket 005's "Hard Constraint"
section for why `!N` must not be used in this sprint's own verification).
Computed 2026-08-30 by running that hash across all 3125 names against its
source (`server/src/mbrelay/naming.py:61` and
`source/relay/RadioRelay.cpp:777`, branch `named-links`, HEAD `b6c8651` —
a source reading, not a hardware measurement, per
`.claude/rules/measurement-citations.md`): it lands **112 of 3125 names on
channel 3, 4, or 7**, and two of those are real fleet boards — **zavaz
lands on channel 3, zetuv on channel 7.** zavaz is the sharp case: channel
3 is getez's, and `.claude/rules/playfield-testing.md` forbids retuning
getez because the torture:8760 relay pool depends on it staying there. So
the reserved set this ticket's formula honors by construction is not
stylistic — a mapping that ignores it collides with a documented hardware
constraint the moment it is fed a real board name.

The derivation itself must be pure, allocation-free logic with no CODAL
dependency, following the same pattern `radioRxLineFits()` already
establishes in this header (see `radio_transport.h:55-57` and its host test
`tests/host/test_radio_transport_rx_capacity.py` /
`tests/host/radio_transport_rx_capacity_shim.cpp`): a header-only free
function taking only primitive types, so it is host-testable by
`#include`-ing the header directly, with zero link against
`radio_transport.cpp` (which requires `pxt.h` and cannot be host-compiled
at all — see `src/DESIGN.md` §1's layering table).

## Acceptance Criteria

- [ ] A new pure function (suggested: `bool deriveRadioAddress(const char*
      name, uint8_t* outChannel, uint8_t* outGroup)`) lives in
      `radio_transport.h`, alongside `radioRxLineFits()`, with no CODAL
      dependency (only `<cstddef>`/`<cstdint>`), no allocation, no heap use.
      It implements exactly the codebook in `docs/radio-addressing.md`:
      normalize (trim ASCII whitespace, `A-Z` -> `a-z`), validate against
      `^[zvgpt][uoiea][zvgpt][uoiea][zvgpt]$`, big-endian base-5 decode
      (`name[0]` most significant), `channel = 25 + 2*(n%25)`, `group = 1 +
      n/25`, `+1` if `group >= 10`.
- [ ] On a name that fails validation (unrecognised letter, wrong length,
      etc.), the function returns `false` and writes the **legacy fallback
      pair (channel 4, group 10)** into `*outChannel`/`*outGroup` — never an
      arbitrary or zero-initialized value.
- [ ] `ensureRadioReady()` calls `microbit_friendly_name()` and this new
      function to obtain the channel/group it brings the radio up on,
      instead of reading `kChannel` and the baked `group_ = 10` default.
- [ ] The existing call order in `ensureRadioReady()` is preserved exactly:
      `uBit.radio.enable()` -> `setFrequencyBand()` -> `setGroup()` ->
      `setTransmitPower()`. Do not reorder. The header comment immediately
      above `ensureRadioReady()`'s declaration (or a comment at the call
      site) explains why the order matters, mirroring the existing comment
      at `radio_transport.cpp:33-37` ("CODAL does not default to band 0 --
      it must be set explicitly, or a robot and the relay could sit on
      different frequencies and never hear each other").
- [ ] `setGroup()`'s existing store-then-apply contract is preserved
      (`radio_transport.h:102-127`): calling it always stores into
      `group_`, and re-applies immediately via `uBit.radio.setGroup()` if
      the radio is already up. In addition, `setGroup()` now sets a new
      `groupOverridden_` flag to `true`. `ensureRadioReady()` consults this
      flag: if `groupOverridden_` is `false` (the board was never
      explicitly told a group — the common case), it uses the *derived*
      group; if `true` (a prior `setGroup()` call, e.g. from the `on start`
      block, ran before radio bring-up), it uses the already-stored
      `group_` value instead of overwriting it with the derived one. This
      is the mechanism that keeps the student-facing "set radio group"
      block (`clasi/issues/radio-group-setup-block.md`, sprint 021 ticket
      005) working unchanged: an explicit override always wins over the
      derived default.
- [ ] `group_`'s hardcoded `= 10` initializer is removed (or reinterpreted
      as "unset" alongside `groupOverridden_ = false`) — a board that is
      never told a group no longer silently defaults to the legacy
      fleet-wide 10.
- [ ] If `setChannel()` has landed (see BLOCKER above), the analogous
      "default is derived, explicit override wins" contract applies to
      `channel_` too, for symmetry with `group_`/`groupOverridden_`. If it
      has not landed, this ticket does not need to add `setChannel()`
      itself — only `ensureRadioReady()`'s direct use of the derived
      channel via `setFrequencyBand()`.
- [ ] No allocation, no heap, anywhere in the new code path — this runs at
      radio bring-up on a microcontroller with no dynamic memory.

## Implementation Plan

### Approach

1. Resolve the BLOCKER note above first — confirm with the team-lead
   whether `setChannel()` has landed on this sprint branch.
2. Add `deriveRadioAddress()` (or equivalent name) to `radio_transport.h`
   as a free function in `namespace diffDrive`, next to
   `radioRxLineFits()`. Port the codebook directly from
   `docs/radio-addressing.md`'s pseudocode (it is already expressed as
   non-negative integer arithmetic with no shifts, no `%` on negatives —
   translates close to line-for-line).
3. Wire it into `ensureRadioReady()` (`radio_transport.cpp:30-47`): call
   `microbit_friendly_name()`, pass it to `deriveRadioAddress()`, use the
   result (respecting `groupOverridden_`) for `setFrequencyBand()` and
   `setGroup()`. Keep the call order unchanged.
4. Add `groupOverridden_` (bool, default `false`) as a new private member;
   set it to `true` inside `setGroup()`.
5. Write the host test (see Testing Plan) proving the C++ derivation
   reproduces the same full-space digest ticket 001's Python
   implementation proves.

### Files to Modify

- `src/comms/radio_transport.h` — new pure derivation function; new
  `groupOverridden_` member; updated doc comments on `group_`,
  `setGroup()`, `ensureRadioReady()`'s declaration comment, and the
  `kChannel`/`group_` block explaining the new derived-default behavior.
  If `setChannel()` has landed, its doc comment and store-then-apply
  contract are preserved verbatim and extended per the last acceptance
  criterion above.
- `src/comms/radio_transport.cpp` — `ensureRadioReady()`'s body calls
  `microbit_friendly_name()` and the new derivation function;
  `setGroup()` sets `groupOverridden_ = true`.

### Files to Create

- `tests/host/radio_address_shim.cpp` — `extern "C"` ctypes surface for the
  new pure function, following `radio_transport_rx_capacity_shim.cpp`'s
  exact pattern: `#include "comms/radio_transport.h"` directly (not the
  `.cpp`), one wrapper function per pure entry point, bool-as-int return
  convention.
- `tests/host/test_radio_address_derivation.py` — host test following
  `tests/host/test_radio_transport_rx_capacity.py`'s structure
  (`compile_shared_lib` fixture from `test_kernel_harness`, `ctypes.CDLL`).
  **Must assert the same full-space digest ticket 001 proves**: for `n =
  0..3124`, derive the name via the same encode logic (can import/port from
  `tools/radio_address.py`'s `index_to_name` on the Python side, since only
  the *decode* direction — name to channel/group — needs to run through the
  C++ shim), call the shim's derivation function, build the canonical
  `"<name>,<channel>,<group>\n"` form, sha256 it, and assert it equals
  `docs/radio-address-vectors.json`'s `$.properties.full_space_sha256`
  (`a1069d8503f83873ab79b97c063ff95f300b34a35a03d83848888cc361bbde31`). One
  algorithm, two languages (Python in ticket 001, C++ here), one contract —
  the same digest proves both.
  Also assert: the legacy fallback pair (4, 10) for a rejected name (e.g.
  `"gauti"`, from `$.reject[]`), and the `groupOverridden_` behavior is
  covered at the unit level if it can be exposed through the shim (a second
  shim entry point wrapping a small harness struct/class instance, or a
  free-function equivalent of the override logic — use judgment here, the
  shim only needs to expose what's pure and testable, not the full
  `RadioTransport` class, which requires `pxt.h`).

### Testing Plan

- **Existing tests to run** (scoped, per `.claude/rules/source-code.md`):
  `uv run pytest tests/host/test_radio_transport_rx_capacity.py
  tests/host/test_wire_constants_drift.py` — the two existing suites that
  touch `radio_transport.h` most directly, to confirm nothing in this
  ticket's header edits regresses them.
- **New tests**: `tests/host/test_radio_address_derivation.py` (described
  above).
- **Verification command**: `uv run pytest tests/host/test_radio_address_derivation.py tests/host/test_radio_transport_rx_capacity.py -v`

### Documentation Updates

Update the doc comments this ticket touches in place
(`radio_transport.h`'s `group_`/`setGroup()`/`kChannel` block,
`ensureRadioReady()`'s call-order comment) — no separate doc file changes.
`docs/radio-addressing.md` is normative and already committed; this ticket
implements against it, not the other way around.
