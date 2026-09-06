# Vevov Encoder Tour, 2026-09-06

Stakeholder assigned Vevov on the farm stand, wheels up, with OTOS off.
This is encoder odometry, not a physical ground track or a field-accuracy test.

## Result

MEASURED Vevov 2026-09-06, `tour.log`, `tour_pose.csv`, `tour_vel.csv`,
`tour_tlm.csv`, and `result.log` in this directory:

- `RUN:tour:wheels` returned all four corner markers and `TOUR:end:ok`.
- The commanded rectangle was 100 x 60 cm; the program uses 200 mm/s
  straight cruise and 90 degrees/s nominal yaw rate.
- Final encoder pose: (-26, 17) mm, heading 355.65 degrees.
- Encoder closure: 31.06 mm; heading residual: -4.35 degrees.
- 459 decoded telemetry frames, zero dropped, zero malformed; 458 pose
  rows after the subscription's initial liveness frame.
- `otos=0` before and after the tour; optical pose columns stayed zero.
- Jerk read back as 800.000061 mm/s^3; lag remained the existing Vevov
  bake of 0.04 seconds. That legacy lag is not a newly fitted response
  constant. Host simulation uses a different, unfitted 0.13-second model.
- `i2cf` rose from 0 to 45. This is an unresolved diagnostic counter,
  not telemetry packet loss; no claim of a fault-free motor run is made.
- Final status in `shutdown.log`: ready=1, active=0, both encoders
  connected, otos=0, tlm=off. `reason=timeout` is the completed zero-speed
  preflight hold's wire obligation, not the cleartext tour's outcome;
  the latter is the separate `TOUR:end:ok` record.

Graph: `reports/vevov-square-bench-20260906/encoder-square.png`, opened in
a separate Preview instance. Summary: the neighboring `summary.json`.
The capture supports a completed encoder tour, not a before/after hardware
improvement claim: no baseline firmware tour was recorded in this session.

## Firmware And Validation

`firmware.hex` is the exact flashed image, SHA-256:

```
c83276e1af5b74eeba86018bf1c962c2353405a82096052a70fde04e98e6f8e0
```

Built with `uv run python tools/make_deploy.py --robot vevov --no-otos`.
`build.log` records a clean compilation and its translation-unit checks.
`flash.log` records the farm erase recovery and successful programming.
Identity read from the board: `device NEZHA2 robot vevov 1198504156`;
firmware ID: `id diffdrive vevov 1.20260906.2 vevov`.

This is a USB/farm bench image: the worktree has no WiFi secrets and the
normal test-program radio default is off, so both wireless carriers are
disabled. OTOS boot initialization is skipped; the wheels tour also avoids
world sampling and sensor corner reads. The regular build default is unchanged.

HOST TESTED 2026-09-06, no hardware board involved, `regression.log`:
1877 passed in 80.08 seconds. Controller comments and indentation were
cleaned up after flashing; no behavior changed after the recorded build.
The updated host plot is `reports/tovez-sim-square-20260906/sim-square.png`;
its `final-simulation.log` reports 17.0 mm / -1.67 degrees with jerk 800,
and 4.8 mm / -0.53 degrees with jerk disabled. These are model results,
not Vevov measurements.

`bench.py` records a session with identity, readiness, OTOS and jerk
readback guards; `plot.py` regenerates the graph using `tools/tlm.py`'s
pose schema. Resolve Vevov's current farm endpoint again before reusing
the recorder, since the recorded socket is not a permanent assignment.

## Master Integration

Integrated committed master `bb4e2dd` with motion fix `974b52b`, retaining
master's comment cleanup and the earlier simulator I2C extraction.
The conflicts in the engine and shaper retained the lag-aware drive,
rest-confirmed completion, and jerk-aware floor behavior. Motor-port
comments were shortened to satisfy master's comment-volume gate.

HOST TESTED 2026-09-06, no hardware board involved,
`merge-regression.log`: all 1879 tests passed in 87.70 seconds on the
combined tree. This does not replace or imply a repeat of the earlier
hardware capture; the flashed image is still identified by the hash above.