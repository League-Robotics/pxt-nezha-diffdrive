---
status: done
sprint: '017'
tickets:
- 017-005
---

# Stale `main.ts` and pre-013 paths survived the sprint 013 stale-path sweep -- 40+ live references

Priority: **Medium** -- individually trivial, collectively a reader-hostile map,
and the fix should come with the guard that makes it stick.

Sprint 013 ticket 006 was scoped as *"final sweep -- DESIGN.md, doc/tool prose,
repo-wide stale-path verification."*

## `main.ts` -- retired in sprint 012, still referenced 40 times

**16 in live source**: `shims.cpp` x5 (`:143`, `:389`, `:742`, `:745`,
`:1035`), `comms/protocol.h` x2 (`:100`, `:234`), `comms/protocol.cpp` x3
(`:61`, `:63`, `:374`), `comms/wire_adapter.cpp` x2 (`:91`, `:96`),
`motion/motion_engine.h` x2 (`:13`, `:70`), `motion/motion_engine.cpp` (`:229`),
`blocks/sim.ts` (`:162`). Plus `tools/tour_square.py:5` and **23 in
`src/DESIGN.md`**.

`protocol.cpp:374` is the one most likely to cost someone real time -- it says
`startProtocol()` is *"called once from a top-level statement in main.ts's
`diffDrive` namespace"*. The call is in `src/blocks/motion.ts:66`.

## Pre-sprint-013 include paths in live headers (6)

| File:line | Says | Is |
|---|---|---|
| `motion/motion_engine.h:135, :148` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `platform/encoder_pose_source.h:10` | `src/otos_port.h` | `src/platform/otos_port.h` |
| `comms/wire_handler.h:144, :168` | `src/wire_adapter.cpp` | `src/comms/wire_adapter.cpp` |
| `comms/wire_handler.h:276` | `src/wire_adapter.h` | `src/comms/wire_adapter.h` |

Plus `tools/DESIGN.md:110` -> `src/heading_wrap.h`.

## Comment references to functions that no longer exist (5)

| Cited | From | Kind |
|---|---|---|
| `Protocol::formatDiag()` | `comms/radio_transport.h:196, :240`; `comms/wire_adapter.cpp:163` | **asserted as current -- live** |
| `parseLine()` | `comms/protocol.cpp:130` | historical |
| `sendDebug()` | `comms/wire_handler.cpp:1138` | historical |
| `sendTelemetry()`, `sendDeviceBanner()` | `comms/protocol.h:57` | historical |

`wire_adapter.cpp:163` tells a reader *"shims.cpp's DIAG verb reads many more
(protocol.cpp's `formatDiag()`)"* -- a pointer into nothing. This is
`guidelines.md` anti-pattern 3, whose canonical example is a dangling
`readLine()` reference.

## What to change -- with a guard

Fix the references, **and add a host test that greps `src/` and `docs/` for
`src/<file>` paths not present on disk.** That would have caught every path
finding here and will keep catching them. The pattern already exists:
`tests/host/test_pxt_manifest_completeness.py` does exactly this for
`pxt.json`'s file list -- no compiler, reads source as text, cheap.
