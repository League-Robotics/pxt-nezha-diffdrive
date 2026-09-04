---
status: pending
---

# `parallax_k` and a registered `mount_z_cm` correct the same parallax twice

Priority: **Medium** · Found 2026-09-04 during sprint 029 ticket 007 on tovez.

## Description

`tools/camlink.py::Cam.register()` registers a robot tag with its
`mount_z_cm`, and the aprilcam daemon then applies the tag-height
parallax correction itself (`list_tag_parameters` reports
`mount_z_applied: true`). `tools/field_dance.py` (`drive()`, the
return-home check) ALSO divides camera distances by the entry's
`parallax_k`. For tovez (mount_z 11.3 cm registered, k 1.1167 borrowed
from vevov) every drive read ~12 % short:
`captures/bench-acceptance-029-20260904d/field-dance-refit-run1.log`
(17.6 cm for 20, 35.3 cm for 40 -- i.e. 20/1.1167, 40/1.1167), while a
raw 5 cm probe of the registered position read 4.87 cm
(`heading-probe.log`). Same shape as the +90 deg double-add fixed in
fc5588f: two layers each believing they own a correction.

Stop-gap applied: tovez's `parallax_k` set to 1.0 in
`tools/field_calibration.json` with a MEASURED note. vevov's tag 53 is
registered with `mount_z 0` and still relies on its k = 1.119.

## Remedy

Pick one owner for parallax: register `mount_z_cm` for every robot and
delete `parallax_k` from `field_calibration.json` and from every tool
that divides by it (`field_dance.py`, and audit `reposition.py`,
`park.py`, `tour_*.py`, `leg_analysis.py`, `pivot_truth.py`), or keep
the tool-side factor and register `mount_z 0`. Add a host test that a
registered tag's distance is used unscaled. Re-fit vevov's entry
accordingly and cite the capture.
