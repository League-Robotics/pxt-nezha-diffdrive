---
id: '003'
title: Delete the dead tools and dead blocks, with a reference sweep
status: done
use-cases:
- SUC-004
depends-on: []
github-issue: ''
issue: tools-consolidation-inprocess-aprilcam-wrap-link-layer.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Delete the dead tools and dead blocks, with a reference sweep

## Description

Delete the tools that are dead, before the consolidation tickets waste
effort migrating them. `tests/DESIGN.md` already states the right policy
for `tests/dev/` -- "deleted rather than left to rot"; this applies it to
`tools/`.

**Note on ordering.** The sprint brief put deletion last. It runs third
instead, and the sprint's Architecture section records why: with
deletion last, tickets 004, 006 and 008 would each migrate
`tour_square.py`, `tour_closedloop.py` and `truth_check.py` onto the new
CSV codec, the new `Link` and the new `Cam` -- three files of thrown-away
work and three chances to create a conflict. The `tools/DESIGN.md` truth
pass does stay last (ticket 012), because *that* is the artifact that
must describe the final state.

**Note on the roadmap's "five reference-only tools".** Only three whole
files are defensibly dead. `tour_practice.py` and `practice_chart.py`
are live -- only the dead blocks inside them go. `camproc.py` is the
fourth deletion but belongs to ticket 008, for a different reason.

**The stale-relay-address justification no longer applies.** TL-01 was
fixed before this sprint: `robotlink.py` derives the pair with
`radio_address(robot)` and `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP` are gone. These
files are still worth deleting; that is not the reason. Do not repeat
the stale claim in a commit message.

## Acceptance Criteria

### Whole files deleted

- [x] `tools/truth_check.py` -- dead on arrival: five subprocess
      launches per fix against a hard-coded `127.0.0.1:5280`, reading v1
      JSON keys (`id`, `orientation_yaw`, `world_xy`) that the v2 client
      does not emit. Against the current daemon its `cam_yaw()` returns
      `None` and it exits with "camera cannot see tag 53" -- sending the
      operator to the lights and the camera for a tool defect.
      `pivot_truth.py` measures the same thing through the v2 client.
- [x] `tools/tour_square.py` -- `tools/DESIGN.md` itself calls it an
      "earlier variant kept for reference"; nothing imports it.
- [x] `tools/tour_closedloop.py` -- same, and it hard-codes a Shelly URL.

### Dead blocks removed (files kept)

- [x] `tools/tour_watch.py` -- the `vel` list that is never populated
      ("not currently plumbed") and the chart branch that draws "no
      wheel-speed samples" because of it. `row['vl']` is decoded two
      lines later, so the data exists; either plumb it or delete the
      branch. Deleting is the default.
- [x] `tools/tour_practice.py` -- `wheel_speeds()`, whose own header
      says "not called anywhere in this file -- kept for reference only".
- [x] `tools/practice_chart.py` -- the differencing fallback that
      existed for `wheel_speeds()`, and the duplicate `TRACK_CM = 12.0`
      (one owner, or none).
- [x] `tools/camlink.py` -- the `--hz` argument that its own code says
      is ignored, and the `_stream()` docstring's false claim that "the
      camera library and pyserial live in DIFFERENT interpreters". (The
      rest of `camlink.py`'s subprocess shape is ticket 008's.)

### Tests

- [x] The four `truth_check` tests and the `import truth_check` line in
      `tests/tools/test_run_verbs.py` are deleted with their subject.

### The reference sweep -- this is the part that must not be skipped

- [x] For **each** deleted path, grep `tools/ tests/ test/ docs/
      .claude/ clasi/issues/ clasi/sprints/034-*/` and resolve every
      hit. Known hits to expect: `tools/tlm.py` references
      `truth_check`; `tools/DESIGN.md` lists `truth_check.py` and
      `pivot_truth.py` as "the ground-truth pair" and describes
      `tour_square`/`tour_closedloop`; `tests/tools/DESIGN.md` and
      `tests/DESIGN.md` mention them.
- [x] **Do not edit** `docs/code-review/**` -- those are dated historical
      records and rewriting them destroys the audit trail this repo's
      `.claude/rules/measurement-citations.md` depends on. Same for
      `clasi/sprints/done/**`.
- [x] **Do not edit** `.claude/worktrees/sprint-20-work-tree-8741c7/` --
      it is a stale worktree checkout that shadows the whole repo and
      will pollute every grep. Exclude it from the sweep and **report its
      existence in your ticket record**; per the "worktree CLASI status
      is stale" project knowledge, a worktree's copy is never authority.
- [x] Any hit that is a live instruction to a human or an agent
      (`tools/DESIGN.md`, `tests/*/DESIGN.md`, `tools/tlm.py`'s
      docstring, anything under `.claude/rules/`) is corrected here, not
      deferred -- a doc telling the next session to run a file that no
      longer exists is the same defect class this sprint is fixing.

## Implementation Plan

### Approach

1. `git rm` the three files.
2. Remove the dead blocks and the `--hz` plumbing.
3. Delete the `truth_check` tests.
4. Run the sweep. Fix live references; leave the historical record alone.
5. Add a guard test so the names cannot come back by copy-paste.

### Files

Deleted: `tools/truth_check.py`, `tools/tour_square.py`,
`tools/tour_closedloop.py`.
Edited: `tools/tour_watch.py`, `tools/tour_practice.py`,
`tools/practice_chart.py`, `tools/camlink.py`, `tools/tlm.py`,
`tools/DESIGN.md`, `tests/tools/test_run_verbs.py`, plus whatever the
sweep turns up.

### Re-anchoring

Line numbers in the issue are from 2026-09-02. Grep for the symbol
names (`wheel_speeds`, `TRACK_CM`, `--hz`, `truth_check`), not the
cited ranges.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools -q` (foreground,
  scoped).
- **New tests to write**: one guard in `tests/tools/` asserting that no
  file under `tools/` or `tests/` mentions `truth_check`, `tour_square`
  or `tour_closedloop` -- the same shape as the existing
  `test_camlink.py::test_real_calibration_file_has_no_mounts_table_leftovers`
  guard. Exclude `docs/` and `clasi/sprints/done/` from that guard
  explicitly, with the reason in the test's docstring.
- **Verification command**: `uv run pytest tests/tools -q`

## Implementation record

### Deleted (via `git rm`, so the commit records the removal)

- `tools/truth_check.py` (215 lines)
- `tools/tour_square.py` (137 lines)
- `tools/tour_closedloop.py` (164 lines)

### Dead blocks removed

- `tools/tour_watch.py` -- the `vel` list, its `chart()` parameter, and
  the whole second subplot (which could only ever draw the "no
  wheel-speed samples" placeholder). `chart()` is now a one-panel
  figure. The comment that explained why `vel` stayed empty is replaced
  by one saying where the wheel-speed data actually is (`row['vl']`/
  `row['vr']`, already written to each run's `_tlm.csv`) for whoever
  wants the panel back.
- `tools/tour_practice.py` -- `wheel_speeds()`, its `TRACK_CM`, the
  docstring parenthetical that advertised it as "kept for reference
  only", and the now-unused `math` / `field.wrap` imports.
- `tools/practice_chart.py` -- the differencing fallback in
  `wheel_speeds()` (it now returns `[]` when the header carries neither
  `vl_cms` nor `vl_mms`; the caller's `if ws:` already handled that),
  the duplicate `TRACK_CM = 12.0` -- **no owner left**, both copies are
  gone -- and the now-unused `math` / `field.wrap` imports.
- `tools/camlink.py` -- the `--hz` argument (self-documented as
  ignored) and `_stream()`'s `hz` parameter; the `_stream()` docstring's
  false "the camera library and pyserial live in DIFFERENT interpreters
  (the aprilcam venv has no pyserial)" claim, replaced by a plain
  description of the parent/child split and of why there is no rate to
  ask for.
- `tools/camproc.py` -- the other end of that plumbing: `Cam.__init__`'s
  `hz` kwarg, `self.hz`, and the `'--hz', str(self.hz)` pair in
  `_spawn_process()`. Required, not scope creep: leaving it would have
  made every `Cam()` spawn a `camlink.py` that exits on an unrecognised
  argument. No caller anywhere passed `hz=`. The rest of `camproc.py`'s
  subprocess shape is untouched -- that is ticket 008's.

### Tests

- `tests/tools/test_run_verbs.py` -- `import truth_check` and its three
  test functions (`..._otos_fix_sends_run_fix_not_run10`,
  `..._send_pivot_sends_the_degree_value_directly` (4 parametrised
  cases), `..._pivot_verb_table_is_gone`) deleted with their subject;
  module docstring and section comments retargeted from five bench
  tools to four.
- New: `tests/tools/test_deleted_tools_stay_deleted.py` -- six
  parametrised guards (paths gone, and no file under `tools/` or
  `tests/` names any of the three stems). The `docs/` and
  `clasi/sprints/done/` exclusions and the measurement-citations reason
  for them are stated in the module docstring.

### The reference sweep -- every live reference corrected

| file | what changed |
|---|---|
| `tools/DESIGN.md` | dropped the `tour_square`/`tour_closedloop` "earlier variants kept for reference" bullet (replaced by a short unnamed note on why they went); "Ground truth" section is now `pivot_truth.py` alone; both stale prose lists in the pre-005 numeric-vocabulary section lost the third name |
| `tools/camproc.py` | module docstring's list of the seven replaced `Cam` scaffolds, and `Cam`'s `respawn=True` docstring |
| `tools/field.py` | `turn_total()`'s "the failure this replaces" paragraph |
| `tools/tlm.py` | module docstring's list of the six tools that used to parse `TLM:` themselves |
| `tests/tools/DESIGN.md` | three places: the `test_run_verbs.py` blurb (five tools -> four), the RUN-coverage list, the section-6 coverage list |
| `tests/tools/test_field.py` | `turn_total()` section comment |
| `tests/tools/test_parallax_ownership.py` | two entries removed from `_AUDITED_TOOLS` -- this one was a latent failure, not just prose: the test opens each listed file |
| `tests/tools/test_run_verbs.py` | see Tests above |
| `test/test.ts` | the `RUN:pivot:<deg>` handler comment's list of callers |
| `test/DESIGN.md` | the `test.ts` bullet's list of tools the pivot/turn-rate verbs were added for |

After the sweep, `grep -rE 'truth_check|tour_square|tour_closedloop'
tools/ tests/` is empty (the new guard file excludes itself, since it
names the stems on purpose).

### Deliberately left alone

- **`docs/code-review/**`** -- 10 files, ~60 hits across the
  2026-08-23, 2026-08-26 and 2026-09-02 reviews. Dated records; per the
  acceptance criteria and `.claude/rules/measurement-citations.md`,
  rewriting them destroys the audit trail.
- **`clasi/issues/done/run-fiber-motion-resets-the-board-on-fw-1-20260829-1.md`**
  -- an archived, closed issue; same reasoning. (No hits under
  `clasi/sprints/done/**` at all.)
- **`clasi/sprints/034-.../sprint.md`, `issues/*.md`, tickets 007 / 008
  / 012** -- these are this sprint's own plan describing the deletion.
  Ticket 007 explicitly reads "ticket 003 will have deleted
  `tour_square.py` and `tour_closedloop.py` by now"; correcting them
  would be correcting a correct statement. Ticket 012 owns the full
  `tools/DESIGN.md` truth pass, so the DESIGN edits above were kept to
  exactly the references that named a file that no longer exists.
- **`clasi/sprints/034-.../design/`** overlay copies -- not edited, per
  the dispatch instruction; the canonical `tools/DESIGN.md`,
  `tests/DESIGN.md` and `tests/tools/DESIGN.md` are the ones corrected.
  (`tests/DESIGN.md` turned out to have no hits.)
- **`.claude/rules/*.md` and `docs/robot-connections.md`** -- swept, no
  hits. `captures/**` -- historical, not swept.
- `tools/tour_watch.py`'s `chart()` still takes an unused `fixes`
  parameter. Pre-existing and out of this ticket's scope.

### The stale worktree (reported, not edited)

`.claude/worktrees/sprint-20-work-tree-8741c7/` exists, is a **detached
HEAD** at `1b2c7f3` ("chore(roadmap): insert sprint 031 ... 031-034
renumbered to 032-035"), and still carries live copies of
`tools/truth_check.py` and `tools/tour_square.py`. It was excluded from
every grep in this ticket (`--exclude-dir=worktrees`).

It is not alone: `.claude/worktrees/` currently holds **nine**
checkouts (`aprilcam`, `blocks-local-codeserver-test-bf93c6`,
`gopiv-bench-fullduty`, `robot-circular-movement-e0358d`,
`speed-floor-70`, `sprint-20-work-tree-8741c7`, `sprint-31-oop-fe4d5a`,
`tovez-calibration-20260905`, `wifi-transport`). Together they answer
**348 files** to this ticket's sweep grep -- roughly ten times the real
hit count, all of it noise. Per the "worktree CLASI status is stale"
project knowledge, a worktree's copy is never authority; nothing in
them was changed here. Cleaning them up is a separate decision for the
stakeholder.
