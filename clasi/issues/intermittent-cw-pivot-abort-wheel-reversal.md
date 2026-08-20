---
status: pending
---

# Intermittent CW pivot abort — suspected wheel-reversal failure

> **DIRECTION LABELS IN THIS ISSUE ARE INVERTED (2026-08-19, camera-
> measured).** vevov's rotation was mirrored: commanded sign and physical
> direction were opposite, because both motor fwdSigns had been flipped
> and `NezhaMotorPort` applies fwdSign to the encoder as well as the duty,
> so odometry agreed with the command while the robot turned the other
> way. Measured on one commanded `+360` CCW pivot: odometry believed
> **+360.83 deg**, AprilCam measured **−342.58 deg**.
>
> Consequence for this issue: the `-360` command that aborted was
> physically **counter-clockwise**, and the `+360` runs that were clean
> were physically clockwise. The failing wheel is therefore the OPPOSITE
> side from whatever "CW pivot" implied here, and the reversal-dwell
> hypothesis below is aimed at the wrong motor.
>
> A port-swap fix (`left{1,-1}` / `right{2,+1}`, each motor keeping its
> own sign) is committed and flashed but **UNVERIFIED** — the Nezha brick
> was off charge. Re-measure a `+360` "P" pivot under the camera first;
> until then treat every direction word below as suspect, and re-derive
> which physical side fails rather than trusting the text.

## Description

Bench-observed on vevov (2026-08-19, camera-instrumented): a commanded
-360 deg in-place pivot aborted at ~-191 deg believed with ~22 cm of
odometric translation (camera confirmed ~7.5 cm physical displacement
and a wildly wrong final heading) — the move engine's deadline killed
it. The IDENTICAL command retried immediately afterward ran perfectly
(-360.84 believed, ~zero translation).

A pivot that translates means one wheel under-rotated grossly.
Suspected cause: the Nezha brick's known H-bridge reversal behavior —
one motor failing to take its direction flip (the port's 100 ms
reversal dwell + write-shaping exists to guard exactly this class, but
evidently doesn't fully close it). CCW pivots have not shown the
failure; the square tour (all CCW turns) is unaffected so far.

Repro rate: 1 of 2 CW attempts that session. Next steps: instrument
DIAG during a CW pivot (wedge/wedge-suspect flags, per-wheel duty and
velocity), check whether the failing wheel is consistently the same
side, and consider strengthening the reversal-dwell or adding a
reversal-verify (commanded sign vs measured velocity sign after dwell)
in the port layer.
