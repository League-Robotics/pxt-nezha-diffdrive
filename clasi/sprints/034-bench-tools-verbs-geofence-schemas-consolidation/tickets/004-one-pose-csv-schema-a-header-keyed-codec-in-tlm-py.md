---
id: '004'
title: 'One pose-CSV schema: a header-keyed codec in tlm.py'
status: done
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

- [x] `tlm.py` has one pose-CSV writer and one reader. The reader binds
      columns **by header name** and never by count or position.
- [x] The surviving schema is `tour_capture.py`'s wire-unit header --
      it is already the only one `leg_analysis.py` reads and already what
      `tour_chart.py` assumes throughout.
- [x] `tour_watch.py` and `tour_practice.py` write it.
- [x] `tour_chart.py` and `leg_analysis.py` read through it; the
      column-count branch is gone.
- [x] A CSV carrying a legacy header is either converted or **refused
      with a message naming the file and the schema it found**. It is
      never silently mis-scaled. Which of the two is your call; refusing
      clearly satisfies the sprint's success criterion.
- [x] An unknown header is refused, not guessed at.
- [x] `--meta`'s `start_world_cm[2]` has one documented unit (degrees,
      matching every camera sample in this repo), the code converts
      rather than assuming, and `--help` says the unit.
- [x] Existing files under `captures/` are **not** rewritten. This is a
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

## Implementation record

**API.** `tools/tlm.py` gained `POSE_CSV_COLUMNS`,
`POSE_CSV_WHEEL_COLUMNS`, `POSE_CSV_SCHEMA`, `PoseCsvSchemaError`,
`write_pose_csv(rows, path, wheels=False) -> int` and
`read_pose_csv(path) -> (rows, schema)`. A row on BOTH sides of the
codec is a decoded telemetry frame (`x`/`y`/`h`/`ox`/`oy`/`oh`, `now`,
optional `vl`/`vr`) plus a host-side `t_host` -- so a recorder writes
`dict(frame, t_host=time.time())` unconverted and a reader hands a CSV
row straight to `pose_cm()`/`otos_cm()`/`wheels_mms()`. No tool carries
a scale factor of its own; `tlm.py` remains the one place any exists.
`write_pose_csv()` refuses a row missing a required key (a blank cell
reads downstream as a real zero) but does NOT refuse a zero-row
capture: that guard is `write_tlm_csv()`'s and its `.meta.json`
sidecar's, already applied to the same run in one place.

**Legacy-header decision: CONVERT the headers this repo's own tools
wrote, REFUSE everything else naming the file and the header found.**
Converting was chosen over blanket refusal because the whole point of a
recording is to still be readable, and a rename-and-rescale against a
named header is not a guess -- the conversion factors are the inverse
of `pose_cm()`/`otos_cm()`'s, written beside them. The headers on this
working tree's own recordings were surveyed rather than assumed
(2026-09-06), which found two variants the ticket's table did not
list, both now converted: `tour_practice`'s WITHOUT the wheel pair and
with the older `vl_cms`/`vr_cms` spelling (optional plans on one legacy
entry), and the wire-unit variant with unsuffixed OTOS columns
(`...,h_cdeg,ox,oy,oh`) that seven `captures/` files carry -- refusing
that one would have cost seven recorded runs over a suffix. All 35
pose CSVs under `captures/` and `.tmp/` were read back through the
codec read-only: 23 read (every one under `captures/` among them), 12
refused, all 12 scratch files under `.tmp/`.

Two real historical shapes are deliberately refused rather than
converted, and both refusals are for the same reason -- a column the
schema needs is ABSENT, not zero, and fabricating it would put data on
a chart that no instrument ever produced. The pre-OTOS five-column
`t_host,t_dev_ms,x_mm,y_mm,h_cdeg` (4 files) has no OTOS columns:
zero-filling them would draw a sensor that said nothing as a boundary
fix at the world origin, exactly the failure `tour_chart.py`'s own
`otos_dead` check exists to prevent. The earliest `tour_practice`
variant, `t,enc_x,...,otos_h` with no `dev_ms` (8 files), has no device
clock, which is the timebase every consumer segments legs and plots
against. Both refuse by name, with the header they found.

**Files migrated.** Writers: `tour_capture.py`, `tour_watch.py`,
`tour_practice.py` (the last now writes the optional wheel pair).
Readers: `tour_chart.py` (its `len(pose_all[0]) >= 5`/`>= 8` branch
deleted), `practice_chart.py` (was reading the OTOS track positionally
at `p[4]`/`p[5]`), `leg_analysis.py` (its hard-coded `POSE_CSV_FIELDS`
is now an alias for `tlm.POSE_CSV_COLUMNS`, and it no longer names a
CSV column). All three readers convert `PoseCsvSchemaError` into this
project's `SystemExit` CLI convention, so an unrecognised file is a
one-line refusal rather than a traceback.

**TL-17.** `tour_chart.py --meta`'s `start_world_cm[2]` is DEGREES --
one documented unit, matching every `yaw_deg` camera sample in this
repo; the code converts with `math.radians()` where it previously
consumed the value as radians, and `--help` states the unit.

**Verification.** `uv run pytest tests/tools/test_tlm.py
tests/tools/test_leg_analysis.py tests/tools/test_tour_capture.py -q`
-> 94 passed; `uv run pytest tests/tools -q` -> 472 passed. The chart
tools cannot be imported under this project's test venv (no
matplotlib), so their migration was additionally smoke-tested by
running both against synthetic fixtures under `uv run --with
matplotlib`: a wire-unit capture and the equivalent legacy `tour_watch`
capture now produce the SAME chart (closure 318 mm both ways, where the
legacy one used to be read 10x small), and a camera CSV handed in by
mistake is refused by name instead of plotted.
