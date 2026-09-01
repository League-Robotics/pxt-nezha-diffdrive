# tigez calibration — 2026-08-30 (playfield, camera-truthed)

First full calibration pass on tigez, per the stakeholder's scheme:
camera pose → 80 cm straight → rotation sweep → tag-mount circle solve
→ refinement → NE-dot square tour. Raw data:
`captures/tigez-cal-20260830/cal.jsonl`. Values also written to
`radio-robot-lib/config/robots/tigez.json` (vision + geometry blocks).

## Measured values

| quantity | value | how |
|---|---|---|
| travelCalib | **0.78623 mm/deg** (L 0.78642 / R 0.78603) | 80 cm commanded, 800.9 mm camera, 10184/10189 tenth-deg counts |
| wheel diameter | **90.10 mm** | travelCalib x 360 / pi |
| track width | **114.4 mm** (sd 4.4) | 8-pivot sweep +-45/90/135/180, camera yaw vs encoder arcs |
| rotation | physical = **1.038 x commanded − 0.83°** at baked defaults | same sweep, unwrapped fit |
| rotational_slip (fw 0.20260829.2) | **0.992** | live-trimmed: gain 1.042 → 0.986 |
| tag mount (tag 57) | lever **(−0.67, −0.02) cm**, yaw **−89.65°** (see correction), z **11.7 cm** | 9-pose circle solve, rms 0.18 cm; verified 0.10 cm wobble/90° |

The −0.83°/turn offset is deliberately NOT folded into the slip
(fixed offsets never belong in scale constants — see
`clasi/issues/calibration-skill-emits-a-paste-able-makecode-block.md`).

## Paste-able MakeCode block

Paste at the TOP of the student program (values are tigez's, measured
2026-08-30 — recalibrate after any rebuild):

```javascript
// ---- tigez calibration 2026-08-30 -- paste at the TOP of your program ----
diffDrive.setTrackWidth(11.44)                             // cm, measured
diffDrive.setWheelCalibration(0.78623)                     // mm per shaft degree
diffDrive.setConfigValue(ConfigField.RotationalSlip, 0.992)
// tag 57 rides 6.7 mm behind the centre of rotation, 117 mm up,
// rotated +91.15 deg -- registered with the AprilCam daemon, not here.
```

UNVERIFIED: this exact snippet has not yet been compiled through a
MakeCode build (same caveat as the issue's draft). The RotationalSlip
value was trimmed on fw 0.20260829.2's rotation model; re-verify the
gain once on a MakeCode-built hex before classroom use.

## Verification tour

See `reports/tigez-field-square-20260830.md` (NE orange dot, 100 x 60
orange-dots rectangle, camera-scored).

## Correction (2026-08-31)

The +91.15° mount yaw measured above described a tag plate that was
mounted ~90° off — the plates are REMOVABLE (top = robot front) and
it was later remounted correctly. With the plate on correctly the
registration is **−89.65°** (verified: aprilcam yaw reads true
heading ±1°; 180° pivot wobble 0.50 cm). The ~−90 every fleet tag
carries cancels aprilcam's yaw convention (tag x-axis/paper-right),
not physical rotation. Registrations are in-memory per-session —
re-register and probe-fit at every session start. Full story:
`reports/tigez-field-square-20260831.md`.
