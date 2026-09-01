---
status: done
---

# `dist_taper` retained as a window ceiling silently defeats constant-decel above ~200 mm/s

## Description

Sprint 025 ticket 001 kept `distTaper_` as a **ceiling** on the braking
window, so the constant-deceleration solve only engages once
`remain <= distTaper_`. With the shipped default (`distTaper_` = 400 counts
≈ 31.5 mm) that ceiling is smaller than the braking distance the new law
needs at any useful speed, so the feature is inert exactly where it matters.

Braking distance under constant `a` is `v²/(2a)`. At `a_decel = 300 mm/s²`:

| cruise | needed window | vs 31.5 mm default |
|---|---|---|
| 100 mm/s | 16.7 mm | fits |
| 200 mm/s | 66.7 mm | **2.1x too small** |
| 300 mm/s | 150 mm | **4.8x too small** |
| 400 mm/s | 267 mm | **8.5x too small** |

MEASURED gopiv 2026-09-01, sprint-025 firmware, 300–400 mm legs over the
magni USB serial daemon (lossless), `captures/gopiv-profile-sweep-20260901/`
(`sweep_gopiv_baseline.json`, `sweep_gopiv_shaped.json`,
`sweep_gopiv_wide.json`; capture script `sweep_tcp.py`):

**Legacy** (`accel=0 decel=0`, `sweep_gopiv_baseline.json`) — the brake
window is pinned near 25 mm at every speed, so demanded decel grows as v²
and the ramp-down collapses to one control tick:

| cruise | brake window | decel achieved | ticks decelerating |
|---|---|---|---|
| 100 | 27.7 mm | 149 mm/s² | 6 |
| 200 | 27.0 mm | 623 mm/s² | 4 |
| 300 | 21.1 mm | 2 180 mm/s² | 2 |
| 400 | 25.4 mm | unmeasurable | **1** |

**Shaped, default taper** (`accel=500 decel=300`, `dist_taper` left at 400
counts, `sweep_gopiv_shaped.json`) — 400 mm/s is still a one-tick stop:

| cruise | brake window | ticks decelerating |
|---|---|---|
| 100 | 18.8 mm | 3 |
| 200 | 27.9 mm | 5 |
| 300 | 152.6 mm | 3 |
| 400 | 29.7 mm | **1** |

**Shaped, ceiling raised** (`dist_taper 5000` counts ≈ 394 mm,
`sweep_gopiv_wide.json`) — the ramp-down appears:

| cruise | brake window | predicted `v²/2a` | ticks decelerating |
|---|---|---|---|
| 200 | 209.4 mm | 66.7 mm | 5 |
| 300 | 153.8 mm | 150.0 mm | **13** |
| 400 | 196.6 mm | 266.7 mm | **14** |

At cruise 300 the measured window (153.8 mm) matches the constant-`a`
prediction (150.0 mm) to 2.5%. At cruise 400 the ramp-down goes from
**1 control tick to 14**.

## Cause

`serviceMove()`'s constant-`a` branch is gated behind the same
`remain <= distTaper_` window test the legacy taper uses, so
`distTaper_` bounds how early braking can begin. The sprint architecture
called for retaining it "as a window ceiling" to guarantee the new law
could never widen a move beyond the old behaviour — a conservative choice
that turns out to cap the feature below its useful range.

## Proposed fix

When `aDecelMmS2_ > 0`, derive the braking window from the kinematics
rather than from `distTaper_`: engage the solve when
`remain_mm <= v_cmd² / (2 * aDecelMmS2_)` (plus a small margin). Keep
`distTaper_` authoritative only in legacy mode. If a ceiling is still
wanted as a safety bound, it must default to something at least as large
as `vMaxMmS_² / (2 * aDecelMmS2_)` — with the shipping `vMaxMmS_` of
250 mm/s and `a_decel` 300, that is ~104 mm ≈ 1320 counts, not 400.

Note this interacts with the ticket-002 distance-chosen default: because
`v_default` already limits speed by leg length via `brakeFrac_`, a
correctly-derived window and the default-cruise policy agree by
construction — both are the same `v² = 2ad` relation.

## Verification

Re-run `captures/gopiv-profile-sweep-20260901/sweep_tcp.py` against gopiv
with `dist_taper` left at its default; the shaped-mode ramp-down at
cruise 300 and 400 must show the same tick counts as the ceiling-raised
run above (13 and 14) without needing the manual `SET dist_taper`.
Host-side, extend `tests/host/test_motion_engine_acceleration_profile.py`
with a case at cruise 400 that asserts the braking window tracks
`v²/(2a)` while `distTaper_` is at its default.

## Related

- `clasi/issues/trajectory-shaping-constant-acceleration-profiles-speed-chosen-by-distance.md`
  — the parent issue; this is a defect in its ticket-001 implementation,
  found during the Tier-2 bench sweep it called for.
- Sprint 025, ticket 001 (`tickets/done/001-...`) — where the ceiling was introduced.
