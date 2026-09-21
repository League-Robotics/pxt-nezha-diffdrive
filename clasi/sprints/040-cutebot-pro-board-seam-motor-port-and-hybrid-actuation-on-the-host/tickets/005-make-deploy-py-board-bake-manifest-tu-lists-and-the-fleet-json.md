---
id: '005'
title: make_deploy.py board bake, manifest/TU lists, and the fleet JSON
status: open
use-cases: ["SUC-001"]
depends-on: ["001", "002", "004"]
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

- [ ] `geometry.firmware_bake.board` absent or `"nezha"` produces a
      byte-identical scratch copy to today's build (re-confirms ticket
      001's guarantee still holds through this ticket's own changes).
- [ ] `geometry.firmware_bake.board: "cutebot-pro"` selects
      `DIFFDRIVE_BOARD_CUTEBOT_PRO` in the scratch copy's
      `platform/board.h`.
- [ ] An unrecognized `board` value (e.g. a typo) makes
      `make_deploy.py` exit loudly with a clear message naming the bad
      value — proven by a test feeding it one.
- [ ] `EXPECTED_CPP_FILES`, the pxt-bound TU exclusion list, and
      `pxt.json`'s `files` all correctly enumerate every file added by
      tickets 001-004, verified by `test_pxt_manifest_completeness.py`
      and `test_pxt_bound_exclusion_is_current.py` passing with no
      manual exception added to either.
- [ ] A fleet JSON entry exists for the assigned board (name confirmed
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
