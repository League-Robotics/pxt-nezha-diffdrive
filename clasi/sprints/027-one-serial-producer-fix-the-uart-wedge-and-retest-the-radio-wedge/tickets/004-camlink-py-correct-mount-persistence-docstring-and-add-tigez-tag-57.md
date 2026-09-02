---
id: '004'
title: 'camlink.py: correct mount-persistence docstring and add tigez (tag 57)'
status: open
use-cases:
- SUC-003
depends-on: []
github-issue: ''
issue: camlink-mounts-table-is-stale-for-tigez.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# camlink.py: correct mount-persistence docstring and add tigez (tag 57)

## Description

`tools/camlink.py` is the single place this repo records what it knows
about robot-mounted camera tags, and two defects in it currently drive
a repeated, unnecessary probe ritual — see
`clasi/issues/camlink-mounts-table-is-stale-for-tigez.md` for full
background.

1. **Stale docstring (`tools/camlink.py:10-16`).** It states mount
   parameters are "NOT persisted across a daemon restart" and that
   `ensure_registered()` must be called "every session." AprilCam
   changed: mount registrations now persist to
   `state_dir/mounts/registry.json` and reload automatically at daemon
   startup (AprilCam agent guide §6); only an explicit `unregister_tag`
   removes one. Annotations remain per-session — that half of the
   docstring is still correct. `ensure_registered()` stays harmless
   (idempotent re-registration) but should no longer be framed as
   mandatory session setup.
2. **Missing tigez (tag 57) in `MOUNTS`.** `MOUNTS` covers 53 (vevov),
   52 (tovez), 10/11 (fixed calibration tags) but not 57 — the tag on
   **tigez**, the board on the playfield since 2026-08-30. Its
   parameters are already measured (tigez calibration, 2026-08-30):
   mount `(-0.67, -0.02)` cm at −89.65°. A session working tigez
   currently finds no entry and re-probes a known constant.

Fix, per the issue's own three-step Fix section:

1. Correct the module docstring: registrations persist and reload at
   daemon start; annotations do not. Keep `ensure_registered()` as
   cheap idempotent insurance, not mandatory setup.
2. Add tag 57 to `MOUNTS` with its measured offsets, `mount_z`, and
   `mount_yaw_rad = -math.pi/2`.
3. Add a comment splitting `mount_yaw_rad` into its two parts: −90.00°
   is the AprilCam convention (fixed for every tag on every robot,
   never re-measured), and only the sub-degree residual (tigez's 0.35°)
   is physical mounting, changing only if the plate is remounted.

This ticket is independent of tickets 001-003 (unrelated tool, no
shared code) and can be done in any order relative to them.

## Acceptance Criteria

- [ ] `tools/camlink.py`'s module docstring no longer states mount
      registrations are "NOT persisted" — it states they persist and
      reload automatically at daemon startup, and that only
      annotations are per-session.
- [ ] `ensure_registered()`'s own doc comment (if any) reflects that it
      is cheap idempotent insurance, not mandatory session setup.
- [ ] `MOUNTS` includes an entry for tag 57 (tigez) with mount
      `(-0.67, -0.02)` cm, its `mount_z`, and
      `mount_yaw_rad = -math.pi/2`.
- [ ] A comment on the tag 57 entry (or on `mount_yaw_rad` generally,
      if that reads more naturally) splits the −90.00° AprilCam
      convention term from the 0.35° physical residual, per the issue's
      Fix step 3.
- [ ] If a host test already pins `MOUNTS`'s shape or entries, it is
      extended to cover tag 57; if none exists, this ticket does not
      need to add one for a pure data/doc correction.
- [ ] `uv run pytest` (full host suite) passes.
- [ ] No new comment names a sprint, a ticket, an `R-NN` code, or any
      `.md` filename other than the referenced rule file path itself if
      already a repo convention — check
      `test_archaeology_marker_budget.py`'s actual scope (this file may
      be outside `src/`, in which case the budget likely does not apply;
      confirm rather than assume).

## Implementation Plan

**Approach**: Read `tools/camlink.py:10-16` and the `MOUNTS` table in
full first, then make both edits together (they are adjacent, small,
and independent of each other in effect). Use the issue's own measured
values verbatim — do not re-derive or re-probe.

**Files to modify**: `tools/camlink.py` (docstring, `MOUNTS`).

**Files NOT to modify**: any firmware source (`src/`), any other tool
(`tools/`) — this ticket's scope is exactly the two defects the issue
names.

## Testing

- **Existing tests to run**: `uv run pytest`, including any existing
  `tools/` test that imports or exercises `camlink.MOUNTS`.
- **New tests to write**: only if extending an existing `MOUNTS` test
  to cover tag 57 (see Acceptance Criteria) — no new test file for a
  pure data/doc correction otherwise.
- **Verification command**: `uv run pytest`.
