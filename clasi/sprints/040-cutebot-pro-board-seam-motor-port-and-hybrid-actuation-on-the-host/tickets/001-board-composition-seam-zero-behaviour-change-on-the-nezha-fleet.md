---
id: '001'
title: 'Board composition seam: zero behaviour change on the Nezha fleet'
status: open
use-cases: ["SUC-001"]
depends-on: []
github-issue: ''
issue: cutebot-pro-board-seam-and-hybrid-port.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Board composition seam: zero behaviour change on the Nezha fleet

## Description

Move every Nezha-only site the design doc's §2.1 leak list names behind
a new compile-time board-composition seam, with **no Cutebot code in
this ticket** — the point is to prove the seam is neutral in isolation,
before a second board's behaviour can possibly mask a regression in it.

Per `docs/design/cutebot-pro-support.md` §2.1 and §4, and
`src/DESIGN.md` §1/§9:

- Add `src/platform/board.h`: one literal, `DIFFDRIVE_BOARD` (values
  `DIFFDRIVE_BOARD_NEZHA` / `DIFFDRIVE_BOARD_CUTEBOT_PRO`), defaulting
  to Nezha.
- Add `src/platform/board_nezha.cpp`, compiled under `#if
  DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA`: the exact
  `NezhaMotorPort left{1,-1}; right{2,+1};` construction currently
  inline in `shims.cpp`'s `Rig`, the Nezha `diffdrive_emergency_motor_stop()`
  frame (currently `src/platform/nezha_port.cpp:52-65`), and the
  Nezha-only diag ordinals currently read directly off
  `ensure().left`/`ensure().right` in `shims.cpp`'s `diagValue()`
  (ordinals 21/22/23/24/27/35-40, `src/shims.cpp:1170-1236`) — these
  become calls through a small per-board diagnostics hook rather than
  assuming a `NezhaMotorPort` type.
- Move `Rig`'s `NezhaMotorPort left`/`right` members to be
  board-composed (a reference or a board-owned pair `Rig` holds through
  the seam) rather than declared as concrete `NezhaMotorPort` fields —
  `Rig`'s declaration-order constraints (kernel/engine/odometry all
  depend on `left`/`right` existing before they construct) are
  preserved exactly.
- Generalize `configureMotor()` (`src/shims.cpp:1295-1335`) and
  `core/motor_wiring.h` so the wiring-swap decision is made against
  whatever the composed board provides, not hard-coded to
  `NezhaMotorPort`. Nezha's own behaviour (M1-M4 swap, `busGuard`
  sequencing, stop-first) is **unchanged** — this ticket only makes the
  call site board-generic; it does not touch what Nezha does with it.
- Generalize `kRole` (`src/comms/protocol.cpp:100`, currently the
  literal `"NEZHA2"`) into a per-board string the composed board
  supplies, reusing sprint 037's runtime-settable role/common_name
  mechanism — `kRole` for a Nezha build must still read `"NEZHA2"`.
- `tools/make_deploy.py`: rename/generalize `_MOTOR_BAKE_RES`'s target
  (still only ever matching `board_nezha.cpp`'s two `NezhaMotorPort`
  lines) and add `EXPECTED_CPP_FILES` entries for the two new files
  (`board_nezha.cpp` this ticket; `board_cutebot.cpp` is added, empty
  or stubbed, by ticket 002 — decide with that ticket's author whether
  to stub it here or there, but `EXPECTED_CPP_FILES`/manifest entries
  for both are cheapest to add together now since this ticket is
  already touching that list).
- Update `pxt.json`'s `files` list for the new `platform/board*` files
  (`test_pxt_manifest_completeness.py` enforces this) and the
  pxt-bound TU exclusion list (`tests/DESIGN.md` §own table) if
  `board_nezha.cpp`/`board_cutebot.cpp` need a `pxt.h`-gated section
  the way `nezha_port.cpp` does (only the emergency-stop frame is
  target-bound; the composition literal itself is portable).

**Do not implement any Cutebot behaviour in this ticket** — a stub
`board_cutebot.cpp` (if added here at all) must not compile into
anything reachable unless `DIFFDRIVE_BOARD_CUTEBOT_PRO` is selected,
and no fleet config selects it yet.

## Acceptance Criteria

- [ ] With no `geometry.firmware_bake.board` key in a robot's config
      (the status quo for every fleet robot today), `make_deploy.py`'s
      generated scratch-copy `src/` tree diffs **byte-identical**
      against what the same command produced before this ticket, for
      at least one real fleet robot config (e.g. tovez or gopiv).
- [ ] Full host suite (`uv run pytest`) is green with the seam merged
      and no Cutebot source anywhere in the tree.
- [ ] `diagValue()` ordinals 21/22/23/24/27/35-40 return identical
      values to before this ticket on a Nezha-composed build (host
      test or source-level equivalence check).
- [ ] `configureMotor()`'s Nezha behaviour (M1-M4 swap decision,
      stop-first, bus-guard sequencing) is unchanged, pinned by the
      existing `motor_wiring`/`configureMotor` host tests continuing
      to pass unmodified.
- [ ] `EXPECTED_CPP_FILES`, the pxt-bound TU exclusion list, and
      `pxt.json`'s manifest all list the new file(s) with no existing
      entry removed or reordered in a way that breaks
      `test_pxt_manifest_completeness.py`.
- [ ] `kRole` on a Nezha-composed build still reports `"NEZHA2"` byte
      for byte (source-level pin or host test).

## Testing

- **Existing tests to run**: the full `uv run pytest` host suite,
  including `test_pxt_manifest_completeness.py`,
  `test_pxt_bound_exclusion_is_current.py`, and every existing
  `motor_wiring`/`configureMotor`/diag-ordinal test.
- **New tests to write**: a host test (or, if a full host-portable
  `Rig` equivalent does not exist, a source-diff script invoked from a
  test) proving the scratch-copy byte-identity claim above for at
  least one robot config with no `firmware_bake.board` key; a small
  test pinning `DIFFDRIVE_BOARD`'s default value.
- **Verification command**: `uv run pytest`, plus one real
  `tools/make_deploy.py` run for a fleet robot compared byte-for-byte
  against a pre-ticket baseline scratch copy.
