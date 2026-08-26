---
status: in-progress
sprint: '017'
tickets:
- 017-006
---

# Comment volume is a process output: 1.22 lines per code line vs the vendored kernel's 0.05

Priority: **Medium** -- but the *standard* should land before the cleanup, or
sprints 015+ will refill it the way 010-013 refilled sprint 009's work.

## The measurement

| Group | Code | Comment | Ratio |
|---|---:|---:|---:|
| `src/` project-owned (26 files) | 3687 | **4508** | **1.22** |
| `src/core/diffdrive.h/.cpp` -- vendored, human-written | 1103 | 53 | **0.05** |
| `tools/` (23 files) | 3950 | 408 | **0.10** |

One repository, the same readers, a factor of **twenty-four**. The vendored
kernel is the most subtle code in the project -- PID with accel feedforward,
adaptive bias, lambda authority scaling, crawl-pulse dithering, two latch
families, lock-free `Output` publication -- and it is comprehensible at 0.05.

Worst files (all headers): `comms/serial_transport.h` **5.63** (19 code lines,
107 comment), `comms/radio_transport.h` 5.05, `motion/motion_engine.h` 4.79,
`comms/wire_adapter.h` 4.33, `platform/encoder_pose_source.h` 4.10 (lines 1-70
are one comment block -- 63% of the file), `core/heading_wrap.h` 4.00 (a
**six-line function under forty-four lines of comment**).

## Sprint 009 ran, and the actively-edited files grew back

Comment lines immediately before sprint 009's dedicated cleanup vs today:

| File | pre-009 | today | delta |
|---|---:|---:|---:|
| `wire_adapter.h` | 440 | 277 | -163 |
| `shims.cpp` | 706 | 599 | -107 |
| `protocol.h` | 216 | 151 | -65 |
| `protocol.cpp` | 245 | 200 | -45 |
| `wire_adapter.cpp` | 423 | 382 | -41 |
| `serial_transport.h` | 133 | 107 | -26 |
| `wire_handler.h` | 471 | 465 | -6 |
| `motion_engine.cpp` | 135 | 135 | 0 |
| `motion_engine.h` | 374 | **393** | **+19** |
| `nezha_port.cpp` | 77 | **118** | **+41** |
| `wire_handler.cpp` | 378 | **427** | **+49** |
| `radio_transport.h` | 147 | **197** | **+50** |
| **total** | **3745** | **3451** | **-294 (-8%)** |

Ten cleanup tickets bought 8%, and every file sprints 010-013 touched is now
*above* its pre-cleanup count. Another cleanup sprint buys another 8% and gets
re-consumed.

## Proposed standard -- write-time, not cleanup-time

Add to `docs/code-review/guidelines.md`:

> A comment must state something a competent reader cannot recover from the code
> in front of them: a unit, a sign convention, an invariant, a measured hardware
> fact, a wire layout, or a hazard.
>
> Sprint numbers, ticket numbers, issue filenames, code-review IDs, and "this
> used to be X" belong in the commit message. Git already stores them.
>
> If the comment is longer than the code it describes, it is a design-doc
> section wearing a comment's clothes. Move it, or cut it to the fact.

## Mechanical ratchet, available today

Comment lines carrying `sprint N` / `ticket N` / `R-NN` / `KERN-NN` /
`WIRE-NN` / `BLK-NN` / `API-NN` / an `.md` filename: **363** across `src/`
(worst: `wire_adapter.cpp` 50, `wire_handler.h` 47, `shims.cpp` 40,
`wire_handler.cpp` 40, `motion_engine.h` 37). The vendored kernel, 1103 code
lines, carries **2**.

A host test in the `test_pxt_manifest_completeness.py` style -- no compiler,
reads source as text -- asserting `total <= 363`, ratcheting down. The value is
not the number; it is that a sprint adding a ticket reference must either cut
one elsewhere or raise the budget in a diff someone reviews.

## Two comments that are wrong, not merely long -- fix these first

- **`src/blocks/motion.ts:1-12`**, the namespace docstring that surfaces in the
  extension's own documentation and is the first thing a student reads: *"The
  wheel servo runs in its own fiber on the micro:bit ... the function bodies
  here are the browser-simulator fallbacks."* The kernel's fiber is
  **deliberately unwired** (`shims.cpp:190`) and "the robot only moves while
  something ticks" is a stated **system invariant** in
  `docs/design/design.md`; the sim fallbacks moved to `sim.ts` in sprint 012.
  This teaches the exact mental model the tick model exists to replace.
- **`src/blocks/motion.ts:200-206`**, `isMoving()`: *"Checks state only -- it
  does not itself advance the move."* It calls `updateMove()` ->
  `engine.serviceMove()`, which reissues `kernel_.drive()`, can end the move,
  and can fire `deliverStopNow()`. The 2026-08-23 verify pass already found this
  false (BLK-12); unchanged since.

Keep list (do **not** touch in any cleanup pass), work order, and per-file data:
[`docs/code-review/2026-08-26/raw/comment-audit.md`](docs/code-review/2026-08-26/raw/comment-audit.md).
