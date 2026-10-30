---
status: pending
---

# Sprint 044 close-out housekeeping

- A bare `uv run pytest` fails collecting `test_field_dance_accel_bake.py`
  without a camera daemon (`field-dance-test-needs-a-live-camera-daemon-to-collect.md`).
- The canonical `docs/design` edits ticket 011 deferred.
- `.tmp/deploy-head.stale-*` directories from make_deploy's partial-build
  check.
- Ticket 009 left open items, carried here:
  - tigez encoders-only leg run (never run).
  - Arrival median < 1 / p90 < 2 cm held only on `tovez-drift5`; vevov runs 1.4-1.7 / 2.6-3.2 cm.
  - vevov `otos_linear_scale` 1.033 reads ~1.4 % long over 92 m (leg-distance ratio 1.0139); try 1.023.
  - Arms still to measure and bake: gopiv, zuvat, tigez; tovez wants a camera-referenced arm fit.
- aprilcam loses tag 53 at rest in the south band (y -25..-30) for >15 s while it is plainly in
  the frame; MCP `get_tag` does not report tag 53 at all while devlink `Cam` does.
