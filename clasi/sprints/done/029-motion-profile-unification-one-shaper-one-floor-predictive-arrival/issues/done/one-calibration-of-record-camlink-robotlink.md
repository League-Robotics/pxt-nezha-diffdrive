---
status: done
sprint: 029
tickets:
- 029-006
---

# One calibration of record: camlink reads field_calibration.json and never re-registers a stale mount; robotlink derives the relay address from the board name

Priority: **Critical** · Source: [code review 2026-09-02](../../../docs/code-review/2026-09-02/review.md)

Findings: TL-01, TL-02, TL-11 ([tools-and-tests](../../../docs/code-review/2026-09-02/raw/tools-and-tests.md)). Triage #19.

## Description

**TL-02 (Critical).** `tools/camlink.py:55` carries
`MOUNTS[53] = (-3.61, -0.05, 11.8, -pi/2)`; `Cam.__init__` ->
`ensure_registered()` (`:80-96`) sends every entry to the aprilcam daemon
with `register_tag()` unconditionally. Mount registrations now persist in
the daemon (`state_dir/mounts/registry.json`), so this is an overwrite,
not "cheap idempotent insurance". `tools/field_calibration.json` (MEASURED
vevov 2026-09-02, after the tag-53 remount) holds a different lever and
`field_dance.py` assumes the raw tag. Whichever tool ran last decides what
the daemon reports as vevov's centre, silently. The 2026-08-31 rails crash
was a pose disagreement of exactly this shape.

**TL-01.** `tools/robotlink.py:21-22` `ZAVAZ_CHANNEL = 4, ZAVAZ_GROUP = 10`;
vevov moved to 37/43 on 2026-08-30 (`playfield-testing.md`,
`field_calibration.json`). Every `open_link(radio=True)` tool tunes the
relay at nothing and presents as a silent robot. `test_robotlink.py:183`
pins the stale constant.

**TL-11.** `field_calibration.json` stores the fixed +90 deg convention as a
probe-fitted 91.116 deg -- the recurrence
`tag-yaw-is-the-front-edge-not-the-hat.md` forbids.

## Remedy

- `field_calibration.json` is the one calibration of record; `camlink`
  loads it, registers only what it loaded, and only on an explicit
  `--register`, never as a constructor side effect. Delete `MOUNTS`.
- `robotlink` derives channel/group from the board name (the relay's `!N`
  derivation, `radio-address-derived-from-board-name`) or reads them from
  `field_calibration.json`; fix the pinned test.
- Store only the sub-degree mount residual; the +90 is the convention.

## Acceptance

- Starting any camproc tool leaves the daemon's registry unchanged.
- `open_link(radio=True)` on vevov gets a pong on the first try.

## Related

- `camlink-mounts-table-is-stale-for-tigez.md` (sprint 027, done) fixed
  tag 57 the same way tag 53 has now gone stale.
