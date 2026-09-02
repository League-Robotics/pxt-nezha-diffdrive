---
status: pending
sprint:
---

# `goToWorld` still overshoots by a fixed ~50 mm on corrected firmware — the 2026-08-25 finding restated against 67455bf

## Summary

Sprint 020 re-measured `goToWorld` absolute arrival on firmware
containing every sprint 015/016 motion correction (arc consolidation,
phase-handoff fix, stop delivery, timeout budget) plus the verified
`travelCalib` 0.7878. **The fixed overshoot survives, essentially
unchanged**: median 48.1 mm then, **50.6 mm now**.

MEASURED vevov 2026-08-26/27, `captures/gotoworld-arrival-20260826.csv`:
ten camera-seeded, camera-scored single hops at 42–97 cm leg length,
firmware 67455bf (flash provenance in
`captures/travelcalib-verify-20260826.csv`):

- median position error **50.6 mm**, p90 64.6 mm, max 84.7 mm
- **0/10 within 20 mm**, 5/10 within 50 mm
- the error is along-track PAST the target, ~35–44 mm at every leg
  length — fixed distance, not proportional, same character as the
  original
- closure contrast: three seeded `tour:world` runs arrived 29–32 mm
  from the final corner; consecutive tours landed 7–12 mm apart.
  Chaining flatters the fixed overshoot, as the original campaign found.

Secondary observation: believed-vs-camera error (OTOS drift) was
1.3–6.4 cm per hop, and the two worst arrivals (63.8 and 84.7 mm) were
both westward legs along the field's north side with the largest belief
errors — at the top of the range, sensor drift rivals the control
overshoot.

## Where to look (carried over, still unanswered)

The original diagnosis fork stands: ramp-down/taper stopping distance
not subtracted from the planned segment, vs. late `serviceMove()`
completion. `tools/leg_analysis.py`'s `straight-overrun` classifier
(sprint 011 ticket 002) was built for exactly this shape and has not
yet been run against the new capture. Note `RUN:straight` at the same
speeds does NOT overshoot (campaign 1: encoder vs commanded within
0.1–0.3 %), so the defect is specific to the goTo path
(`startGoTo()`/`goToR()`), not the shared shaping.

Related: `goto-under-closed-profile-terminates-legs-early.md` — found
in the same campaign, on the same verb.
