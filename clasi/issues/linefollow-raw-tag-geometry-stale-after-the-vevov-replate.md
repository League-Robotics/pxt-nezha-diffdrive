# tools/linefollow/ raw-tag geometry is stale after the vevov replate

**Opened:** 2026-09-05 · **Robot:** vevov (tag 53) · **Severity:** medium
(silently wrong geometry, not a crash)

## What

`tools/linefollow/follow.py`, `camlog.py`, `stage.py` and `sensor_run.py`
all read vevov's entry in `tools/field_calibration.json` for the RAW-tag
path:

```python
LEVER, K, CAM, TAG = _E['lever_cm'], _E['parallax_k'], _E['camera'], _E['tag_number']
```

That path is legitimate — the daemon does not correct a raw reading, so
the tool must (`tools/DESIGN.md`; `tests/tools/test_parallax_ownership.py`
pins exactly which files may divide by a tool-side `parallax_k`).

vevov's `lever_cm` and `parallax_k` are now the registered-mount
placeholders `[0.0, 0.0]` and `1.0`, so the raw-tag path is **not
calibrated**.

## Why this is not a regression from the edit that exposed it

The previous values (`lever_cm` `[0.227, -2.727]`, `parallax_k` 1.1192)
were fitted on 2026-09-02 against the tag plate's **old** position
(`captures/vevov-cal-20260902/02-levercal-pass1.txt`,
`03-levercal-pass2.txt`, `04-probe-50cm.txt`).

vevov's plate was found mounted **backwards** and was physically
remounted on 2026-09-05 — MEASURED, `reports/pf2-recal-20260905/`:
`02-mount-vevov.log` (178.6 deg probe gap), `03-probe-verify-vevov.log`
(the same gap in the other direction under a temporary residual-180
registration, which is what proved the remount), `04-mount-vevov-replate/mount.json`
(post-remount solve, lever -2.79/+0.03 cm, rms 4.8 mm). The old numbers
described a plate position that no longer exists, so they were obsolete
either way.

The 2026-09-05 recalibration solved the mount for the **registered**
path (`mount_x_cm`/`mount_y_cm`/`mount_z_cm`, which the daemon applies
itself). It did not re-fit the raw-tag pair, because nothing in that
session used the raw-tag path.

## What would settle it

A fresh raw-tag pivot solve on vevov, as
`captures/vevov-cal-20260902/` did: in-place +-90 pivots with the tag
UNREGISTERED, least squares over `tag = centre + R(yaw) * lever`, plus
two opposing 50 cm legs for `parallax_k`. Write both back into vevov's
entry and drop the `_linefollow_hazard` note.

Until then, treat any `tools/linefollow/` run on vevov as
geometrically uncalibrated — the line follower's own sensor loop
(PlanetX Trackbit) is unaffected; it is the camera-mapped logging and
staging that read these keys.

## Related

- `.claude/rules/tag-yaw-is-the-front-edge-not-the-hat.md`
- `clasi/sprints/done/031-drivetrain-tuning-and-gate-acceptance-on-tovez/issues/done/parallax-k-and-registered-mount-z-correct-twice.md`
- `reports/pf2-recal-20260905/NOTES.md`
