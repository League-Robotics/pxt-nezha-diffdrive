---
id: "006"
title: "blocks and test-program boil-down and factual fixes"
status: open
use-cases: [SUC-001]
depends-on: ["001"]
github-issue: ""
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

- [ ] Annex rows 1-8 and 10 applied, re-anchored by quoted content;
      row 9 handled per its note; every no-op recorded with its reason.
- [ ] All five factual fixes applied; BT-08 verified and either fixed
      or recorded.
- [ ] `git diff` touches **no** `//%` line and **no** `/** ... */`
      JSDoc block in any `src/blocks/*.ts` file.
- [ ] `tests/host/test_block_toolbox_order.py` passes.
- [ ] `tests/host/test_typescript_typecheck.py` passes.
- [ ] `world.ts` distinguishes the cache reads from the five bus-touching
      functions, and the same-fiber constraint survives, scoped to the
      latter.
- [ ] `setupRadio`'s `group: number = 10` default is unchanged.
- [ ] Every surviving `MEASURED` / `Capture:` claim names an artifact;
      any that does not resolve is reported to ticket 007, not deleted.
- [ ] No trailing `// [unit]` deleted, no identifier renamed, no line
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
