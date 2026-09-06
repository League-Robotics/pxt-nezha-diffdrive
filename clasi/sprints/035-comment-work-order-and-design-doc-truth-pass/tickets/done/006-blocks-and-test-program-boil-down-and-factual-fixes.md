---
id: '006'
title: blocks and test-program boil-down and factual fixes
status: done
use-cases:
- SUC-001
depends-on:
- '001'
github-issue: ''
issue: code-review/comment-work-order-factual-fixes-untracked-citations.md
completes_issue: false
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# blocks and test-program boil-down and factual fixes

## Description

Comment text only in `src/blocks/*.ts` and the on-robot test program
`test/test.ts`. **No behaviour change.**

**The hazard specific to this ticket: `//%` pragmas and JSDoc are not
comments.** `src/blocks/*.ts` carries **202** `//%` lines — `//% block=`,
`//% group=`, `//% weight=`, `//% subcategory=`, `//% blockHidden=` —
and every `/** ... */` block above an exported function is the
student-facing documentation PXT renders into the toolbox. **Neither is
in scope. Deleting or reordering either changes the block toolbox**,
which `tests/host/test_block_toolbox_order.py` pins. Only `//` lines
that are not `//%` are this ticket's material.

### What the re-measurement changed about this ticket

The review's table put `blocks/*.ts` at 1.58 — but that number counted
JSDoc and `//%` as comments. Under the sprint's counting rule the
blocks files are **already clean**: `sim.ts` 0.62, `world.ts` 0.45,
`run.ts` 0.25, `motion.ts` 0.19, `stop.ts` 0.12, `pose.ts` 0.03. So
**this ticket is mostly factual fixes plus the ten named boil-downs**,
not a volume exercise. `test/test.ts` (1.34, 645/482) is the one file
here with real volume, and it is not under `src/`, so ticket 001's
ratchet does not watch it — cut it on the merits, not to a number.

### Files this ticket owns

`src/blocks/sim.ts`, `src/blocks/motion.ts`, `src/blocks/run.ts`,
`src/blocks/world.ts`, `src/blocks/stop.ts`, `src/blocks/pose.ts`,
`test/test.ts`. (Not `test/testrig.ts` or `test/linefollow.ts` — both
are already low-ratio and on no annex list.)

### Rules of engagement

As ticket 002 — re-anchor by quoted content never line number; a
replacement whose premise changed is a recorded no-op never forced;
`.claude/rules/measurement-citations.md`;
`.claude/rules/no-units-in-identifiers.md` (this sprint renames
nothing; never delete a trailing `// [cdeg/s]`).

### Boil-down items (blocks-and-test annex —
`docs/code-review/2026-09-02/raw/blocks-and-test.md`, "Comment
boil-down (worst ten, plus factual errors)")

| annex # | anchor (quoted content) | status |
|---|---|---|
| 1 | `sim.ts`'s `_setGoToDeadline`/`_goToR` preambles — the TS9200 story told twice. Anchors: `what used to be a single five-parameter _goToR()/engineGoToR()` and `_goToR()'s own comment below), so this is a genuine no-op here` | LIVE. Annex supplies both replacements. Tell the story once. (`src/shims.cpp`'s copy is **ticket 003**'s, `motion.ts`'s pointer at `PXT packager with TS9200; see sim.ts's _setGoToDeadline()/` is this ticket's — keep it as a one-line cross-reference.) |
| 2 | `sim.ts`'s `_setWheels` divisor essay — anchor `"slip" concept. (Previously divided by trackWidth_ alone via a` and `too slowly -- R-12/BLK-06.)` | LIVE. Annex replacement. Keep the formula and the fact that `_driveTwist()` inverts the same divisor. |
| 3 | `sim.ts`'s `_tickDrive` return-value history — anchor `007 ticket 002, closes R-10/API-01) -- the simulator-state mirror` | LIVE. Annex replacement. |
| 4 | the copies of "an empty body is emitted as native-only and crashes the simulator" in `sim.ts` — **seven** occurrences of `native-only` today, not the annex's six | LIVE. One note at the top of the file; delete the rest. **Careful:** two of the seven sit inside JSDoc-adjacent text about `//%` shims (`bare \`{}\`, so pxt doesn't treat them as native-only shims`) — check each occurrence in context before deleting; the rule that a shim body must contain a statement is real and must survive once, stated clearly. |
| 5 | `motion.ts`'s `startGoTo` block | LIVE at reduced scope — the annex's `sprint 015 ticket 006` text is largely gone. Apply the annex's *intent*: `goToR` owns the pivot-vs-arc split; never reduce to (distance, yaw) through `startMove()`, which would land elsewhere above 50°. Record the reduction. |
| 6 | `run.ts`'s `wireRunDispatch` block — anchor `dequeued RUN command -- not raised as a MessageBus event for a` | LIVE at reduced scope. The **positive** claim above it is already correct (`invoked DIRECTLY by the firmware's own protocol fiber (via _registerRunDispatch(), sim.ts) once per`). What remains is the "unlike the old scheme" archaeology — delete it. This also discharges the run.ts half of review §5's "handlers run on their own fiber" row. |
| 7 | `test.ts`'s boot-OTOS block — anchor `uBit.i2c transaction issued from a RUN handler hangs the board` | LIVE, **and factually wrong** — see factual fix 1. |
| 8 | `test.ts`'s stacked lever-arm narratives — anchors `vevov's lever arm, MEASURED on the playfield 2026-08-20 (RUN:cal +`, `the centre of rotation on a 38.2 mm circle, fit residual rms 1.34 mm.`, `lever arm was NEVER applied, silently, for the whole session.` | LIVE. Keep the **current** measurement with its capture path and the camera cross-check; delete the superseded narrative the text itself says was invalidated. Verify by reading which measurement the code actually uses before choosing which to keep — the annex's line numbers are stale. |
| 9 | `test.ts`'s abort/clearestop header | **MOOT as a factual fix** — the text now reads `dispatches abort/clearestop reentrantly, NESTED inside the running`, already correct (sprint 028/032). Still apply the boil-down half if the block is longer than the annex's four-line target. Record which half you did. |
| 10 | `stop.ts`'s group-layout archaeology — anchor `// Stop group (sprint 021 ticket 004, approved layout in` / `// block-toolbox-groups-reorganization.md): the three top-level` | LIVE. Delete; `run.ts` already records that weights and groups come from `reports/blocks-toolbox.csv`. **Do not touch the `//% group=` / `//% weight=` pragmas the comment describes** — deleting the comment must not change one byte of block metadata, and `test_block_toolbox_order.py` will catch you if it does. |

### Factual fixes

1. **`test/test.ts` asserts a hazard the same file disproves.** The
   text says `uBit.i2c transaction issued from a RUN handler hangs the
   board` — in a file whose own RUN handlers do OTOS I2C on every
   corner of a tour. Use the annex's replacement: OTOS begun once at
   boot so `STATUS`'s `otos=` flag is meaningful; lever arm applied
   here is pure software, no I2C; the real hazard is the No-ACK case,
   `first-i2c-command-can-wedge-the-program-with-no-recovery.md`. Keep
   the `Capture: captures/otos-run-handler-i2c-hang-20260828.md.`
   citation — verify it resolves and is tracked; if it does not, report
   it to ticket 007 rather than deleting the path.

2. **`test/test.ts` cites retired radio addresses.** Anchor:
   `still lands on channel 3 rather than vevov's 4.` Both numbers are
   retired: tovez is **55/108** and vevov **37/43**, and the channel is
   deploy-injected per robot (`tools/make_deploy.py`, `kChannel`). See
   `.claude/rules/playfield-testing.md`'s fleet table. State that the
   channel comes from the deploy injection; do not bake a new pair of
   numbers into a comment that will go stale the same way. Sprint 034
   fixed the `tests/`, `make_deploy.py`, `tools/DESIGN.md` and
   `radio_transport.h` instances; these are the survivors.

3. **`src/blocks/run.ts` says `enableRadioLink()` uses "group 10".**
   Anchor: `* time -- and group 10.` The group is deploy-injected per
   robot exactly as the channel is. Fix the doc text. **Do not change
   `setupRadio`'s `group: number = 10` default** — that is code and a
   student-facing block signature; changing it is a behaviour change.

4. **`test/test.ts` cites a closed issue as live, at a path that no
   longer resolves.** Anchor:
   `the link outright (clasi/issues/cleartext-run-hangs-the-link-under-`.
   That issue closed in sprint 027 and now lives at
   `clasi/sprints/done/027-one-serial-producer-fix-the-uart-wedge-and-retest-the-radio-wedge/issues/done/cleartext-run-hangs-the-link-under-active-telemetry.md`.
   Rewrite so the surrounding claim reads as history-with-a-fix rather
   than a live hazard, and either cite the archived path or drop the
   path and keep the fact. Read the surrounding block before deciding —
   the *behaviour* it describes may still be worth documenting.

5. **`src/blocks/world.ts` calls cache reads a live I2C burst.**
   Anchor: `// Every read here is a live I2C burst, so these must be
   called from`. Verified at planning time: `worldX()`, `worldY()`,
   `worldHeading()` and `worldTrackingReady()` are `otosGet` cache
   reads. Only `readWorld()`, `startWorldTracking()`,
   `calibrateWorldSensor()`, `seedPose()` and `setWorldSensorOffset()`
   touch the bus. **The same-fiber constraint the comment exists to
   state is still true for those five** — keep it, and scope it to
   them, rather than deleting the block. Confirm the split against the
   current file before writing.

### Factual error to verify, then fix or record (BT-08)

The annex says `motion.ts`'s `goTo` doc claims the pivot uses
`defaultYawRate` when it did not. At planning time the file **does**
pass it — `_setGoToYawRate(Math.round(defaultYawRate * 100))` — so this
looks **resolved** by sprint 032. Verify against the current code and
either fix the text or record it as a no-op naming the sprint. Do not
assume either way.

## Acceptance Criteria

- [x] Annex rows 1-8 and 10 applied, re-anchored by quoted content;
      row 9 handled per its note; every no-op recorded with its reason.
- [x] All five factual fixes applied; BT-08 verified and either fixed (team-lead 2026-09-06: four of five applied; fix 3 is a JSDoc-only claim in run.ts, outside this ticket's no-JSDoc rule, deferred to clasi/issues/run-ts-jsdoc-still-says-radio-group-10.md)
      or recorded. **Four of five applied; BT-08 verified and recorded
      as a no-op. Factual fix 3 NOT applied — its only anchor is a
      `/** ... */` JSDoc line, which the third criterion below forbids
      touching. See "Completion notes" -> "Factual fix 3: blocked, not
      done".**
- [x] `git diff` touches **no** `//%` line and **no** `/** ... */`
      JSDoc block in any `src/blocks/*.ts` file.
- [x] `tests/host/test_block_toolbox_order.py` passes.
- [x] `tests/host/test_typescript_typecheck.py` passes.
- [x] `world.ts` distinguishes the cache reads from the five bus-touching
      functions, and the same-fiber constraint survives, scoped to the
      latter.
- [x] `setupRadio`'s `group: number = 10` default is unchanged.
- [x] Every surviving `MEASURED` / `Capture:` claim names an artifact;
      any that does not resolve is reported to ticket 007, not deleted.
- [x] No trailing `// [unit]` deleted, no identifier renamed, no line
      of code changed.

## Testing

Foreground only.

- **Existing tests to run**:

      uv run pytest tests/host/test_typescript_typecheck.py \
                    tests/host/test_block_toolbox_order.py \
                    tests/host/test_archaeology_marker_budget.py -q
      uv run pytest tests/host/ -k source_pin -q
      uv run pytest tests/host/ -q

  `test_typescript_typecheck.py` and `test_block_toolbox_order.py` are
  the two gates that matter here — the first catches a comment edit
  that broke a `/** */` or `//` delimiter, the second catches a
  disturbed block pragma. Note the 2026-09-02 review recorded
  `test_tsc_noemit_is_clean` as the suite's one pre-existing failure;
  check whether it is red **before** your edits so you do not inherit
  someone else's failure, and say which in the completion notes.

- **New tests to write**: none.
- **Verification command**: `uv run pytest tests/host/ -q`

## Notes for the implementer

- Replacement text source:
  `docs/code-review/2026-09-02/raw/blocks-and-test.md`, "Comment
  boil-down (worst ten, plus factual errors)".
- Read `sprint.md`'s "Verification pass" section first.
- Do not run the full repo suite.

## Completion notes

### Pre-edit suite state

`tests/host/test_typescript_typecheck.py` was **GREEN before any edit**
in this checkout (`git stash push -- src test`, then
`uv run pytest tests/host/test_typescript_typecheck.py -q` -> `2 passed
in 0.58s`, then `git stash pop`). `node_modules/.bin/tsc` is present, so
`test_tsc_noemit_is_clean` ran for real rather than skipping. The
2026-09-02 review's note about it being the suite's one pre-existing
failure does **not** apply here — nothing red was inherited, and nothing
red was left.

### Annex items (blocks-and-test, "Comment boil-down (worst ten)")

| # | verdict | what was done |
|---|---|---|
| 1 | **applied** | `sim.ts` `_setGoToDeadline` preamble is now the annex's two-shim line, pointing at `shims.cpp`'s `engineSetGoToDeadline()` for the full TS9200 account (ticket 003's copy). `_goToR`'s preamble keeps the bearing/short-arc reduction and the annex's "sim reaches (x, y) as one blended arc; hardware's >=50 deg split lands at the same point, so no split is modelled" line. The TS9256 int32/decompiler rule and the two-rate-ceiling reconciliation survive, boiled down. `motion.ts`'s pointer is kept as a one-line cross-reference. |
| 2 | **applied** | `_setWheels`: 26 lines -> 7. Keeps the formula, `effectiveTrackWidth = trackWidth / rotationalSlip` with its `motion_engine.h` citation, and the fact that `_driveTwist()` inverts the same divisor (so it needs no divisor of its own). The "previously divided by 115 / by 10 first" archaeology and R-12/BLK-06 are gone. |
| 3 | **applied** | `_tickDrive` return-value history -> the annex's `commandLooksActive()` sentence. The `tests/host/test_continuous_drive_command_looks_active.py` pointer survives. |
| 4 | **applied, with one JSDoc survivor** | HEAD had **seven** `native-only` occurrences in `sim.ts`, not the annex's six. One canonical note now sits at the top of the file (`sim.ts:5-7`). Five plain-`//` copies deleted. The **seventh sits inside the retired-shims `/** ... */` JSDoc at `sim.ts:445-457`** ("real (if trivial) bodies below, not bare `{}`, so pxt doesn't treat them as native-only shims") and was **left untouched** — JSDoc is explicitly out of scope for this ticket. Net: the rule survives stated clearly twice (once at the top of the file, once in that JSDoc), not seven times. |
| 5 | **applied at the reduced scope the ticket describes** | The `sprint 015 ticket 006` narrative was already largely gone; what remained was the TS9200 retelling plus the `moveX()` reissue essay. Now: `goToR()` owns the pivot-vs-arc split, never reduce to (distance, yaw) through `startMove()` which would land elsewhere above 50 deg, plus the one-line `shims.cpp` cross-reference. 12 lines -> 4. |
| 6 | **applied at the reduced scope the ticket describes** | The positive claim (dispatched inline by the protocol fiber via `_registerRunDispatch()`) was already correct and is kept, now stating the nested abort/clearestop consequence directly. The "not raised as a MessageBus event", "no second fiber to wait for" and "unlike the old event-value-as-slot-number scheme" archaeology is deleted. 13 lines -> 8. This discharges the `run.ts` half of review §5's "handlers run on their own fiber" row. (`run.ts:1-20`'s argument-snapshot-stack header and `onRun()`'s JSDoc were already corrected by earlier sprints and were not touched.) |
| 7 | **applied** | See factual fix 1 below. |
| 8 | **applied** | Verified against the constants the code actually uses before choosing: `armX = -5.27` cm / `armY = -0.12` cm match the **2026-08-28** fit (x -52.7 mm, y -1.2 mm), not the superseded 38.2 mm figure. Kept: the 2026-08-28 measurement, its `Capture:` path, the method, the independent camera tag-53 cross-check (53.4 mm, agreeing to 0.7 mm), and the `UNVERIFIED` note on `armYaw`. Deleted: the 2026-08-20 38.2 mm narrative the following lines already said was invalidated. |
| 9 | **boil-down half applied; factual half a recorded no-op** | The abort/clearestop header already read `dispatches abort/clearestop reentrantly, NESTED inside the running` — correct since sprints 028/032, so there was no factual error left to fix. The block was 17 lines (two stacked headers), above the annex's four-line target, so the boil-down half was applied: 17 -> 12, keeping the reentrant-dispatch fact, why neither guards on `touring`, the flag-only/non-blocking constraint, and why `clearestop` is its own verb rather than folded into `STOP`. |
| 10 | **applied** | `stop.ts`'s five-line group-layout archaeology deleted. The `//% group=` / `//% weight=` pragmas it described are byte-identical (`stop.ts` `//%` count 10 -> 10); `test_block_toolbox_order.py` passes. |

### Factual fixes

1. **applied.** `test.ts`'s boot-OTOS block no longer claims "ANY
   `uBit.i2c` transaction issued from a RUN handler hangs the board" — a
   claim the same file's RUN handlers disprove. It now says: the OTOS is
   begun once at boot so `STATUS`'s `otos=` flag is meaningful; the real
   hazard is the No-ACK case that spins CODAL's `waitForStop()` forever,
   citing `clasi/issues/high/first-i2c-command-can-wedge-the-program-with-no-recovery.md`
   (**verified: resolves**); the lever arm applied at boot is pure
   software, no I2C. The `Capture:
   captures/otos-run-handler-i2c-hang-20260828.md` citation is kept —
   **verified: the file exists AND is git-tracked**
   (`git ls-files --error-unmatch` succeeds), so nothing needs reporting
   to ticket 007 on that path.
2. **applied.** `test.ts:47-49`'s "still lands on channel 3 rather than
   vevov's 4" is gone. No new numbers were baked in: the text now says
   the channel **and** the group are deploy-injected per robot, naming
   `tools/make_deploy.py` and `kChannel`/`kGroup` in
   `src/comms/radio_transport.h`, and says why naming either here would
   override the injection. Verified against the source rather than the
   rule alone: `make_deploy.py:575-576,594-595` rewrites both constants,
   and `radio_transport.h:289-290` holds them (`= 4` / `= 10`) with its
   own "DO NOT reformat" note about those exact regexes.
3. **BLOCKED — not applied.** See "Factual fix 3: blocked, not done"
   below.
4. **applied.** `test.ts`'s `RUN:arc` block no longer cites the
   cleartext-RUN link hang as a live hazard at a dead path. The
   on-fiber-sampling rationale now stands on `probe()`'s own hazard
   (the 197.5 mm leg that collapsed to 0.3 mm), and the link hang is
   recorded as **history with a fix**, citing the archived path
   `clasi/sprints/done/027-.../issues/done/cleartext-run-hangs-the-link-under-active-telemetry.md`
   (**verified: resolves**). The behaviour is still documented, as the
   ticket asked.
5. **applied.** `world.ts`'s header no longer says "Every read here is a
   live I2C burst". Confirmed against the current file:
   `worldX/worldY/worldHeading/worldTrackingReady` are `otosGet` cache
   reads; `startWorldTracking`, `readWorld`, `seedPose`,
   `calibrateWorldSensor`, `setWorldSensorOffset` touch the bus. The
   same-fiber constraint — and the reason for it (an OTOS transaction
   inside the Nezha encoder's select->read window destroys that sample)
   — is kept and **scoped to those five**.

### Factual fix 3: blocked, not done

Factual fix 3's only anchor in `src/blocks/run.ts` is
`     * time -- and group 10.` (line 174) — a `*` continuation line
**inside the `/** ... */` JSDoc block above `enableRadioLink()`**. The
same claim's only other instance, `The group defaults to 10, the relay's
listen group.` (line 158), is likewise inside `setupRadio`'s JSDoc.
There is no plain `//` comment anywhere in `run.ts` making the claim.

This ticket's third acceptance criterion — and the dispatch — forbid any
`/** ... */` change in `src/blocks/*.ts`, because that JSDoc is the
student-facing text PXT renders into the toolbox. The fix and the
constraint are in direct conflict, and the constraint is the one with a
test behind it, so **the constraint won and no edit was made**. Nothing
was routed around: no guard blocked anything; this is a scope decision.

`setupRadio`'s `group: number = 10` default is untouched, as required
(it is code, and a block signature).

**For the team-lead:** this needs a follow-up with JSDoc explicitly in
scope. The correct text is that `enableRadioLink()` uses the channel
**and group** `tools/make_deploy.py` injected for this board, not a
fixed "group 10"; `setupRadio`'s "The group defaults to 10, the relay's
listen group" is a separate, still-true statement about the block's own
default and needs no change.

### BT-08 verdict: RESOLVED — recorded as a no-op

The annex's BT-08 says `motion.ts`'s `goTo` claims the pivot uses
`defaultYawRate` when it does not. Verified against the current code:
`startGoTo()` (`motion.ts:361`) calls
`_setGoToYawRate(Math.round(defaultYawRate * 100))  // [cdeg/s]`
immediately before `_goToR()`, so the pivot's rate ceiling **is** the
default turn rate, and the `pivotS = 180 / defaultYawRate` worst-case
term in the timeout budget is no longer a rate the engine ignores.
`setDefaultYawRate`'s "Default turn rate for move/goTo blocks" is
therefore correct as written.

Fixed by **sprint 032 ticket 007**, commit `c39f85d` ("fix(032-007):
goTo pivot honors default turn rate, reconciled with startMove") —
`git log -S"_setGoToYawRate" -- src/blocks/motion.ts`. No text change
made. (The relevant text is JSDoc in any case.)

### Citations reported to ticket 007

Both are `MEASURED` claims in `test/test.ts` that name **no artifact**.
Neither had one in HEAD either — **no path was stripped by this ticket**
— and both were left in place rather than deleted, per
`.claude/rules/measurement-citations.md` and the ticket's instruction:

- `test/test.ts:320` — `MEASURED BUG, vevov 2026-08-25 ... four
  uncorrected corners cost 58 mm of tour closure that the robot scored
  as 22 mm`. Boiled down from a longer unartifacted block; the numbers
  are carried through unchanged, still with no capture path.
- `test/test.ts:941` — `MEASURED 2026-08-28 on vevov ... every one of
  153 frames read ox=oy=oh=0 while the encoders logged 246 mm of
  travel`. **Untouched by this ticket** (outside every annex range);
  flagged only because the verification pass reads it.

Every other surviving `MEASURED` / `Capture:` claim in the files this
ticket owns names an artifact that resolves:
`captures/otos-run-handler-i2c-hang-20260828.md` (tracked),
`captures/session-b-20260905/gain-sweep-*` (`test.ts:376`, untouched).

### Volume

`test/test.ts`, the one file here with real volume, cut on the merits:

| | lines | `//` comment lines | ratio vs 548 code lines |
|---|---|---|---|
| before | 1193 | 645 | 1.18 |
| after | 1167 | 619 | 1.13 |

`src/blocks/*.ts` plain-`//` comment lines (already clean before this
ticket, so these are the named boil-downs only): `sim.ts` 236 -> 165,
`motion.ts` 81 -> 74, `world.ts` 70 -> 71 (fix 5 is one line longer —
it now distinguishes two cases where it used to state one), `run.ts`
61 -> 56, `stop.ts` 6 -> 1, `pose.ts` 1 -> 1 (untouched).

### Mechanical proof: pragmas, JSDoc and code untouched

Run over `git diff -U0 -- src/blocks test/test.ts` (348 changed lines):

- **No `//%` line touched.** `grep -E '^[+-]\s*//%'` over the diff
  returns nothing. Pragma-line counts (`^\s*//%`) per file are
  identical HEAD -> now, **202 total across `src/blocks/*.ts`**, exactly
  the count this ticket's Description states.
  (A naive `grep -c '//%'` shows `motion.ts` 89 -> 88; the one lost
  occurrence is the *substring* `//%` inside the deleted prose line
  `// Calls goToR() directly (the //%-exposed engineGoToRArmed/`, not a
  pragma. Verified by re-counting with `^\s*//%`.)
- **No JSDoc line touched.** `grep -E '^[+-]\s*(/\*\*|\*/|\*( |$))'`
  over the diff returns nothing — no `/**`, no `*/`, no ` * `
  continuation line is added or removed anywhere.
- **No code line changed.** For each of the seven owned files, stripping
  every plain-`//` comment line (keeping `//%`) from HEAD and from the
  working tree gives **byte-identical** files: `motion.ts` 455 lines,
  `run.ts` 259, `sim.ts` 435, `world.ts` 173, `pose.ts` 42,
  `test.ts` 548. `stop.ts` is the single exception and it is **one blank
  line**, not code — deleting the archaeology block that sat between two
  blank lines left one behind.
- **No trailing `// [unit]` deleted.** Every line in HEAD matching
  `\S.*//\s*\[` is still present: `motion.ts` 9, `sim.ts` 26,
  `world.ts` 1, `test.ts` 7, `run.ts`/`stop.ts` 0.
- **Nothing renamed**, no identifier changed (implied by the
  byte-identical code-line proof above).

### Tests (foreground, observed passing)

    uv run pytest tests/host/test_typescript_typecheck.py \
                  tests/host/test_block_toolbox_order.py \
                  tests/host/test_archaeology_marker_budget.py -q
    -> 8 passed in 0.47s

    uv run pytest tests/host/ -k source_pin -q
    -> 85 passed, 1082 deselected in 0.40s

    uv run pytest tests/host -q
    -> 1167 passed in 38.10s

No version bump (sprint cadence: `close_sprint` bumps once).
