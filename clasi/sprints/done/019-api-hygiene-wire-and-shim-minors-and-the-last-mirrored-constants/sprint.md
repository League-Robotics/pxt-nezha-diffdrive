---
id: 019
title: 'API hygiene: wire and shim minors, and the last mirrored constants'
status: done
branch: sprint/019-api-hygiene-wire-and-shim-minors-and-the-last-mirrored-constants
use-cases: []
issues:
- wire-and-shim-minor-defects.md
- duplicated-constants-across-the-shim-boundary.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 019: API hygiene — wire and shim minors, and the last mirrored constants

## Goals

Clear the small, independent defects the 2026-08-26 review found that did not
justify displacing anything larger — and retire the last un-guarded mirrored
constants, which is the habit that produced several of the bigger findings.

## Problem

- **`execHelp()` silently truncates and can drop its own terminator.** Today's 18
  verbs fit in 240 bytes, but `"\n"` is appended last, so the first thing lost to
  overflow is the line terminator — producing a reply the host's reassembler
  never completes. `execRun()` twenty lines below gets this right, with a comment
  explaining exactly this hazard.
- **The OTOS product id is re-typed across the shim boundary.**
  `otos_port.h` defines `kExpectedProductId = 0x5F`; `world.ts` independently
  re-types the literal. If the id ever changes, the port initializes fine and
  the student block returns **false**, disagreeing with its own sibling readback.
- **`dutl`/`dutr` are percent x 100 and nothing says so.** `probe(12)` reads
  10000 at full duty. Both source comments say "duty x100", which reads as
  "percent" and is wrong by 100x — and `tlm.py`, the module that calls itself
  "the only place any wire -> engineering-unit scale factor is written", omits
  these two columns.
- **A "no-op" motion command does not stop prior motion.** `WHEELS_X 0 0 ...`
  during a `WHEELS_V` hold is acked `ok`, clears the planner, and the robot keeps
  driving. The documented contract says "nothing is driven".
- **pi appears 13 times; the centidegree conversion is written out five times**
  in `shims.cpp` alone. The default cruise speed is two constants in two units
  whose comment claims they match, with nothing enforcing it.

## Solution

Each is a small, self-contained change. The unifying thread is the review's
clearest structural finding, which this sprint acts on as a rule:

> Every mirrored constant in this repo that has a drift test — `kVersion`, the
> four 240-byte line caps, `RUN_EVENT_SOURCE`, the `kDiag*` ordinals — has held
> across five sprints. Every one without has drifted or is structurally able to.
> **Every mirrored constant gets a drift test, or gets merged.**

`0x5F` and the two default speeds are merge candidates: `startWorldTracking()`
should return `worldTrackingReady()` rather than knowing the product id, and pi
plus the cdeg conversion belong in one named constant beside `shims.cpp`'s
stated boundary convention.

## Success Criteria

- [ ] HELP cannot lose its terminator — a `static_assert` on the table width, a
      reserved final byte, or multi-line emission.
- [ ] `0x5F` appears once, in `otos_port.h`.
- [ ] `dutl`/`dutr` units documented in `tlm.py`'s table and corrected in both
      source comments; the double x100 kept or removed deliberately.
- [ ] A degenerate motion command either stops prior motion or documents plainly
      that it does not.
- [ ] `kCdegToRad`/`kRadToCdeg` defined once; the seven open-coded sites use them.
- [ ] Every remaining mirrored constant has a drift test or has been merged —
      enumerated, so the answer is checkable rather than asserted.

## Scope

### In Scope

`src/comms/wire_handler.cpp` (`execHelp`), `src/blocks/world.ts`
(`startWorldTracking`), `src/shims.cpp` (`diagValue` duty units, the conversion
constants), `src/motion/motion_engine.cpp` (degenerate-command contract),
`tools/tlm.py` (unit table), `tests/host/` (drift tests).

### Out of Scope

The `shims.cpp` cohesion finding — seven subsystems in one header-less file, with
odometry as the obvious extraction candidate. That is a real change of shape and
deserves its own sprint with its own architecture review, not a slot at the end
of a hygiene sprint.

## Test Strategy

Every item here is host-testable without hardware. The drift tests follow the
existing `test_wire_constants_drift.py` pattern, which is the one mechanism in
this repo with a proven record of holding constants together across sprints.

## Architecture

N/A — trivial. No layering or dependency change; the conversion constants sit
beside the boundary convention `shims.cpp`'s header already states.

## Use Cases

N/A — trivial. No student-visible behaviour changes except
`startWorldTracking()` becoming correct for a future sensor revision, and the
degenerate-command contract being made honest.

## Definition of Ready

- [ ] Sprint planning document complete
- [ ] Architecture review skipped (no architectural impact) or passed
- [ ] Stakeholder has approved the sprint plan
- [ ] Sprints 015 and 016 merged — both touch `shims.cpp` and
      `motion_engine.cpp`

## Tickets

| # | Title | Depends On |
|---|-------|------------|
| 001 | `execHelp()` cannot lose its terminator | — |
| 002 | `startWorldTracking()` stops re-typing the product id | — |
| 003 | `dutl`/`dutr` units: document, and decide the double x100 | — |
| 004 | Degenerate motion command: stop prior motion, or document that it does not | — |
| 005 | `kCdegToRad`/`kRadToCdeg`; retire the seven open-coded conversions | — |
| 006 | Enumerate remaining mirrored constants; drift-test or merge each | 002, 005 |
| 007 | **Build checkpoint** (standing convention, always last) | 001–006 |

Tickets execute serially in the order listed.
