---
id: '035'
title: Comment work order and design-doc truth pass
status: executing
branch: sprint/035-comment-work-order-and-design-doc-truth-pass
use-cases:
- SUC-001
- SUC-002
issues:
- code-review/comment-work-order-factual-fixes-untracked-citations.md
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Sprint 035: Comment work order and design-doc truth pass

## Goals

Apply the code review's 53-block comment boil-down work order (18 in
the motion-and-kernel annex, 12 in comms, 10 in blocks-and-test, 13 in
tools-and-tests) using the guidelines' safety rules: re-anchor by
content rather than line number, treat every item as a possible no-op,
and check each replacement against the *current* code before landing
it — the same discipline sprint 009's comment cleanup ran. Fix the
sixteen comments the review found factually wrong today (wrong file
names, wrong ordinal numbers, "not consulted by anything yet" where it
now is, "handlers run on their own fiber" where they've run on the
protocol fiber since sprint 028, retired radio channel numbers, a cited
function that doesn't exist, and others listed in review section 5).
Track or relocate the six `MEASURED` citations to `captures/` directories
that are gitignored and untracked, so a fresh clone can actually follow
them. Extend `test_archaeology_marker_budget.py` to also ratchet
comment *volume* (comment lines / code lines) per file, not only the
sprint/ticket-ID marker count it ratchets today, so this cleanup holds
instead of drifting back up the way it did between the 08-26 and
09-02 reviews. Add the two new anti-patterns the review names — dated
UPDATE paragraphs stacked on one comment, and citations to untracked
artifacts — to `docs/code-review/guidelines.md` as anti-patterns 6 and 7.

## Problem

Comment-only lines per code line in project-owned `src/` are back above
the 08-26 review's level (~1.4 now vs 1.22 then), and every file the
last two sprints touched grew: `comms/radio_transport.h` runs 7.26
comment lines per code line, `motion/motion_engine.h` 4.30,
`comms/protocol.h` 3.72 — against the vendored kernel's 0.03. The
existing archaeology ratchet (`_BUDGET = 388`) only holds the count of
sprint/ticket-ID markers; the new growth is a different shape — dated
capture citations instead of sprint numbers — and is just as long, so
the existing ratchet doesn't catch it. Sixteen comments assert things
that are no longer true: two say the source files are named
`differential_drive.{h,cpp}` when they're `diffdrive.{h,cpp}`; one says
the RUN drop count is "ordinal 30" when the real count is 28 (30 is
`max_yaw_rate`); one says two fields are "not consulted by anything
yet" when `defaultCruiseForDistance()` reads both; one says `goToWorld`
is "capped-curvature" when the cap was removed; one says the move
engine "lives HERE" in a file it moved out of; two mis-cite which
ordinals expose which streaks; three say handlers run on their own
fiber via MessageBus when they've run nested on the protocol fiber
since sprint 028; one says "ANY I2C from a RUN handler hangs the board"
in the same file whose handlers do OTOS I2C on every corner; one cites
a function (`Protocol::formatDiag()`) that doesn't exist; three
describe a two-fiber writer model retired since the emit ring; one
misquotes a version string and what it's tested against; one gets the
same-text dedupe window wrong by 7.5×; one cites retired radio
addresses; one cites a closed issue as live; one calls a cached read a
live I2C burst. Six `MEASURED` citations from `src/` point at
`captures/` paths that are gitignored and untracked, so the evidence
behind those claims cannot be checked from a fresh clone —
`.claude/rules/measurement-citations.md`'s whole premise is that a
citation names an artifact that can be checked.

## Solution

Work through the four annexes' boil-down lists in order, each item
re-anchored by matching its quoted content in the current file (not by
the line numbers the review cites, which may have shifted), verifying
the replacement text is still accurate against the code as it stands
today before landing it, and treating any item whose premise has
already changed as a no-op rather than forcing a stale replacement.
Fix the sixteen factual errors listed in review section 5 as targeted
text edits — no rewrite needed beyond making the claim true. For the
six untracked capture citations: either `git add -f` the small
JSON/Python capture directories they point at, or move the cited
numbers into a tracked `reports/*.md` file and repoint the citation
there. Extend `test_archaeology_marker_budget.py` with a second ratchet
on comment-lines-per-code-line per file, seeded from this sprint's
post-cleanup measurement so future growth is caught the way marker
count already is. Add anti-patterns 6 (dated UPDATE paragraphs stacked
on a comment) and 7 (citations to untracked artifacts) to
`docs/code-review/guidelines.md`, each with the concrete example the
review found (`nezha_port.cpp:11-55`'s three-update stack; the six
untracked `captures/` citations).

## Success Criteria

**Revised at detail-planning time, 2026-09-06** — the 2026-09-03 text
below each bullet is kept where it still holds and corrected where the
verification pass (see "Verification pass" section) showed it does not.

- The project-owned `src/` aggregate ratio drops from its measured
  **1.126** baseline, and every file listed in the baseline table at or
  above 2.00 is reviewed against the guidelines' write-time standard
  and comes down where the excess is archaeology. **NOT** the original
  "no project-owned file above 2.0": that criterion is unreachable and
  undesirable as written — `core/fiber_identity.h` has 7 code lines and
  `core/heading_wrap.h` 11, so a header stating a contract, a unit and
  one measured fact is above 2.0 no matter how tight it is. Where a
  file's length is genuinely contract-and-invariant rather than
  archaeology, it stays and its baseline is recorded as-is with the
  reason. The ratchet is per-file and seeded from measurement, not a
  blanket cap.
- Every `captures/` path cited as MEASURED from `src/` (including
  `src/DESIGN.md`) resolves in a fresh clone: either force-tracked, or
  repointed at an artifact that is.
- Every factual error that the verification pass classified **live** is
  fixed and spot-checked against current code. The six the pass found
  already resolved or moot are recorded as no-ops with the sprint that
  resolved them, not "fixed".
- `test_archaeology_marker_budget.py` gains a second ratchet that fails
  if a project-owned file's comment ratio regresses past its recorded
  per-file baseline, and the existing `_BUDGET` marker ratchet is
  lowered from 388 to at most the post-cleanup count (356 today).
- `docs/code-review/guidelines.md` lists seven anti-patterns, with 6
  and 7 matching the review's descriptions and examples.
- No behaviour change anywhere. The host suite plus the team-lead's
  desk firmware build after the last ticket is the gate (see Test
  Strategy).

## Scope

### In Scope

**Corrected 2026-09-06 against the verification pass.**

- The **38 live** items of the 53-block boil-down work order, across
  `motion/motion_engine.{h,cpp}`, `core/heading_wrap.h`,
  `platform/nezha_port.{h,cpp}`, `shims.cpp`, `comms/protocol.{h,cpp}`,
  `comms/radio_transport.h`, `comms/serial_transport.h`,
  `comms/run_queue.h`, `comms/emit_queue.h`,
  `comms/wire_handler.{h,cpp}`, `comms/wire_adapter.{h,cpp}`,
  `blocks/*.ts`, `test/test.ts`, `tools/camlink.py` and
  `tests/host/test_kernel_harness.py`. The other 15 are recorded as
  no-ops with the sprint that resolved them.
- A judgement pass over the high-ratio `src/` files that are on no
  annex list (`core/fiber_identity.h`, `core/bus_guard.h`,
  `core/motion_owner.h`, `core/encoder_glitch_armor.h`,
  `motion/velocity_shaper.h`, `comms/run_bridge.h`,
  `comms/transport_sink.h`, `comms/config_fields.h`).
- The **11 live** rows of review section 5's sixteen, plus the two
  further factual errors this planning pass found
  (`wire_handler.h`'s self-contradiction about `gapOutstanding_`;
  `src/DESIGN.md`'s "still 200" for `kMaxPayloadBytes`).
- **Three `git add -f` operations and one citation repoint** — not six
  relocations. `reports/` is gitignored in full, so the "tracked
  `reports/*.md`" alternative does not exist in this repo.
- `tests/host/test_archaeology_marker_budget.py` (the ratchet lives
  under `tests/host/`, not `tests/dev/`) — the new per-file
  comment-volume ratchet, plus lowering `_BUDGET` from 388.
- `docs/code-review/guidelines.md` — anti-patterns 6 and 7.
- `src/DESIGN.md` — the surviving false claims listed in the
  verification pass. The co-located subsystem `DESIGN.md` stubs are
  **out of scope**: all are 19-35 lines and none carries a stale claim.
- One vendored-kernel edit, narrowly: `core/diffdrive.{h,cpp}`'s
  line-1 self-names. Their upstream-provenance lines stay untouched.

### Out of Scope

- Everything in sprints A (motion profile), B (bus/fiber safety), C
  (test program/blocks/simulator), D (odometry, config descriptor
  table, Protocol diet), and E (bench tools). This sprint touches
  comments and documentation only — no behavior change to any file it
  edits. Because of that, sequence this sprint last (or at least after
  A-D land) so the boil-down list's re-anchoring step isn't invalidated
  by code those sprints are still moving; the design doc's own note
  that "re-anchor by content, treat every item as a possible no-op" is
  precisely the discipline that makes running this after the code
  churn settles the safer order, not a strict dependency.
- Any code or test-behavior change; a comment-only sprint asserting a
  behavior change under cover of a "boil-down" would violate the
  sizing decision this sprint is planned under.

## Verification pass (2026-09-06, at detail-planning time)

The brief above was written 2026-09-03. Sprints **033** (comms/shims
cohesion, config descriptor table, Protocol diet) and **034** (bench
tools, verbs, geofence, schemas consolidation) both closed on
2026-09-06 and pre-empted a substantial share of it. Sprint **031**
(motion profile unification) had already rewritten `motion/`. Every
one of the 53 boil-down items, the 16 factual errors and the capture
citations was re-checked against the tree at `7b3fd89` before any
ticket was written. **Anchors below are quoted content, never line
numbers** — the review's line numbers are stale everywhere.

### Re-measured comment ratio (the ratchet baseline)

**Counting rule.** A line is a COMMENT line iff, stripped of leading
whitespace, it begins with `//` **and not** `//%`. Every other
non-blank line is a CODE line; blank lines count as neither. A trailing
`// [mm]` on a line of code is not counted — that is the house style
(`.claude/rules/no-units-in-identifiers.md`) and must never be under
ratchet pressure. `//%` is excluded deliberately: those are PXT block
pragmas, functionally code, and a ratchet that counted them would push
an author to delete required block metadata. `/** … */` JSDoc is
likewise not counted, for the same reason — it is the student-facing
block API documentation PXT renders. The vendored kernel
(`src/core/diffdrive.{h,cpp}`) is excluded from the project-owned
aggregate. This rule reproduces the review's own table closely where
the file has not changed since (`platform/nezha_port.cpp` 0.96 exact,
`comms/wire_adapter.cpp` 1.31 vs 1.29).

**Project-owned `src/` aggregate: 7866 comment / 6987 code = 1.126 at
the seed, 6585 / 6987 = 0.943 after tickets 002-006.** (The review
measured ~1.4 under a rule that counted JSDoc and `//%`.) The 6987
code-line total is IDENTICAL before and after: the whole sprint deleted
comment lines and nothing else. Ticket 008 re-seeded
`_RATIO_BASELINE` from the "achieved" column below.

| file | code | cmt before → after | baseline → achieved |
|---|---|---|---|
| `comms/wire_adapter.h` | 70 | 382 → 262 | **5.46** → **3.74** |
| `comms/radio_transport.h` | 70 | 370 → 258 | **5.29** → **3.69** |
| `comms/serial_transport.h` | 18 | 93 → 70 | **5.17** → **3.89** |
| `motion/motion_engine.h` | 107 | 508 → 396 | **4.75** → **3.70** |
| `comms/protocol.h` | 98 | 434 → 351 | **4.43** → **3.58** |
| `core/fiber_identity.h` | 7 | 29 → 28 | **4.14** → **4.00** |
| `core/bus_guard.h` | 18 | 72 → 48 | **4.00** → **2.67** |
| `core/heading_wrap.h` | 11 | 44 → 31 | **4.00** → **2.82** |
| `platform/vfp_guard.h` | 13 | 50 → 46 | **3.85** → **3.54** |
| `core/motion_owner.h` | 18 | 66 → 64 | **3.67** → **3.56** |
| `core/encoder_glitch_armor.h` | 44 | 125 → 108 | **2.84** → **2.45** |
| `comms/wire_handler.h` | 220 | 580 → 455 | **2.64** → **2.07** |
| `comms/run_bridge.h` | 34 | 84 → 79 | **2.47** → **2.32** |
| `comms/transport_sink.h` | 24 | 54 → 46 | **2.25** → **1.92** |
| `motion/velocity_shaper.h` | 20 | 43 → 38 | **2.15** → **1.90** |
| `comms/config_fields.h` | 59 | 101 → 95 | 1.71 → 1.61 |
| `shims.cpp` | 710 | 1215 → 1007 | 1.71 → 1.42 |
| `comms/wifi_uart.h` | 19 | 30 → 30 | 1.58 → 1.58 |
| `motion/segment.h` | 65 | 90 → 90 | 1.38 → 1.38 |
| `motion/odometry.h` | 57 | 76 → 76 | 1.33 → 1.33 |
| `comms/wire_adapter.cpp` | 397 | 522 → 474 | 1.31 → 1.19 |
| `comms/protocol.cpp` | 338 | 431 → 389 | 1.28 → 1.15 |
| `motion/motion_limits.h` | 58 | 73 → 73 | 1.26 → 1.26 |
| `motion/velocity_shaper.cpp` | 54 | 65 → 65 | 1.20 → 1.20 |
| `comms/emit_queue.h` | 49 | 50 → 39 | 1.02 → 0.80 |
| `platform/platform_ports.h` | 27 | 27 → 20 | 1.00 → 0.74 |
| `platform/nezha_port.cpp` | 255 | 244 → 189 | 0.96 → 0.74 |
| `comms/wire_handler.cpp` | 834 | 717 → 565 | 0.86 → 0.68 |
| `comms/serial_transport.cpp` | 52 | 43 → 43 | 0.83 → 0.83 |
| `platform/nezha_port.h` | 74 | 59 → 58 | 0.80 → 0.78 |
| `platform/otos_port.h` | 69 | 52 → 52 | 0.75 → 0.75 |
| `motion/motion_engine.cpp` | 299 | 224 → 218 | 0.75 → 0.73 |
| `comms/wifi_link.h` | 226 | 145 → 145 | 0.64 → 0.64 |
| `comms/run_queue.h` | 61 | 39 → 36 | 0.64 → 0.59 |
| `blocks/sim.ts` | 379 | 236 → 165 | 0.62 → 0.44 |
| `platform/vfp_guard.cpp` | 12 | 7 → 7 | 0.58 → 0.58 |
| `comms/radio_transport.cpp` | 112 | 65 → 64 | 0.58 → 0.57 |
| `comms/run_bridge.cpp` | 61 | 34 → 34 | 0.56 → 0.56 |
| `blocks/world.ts` | 157 | 70 → 71 | 0.45 → 0.45 |
| `comms/wifi_uart.cpp` | 31 | 11 → 11 | 0.35 → 0.35 |
| `platform/otos_port.cpp` | 163 | 44 → 44 | 0.27 → 0.27 |
| `blocks/run.ts` | 243 | 61 → 56 | 0.25 → 0.23 |
| `blocks/motion.ts` | 423 | 81 → 74 | 0.19 → 0.17 |
| `comms/wifi_link.cpp` | 844 | 113 → 113 | 0.13 → 0.13 |
| `blocks/stop.ts` | 49 | 6 → 1 | 0.12 → 0.02 |
| `blocks/pose.ts` | 38 | 1 → 1 | 0.03 → 0.03 |
| *(vendored, excluded)* `core/diffdrive.h` | 303 | 71 → 71 | 0.23 → 0.23 |
| *(vendored, excluded)* `core/diffdrive.cpp` | 851 | 100 → 100 | 0.12 → 0.12 |
| *(not in `src/`)* `test/test.ts` | 482 | 645 → 619 | 1.34 → 1.28 |

Two facts this table changes about the brief: the **`blocks/*.ts` files
are already clean** (0.03–0.62) — the review's 1.58 for them was JSDoc
and `//%` — so the blocks work in this sprint is factual fixes and a
handful of named boil-downs, not volume; and the volume is concentrated
in `comms/` headers, `motion/motion_engine.h` and `shims.cpp`.

Existing archaeology-marker ratchet: **356** at detail-planning time
against `_BUDGET = 388` (32 lines of slack), **173** after tickets
002-006; ticket 008 lowered `_BUDGET` 388 → 173.
`platform/encoder_pose_source.h`, which the review's table listed at
4.10, no longer exists (deleted in 033).

### Boil-down work order: live / resolved / moot

| annex | items | live | resolved or moot | resolved by |
|---|---|---|---|---|
| motion-and-kernel | 18 | **15** | 3 | 031 (yaw sweep essay, twist-hold handoff essay), 033 (`encoder_pose_source.h` deleted) |
| comms | 12 | **12** | 0 | — |
| blocks-and-test | 10 | **9** | 1 | 028/032 (`test.ts` abort/clearestop "own fiber" already reworded to "NESTED") |
| tools-and-tests | 13 | **2** | 11 | 034 (items 1,2,3,4,7,9,10,11,12,13); item 5 moot — `tools/camproc.py` deleted |
| **total** | **53** | **38** | **15** | |

Several "live" items are **live at reduced scope** — 031/033 already cut
the block, but archaeology remains. Those are called out per ticket.
Notable reductions: `motion_engine.h`'s header is 72 lines, not the 120
the annex measured; `shims.cpp`'s `deliverStopNow()` essay was absorbed
into `Rig::softStop()` by 033 and *replaced* by fresh sprint-033
narration at the same spot; `setKernelValue()`'s per-case commentary
survives only for the `kConfigAccessors` rows, the ten shaping ordinals
having moved to `kLimitsFields`.

The two live tools-and-tests items are:
- `tools/camlink.py` module docstring — a 15-line sprint-029 narrative
  whose replacement text from the annex no longer applies (it cites
  `ensure_registered()`, which the same narrative says was deleted; the
  API is `register()` / `_register_one()` now). Boil down the narrative;
  do **not** paste the annex's replacement.
- `tests/host/test_kernel_harness.py` — `compile_shared_lib`'s
  sprint-017-ticket-009 paragraph, verbatim as the annex describes it.

### The sixteen factual errors: live / resolved

| # | claim | status | evidence |
|---|---|---|---|
| 1 | `differential_drive.{h,cpp}` file names | **LIVE, narrowed** | `core/diffdrive.h:1` and `core/diffdrive.cpp:1` self-name wrongly. Lines 3 of each, and `src/DESIGN.md`'s and `docs/design/specification.md`'s references, name the **upstream** vendored path correctly — leave those alone. |
| 2 | RUN drop count is "ordinal 30" | RESOLVED (033) | `protocol.h` now reads "diagValue() has no ordinal 30 at all"; `src/DESIGN.md` §"Before this consolidation" documents the correction. |
| 3 | `vMaxMmS_`/`brakeFrac_` "not consulted by anything yet" | MOOT (031) | No such text anywhere in `motion/`. |
| 4 | goToWorld "capped-curvature" | RESOLVED | No occurrence in `src/` or `docs/design/`. |
| 5 | `shims.cpp` "MOVE ENGINE … lives HERE" | **LIVE** | Header still lists MOVE ENGINE among the pieces "this file … adds"; the engine is `motion/motion_engine.{h,cpp}` and `shims.cpp` holds a `MotionEngine engine` member plus forwards. |
| 6 | streaks "exposed via ordinal 27" | RESOLVED | `nezha_port.h`'s ordinal-27 sentence sits on `rebaselineCount_`, and `shims.cpp case 27` returns the left+right rebaseline sum. Optional clarity: the streak fields cite no ordinal (21/22). |
| 7 | handlers "run on their own fiber" / MessageBus | **PART LIVE** | `test/test.ts` RESOLVED — already says "dispatches abort/clearestop reentrantly, NESTED inside the running". `src/blocks/run.ts` still carries "not raised as a MessageBus event" archaeology (the positive claim above it is already correct). |
| 8 | "ANY I2C from a RUN handler hangs the board" | **LIVE** | `test/test.ts` "uBit.i2c transaction issued from a RUN handler hangs the board", in the same file whose handlers do OTOS I2C. |
| 9 | `Protocol::formatDiag()` | RESOLVED (033) | No occurrence in `src/`. |
| 10 | "MessageBus RUN bridge / `runSlots_` / listener receives an integer" | **LIVE** | `comms/wire_adapter.h` "protocol.cpp's own MessageBus RUN bridge (runSlots_/handleRun())"; `comms/run_queue.h` "The consumer is a MessageBus listener that receives an integer"; `comms/emit_queue.h` "hands a MessageBus listener a slot number to read later"; `src/DESIGN.md` "protocol.cpp's MessageBus RUN bridge". Truth: `runQueue_` + `RunBridge`/`dispatchJob()` on the same fiber. |
| 11 | two-fiber / TS-fiber writer model | RESOLVED (033) | No "two fibers"/"TS fiber" writer claim survives in `comms/`; `src/DESIGN.md` describes the deletion correctly. |
| 12 | `kVersion` "1.0.10", drift-tested against pxt.json | **LIVE** | `comms/wire_handler.cpp` still says so; `protocol.cpp` declares `kVersion = "unbaked"` and the drift test asserts it is *not* pxt.json's. |
| 13 | "3 s same-text dedupe" | **PART LIVE** | `src/DESIGN.md` RESOLVED (400 ms). Still live in `comms/run_queue.h`: "The 3 s same-text suppression that sat in front of it". |
| 14 | retired radio addresses | **LIVE** | `test/test.ts` "still lands on channel 3 rather than vevov's 4" (tovez is 55/108, vevov 37/43); `src/blocks/run.ts` "and group 10" (group is deploy-injected too). 034 fixed the `tests/`, `make_deploy.py`, `tools/DESIGN.md` and `radio_transport.h` instances only. |
| 15 | cites a link-hang issue as live | **LIVE** | `test/test.ts` cites `clasi/issues/cleartext-run-hangs-the-link-under-...`; that file is at `clasi/sprints/done/027-…/issues/done/cleartext-run-hangs-the-link-under-active-telemetry.md` — closed, and the cited path no longer resolves. |
| 16 | "every read here is a live I2C burst" | **LIVE** | `blocks/world.ts`; `worldX/worldY/worldHeading`/`worldTrackingReady` are `otosGet` cache reads. |

**11 rows carry live work; 6 are resolved or moot** (rows 7 and 13 are
each part-live, counted as live).

### Two factual errors found by this pass, not in the review's sixteen

Carry both — they are the same defect class and were found by the same
method:

1. **`comms/wire_handler.h` contradicts itself about `gapOutstanding_`.**
   Two comment blocks assert it "is GONE, 2026-08-26" and "was DELETED
   2026-08-26 (S8.5)" while the file **declares `bool gapOutstanding_ =
   false;`** further down and `wire_handler.cpp` calls
   `emitReminderIfStalled()`. A reader cannot tell which is true
   without reading the whole file. (Comment-only fix: state what the
   field does today. Do **not** delete the field.)
2. **`src/DESIGN.md` says `kMaxPayloadBytes` is "still 200".** It is
   `240` (`radio_transport.h`). §10 of the same document states 240
   correctly, so the document contradicts itself. This is CM-10's row
   (g), which review §5's sixteen-row table omitted.

### Capture citations: track-or-relocate, re-derived

`.gitignore` ignores `captures/*` **and** `reports/`, so a tracked
report is not an option: `reports/` is out of git entirely. **464 files
under `captures/` are already force-tracked** — that is the established
precedent (alongside `docs/code-review/`), so `git add -f` is the
remedy, and the `reports/*.md` alternative the 2026-09-03 brief offers
is not available.

The review's "six untracked directories" no longer describes the tree:
every `captures/` citation it named from `motion_engine.{h,cpp}` was
rewritten away by sprint 031, and several directories have been
force-added since. The current set of **all** `captures/` paths cited
from `src/` (including `src/DESIGN.md`), with status:

| cited directory | cited from | on disk | tracked | action |
|---|---|---|---|---|
| `gopiv-profile-sweep-20260901/` | `DESIGN.md`, `platform/nezha_port.cpp` | yes, 31 files, 240K | **0** | `git add -f` the whole directory — all JSON/`.py` |
| `motion-profile-probe-20260901/` | `DESIGN.md` | yes, 2 files, 12K | **0** | `git add -f` the whole directory |
| `tigez-cal-20260830/` | `platform/nezha_port.cpp` | yes, 21 files, 2.6M | **0** | track the small evidence only (`notes.md` 8.7K, `log.jsonl` 4.4K, `radio-txcount-diagnostic.patch` 4.7K, `fieldtour5.log.jsonl` 10K); leave the 100–460K JSON blobs untracked; repoint the citation at `notes.md` |
| `tovez-wifi-20260902/` | `DESIGN.md` | **NO — does not exist** | n/a | the same sentence already cites the tracked `docs/knowledge/2026-09-02-wifi-transport-tovez.md`; drop the dangling `captures/` path and keep the tracked doc |
| `tovez-taper-20260829/variants.json` | `shims.cpp` | yes | **tracked** | none (only `__pycache__/` is untracked) |
| `bench-acceptance-029-20260904c/`, `…-20260904d/`, `session-b-20260905/`, `gopiv-floor70-20260829/`, `gopiv-frozen-encoder-fix-20260902/`, `tigez-radio-retest-20260902/` | `DESIGN.md`, `core/diffdrive.cpp`, `motion/segment.h`, `platform/nezha_port.cpp`, `shims.cpp` | yes | **fully tracked** | none |

So: **three `git add -f` operations and one citation repoint**, not six
relocations. The one text edit in `platform/nezha_port.cpp` and the one
in `src/DESIGN.md` are owned by the tickets that own those files, not
by the tracking ticket — see the ticket notes.

## Related Issues

- [`code-review/comment-work-order-factual-fixes-untracked-citations.md`](../../issues/code-review/comment-work-order-factual-fixes-untracked-citations.md)

## Test Strategy

Every ticket is verifiable **host-side, no hardware**. There is no
behaviour change to test, so the suite's job here is to prove that
nothing changed: comment edits break builds and pinned tests, and those
are the failures to catch.

**Scoped foreground runs per ticket** (never `run_in_background`). The
source-pin family under `tests/host/` is what comment edits actually
break, because those tests match source text:

    uv run pytest tests/host/test_archaeology_marker_budget.py \
                  tests/host/test_wire_constants_drift.py \
                  tests/host/test_typescript_typecheck.py \
                  tests/host/test_block_toolbox_order.py \
                  tests/host/ -k source_pin

Each ticket names the subset it must run. The C++ tickets additionally
run `tests/host/test_cxx11_syntax_gate.py` and the kernel harness,
since a mangled `/* */` or a stray `*/` inside an edited block turns a
comment edit into a compile error.

**The build gate is the team-lead's desk firmware build after the last
ticket.** The host suite compiles the portable C++ and the TypeScript
type-check gate covers `blocks/*.ts` and `test/*.ts`, but neither links
the `pxt.h`-bound translation units, and a comment edit in a
`pxt.h`-bound file can still break a real build through a mangled
delimiter or a disturbed `//%` pragma. No separate build-checkpoint
ticket is scheduled; the team-lead runs the desk build once, after
ticket 008, and that build is this sprint's acceptance for "no
behaviour change".

**The no-op rule, binding on every ticket.** A replacement whose
premise has changed is a **recorded no-op**, never forced. If the code
no longer says what the annex quotes, or the annex's replacement text
would itself now be false (the `tools/camlink.py` item is exactly this
case), write the item down as a no-op with the reason in the ticket's
completion notes and move on. Fabricating a fit is the failure mode
this sprint exists to stop, not a way to close an item.

**Two repo rules bind every comment edit here:**

- `.claude/rules/measurement-citations.md` — a boil-down must **not**
  delete the artifact path from a `MEASURED` claim. The board, the
  date and the capture path survive the cut; the narrative around them
  is what goes. A boiled-down `MEASURED` line with no artifact left in
  it is a regression, not a cleanup.
- `.claude/rules/no-units-in-identifiers.md` — units live in trailing
  `// [unit]` comments, not in names. **This sprint renames nothing**
  (CH-04 is triage #24 and the motion-profile design's ticket 3, both
  out of scope here). Never delete a trailing `// [mm]`, `// [ms]`,
  `// [counts/s]` to lower a ratio: the ratchet's counting rule does
  not count them, so there is no pressure to, and doing so destroys the
  house style the rule exists to protect.

## Architecture

**Sizing: Compact** — one changed module (`tests/host/
test_archaeology_marker_budget.py` gains a second, independent
ratchet), no new cross-module dependency, no dependency-direction
change, no data-model change; everything else this sprint touches is
comment and documentation text with no behaviour change. The
trivial/small tier was the other candidate — the borderline is real,
since a second assertion plus a baseline table inside an existing test
module is a small thing — and per the effort-decision rule the heavier
of two adjacent tiers wins a borderline call, so this is planned as
Compact: full section structure, no diagrams, self-review scoped to the
one module. No diagram is warranted: nothing new is composed, and the
one changed module has exactly one dependency (the filesystem under
`src/`) that it already has.

### What Changed

**`tests/host/test_archaeology_marker_budget.py` — one new ratchet
alongside the existing one.** The module today holds a single
responsibility: refuse a regression in *archaeology markers* (sprint
numbers, ticket numbers, finding IDs, `.md` filenames) across
project-owned `src/`, against a hand-reviewed `_BUDGET` that only
ratchets down. This sprint adds a second measurement over the same file
set — *comment volume*, as comment lines per code line, per file —
enforced against a per-file baseline table with the same
ratchets-down-only discipline, and lowers the existing `_BUDGET` from
388 to the post-cleanup count.

The two ratchets share a file walk and an exclusion set and nothing
else. They are deliberately separate assertions with separate baselines
because they catch different regressions: the marker ratchet catches
*archaeology* (which the review says the new growth is not — the new
comments cite dates and capture paths, not sprint numbers), and the
volume ratchet catches *length*. A single fused metric would let one
mask the other, which is exactly how the growth between the 08-26 and
09-02 reviews went unnoticed.

Two decisions inside the new ratchet are load-bearing and are recorded
in the module docstring:

- **Counting rule** as stated in the Verification pass section: `//`
  and not `//%`; JSDoc uncounted; trailing comments uncounted; vendored
  kernel excluded.
- **Per-file baselines, not a blanket cap.** A blanket 2.0 would fail
  `core/fiber_identity.h` (7 code lines) forever while letting
  `comms/wire_adapter.h` (5.46) sit at 1.99 unchallenged. The table
  records each file's measured value and the assertion is per file.

**`docs/code-review/guidelines.md` — anti-patterns 6 and 7 appended**
to the existing list of five, in the established format (name, why,
concrete example from the tree).

**Everything else — comment and documentation text only.** No
signature, no control flow, no build input, no wire field, no config
ordinal changes anywhere in this sprint.

### Why

The 2017-vintage lesson this repo has now learned twice, recorded in
the existing module's own docstring: sprint 009 cut ~470 comment lines
and by sprint 013 every file it touched had grown back past its
pre-cleanup count. A cleanup with no write-time rule behind it does not
hold. The existing ratchet was the write-time rule for archaeology
markers, and it worked — 356 against a 388 budget, no regression. The
growth that this sprint cleans up took a shape the existing ratchet
does not measure. Extending the same mechanism to the new shape is the
minimum change that makes this cleanup hold, and it is why the ratchet
is ticket 001: every later ticket in the sprint can then watch its own
work land against it.

### Impact on Existing Components

**None on production code** — no `src/` behaviour changes, so no
component's interface, dependencies or contract moves.

On `tests/host/test_archaeology_marker_budget.py`: additive. The
existing `test_archaeology_marker_count_is_within_budget` keeps its
name, its regex, its exclusion set and its semantics; only `_BUDGET`'s
value drops. The new test is a sibling function in the same module.
Nothing imports this module (it is a leaf test), so there is no
downstream to break.

One second-order effect worth naming: the new ratchet exerts pressure
on future authors to write shorter comments in project-owned `src/`.
That pressure is the point, and the counting rule is designed so it can
never be relieved by deleting a unit annotation, a `//%` pragma, or a
JSDoc block — the three things in this codebase that look like comments
and are not.

### Design Rationale

**Decision: two separate assertions with two separate baselines, in one
module, rather than a new module or one fused metric.**

- *Context*: the module already owns "refuse a comment-quality
  regression across project-owned `src/`, measured from file text, with
  a reviewed baseline that ratchets down only". Both ratchets are
  instances of that one responsibility.
- *Alternatives considered*: (a) a new
  `test_comment_volume_budget.py` module — rejected: it would duplicate
  the file walk, the `_SOURCE_SUFFIXES` list and the vendored-kernel
  exclusion, and the two would drift the first time `src/` gained a
  subdirectory, which is the exact failure the review found in
  `src/DESIGN.md`'s hand-synchronised lists. (b) One fused
  "comment-quality score" — rejected: it lets a marker regression hide
  behind a volume improvement, and a failure message from it would not
  tell an author what to fix.
- *Consequences*: the module keeps a one-sentence purpose ("refuse
  comment-quality regressions in project-owned `src/` against reviewed
  baselines") with no "and", so it still passes the cohesion test. Its
  docstring grows, which is ironic but correct — the counting rule is a
  decision a future reader cannot recover from the code.

**Decision: `git add -f` rather than a `reports/*.md` relocation for
the untracked capture citations.** The 2026-09-03 brief offered both.
Verification killed the second: `.gitignore` ignores `reports/`
entirely, so a "tracked `reports/*.md`" does not exist in this repo,
while 464 files under `captures/` are already force-tracked and are the
established precedent. The one directory too large to track wholesale
(`tigez-cal-20260830`, 2.6M of JSON) gets its small evidence files
tracked and the citation repointed at `notes.md`.

### Migration Concerns

None. No data, no schema, no wire format, no persisted state. The
ratchet baselines are checked-in constants in a test file; lowering
them later is a reviewed edit, exactly as the existing `_BUDGET`
already works. Deployment sequencing is the ticket order alone.

### Open Questions

None blocking. One judgement call is delegated to ticket 008 rather
than fixed here: **how far to lower each per-file baseline** after the
cleanup lands. Ticket 001 seeds the table from today's measurement (so
the ratchet is live and watching while tickets 002–007 work); ticket
008 re-measures and tightens to the achieved values. If a file's
achieved ratio is barely under its seed, ticket 008 records that rather
than inventing a stretch target — a ratchet set below what the tree
actually achieves fails the next unrelated sprint for no reason.

## Use Cases

### SUC-001: A reader trusts a comment in `src/`

Parent: project-quality (no parent UC — this is an internal-quality
sprint with no student- or operator-visible behaviour).

- **Actor**: A developer or agent reading `src/` to make a change.
- **Preconditions**: The file carries comments asserting facts about
  the current code.
- **Main Flow**: The reader reads a comment; acts on what it says.
- **Postconditions**: The claim held. Where a comment cites a
  `MEASURED` result, the named artifact resolves in a fresh clone.
- **Acceptance Criteria**:
  - [ ] Every factual error classified **live** in the Verification
        pass is corrected, and each **resolved/moot** row is recorded
        as a no-op naming the sprint that resolved it.
  - [ ] Every `captures/` path cited from `src/` resolves in a fresh
        clone.
  - [ ] `comms/wire_handler.h` no longer both declares
        `gapOutstanding_` and says it was deleted.

### SUC-002: The cleanup holds after the sprint closes

Parent: project-quality.

- **Actor**: A future author adding comments to project-owned `src/`.
- **Preconditions**: The sprint's cleanup has landed and baselines are
  recorded.
- **Main Flow**: The author adds comment lines to a `src/` file and
  runs the host suite.
- **Postconditions**: A regression past that file's recorded ratio
  fails, naming the file and both numbers; a regression in archaeology
  markers fails as it already does.
- **Acceptance Criteria**:
  - [ ] `test_archaeology_marker_budget.py` holds a per-file
        comment-volume ratchet seeded from measurement, and its
        docstring states the counting rule including why `//%` and
        JSDoc are excluded.
  - [ ] `_BUDGET` is lowered to at most the post-cleanup marker count.
  - [ ] `docs/code-review/guidelines.md` lists seven anti-patterns.

## GitHub Issues

(GitHub issues linked to this sprint's tickets. Format: `owner/repo#N`.)

## Definition of Ready

Before tickets can be created, all of the following must be true:

- [x] Sprint planning document is complete (sprint.md, including its
      Architecture and Use Cases sections) — 2026-09-06
- [x] Architecture review passed (or skipped, for changes with no
      architectural impact) — **passed** 2026-09-06; Compact sizing,
      self-review scoped to the one changed module
- [ ] Stakeholder has approved the sprint plan — not recorded by the
      planner; the team-lead owns this gate

## Tickets

Grouped by **file family**, so no two tickets edit the same file.
Ticket 001 is the foundation — it installs the measuring instrument, so
002-007 can each watch their own work land against it. 008 runs last
because it re-seeds both ratchets from the post-cleanup tree and
reconciles `src/DESIGN.md` against what 002-007 actually wrote.

| # | Title | Files owned | Depends On |
|---|-------|-------------|------------|
| 001 | Comment-volume ratchet and guidelines anti-patterns 6 and 7 | `tests/host/test_archaeology_marker_budget.py`, `docs/code-review/guidelines.md` | — |
| 002 | motion/ and core/ boil-down and factual fixes | `src/motion/*`, `src/core/*` (incl. `diffdrive.{h,cpp}` line 1 only) | 001 |
| 003 | platform/ and shims.cpp boil-down and factual fixes | `src/platform/*`, `src/shims.cpp` | 001 |
| 004 | comms transports, queues and Protocol boil-down and factual fixes | `src/comms/{radio,serial}_transport.*`, `protocol.*`, `run_queue.h`, `emit_queue.h`, `run_bridge.*`, `transport_sink.h`, `config_fields.h` | 001 |
| 005 | comms wire layer boil-down and factual fixes | `src/comms/wire_handler.{h,cpp}`, `src/comms/wire_adapter.{h,cpp}` | 001 |
| 006 | blocks and test-program boil-down and factual fixes | `src/blocks/*.ts`, `test/test.ts` | 001 |
| 007 | Track the cited capture directories and finish the tools/tests hygiene items | `captures/**` (`git add -f`), `tools/camlink.py`, `tests/host/test_kernel_harness.py` | 001 |
| 008 | `src/DESIGN.md` truth pass, re-measure and tighten both ratchets | `src/DESIGN.md`, `tests/host/test_archaeology_marker_budget.py`, `sprint.md` | 001-007 |

Tickets execute serially in the order listed.

**Two cross-ticket handoffs**, both deliberate and both recorded in the
tickets themselves — the file-family rule means the text edit and the
tracking operation land in different tickets:

- Ticket **003** repoints `platform/nezha_port.cpp`'s citation at
  `captures/tigez-cal-20260830/notes.md`; ticket **007** force-tracks
  that file and verifies the path resolves.
- Ticket **008** drops `src/DESIGN.md`'s dangling
  `captures/tovez-wifi-20260902/` path; ticket **007** verifies there
  is nothing to track and that the tracked
  `docs/knowledge/2026-09-02-wifi-transport-tovez.md` citation carries
  the claim.

**Gate.** After ticket 008 and before `close_sprint`, the **team-lead
runs a desk firmware build**. No separate build-checkpoint ticket is
scheduled. See Test Strategy for why the host suite alone is not
sufficient for a comment-only sprint touching `pxt.h`-bound files.
