---
id: '002'
title: 'Fix camera-parallax double correction: one owner for mount_z_cm vs parallax_k'
status: done
use-cases:
- SUC-006
depends-on: []
github-issue: ''
issue: parallax-k-and-registered-mount-z-correct-twice.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# Fix camera-parallax double correction: one owner for mount_z_cm vs parallax_k

**Type: (b) desk code change — programmer.**

## Description

`tools/camlink.py::Cam.register()` registers a tag with `mount_z_cm`,
and the aprilcam daemon applies that tag-height parallax correction
itself. `tools/field_dance.py` ALSO divides camera distances by a
tool-side `parallax_k` — for tovez every drive read ~12% short until
`parallax_k` was force-set to 1.0 as a stop-gap
(`parallax-k-and-registered-mount-z-correct-twice.md`).

Per this sprint's Design Rationale, register `mount_z_cm` as the sole
owner: delete `parallax_k`'s division from every tool that applies it.
Audit and fix `tools/field_dance.py` (the confirmed offender) plus
`tools/reposition.py`, `tools/park.py`, `tools/tour_*.py`,
`tools/leg_analysis.py`, `tools/pivot_truth.py` — anything dividing a
camera distance by `parallax_k` on a tag that is ALSO registered with a
non-zero `mount_z_cm`.

Do not touch vevov's existing entry (`mount_z 0`, `k = 1.119`) as part
of this ticket — flag it in the closing note as a fast-follow re-fit
once this convention lands, per the issue's own remedy. Changing it
blind, without a fresh capture, would just move the bug rather than
fix it.

## Acceptance Criteria

- [x] Exactly one layer (the daemon's registered `mount_z_cm`) applies
      the parallax correction; `parallax_k`'s division is removed from
      every audited tool. Done: `tools/field_dance.py` no longer reads
      `parallax_k` at all (removed `K = _ENTRY['parallax_k']` and both
      `/ K` divisions; both distance computations now go through
      `field.registered_pose_distance()`, whose signature has no
      scaling-factor parameter to plug one into). Audited
      `reposition.py`, `park.py`, `leg_analysis.py`, `pivot_truth.py`,
      and every `tour_*.py` — none of them ever read `parallax_k` in
      the first place (grep-confirmed, and pinned by
      `tests/tools/test_parallax_ownership.py::test_no_audited_tool_divides_a_distance_by_parallax_k`).
      `tools/linefollow/` still applies `parallax_k`, deliberately,
      against a RAW/unregistered tag reading, not a registered one —
      out of this ticket's audit list and not a double correction.
- [x] `tools/field_calibration.json`'s tovez entry no longer needs the
      `parallax_k = 1.0` stop-gap value to read correctly (or the field
      is removed/documented as inert). Done: the key is removed from
      tovez's entry; `_lever_parallax_note` documents why.
- [ ] A repeat of a `field-dance-refit-run1.log`-style drive on tovez
      reads within travel-calib tolerance of the commanded distance —
      capture cited (board, date, path). **UNVERIFIED — no hardware or
      camera in this dispatch.** Would be settled by: register tovez's
      tag (`camlink.py --register tovez`), run `uv run
      tools/field_dance.py --tcp <zilch-host>:<port>`, and confirm the
      drive rows (20/-40/20 cm) read within `TOL_CM` (3 cm) of
      commanded with no dilation artifact, citing the new capture path.
- [x] vevov's entry is explicitly flagged (not silently changed) in the
      closing note for a fast-follow re-fit. Done: vevov's JSON entry
      (`mount_z_cm`, `parallax_k`, notes) is byte-for-byte untouched,
      and both `tools/DESIGN.md` and this ticket's closing note flag it
      explicitly.
- [x] `tools/DESIGN.md` is updated to document the single-owner
      parallax convention. NOTE: this sprint's design overlay could not
      seed `tools/DESIGN.md` alongside `src/DESIGN.md` (both collide on
      the same bare "DESIGN.md" overlay slug — see sprint.md's Open
      Questions, flagged as tooling defect task_d119bad8) — edit the
      canonical `tools/DESIGN.md` directly as a normal tracked change,
      not through the sprint's `design/` overlay. Done: new "Camera-
      parallax correction: one owner, never two (sprint 031 ticket
      002)" section added.

## Testing

- **Existing tests to run**: any existing `tools/` / `tests/tools/`
  suite covering `field_dance.py`, `camlink.py`, `reposition.py`.
- **New tests to write**: a host test asserting a registered tag's
  distance is used unscaled (no `parallax_k` division applied when
  `mount_z_cm` is registered and applied by the daemon).
- **Verification command**: `uv run pytest tests/tools/`
