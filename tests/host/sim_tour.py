"""sim_tour.py -- run a tour against the WHOLE firmware stack on the host.

This is the tier radio-robot-elite calls `--tier sim` (its
`src/tests/system/systest.py`): simulated motors and encoders, real
motion control. The firmware under test here is the real
`NezhaMotorPort` pair -- sigma-delta duty quantizer, output deadband,
slew limiter, write throttle, reversal dwell, encoder glitch armor --
under the real `DifferentialDrive` kernel, `MotionEngine` and
`VelocityShaper`, talking to a simulated Nezha brick over the real
8-byte I2C frame (`tests/host/sim_nezha_bus.h`).

Everything below `diffDrive::I2CBus` is simulated. Everything above it
is the code that ships.

WHY IT MATTERS THAT THIS GOES BELOW THE PORT. Every other host harness
in this repo substitutes `FakeMotor` at the `DiffDrive::Motor`
interface, which is ABOVE the shaping layer -- so none of them can see
`writeShapedDuty()`'s 100 ms reversal dwell. A pivot reverses exactly
one wheel, so that wheel is held at commanded zero while the other
starts immediately. That asymmetry is on the critical path of every
corner of every tour, and it was invisible to simulation until this
harness existed.

WHAT THIS CANNOT TELL YOU. Absolute numbers for a specific robot.
`tau`, `breakaway` and `duty_vel_max` are plant parameters; unfitted,
they are a guess. Sprint 031 ticket 011's host model asserted three PID
candidates held both acceptance bars and hardware held neither, because
its per-wheel residual was hypothesized rather than measured. Use this
for MECHANISM (does knob X cause effect Y, and in which direction) and
the robot for values.

Run it::

    uv run python tests/host/sim_tour.py
"""

from __future__ import annotations

import ctypes
import math
import os
import pathlib
import subprocess
import sys
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_SRC = _REPO / "src"

#: Everything the host build needs. `nezha_port.cpp` is on this list --
#: it was not host-compilable at all until the `I2CBus` seam landed.
_SOURCES = [
    _HERE / "sim_robot_shim.cpp",
    _SRC / "platform" / "nezha_port.cpp",
    _SRC / "core" / "diffdrive.cpp",
    _SRC / "motion" / "motion_engine.cpp",
    _SRC / "motion" / "velocity_shaper.cpp",
]

_TICK_US = 24000  # [us] the kernel's own control period


def build(out_dir=None):
    """Compile the sim-robot shared library and return its path.

    One translation unit per `c++ -c`, following
    `test_kernel_harness.compile_shared_lib()`'s own rule and for its
    own reason: a combined command line applies the SAME include search
    path to every file on it, and the real PXT build never passes a
    project-root `-I` at all -- it resolves each `#include "..."`
    relative to the including file's own directory. So a production
    `src/` source is compiled with NO `-I`, which is what makes a
    misspelled internal include fail here the way it fails the real
    build; only this directory's own scaffolding gets a search path.

    Serial compilation is also what keeps this runnable on a loaded
    machine -- five concurrent `clang++` children is enough to hit
    `posix_spawn: Resource temporarily unavailable` when a few Claude
    sessions and the aprilcam daemon are already resident.
    """
    prebuilt = os.environ.get("SIMROBOT_LIB")
    if prebuilt:
        # Escape hatch for a machine that cannot fork a compiler (this
        # happens: several resident Claude MCP servers plus the aprilcam
        # daemon are enough to hit the per-user process limit). The
        # caller is asserting the library is current -- nothing here can
        # check that, so it prints what it is using.
        print(f"using prebuilt {prebuilt} (SIMROBOT_LIB)")
        return pathlib.Path(prebuilt)
    out_dir = pathlib.Path(out_dir or tempfile.mkdtemp(prefix="simrobot-"))
    lib = out_dir / "libsimrobot.so"
    objects = []
    for i, source in enumerate(_SOURCES):
        obj = out_dir / f"{source.stem}.{i}.o"
        cmd = ["/usr/bin/c++", "-std=c++11", "-Wall", "-Wextra", "-fPIC",
               "-O2", "-DDIFFDRIVE_HOST_BUILD", "-c"]
        if not source.resolve().is_relative_to(_SRC.resolve()):
            cmd += ["-I", str(_SRC), "-I", str(_HERE)]
        cmd += [str(source), "-o", str(obj)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"host compile failed for {source}:\n{r.stderr}")
        objects.append(obj)
    r = subprocess.run(["/usr/bin/c++", "-shared", "-fPIC", "-o", str(lib)]
                       + [str(o) for o in objects],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"host link failed:\n{r.stderr}")
    return lib


def _bind(lib):
    f = ctypes.CDLL(str(lib))
    P = ctypes.c_void_p
    F = ctypes.c_float
    f.srCreate.argtypes = [F, F, F, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int]
    f.srCreate.restype = P
    f.srDestroy.argtypes = [P]
    f.srBegin.argtypes = [P]; f.srBegin.restype = ctypes.c_int
    f.srSetKernelConfig.argtypes = [P, F, F, F, F, F, F, F, F]
    f.srSetGeometry.argtypes = [P, F, F, F]
    f.srSetLimits.argtypes = [P, F, F, F, F, F, F]
    f.srConfigureShaping.argtypes = [P, F, F, F, F]
    f.srSetGroundGains.argtypes = [P, F, F]
    f.srMoveX.argtypes = [P, F, F, F, ctypes.c_uint32]
    f.srStop.argtypes = [P]
    f.srTick.argtypes = [P, ctypes.c_uint32]; f.srTick.restype = ctypes.c_int
    for name in ("srPoseX", "srPoseY", "srPoseHeading", "srCountsPerMm",
                 "srEffectiveTrackWidth"):
        getattr(f, name).argtypes = [P]
        getattr(f, name).restype = F
    for name in ("srWheelVelocity", "srWrittenDuty", "srAppliedDuty"):
        getattr(f, name).argtypes = [P, ctypes.c_int]
        getattr(f, name).restype = F
    f.srBusWrites.argtypes = [P]; f.srBusWrites.restype = ctypes.c_uint32
    return f


class SimRobot:
    """tovez as flashed (firmware 1.20260905.1), unless overridden.

    Every default below is a value READ OFF THE ROBOT over the wire on
    2026-09-05 with `GET` (reports/tovez-square-tour-20260905.md records
    the full set), except the three plant parameters, which are marked.
    """

    def __init__(self, lib,
                 # --- plant (NOT measured on tovez; see module docstring)
                 tau=0.13, breakaway_mm_s=25.0, full_duty_mm_s=676.0,
                 # --- firmware, as baked
                 track_width=114.2, travel_calib=0.7878,
                 rotational_slip=0.962,
                 accel=400.0, decel=400.0, v_floor=70.0, omega_floor=20.0,
                 lag=0.13, stop_distance=0.0,
                 full_duty_velocity=10795.0, kp=0.0, ki=6.0, i_max=765.6,
                 kaff=0.0, pid_max=1276.0, twist_hold_gain=4.0,
                 # --- port shaping (firmware shipped values)
                 output_deadband=0.03, reversal_dwell=100.0,
                 slew_rate=25.0, write_throttle=19000.0,
                 # --- tovez motor bake: left = port 2 (-1), right = port 1
                 left_port=2, left_sign=-1, right_port=1, right_sign=1,
                 ground_gain_1=1.0, ground_gain_2=1.0,
                 settle_ticks=16):
        self.f = lib
        cpm = 10.0 / travel_calib  # [counts/mm]
        self.cpm = cpm
        self.h = lib.srCreate(tau, breakaway_mm_s * cpm, full_duty_mm_s * cpm,
                              left_port, left_sign, right_port, right_sign)
        lib.srSetGeometry(self.h, track_width, travel_calib, rotational_slip)
        lib.srSetKernelConfig(self.h, 100.0, full_duty_velocity, kp, ki,
                              i_max, kaff, pid_max, twist_hold_gain)
        lib.srSetLimits(self.h, accel, decel, v_floor, omega_floor, lag,
                        stop_distance)
        lib.srConfigureShaping(self.h, output_deadband, reversal_dwell,
                               slew_rate, write_throttle)
        lib.srSetGroundGains(self.h, ground_gain_1, ground_gain_2)
        assert lib.srBegin(self.h) == 0, "kernel.begin() refused"
        # Ticks spent at commanded zero between moves. NOT cosmetic:
        # `writeShapedDuty()` CREDITS time already spent at commanded
        # zero toward the reversal dwell (`dwellStart_ = atZero_ ?
        # zeroSince_ : now`), so a long inter-move gap satisfies the
        # dwell before the next move even starts, and the dwell then
        # never bites. 16 ticks is 384 ms against a 100 ms dwell.
        self.settle_ticks = settle_ticks
        self.trace = []          # (t_s, vl_mm_s, vr_mm_s, duty1, duty2)
        self.t = 0.0

    def close(self):
        self.f.srDestroy(self.h)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- pose, in the units the reports use -----------------------------
    @property
    def x(self):
        return self.f.srPoseX(self.h)      # [mm]

    @property
    def y(self):
        return self.f.srPoseY(self.h)      # [mm]

    @property
    def heading_deg(self):
        return math.degrees(self.f.srPoseHeading(self.h))

    def move_x(self, distance_mm, rotation_deg, cruise, timeout_ms=20000):
        """One `MOVE_X`, then tick to completion. Returns ticks run.

        The extra settle ticks after the move goes inactive are not
        padding: the engine has commanded neutral by then, but a lagged
        wheel keeps coasting for several more ticks and THAT coast is
        where a pivot's overshoot actually lands.
        """
        self.f.srMoveX(self.h, float(distance_mm),
                       math.radians(rotation_deg), float(cruise),
                       int(timeout_ms))
        n = 0
        limit = int(timeout_ms * 1000 / _TICK_US) + 200
        while n < limit:
            active = self.f.srTick(self.h, _TICK_US)
            self._record()
            n += 1
            if not active:
                break
        for _ in range(self.settle_ticks):   # coast to rest
            self.f.srTick(self.h, _TICK_US)
            self._record()
        return n

    def _record(self):
        self.t += _TICK_US / 1e6
        self.trace.append((
            self.t,
            self.f.srWheelVelocity(self.h, 0) / self.cpm,
            self.f.srWheelVelocity(self.h, 1) / self.cpm,
            self.f.srWrittenDuty(self.h, 1),
            self.f.srWrittenDuty(self.h, 2),
        ))


#: The orange-dots square: NE -> NW -> SW -> SE -> NE, eight moves.
#: Same route, same cruises as the hardware run in
#: reports/tovez-square-tour-20260905.md.
SQUARE = [(1000.0, 0.0, 150), (0.0, 90.0, 100),
          (600.0, 0.0, 150), (0.0, 90.0, 100),
          (1000.0, 0.0, 150), (0.0, 90.0, 100),
          (600.0, 0.0, 150), (0.0, 90.0, 100)]


def run_square(lib, **kw):
    """Drive SQUARE and return (closure_mm, net_heading_deg, per_move)."""
    with SimRobot(lib, **kw) as r:
        x0, y0, h0 = r.x, r.y, r.heading_deg
        bounds = []          # (start, end) trace index per move
        per_move = []
        for dist, rot, cruise in SQUARE:
            ax, ay, ah = r.x, r.y, r.heading_deg
            t_start = len(r.trace)
            r.move_x(dist, rot, cruise)
            seg = r.trace[t_start:]
            bounds.append((t_start, len(r.trace)))
            moved = math.hypot(r.x - ax, r.y - ay)
            per_move.append({
                "cmd_dist": dist, "cmd_rot": rot,
                "moved_mm": moved,
                "dheading": (r.heading_deg - ah + 540) % 360 - 180,
                "peak_l": max((abs(s[1]) for s in seg), default=0.0),
                "peak_r": max((abs(s[2]) for s in seg), default=0.0),
            })
        closure = math.hypot(r.x - x0, r.y - y0)
        net = (r.heading_deg - h0 + 540) % 360 - 180
        return closure, net, per_move, r.trace, bounds


def main():
    lib = _bind(build())
    print("square tour, host sim -- real port + kernel + engine + shaper")
    print("(plant tau/breakaway NOT fitted to tovez -- mechanism, not values)\n")
    header = (f"{'config':30s} {'closure':>9s} {'net h':>8s}   "
              f"{'pivots, camera deg':<30s}")
    print(header)
    print("-" * len(header))
    keep = {}
    for label, kw in [
        ("as flashed (dwell 100, th 4)", {}),
        ("twist_hold_gain 0", dict(twist_hold_gain=0.0)),
        ("reversal_dwell 0", dict(reversal_dwell=0.0)),
        ("dwell 0 + th 0", dict(reversal_dwell=0.0, twist_hold_gain=0.0)),
        ("back-to-back moves (2 tick gap)", dict(settle_ticks=2)),
        ("  ... same, dwell 0", dict(settle_ticks=2, reversal_dwell=0.0)),
        ("  ... same, th 0", dict(settle_ticks=2, twist_hold_gain=0.0)),
    ]:
        closure, net, moves, trace, bounds = run_square(lib, **kw)
        pivots = [m["dheading"] for m in moves if m["cmd_rot"]]
        keep[label] = (moves, trace, bounds)
        print(f"{label:30s} {closure:7.1f}mm {net:+7.2f}   "
              + " ".join(f"{p:+6.2f}" for p in pivots))

    # The mechanism, per tick. Pivot 1 is move index 1; `duty1`/`duty2`
    # are what was actually WRITTEN to the brick -- post-quantizer,
    # post-deadband, post-slew, post-throttle, post-dwell -- so a wheel
    # held by the reversal dwell shows a literal 0.00 while its partner
    # is already driving.
    for label in ("as flashed (dwell 100, th 4)", "reversal_dwell 0"):
        moves, trace, bounds = keep[label]
        lo, hi = bounds[1]
        print(f"\n  pivot 1 -- {label}")
        print(f"    {'t':>6s} {'vl':>8s} {'vr':>8s} {'duty1':>7s} {'duty2':>7s}")
        t0 = trace[lo][0]
        for s in trace[lo:min(lo + 14, hi)]:
            print(f"    {s[0]-t0:6.2f} {s[1]:+8.1f} {s[2]:+8.1f} "
                  f"{s[3]:+7.2f} {s[4]:+7.2f}")


if __name__ == "__main__":
    sys.exit(main())
