---
id: '022'
title: Per-robot radio channel and a boot identity banner
status: executing
branch: sprint/022-per-robot-radio-channel-and-a-boot-identity-banner
use-cases: []
issues:
- firmware-hardcodes-one-radio-channel-for-a-multi-channel-fleet.md
- no-boot-banner-so-a-flash-cannot-be-confirmed.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 022: Per-robot radio channel and a boot identity banner

## Goals

Make a flashed hex **know which robot it is for**, and make a flashed robot
**say which build it is running**. Both are prerequisites for trusting any
bench measurement, and the lack of both cost a full session on 2026-08-26.

## Problem

**One channel, several robots.** `src/comms/radio_transport.h` hardcodes
`kChannel = 4`, but `radio-robot-lib/config/robots/` says vevov is on **4** and
tovez is on **3**. Every hex this repo builds puts its robot on channel 4, so
tovez has been sitting on vevov's channel. `make_deploy.py --robot` selects only
the flash target and never reads robot config.

Because radio is a broadcast, that is not merely untidy: a second powered robot
on the same group and channel receives every command and can reply. On
2026-08-26 a command sent over zavaz (channel 4) was answered by tovez, while a
board named vevov was simultaneously present having been reprogrammed as a
RADIOBRIDGE by someone else. Which robot would execute a given motion verb could
not be established from the link alone. **A motion command on a shared channel
can move a robot nobody is looking at.**

**No boot banner.** `test/test.ts` displays nothing at startup, so a fresh flash
and a months-old build are indistinguishable at a glance. Sprint 018 ticket 003
had to prove firmware identity indirectly — send a verb no earlier build has,
check for a reply; send a bogus verb, check for silence — purely to establish
that a flash had landed.

## Solution

One mechanism serves both. `make_deploy.py` already builds from a **scratch
copy** (`sync()` into `.tmp/deploy-head`), so it can read the target robot's
config and inject both the radio channel and a version/identity string into that
copy before building. The repo's own source keeps its current defaults, so an
un-parameterised build behaves exactly as today.

The boot banner goes in `test/test.ts`, **not** the extension. `src/blocks/` is
student-facing and a banner there would hijack the display of every student
program that imports this extension. The bench robots run `test.ts`, which is
what gets flashed.

## Success Criteria

- [ ] `make_deploy.py --robot tovez` produces a hex on **channel 3**;
      `--robot vevov` produces one on **channel 4**; both read from
      `radio-robot-lib/config/robots/<robot>.json`, not from a table in this
      repo.
- [ ] A build with no robot specified still uses channel 4, unchanged.
- [ ] On boot the robot shows `IconNames.Rollerskate`, then scrolls the version
      as **day.revision** — `0.20260826.5` renders `26.05`.
- [ ] The banner is in `test/test.ts` only; nothing in `src/blocks/` touches the
      display on boot.
- [ ] Both robots flashed and each confirmed reachable **on its own channel via
      its own relay** — vevov over zavaz, tovez over getez.
- [ ] `clasi design validate`, `ruff`, `tsc --noEmit` and the full pytest suite
      all green.

## Scope

### In Scope

`tools/make_deploy.py` (robot config read + build-time injection),
`src/comms/radio_transport.h` (however the channel is parameterised),
`test/test.ts` (boot banner), `tests/` (guards for both).

### Out of Scope

- **`kGroup` (10).** Shared fleet-wide; not per-robot. Do not make it one
  without evidence.
- **The student-facing radio block** proposed in `radio-group-setup-block.md`
  (sprint 021). That is a runtime classroom concern; this is build-time fleet
  identity. They should agree on where radio identity lives before both are
  built, but that is a conversation, not this sprint.
- **The `tovez.json` geometry contradictions** — `trackwidth = 115` under a note
  specifying 128 mm, `rotational_slip = 1.0` under a note documenting 0.9371.
  Real, in the same config file, and deliberately not touched here: those notes
  are detailed enough that someone had a reason, and picking a side is the
  stakeholder's call.

## Test Strategy

The channel injection is testable without hardware: build for each robot and
assert the resulting scratch copy carries the expected constant. The manifest
guard (`test_pxt_manifest_completeness.py`) constrains the mechanism — any new
`src/` file must be in `pxt.json`'s `files` array, in both directions.

The banner cannot be unit-tested (no TypeScript is executed by any test), so its
verification is the build checkpoint plus reading it off the display on the
bench — which is precisely the capability this sprint exists to create.

## Architecture

Compact. No new component; one new **seam**: the build learns the target robot.
`make_deploy.py` gains a dependency on `radio-robot-lib`'s robot config, which is
already this fleet's canonical source of per-robot truth and is already consulted
by other tooling. No dependency direction changes inside `src/` — the firmware
keeps a compile-time constant, it is simply no longer the same constant for
every robot.

Design note for the implementer: the repo currently has THREE places that
believe things about robot identity — this firmware constant, `camlink.py`'s
`MOUNTS` table, and `radio-robot-lib`'s per-robot JSON. The JSON is canonical.
Prefer reading it over adding a fourth.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] Architecture review passed
- [ ] Stakeholder approved
- [ ] Both robots on the bench and charged (stated 2026-08-26)

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | `make_deploy.py` reads the robot's `radio_channel` and injects it into the scratch build | — |
| 002 | Boot banner in `test/test.ts`: skate icon then `day.revision`, injected by the same seam | 001 |
| 003 | Build checkpoint, then flash vevov (ch 4) and tovez (ch 3) and confirm each on its own relay | 001, 002 |

Tickets execute serially in the order listed.

> **Operational consequence to expect.** Once tovez is correctly on channel 3,
> **zavaz will no longer reach it** — that needs getez, which was unplugged as
> of 2026-08-26. Verifying tovez after flashing therefore requires getez
> connected, or a USB link to tovez on the bench.
