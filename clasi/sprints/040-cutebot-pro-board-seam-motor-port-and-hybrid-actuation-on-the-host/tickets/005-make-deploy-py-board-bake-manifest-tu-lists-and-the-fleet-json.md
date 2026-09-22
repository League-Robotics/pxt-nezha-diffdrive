---
id: '005'
title: make_deploy.py board bake, manifest/TU lists, and the fleet JSON
status: in-progress
use-cases:
- SUC-001
depends-on:
- '001'
- '002'
- '004'
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# make_deploy.py board bake, manifest/TU lists, and the fleet JSON

## Description

Depends on ticket 001 (the `DIFFDRIVE_BOARD` seam and literal this
ticket's bake key selects), ticket 002 (`cutebot_port.{h,cpp}` must
exist to add to the file lists), and ticket 004 (the actuation-policy
file must exist too) — this ticket is the "wire everything up for a
real deploy" step, done last among the code tickets so every file it
needs to enumerate already exists.

Per `docs/design/cutebot-pro-support.md` §4 and §9's own Sprint 040
scope:

- `tools/make_deploy.py`: add `geometry.firmware_bake.board` as a new
  opt-in bake key (same opt-in convention as every other
  `firmware_bake` key — see `_read_robot_firmware_bake()`,
  `tools/make_deploy.py:1128-1150`, already read during architecture
  planning): `"nezha"` (default/absent) or `"cutebot-pro"`, injected
  into the scratch copy's `platform/board.h` literal via a new
  `_inject_board()` function following `_inject_motors()`'s exact
  shape (`tools/make_deploy.py:1246-1286`) — scratch-copy-only
  substitution, loud `sys.exit()` on an unrecognized value (**fail
  loudly on an unknown `board`**, per this sprint's hard constraint —
  do not silently fall back to Nezha for a typo).
- Update `EXPECTED_CPP_FILES` (`tools/make_deploy.py:286-300`) to add
  `src/platform/board_nezha.cpp`, `src/platform/board_cutebot.cpp`,
  `src/platform/cutebot_port.cpp`, and
  `src/platform/cutebot_actuation_policy.cpp` (confirm exact filenames
  against what tickets 001/002/004 actually created — this ticket's
  author must reconcile against the real tree, not this list, if they
  diverge).
- Update the pxt-bound TU exclusion list / `tests/DESIGN.md`'s own
  table (read during architecture planning: `tests/DESIGN.md:55-94`)
  for any new file that reaches `pxt.h` — expect `board_cutebot.cpp`
  and `cutebot_port.cpp` to need the same `#ifndef
  DIFFDRIVE_HOST_BUILD` treatment `nezha_port.cpp` already has, per
  ticket 002's own requirement that the shaping/encoder logic run on
  the host.
- Update `pxt.json`'s `files` list for every new `.h`/`.cpp` from
  tickets 001/002/003/004 (`test_pxt_manifest_completeness.py`
  enforces completeness — run it, do not hand-audit).
- Fleet JSON: add a new robot entry to
  `radio-robot-lib/config/robots/<name>.json` (schema:
  `robot_config.schema.json` in the same directory) for the assigned
  Cutebot Pro board. **The board's name is unresolved as of this
  sprint being planned** — the design doc's §8 opening note records the
  stakeholder naming "zeguz on mangi" while `mbdeploy list --remote`
  showed "zetuv on magni" and no zeguz, with zetuv refusing a connect
  as busy. Resolve the name with the stakeholder (or by a fresh
  `mbdeploy list --remote` + `HELLO` per the design doc's own §8 step
  1) before writing the JSON; if this ticket is executed before that
  resolution lands, create the config under the stakeholder-confirmed
  name at execution time rather than guessing — this is a placeholder
  decision point, not a detail to invent. Set `identity.hardware_model`
  to a descriptive free string (e.g. `"ELECFREAKS Cutebot Pro"` — the
  schema's `hardware_model` field is unconstrained) and
  `geometry.firmware_bake.board: "cutebot-pro"`. No other bake keys
  (travel_calib, trackwidth, motors, lag_s, etc.) are set — those are
  bench measurements, Sprint 041's job (`docs/design/
  cutebot-pro-support.md` §8-9).

## Acceptance Criteria

- [x] `geometry.firmware_bake.board` absent or `"nezha"` produces a
      byte-identical scratch copy to today's build (re-confirms ticket
      001's guarantee still holds through this ticket's own changes).
- [x] `geometry.firmware_bake.board: "cutebot-pro"` selects
      `DIFFDRIVE_BOARD_CUTEBOT_PRO` in the scratch copy's
      `platform/board.h`.
- [x] An unrecognized `board` value (e.g. a typo) makes
      `make_deploy.py` exit loudly with a clear message naming the bad
      value — proven by a test feeding it one.
- [x] `EXPECTED_CPP_FILES`, the pxt-bound TU exclusion list, and
      `pxt.json`'s `files` all correctly enumerate every file added by
      tickets 001-004, verified by `test_pxt_manifest_completeness.py`
      and `test_pxt_bound_exclusion_is_current.py` passing with no
      manual exception added to either.
- [x] A fleet JSON entry exists for the assigned board (name confirmed
      with the stakeholder, or left as an explicit TODO comment in the
      ticket's own completion notes if execution happens before the
      name is confirmed) with `hardware_model` and
      `geometry.firmware_bake.board: "cutebot-pro"` set, and no other
      bake key invented ahead of Sprint 041's measurements.

## Testing

- **Existing tests to run**: full `uv run pytest`, especially
  `test_pxt_manifest_completeness.py`,
  `test_pxt_bound_exclusion_is_current.py`, and any existing
  `make_deploy.py` bake tests (`_inject_motors`/`_inject_geometry`
  style unit tests in `tests/tools/`).
- **New tests to write**: a `tests/tools/` unit test for
  `_inject_board()` mirroring the existing `_inject_motors()` test
  shape — default/absent, `"nezha"`, `"cutebot-pro"`, and an
  unrecognized value's loud failure.
- **Verification command**: `uv run pytest`, plus one real
  `tools/make_deploy.py` invocation per board value against a scratch
  robot config.

## Completion Notes

**Files added (pxt-nezha-diffdrive).**
`tests/tools/test_make_deploy_board_bake.py` — pins `_inject_board()`
(absent key, explicit `"nezha"`, `"cutebot-pro"`, an unrecognized
string, a malformed type, a corrupted regex site) using the same
synthetic-`board.h` + `RADIO_ROBOT_LIB`-monkeypatch shape
`test_make_deploy_motors.py` already uses; a second suite of tests
(`TestRealSiblingConfig`) exercises `_inject_board()` against the REAL
`radio-robot-lib` checkout this ticket also writes
`config/robots/zeguz.json` into, skipping cleanly
(`pytest.skip()`, following `test_ruff_clean.py`'s own precedent for
an absent optional dependency) when that checkout or the zeguz config
specifically is not present. 21 tests total (17 pure-Python + 4
real-sibling), all passing in this checkout.

**Files modified (pxt-nezha-diffdrive).** `tools/make_deploy.py`:
`_inject_board(deploy_dir, robot)` (new, placed beside
`_read_robot_firmware_bake()`/before `_inject_geometry()`), wired into
all three build paths `main()` already injects geometry/motors from
(`--fault-spin`, `--program <other>`, and the primary `test.ts` build)
— `_inject_geometry()` is injected in all three today, so `board`
followed that precedent rather than `_inject_motors()`'s narrower
two-of-three placement (a robot's board identity is a build-wide fact,
not something that should differ between the primary deploy and a
`--fault-spin`/other-program variant of the same robot). `_inject_motors()`
gained one new refusal (see table below) and its docstring documents
why. `tools/DESIGN.md`: the `make_deploy.py` inventory row and the
`_inject_motors()` prose paragraph both extended to name the new
`board` bake and its cross-check with `_inject_motors()`.
`EXPECTED_CPP_FILES`, the pxt-bound TU exclusion list
(`tests/DESIGN.md`), and `pxt.json`'s `files` needed NO changes here —
tickets 001/002/004 already added every file this ticket's own
description asked to reconcile (`board_nezha.cpp`, `board_cutebot.cpp`,
`cutebot_port.cpp`, `cutebot_actuation_policy.cpp`); verified, not
re-added, by re-running `test_pxt_manifest_completeness.py` /
`test_pxt_bound_exclusion_is_current.py` / `test_make_deploy_board_seam.py`
before touching anything.

**`_inject_board()`'s injection-behaviour table**, its own doc comment's
summary tested by `test_make_deploy_board_bake.py`:

| `firmware_bake.board` | `board.h` result | reports in build log |
|---|---|---|
| absent (no key, or no `firmware_bake` block at all) | untouched — file never opened | no |
| `"nezha"` | re-substituted to the same tracked literal (explicit no-op) | yes — `('board', 'nezha')` |
| `"cutebot-pro"` | `DIFFDRIVE_BOARD_CUTEBOT_PRO` | yes — `('board', 'cutebot-pro')` |
| anything else (typo, wrong type, `1`, `["cutebot-pro"]`, ...) | `sys.exit()` naming the bad value, the robot, and the accepted set | n/a (build aborts) |

**The `_inject_motors()` / cutebot-pro cross-check decision (this
ticket's own "decide and document" item).** Chose REFUSE, not silent
no-op. `board_nezha.cpp`'s whole body — including the two
`NezhaMotorPort` lines `_inject_motors()` substitutes over — sits
behind `#if DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA` (confirmed by
reading the file), so on a `cutebot-pro` build the substitution would
still "succeed" (the regex site exists in the always-compiled
translation unit) but compile into dead code that never runs — a
silent no-op indistinguishable, from the config author's side, from a
working bake. That is exactly the class of stale-but-plausible config
this fleet's own rules exist to catch (the mounts-table story in
`.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`), so
`_inject_motors()` now `sys.exit()`s when a robot's config declares
BOTH `firmware_bake.board: "cutebot-pro"` AND a `firmware_bake.motors`
block, naming both keys and telling the operator to remove one.
`board: "cutebot-pro"` with no `motors` block (zeguz's own real shape)
does not trip this — proven by
`test_cutebot_pro_board_alone_does_not_trip_the_motors_refusal`.

**Fleet JSON (radio-robot-lib, committed separately, not pushed).**
`config/robots/zeguz.json` — `identity.hardware_model` "ELECFREAKS
Cutebot Pro", `identity.drivetrain_type` "diffdrive",
`geometry.firmware_bake.board` "cutebot-pro", and NO other bake key.
Computed radio pair, via `make_deploy.derive_radio_from_name('zeguz')`
(this repo's own name-derived-addressing implementation, MEASURED this
session by direct call, not transcribed): **channel 71, group 199** —
matches `.claude/rules/playfield-testing.md`'s own 73-channel table
row for zeguz, so the two independent sources (the derivation formula
and the hand-kept table) agree.

**The name-resolution question is UNRESOLVED, exactly as the ticket's
own description anticipated, and is called out both in
`zeguz.json`'s own `identity._identity_note` and here.** The
stakeholder's dispatch instruction for this session states the name as
"zeguz" (matching the design doc's own §8 note); a prior farm listing
saw "zetuv on magni" instead, busy/refusing connect, with no fresh
`mbdeploy list --remote` + `HELLO` run this session to settle it (no
robot access in this host-only ticket). Per the ticket's own
instruction ("create the config under the stakeholder-confirmed name
at execution time rather than guessing"), `zeguz.json` was created
under the name given for this dispatch, with an explicit note that a
`HELLO` mismatch (the board answering "zetuv") means renaming the file
and recomputing its radio pair for that name — NOT editing this one's
values in place, since `zetuv`'s derived pair (49, 250, also computed
this session) differs from zeguz's.

**Schema validation, honestly reported.** `robot_config.schema.json`'s
own docstring says `data/robots/*.json` (its stated target directory,
which does not exist in this checkout — the real files are under
`config/robots/`) "does not yet validate against this document"
pending a later JSON-reshape migration. Confirmed directly this
session: `jsonschema.validate()` against `zeguz.json` fails on
`schema_version` (`additionalProperties: false` at the object root,
which the schema does not declare) — and the SAME failure mode
reproduces against the real, long-shipped `tovez.json`
(`geometry.firmware_bake` and every underscore-prefixed provenance
note are likewise undeclared `additionalProperties`). `zeguz.json`
therefore follows the REAL fleet convention (the shape every other
`config/robots/*.json` actually uses, which is what `make_deploy.py`
reads) rather than the letter of the not-yet-enforced generated
schema, and this divergence is not new or specific to this file.

**`docs/design/cutebot-pro-support.md` Sec.8's "zeguz on mangi" vs
"zetuv on magni" spelling** (one letter transposed) is UNEXPLAINED, not
resolved this session — it could be a typo in the design doc's own
note, or two genuinely different farm nodes. Not chased further:
node identity is orthogonal to the robot-name question this ticket had
to leave open, and no farm access exists in this host-only ticket to
check `mbdeploy list --remote` against either spelling.

**`test/DESIGN.md`'s "placeholder table" was NOT touched, and this is
a deliberate decision, not an oversight.** The ticket text (Scope item
5) says "tools/DESIGN.md and test/DESIGN.md's placeholder table
updated for the new bake." Reading `test/DESIGN.md` (the TS-programs
design doc, singular `test/`) shows its placeholder table is
specifically the four `test.ts`-file substitutions `make_deploy.py`
performs (`BOOT_VERSION`, `BOOT_ROBOT`, `BOOT_RADIO_LINK`,
`otosBootId`) — `board.h` is a different file, never touched by any of
those four regexes, and adding a row for it there would misdescribe
what that table is. `tools/DESIGN.md` (updated, see above) is where
the geometry/motors bake prose already lives and where the board bake
now lives beside it. `tests/DESIGN.md` (plural, the pytest-suite
design doc) needed no change: its translation-unit/exclusion tables
were already correct per tickets 001/002/004, confirmed by re-running
`test_pxt_manifest_completeness.py`/`test_pxt_bound_exclusion_is_current.py`
rather than re-editing.

**Full-suite result.** `uv run pytest tests/host tests/tools -q
--ignore=tests/tools/test_field_dance_accel_bake.py` — **2281 passed**,
MEASURED this session (matches ticket 001's own note on why that one
file is excluded: it imports `tools/field_dance.py`, which connects to
a live AprilCam daemon at import time, and none runs in this host-only
session). `ruff check tools/make_deploy.py
tests/tools/test_make_deploy_board_bake.py` — clean.

**Not attempted / left for later.** A real `tools/make_deploy.py
--robot zeguz --board cutebot-pro` DOCKER BUILD (compiling a hex) —
that is this sprint's own mandated last-ticket build checkpoint
(ticket 007), not this ticket's; this ticket's own verification is the
scratch-copy substitution proven directly (`_sync_scratch()` +
`_inject_board()` against the real tree, no compile). Confirming the
robot's real identity via `HELLO` and, if it answers `zetuv`, renaming
`zeguz.json` accordingly — flagged above and left for the session that
has robot access. Any geometry/motors/travel_calib bake for zeguz —
explicitly Sprint 041's job per this ticket's own non-negotiable.
