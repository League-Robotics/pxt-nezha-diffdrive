---
id: "005"
title: 'Add the "set radio group" Setup block'
status: open
use-cases: [SUC-004]
depends-on: ["004"]
github-issue: ""
issue: radio-group-setup-block.md
# completes_issue: Controls whether linked issues are archived when this ticket
# is moved to done. Default: true (archive when all referencing tickets are done).
# Set to false (scalar) to suppress archival for ALL linked issues on this ticket.
# Set to a mapping {filename.md: false} to suppress archival per issue filename.
# Use false for tickets that partially address a multi-sprint umbrella issue.
completes_issue: true
# exception: Written by a lower agent when it cannot proceed (see architecture §exception-protocol).
# exception:
#   thrown_by: "programmer"          # "programmer" | "sprint-planner"
#   thrown_at: "2026-05-07T14:23:00Z"
#   attempted: |
#     Description of what was attempted before giving up.
#   conflict: "architecture-update.md §3 — reason the agent is blocked"
#   surface: "internal"              # "user-visible" | "internal"
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Add the "set radio group" Setup block

## Description

Add a student-facing block that sets the radio group the robot listens
on, defaulting to 10 (the fleet's existing convention), idempotent
whether it runs before or after the radio has lazily come up. This
reaches the already-working `ensureRadioReady()`/`kGroup = 10` default
in `src/comms/radio_transport.h`/`.cpp` — today `kGroup` is a
`constexpr` with no student-facing way to change it.

Depends on ticket 004 (toolbox reorganization): the block belongs in
the new Remote group (`on run`, `on run command`, `set radio group`)
that ticket creates. Placing it there directly, rather than adding it
to Move/Setup first and moving it later, avoids a second toolbox edit.

Explicitly does NOT expose the channel (fixed at 4, the fleet's zavaz
relay) — channel selection stays out of student control; sprint 022's
`make_deploy.py --robot` injects it per-robot at deploy time instead.
Only the group is student-editable.

## Acceptance Criteria

- [ ] New block, in the Remote toolbox group, e.g. `set radio group
      %group`, default value 10.
- [ ] Doc comment states plainly: "the robot listens for RUN commands
      from the radio relay on this group."
- [ ] `RadioTransport::kGroup` becomes a mutable field (e.g. `group_`)
      with a public `setGroup(uint8_t)`; `ensureRadioReady()` reads the
      field instead of the old constant. Channel and transmit power are
      untouched (`kChannel`, `kTransmitPower` stay `constexpr`).
- [ ] `setGroup()` is idempotent regardless of call order: if the radio
      is already up, it re-applies immediately via
      `uBit.radio.setGroup()`; if not yet up, the stored value is
      picked up whenever `ensureRadioReady()` eventually runs. It does
      NOT eagerly call `uBit.radio.enable()` on a program that never
      otherwise sends/receives (preserves the existing lazy-init
      RAM/softdevice-cost tradeoff — see `radio_transport.h`'s own
      header comment).
- [ ] Native passthrough is a small free function beside
      `startProtocol()` in `protocol.cpp` (same lazy-singleton
      `Protocol&` access pattern), exposed as a `//%`-shimmed block API
      function with at most four parameters on one line.
  - [ ] The shim's simulator fallback in `sim.ts` has a real (non-empty)
      body from the start — do not reintroduce the empty-`{}`-crashes-
      the-sim defect ticket 002 just fixed.
- [ ] Verified on hardware: changing the group actually changes what
      the robot listens on. Use vevov (zavaz relay, channel 4) for this
      check — tovez's relay (`getez`) is not connected, so tovez cannot
      verify radio RX behavior, only USB-tethered checks.
- [ ] After this ticket, the toolbox as a whole matches
      `block-toolbox-groups-reorganization.md`'s "Decision" table
      exactly: 40 blocks (39 existing + this one) across the eight
      declared groups, in order, with no block in a group the table
      does not name (final end-to-end toolbox check — ticket 004
      verified the 39 pre-existing blocks; this ticket's completion is
      the first point at which the full 40-block picture exists).

## Implementation Plan

**Approach**: Change `radio_transport.h`'s `kGroup` from `static
constexpr uint8_t kGroup = 10;` to a private mutable field with a
default of 10, add a public `setGroup(uint8_t group)` that applies the
idempotent-reapply logic described above, and update
`ensureRadioReady()` (`radio_transport.cpp`) to read the field. Add a
thin free-function passthrough in `protocol.cpp` (mirroring `void
startProtocol() { protocol(); }`) that forwards into the `Protocol`'s
owned `RadioTransport` instance — add a small `Protocol::setRadioGroup()`
forwarding method if `radioTransport_` isn't otherwise reachable from
outside `Protocol`. Add the block itself to `src/blocks/run.ts`
(co-located with the other Remote-group blocks), its `//%
shim=diffDrive::...` declaration, and its `sim.ts` fallback (a real,
trivial body — e.g. record the value in a sim-side variable, no
behavior change needed since the simulator has no radio).

**Files to create/modify**:
- `src/comms/radio_transport.h` (mutable field + `setGroup()`
  declaration)
- `src/comms/radio_transport.cpp` (`ensureRadioReady()` reads the
  field; `setGroup()` implementation)
- `src/comms/protocol.cpp` (and `protocol.h` if a new public method is
  needed) — free-function passthrough
- `src/blocks/run.ts` (new block, `group="Remote"`, no `advanced=`)
- `src/blocks/sim.ts` (new shim's simulator fallback — real body)

**Testing plan**: Local editor (per ticket 001's doc) to confirm the
block appears in Remote with the right default and doc comment, and
that the simulator doesn't crash when it's called. Hardware check on
vevov: flash a program that calls `set radio group` with a non-default
value from `on start`, confirm (via the zavaz relay) that RUN commands
on the OLD group no longer reach it and commands on the NEW group do;
repeat with the block called after a radio TX/RX has already happened,
to confirm the idempotent-reapply path. Scope any C++ host tests this
repo has for `radio_transport.*` (see `tests/host/` for the existing
`RadioTransport`-adjacent tests, e.g. the wire-constants-drift and RX-
capacity tests) — run those to confirm no regression, and add a host
test for the new `setGroup()`/`ensureRadioReady()` interaction if the
existing host-test harness can exercise `RadioTransport` without a full
CODAL target (confirm feasibility at implementation time; `pxt.h`
dependency in `radio_transport.cpp` may limit host-testability the same
way it already limits testing of the rest of that file).

**Documentation updates**: Update `radio_transport.h`'s own header
comment (which currently states "No per-robot channel-selection surface
yet" in the `kGroup`/`kChannel`/`kTransmitPower` comment block) to
reflect that group is now student-settable while channel remains fixed.
