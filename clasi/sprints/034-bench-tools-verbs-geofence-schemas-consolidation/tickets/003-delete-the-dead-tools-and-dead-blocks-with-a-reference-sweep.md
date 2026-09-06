---
id: '003'
title: Delete the dead tools and dead blocks, with a reference sweep
status: open
use-cases: [SUC-004]
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

- [ ] `tools/truth_check.py` -- dead on arrival: five subprocess
      launches per fix against a hard-coded `127.0.0.1:5280`, reading v1
      JSON keys (`id`, `orientation_yaw`, `world_xy`) that the v2 client
      does not emit. Against the current daemon its `cam_yaw()` returns
      `None` and it exits with "camera cannot see tag 53" -- sending the
      operator to the lights and the camera for a tool defect.
      `pivot_truth.py` measures the same thing through the v2 client.
- [ ] `tools/tour_square.py` -- `tools/DESIGN.md` itself calls it an
      "earlier variant kept for reference"; nothing imports it.
- [ ] `tools/tour_closedloop.py` -- same, and it hard-codes a Shelly URL.

### Dead blocks removed (files kept)

- [ ] `tools/tour_watch.py` -- the `vel` list that is never populated
      ("not currently plumbed") and the chart branch that draws "no
      wheel-speed samples" because of it. `row['vl']` is decoded two
      lines later, so the data exists; either plumb it or delete the
      branch. Deleting is the default.
- [ ] `tools/tour_practice.py` -- `wheel_speeds()`, whose own header
      says "not called anywhere in this file -- kept for reference only".
- [ ] `tools/practice_chart.py` -- the differencing fallback that
      existed for `wheel_speeds()`, and the duplicate `TRACK_CM = 12.0`
      (one owner, or none).
- [ ] `tools/camlink.py` -- the `--hz` argument that its own code says
      is ignored, and the `_stream()` docstring's false claim that "the
      camera library and pyserial live in DIFFERENT interpreters". (The
      rest of `camlink.py`'s subprocess shape is ticket 008's.)

### Tests

- [ ] The four `truth_check` tests and the `import truth_check` line in
      `tests/tools/test_run_verbs.py` are deleted with their subject.

### The reference sweep -- this is the part that must not be skipped

- [ ] For **each** deleted path, grep `tools/ tests/ test/ docs/
      .claude/ clasi/issues/ clasi/sprints/034-*/` and resolve every
      hit. Known hits to expect: `tools/tlm.py` references
      `truth_check`; `tools/DESIGN.md` lists `truth_check.py` and
      `pivot_truth.py` as "the ground-truth pair" and describes
      `tour_square`/`tour_closedloop`; `tests/tools/DESIGN.md` and
      `tests/DESIGN.md` mention them.
- [ ] **Do not edit** `docs/code-review/**` -- those are dated historical
      records and rewriting them destroys the audit trail this repo's
      `.claude/rules/measurement-citations.md` depends on. Same for
      `clasi/sprints/done/**`.
- [ ] **Do not edit** `.claude/worktrees/sprint-20-work-tree-8741c7/` --
      it is a stale worktree checkout that shadows the whole repo and
      will pollute every grep. Exclude it from the sweep and **report its
      existence in your ticket record**; per the "worktree CLASI status
      is stale" project knowledge, a worktree's copy is never authority.
- [ ] Any hit that is a live instruction to a human or an agent
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
