---
id: '002'
title: Add set-radio-group Setup block
status: open
use-cases: []
depends-on: []
github-issue: ''
issue: radio-group-setup-block.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Add set-radio-group Setup block

## Description

Radio RX is already on by default at group 10 / channel 4: the
protocol fiber polls `RadioTransport::tryReceiveLine()` every loop,
which lazily calls `ensureRadioReady()` on its first invocation
(`radio_transport.cpp:30-47`) — `uBit.radio.enable()`, then
`setFrequencyBand(kChannel)`, then `setGroup(kGroup)`, then
`setTransmitPower(kTransmitPower)`, with `kGroup = 10`, `kChannel = 4`,
`kTransmitPower = 7` all fixed `constexpr` in
`radio_transport.h:182-184`. There is currently no way to change the
group from a student program, and no visibility into it either.

Add a new Setup-group block that lets a student set the radio group
(default 10), applied idempotently whether it's called before or
after the radio has already come up:

- **TS block**: `//% block="set radio group %group"`, default 10, in
  the Setup group (or whichever group Ticket 004's approved layout
  eventually places it in — coordinate with that ticket if it lands
  first; do not block on it, since this ticket's own default group
  placement can be adjusted trivially later).
- **Shim**: new `//% shim=diffDrive::setRadioGroup` declaration plus a
  sim-side fallback in `src/sim.ts` (the sim has no real radio, so a
  no-op body — consistent with this file's existing precedent for
  shim-only, hardware-only surfaces).
- **C++ setter**: a new public method on `RadioTransport` (e.g.
  `setGroup(uint8_t group)`) that:
  - If `radioReady_` is already `true`, calls
    `uBit.radio.setGroup(group)` immediately.
  - If `radioReady_` is still `false`, just records the requested
    group so the next `ensureRadioReady()` call applies it instead of
    the `kGroup` constant.
  - `kChannel` and `kTransmitPower` are untouched by this ticket —
    `kGroup` stops being applied as a hardcoded constant in
    `ensureRadioReady()` and instead reads the stored (defaulted-to-10)
    value.
- **Doc comment** on the TS block should say plainly: "the robot
  listens for RUN commands from the radio relay on this group" (per
  the issue's own suggested wording).

**Explicitly out of scope** (per sprint.md Out of Scope): no channel
setter, no channel default change, no block exposing channel at all —
channel stays fixed at 4 (fleet convention; the zavaz relay this
project's robots use is on channel 4, never channel 3/getez).

## Acceptance Criteria

- [ ] A `set radio group %group` block exists in the toolbox, defaults
      to 10.
- [ ] Calling the block from `on start`, BEFORE any other radio
      activity, results in the robot listening on the requested group
      once the radio comes up — verified on tovez (flash, set a
      non-default group in a test program, confirm via the relay or
      via `DIAG` radio counters that the robot is or isn't reachable
      on the expected group).
- [ ] Calling the block AFTER the radio is already active changes the
      live group immediately (`uBit.radio.setGroup()` called directly)
      — verified on tovez.
- [ ] Channel remains fixed at 4 in both cases; no block or shim
      exposes channel.
- [ ] A bare program that never calls the new block still defaults to
      group 10 (no regression to current fleet behavior).
- [ ] Full native build succeeds; C++ ABI change is additive only (new
      method, no existing signature changed).

## Implementation Plan

**Approach**: Additive change across three layers (TS block →
shim → C++), following the existing pattern other setters in this
codebase use (e.g. `setTaperWindows`/`setRampMs` in `sim.ts` /
`shims.cpp` for the shim-declaration convention; `kMaxPayloadBytes`
public-member precedent in `radio_transport.h` for where a new public
method belongs relative to existing private state).

**Files to modify**:
- `src/radio_transport.h` — add a public `setGroup(uint8_t group)`
  method declaration; add a private stored-group field (defaulting to
  `kGroup`'s current value, 10) that `ensureRadioReady()` reads instead
  of the `kGroup` constant directly. Keep `kGroup` itself as the
  compile-time default value the stored field initializes to.
- `src/radio_transport.cpp` — implement `setGroup()`: branch on
  `radioReady_` as described above; update `ensureRadioReady()` to
  apply the stored field instead of the `kGroup` constant literal.
- `src/shims.cpp` — new `//% shim=diffDrive::setRadioGroup` native
  forward calling the new `RadioTransport` method (find the existing
  `RadioTransport`/`Protocol` access pattern other shims in this file
  use, e.g. near other radio-adjacent shims).
- `src/sim.ts` — new `_setRadioGroup(group: number): void { }`-style
  sim fallback (no-op is correct here — no real radio in-browser),
  named to match whatever the new shim's TS-side name is chosen to be.
- `src/motion.ts` (or wherever Setup-group blocks currently live) —
  new exported TS function with the `//% block=` annotation, calling
  the new shim.

**Testing plan**:
- Native build + flash to tovez (mbdeploy, `built/mbcodal-binary.hex`).
- Test both call orders (block before vs. after other radio-touching
  code) against the fleet's RADIOBRIDGE relay or a bench proxy for it.
- Confirm channel stays 4 via `DIAG` or direct code inspection of
  `ensureRadioReady()`.
- Local editor: confirm the new block appears in the toolbox and
  compiles/converts to blocks cleanly (this ticket lands after Ticket
  001, so JS→Blocks conversion should already be working end-to-end
  for the whole extension by the time this is tested).

**Documentation updates**: Update the block's own `/** ... */` doc
comment (student-facing, in the extension itself) per the issue's
suggested wording. No separate design-doc update required — this is
additive to the Radio Transport leaf's existing documented public
surface, not a new subsystem (see sprint.md Architecture, Step 3).
