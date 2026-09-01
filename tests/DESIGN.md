# tests — Python-run test root

**Owner:** Eric Busboom · **Last reviewed:** 2026-09-01 · **Status:** stable

Every test in this tree lives in a subdirectory named for its **type**,
and the type answers one question: *what does it need, and does CI run
it?*

| directory | needs | run by `uv run pytest` | lifetime |
|---|---|---|---|
| [`host/`](host/DESIGN.md) | a C++ compiler | yes | permanent |
| [`tools/`](tools/DESIGN.md) | nothing | yes | permanent |
| [`system/`](system/DESIGN.md) | a real robot | **no** — run by hand | permanent |
| `dev/` | a real robot | **no** | disposable |

`uv run pytest` from the repo root runs `host/` and `tools/` and nothing
else. That is deliberate: the other two need hardware that is not
present in a clean checkout, and a suite that cannot run everywhere is
not a suite.

## The two permanent pytest suites

- **`host/`** — this extension's portable firmware C++ (kernel, motion
  engine, v6 wire stack, wire adapter) compiled for the desktop with the
  system compiler and driven from pytest through `ctypes`, against fake
  ports. No micro:bit, PXT, or CODAL anywhere in the link.
- **`tools/`** — plain-Python unit tests over `tools/` scripts' own
  logic, no shim compilation and no hardware or network.
  `test_make_deploy_triage.py` pins `tools/make_deploy.py`'s
  `classify_attempt()` against saved/synthetic build logs;
  `test_tlm.py` pins `tools/tlm.py`'s `TlmStream` parser against the
  shared golden fixture in `tests/host/golden_telemetry.py`.

## `system/` — the hardware tour suite

Not pytest. `system/run_tour.py` drives a **real robot** through a
`.tour` script and charts what came back, so it is run deliberately,
one tour at a time, at a bench with a board attached:

```
uv run --with numpy --with matplotlib python tests/system/run_tour.py \
    tests/system/tours/square.tour --host localhost --out reports/tours-<date>
```

`system/tourfile.py` parses the `.tour` format (documented in its own
docstring) and `system/tours/` holds the figures. These are permanent —
they are the regression the motion work is judged against, re-run
whenever shaping, geometry, or a robot's tuning changes. Results go to
`reports/` as markdown with the charts beside them.

## `dev/` — development scripts, deliberately disposable

Measurement harnesses written to answer **one open question**. They are
kept only while that question is open; when it closes, or when a
permanent test or a `.tour` covers the same ground, the script is
deleted rather than left to rot. Nothing imports from here, and nothing
in CI touches it.

Currently live:

- `closure.py` — square-tour closure on the bench in pure odometry,
  with the tuning knobs (`--overrun`, `--twist`, `--floor`,
  `--yawtaper`) as flags. Backs `reports/gopiv-closure-20260901.md`;
  keep while closure tuning is still being re-measured per robot and
  per battery.
- `sweep_tcp.py` — measures the velocity profile the wheels **actually**
  execute over a farm-node serial daemon: peak speed, accel ramp, decel
  slope, braking distance. The one thing the host harness cannot
  supply, because it measures the compiled engine rather than the robot.

Deleted 2026-09-01, and why, as the standard for what belongs here:
`tight_tour.py` (superseded by `system/run_tour.py`, which does the same
job for any `.tour` file and charts it) and `profile_probe.py` (asked
what shape the compiled profile has; that is now pinned by
`host/test_motion_engine_acceleration_profile.py` and friends, so a
script that prints it answers nothing a failing test would not).

Not to be confused with the sibling `test/` root (singular) — those are
PXT `testFiles`, on-robot MakeCode programs with no assertions,
documented in [`test/DESIGN.md`](../test/DESIGN.md). `RUN:square`,
`RUN:infinity` and `RUN:spline` live there: the same three figures
`system/tours/` drives from the host, but running on the robot itself.
