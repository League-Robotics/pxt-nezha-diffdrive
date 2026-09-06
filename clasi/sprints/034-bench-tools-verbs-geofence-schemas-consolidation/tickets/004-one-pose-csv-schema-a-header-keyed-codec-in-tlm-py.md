---
id: '004'
title: 'One pose-CSV schema: a header-keyed codec in tlm.py'
status: in-progress
use-cases:
- SUC-003
depends-on:
- '003'
github-issue: ''
issue: tools-v6-verbs-geofence-pose-csv-schema.md
completes_issue: true
---
<!-- CLASI: Before changing code or making plans, review the SE process in CLAUDE.md -->

# One pose-CSV schema: a header-keyed codec in tlm.py

## Description

Three pose-CSV schemas, one reader that guesses.

| writer | header | units |
|---|---|---|
| `tour_capture.py` | `t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg` | wire (mm, cdeg) |
| `tour_watch.py` | `t,dev_ms,enc_x_cm,enc_y_cm,enc_h_deg,otos_x_cm,otos_y_cm,otos_h_deg` | cm, deg |
| `tour_practice.py` | `t,enc_x,enc_y,enc_h,otos_x,otos_y,otos_h,dev_ms,vl_mms,vr_mms` | cm, deg |

`tour_chart.py` decides the shape by **column count** (`len(pose_all[0])
>= 5`, `>= 8`) and assumes wire units throughout (`MAX_POSE_MM`,
`end_h = pose[-1][3] / 100.0`, `oh0 = math.radians(pose[0][3] / 100.0)`).
A `tour_watch` pose CSV has eight columns, so it is **accepted**, plotted
10x too small, with heading divided by 100 and the OTOS diamonds landing
on the wrong columns -- and the chart title prints a confident "closure
N mm". No error is raised. `leg_analysis.py` hard-codes the
`tour_capture` header only.

`tlm.py` went to the trouble of binding wire columns **by name** from
the last `thdr` precisely so a shape change is handled. The CSV layer
regressed to positions. The fix puts the codec beside the thing that
already does it right -- see the sprint's Design Rationale 8 for why
this lives in `tlm.py` rather than a new module.

Riding along: **TL-17**, `tour_chart.py --meta`. It reads
`start_world_cm[2]` as **radians** (`rot = wh0 - oh0` against an `oh0`
that went through `math.radians`), no `tools/` script writes the field
at all, and the help text does not state the unit. Every `camlink`
sample in this repo is `yaw_deg`. A future writer using the tools' own
unit gets a 57x rotation and a plausible-looking overlay.

## Acceptance Criteria

- [ ] `tlm.py` has one pose-CSV writer and one reader. The reader binds
      columns **by header name** and never by count or position.
- [ ] The surviving schema is `tour_capture.py`'s wire-unit header --
      it is already the only one `leg_analysis.py` reads and already what
      `tour_chart.py` assumes throughout.
- [ ] `tour_watch.py` and `tour_practice.py` write it.
- [ ] `tour_chart.py` and `leg_analysis.py` read through it; the
      column-count branch is gone.
- [ ] A CSV carrying a legacy header is either converted or **refused
      with a message naming the file and the schema it found**. It is
      never silently mis-scaled. Which of the two is your call; refusing
      clearly satisfies the sprint's success criterion.
- [ ] An unknown header is refused, not guessed at.
- [ ] `--meta`'s `start_world_cm[2]` has one documented unit (degrees,
      matching every camera sample in this repo), the code converts
      rather than assuming, and `--help` says the unit.
- [ ] Existing files under `captures/` are **not** rewritten. This is a
      format change for new recordings; old captures are handled by the
      reader's legacy path or refused.

## Implementation Plan

### Approach

1. Add the column list, `write_pose_csv()` and `read_pose_csv()` to
   `tlm.py`, modelled on its existing `write_tlm_csv` /
   `read_meta_sidecar` fail-loud trio.
2. Follow `.claude/rules/no-units-in-identifiers.md` for any new Python
   identifier: the unit goes in a trailing `# [unit]` comment on the
   declaration, not in the name. The *CSV column names* keep their
   `_mm`/`_cdeg` suffixes -- those are wire field names, which that rule
   explicitly exempts, and they are what makes the header
   self-describing.
3. Migrate the two writers, then the two readers.
4. Handle `--meta`.

### Files

- `tools/tlm.py` -- the codec.
- `tools/tour_watch.py`, `tools/tour_practice.py` -- writers.
- `tools/tour_chart.py`, `tools/leg_analysis.py` -- readers; delete the
  column-count branch.
- `tests/tools/test_tlm.py`, `tests/tools/test_leg_analysis.py`.

### Re-anchoring

Line numbers in the issue are from 2026-09-02 and have moved (the
writers are at `tour_capture.py:133`, `tour_watch.py:219`,
`tour_practice.py:148` today). Grep for `writerow`, `read_csv`,
`MAX_POSE_MM`, `start_world_cm`.

### Depends on

Ticket 003 -- so this never migrates a file that is about to be deleted.

## Testing

- **Existing tests to run**: `uv run pytest tests/tools/test_tlm.py
  tests/tools/test_leg_analysis.py tests/tools/test_tour_capture.py -q`
  (foreground, scoped).
- **New tests to write**:
  - Round-trip: write rows, read them back, assert equality including
    units.
  - **The regression that motivates the ticket**: build a legacy
    `tour_watch`-schema CSV (cm/deg, eight columns) in the test's own
    tmp dir, feed it to the reader, and assert it is converted correctly
    **or** refused with the filename in the message -- and explicitly
    assert it is *not* silently returned at 1/10 scale.
  - A legacy `tour_practice`-schema CSV (ten columns).
  - An unknown header raises, naming the file.
  - A header-only file, and an empty file.
- **Verification command**: `uv run pytest tests/tools/test_tlm.py
  tests/tools/test_leg_analysis.py tests/tools/test_tour_capture.py -q`
