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

`--board cutebot-pro` (sprint 040 ticket 006) runs the SAME tier one
board over: `CutebotDevice`/`CutebotMotorPort`/`CutebotTapAdapter`/
`CutebotActuationPolicy` (src/platform/cutebot_port.h,
cutebot_actuation_policy.h) under the real kernel and `MotionEngine`,
over a simulated 0x10 slave (`sim_cutebot_bus.h`) via a dedicated
whole-stack shim (`sim_cutebot_robot_shim.cpp`, the Cutebot analogue of
`sim_robot_shim.cpp`). No Cutebot Pro has been fitted yet -- see
`SimCutebotRobot`'s own docstring for exactly which of its numbers are
UNVERIFIED placeholders versus a firmware default. `--board` with no
value, or no `--board` at all, keeps running the Nezha tier above,
byte-for-byte unchanged.

Run it::

    uv run --with matplotlib python tests/host/sim_tour.py
    uv run python tests/host/sim_tour.py --board cutebot-pro
"""

from __future__ import annotations

import argparse
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

#: The Cutebot Pro analogue of `_SOURCES` above -- `cutebot_port.cpp`
#: needed no `I2CBus`-seam wait the way `nezha_port.cpp` did (it was
#: host-portable from the day it was written, sprint 040 ticket 002);
#: it gains `cutebot_actuation_policy.cpp` for the hybrid decision
#: `sim_cutebot_robot_shim.cpp`'s `CutebotDevice` calls once per cycle.
_CUTEBOT_SOURCES = [
    _HERE / "sim_cutebot_robot_shim.cpp",
    _SRC / "platform" / "cutebot_port.cpp",
    _SRC / "platform" / "cutebot_actuation_policy.cpp",
    _SRC / "core" / "diffdrive.cpp",
    _SRC / "motion" / "motion_engine.cpp",
    _SRC / "motion" / "velocity_shaper.cpp",
]

_TICK_US = 24000  # [us] the kernel's own control period


def _compile_lib(sources, lib_name, prebuilt_env, out_dir=None):
    """Shared compile/link recipe behind `build()` and `build_cutebot()`.

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
    prebuilt = os.environ.get(prebuilt_env)
    if prebuilt:
        # Escape hatch for a machine that cannot fork a compiler (this
        # happens: several resident Claude MCP servers plus the aprilcam
        # daemon are enough to hit the per-user process limit). The
        # caller is asserting the library is current -- nothing here can
        # check that, so it prints what it is using.
        print(f"using prebuilt {prebuilt} ({prebuilt_env})")
        return pathlib.Path(prebuilt)
    out_dir = pathlib.Path(out_dir or tempfile.mkdtemp(prefix=f"{lib_name}-"))
    lib = out_dir / f"lib{lib_name}.so"
    objects = []
    for i, source in enumerate(sources):
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


def build(out_dir=None):
    """Compile the sim-robot (Nezha) shared library and return its path.

    See `_compile_lib()` for the recipe itself -- unchanged since before
    `--board` existed, and this function's own name/signature/output
    path (`libsimrobot.so`) are preserved exactly so existing callers
    (`test_sim_profile_tracking.py` and friends import `build` directly)
    see no difference.
    """
    return _compile_lib(_SOURCES, "simrobot", "SIMROBOT_LIB", out_dir)


def build_cutebot(out_dir=None):
    """Compile the sim-Cutebot-Pro shared library and return its path.

    The Cutebot analogue of `build()` above, compiling
    `_CUTEBOT_SOURCES` (`sim_cutebot_robot_shim.cpp`'s own header
    explains the composition) behind the same `SIMCUTEBOT_LIB` prebuilt
    escape hatch.
    """
    return _compile_lib(_CUTEBOT_SOURCES, "simcutebot", "SIMCUTEBOT_LIB",
                        out_dir)


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
    f.srSetJerk.argtypes = [P, F]
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


def _bind_cutebot(lib):
    """The `_bind()` above, for `sim_cutebot_robot_shim.cpp`'s `sc*`
    surface -- see that file's own header for the composition (real
    `CutebotDevice`/`CutebotMotorPort`/`CutebotTapAdapter` pair under
    the real kernel and `MotionEngine`, over a simulated 0x10 slave).
    Deliberately a separate binder rather than folding onto `_bind()`:
    the two shims are different translation units with different
    symbols (`sc*` vs `sr*`), and `_bind()`'s own signature/behavior
    must stay untouched for the Nezha path's existing callers.
    """
    f = ctypes.CDLL(str(lib))
    P = ctypes.c_void_p
    F = ctypes.c_float
    f.scCreate.argtypes = [F, F, F, ctypes.c_int, ctypes.c_int]
    f.scCreate.restype = P
    f.scDestroy.argtypes = [P]
    f.scBegin.argtypes = [P]; f.scBegin.restype = ctypes.c_int
    f.scSetKernelConfig.argtypes = [P, F, F, F, F, F, F, F, F]
    f.scSetGeometry.argtypes = [P, F, F, F]
    f.scSetLimits.argtypes = [P, F, F, F, F, F, F]
    f.scSetJerk.argtypes = [P, F]
    f.scSetOnboardMode.argtypes = [P, ctypes.c_int]
    f.scSetOnboardMode.restype = ctypes.c_int
    f.scOnboardMode.argtypes = [P]; f.scOnboardMode.restype = ctypes.c_int
    f.scSetOnboardFloor.argtypes = [P, F]
    f.scSetOnboardFloor.restype = ctypes.c_int
    f.scOnboardFloor.argtypes = [P]; f.scOnboardFloor.restype = F
    f.scMoveX.argtypes = [P, F, F, F, ctypes.c_uint32]
    f.scStop.argtypes = [P]
    f.scTick.argtypes = [P, ctypes.c_uint32]; f.scTick.restype = ctypes.c_int
    for name in ("scPoseX", "scPoseY", "scPoseHeading", "scCountsPerMm",
                 "scEffectiveTrackWidth"):
        getattr(f, name).argtypes = [P]
        getattr(f, name).restype = F
    for name in ("scWheelVelocity", "scAppliedDuty"):
        getattr(f, name).argtypes = [P, ctypes.c_int]
        getattr(f, name).restype = F
    for name in ("scFrameCount", "scOnboardFrameCount", "scEngageCount",
                 "scReleaseCount"):
        getattr(f, name).argtypes = [P]
        getattr(f, name).restype = ctypes.c_uint32
    f.scOnboardActive.argtypes = [P]; f.scOnboardActive.restype = ctypes.c_int
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
                 settle_ticks=16, jerk=0.0):
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
        lib.srSetJerk(self.h, jerk)
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
        # (t_s, vl_mm_s, vr_mm_s, duty1, duty2, x_mm, y_mm, h_deg)
        self.trace = []
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
            self._record(active)
            n += 1
            if not active:
                break
        for _ in range(self.settle_ticks):   # coast to rest
            a = self.f.srTick(self.h, _TICK_US)
            self._record(a)
        return n

    def _record(self, active=1):
        self.t += _TICK_US / 1e6
        self.trace.append((
            self.t,
            self.f.srWheelVelocity(self.h, 0) / self.cpm,
            self.f.srWheelVelocity(self.h, 1) / self.cpm,
            self.f.srWrittenDuty(self.h, 1),
            self.f.srWrittenDuty(self.h, 2),
            self.x, self.y, self.heading_deg, active,
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


class SimCutebotRobot:
    """A Cutebot Pro under the real hybrid actuation path -- the
    `--board cutebot-pro` analogue of `SimRobot` above.

    UNVERIFIED, ALL OF IT (see this module's own docstring and
    `.claude/rules/measurement-citations.md`): no Cutebot Pro has been
    fitted yet, so every default below is a PLACEHOLDER, not a
    measurement. `tau`/`breakaway_mm_s`/`full_duty_mm_s` are copied
    from `SimRobot`'s own Nezha placeholders (same caveat, same
    non-status); the firmware-shape defaults (`track_width` through
    `twist_hold_gain`) are ALSO unbaked for a Cutebot -- no fleet JSON
    entry carries them the way tovez's do for `SimRobot` -- and are
    kept numerically equal to `SimRobot`'s own tovez bake purely so the
    two boards' host tours are comparable at the desk, not because a
    Cutebot Pro is expected to match tovez's kernel tuning. `left_sign`/
    `right_sign` default to `board_cutebot.cpp`'s own `+1`/`+1`
    placeholders (that file's own comment: UNVERIFIED against a real
    mount). There is no port-shaping constructor argument here at all
    (`CutebotMotorPort` has none -- see cutebot_port.h's "minimal
    shaping, deliberately" header note): no reversal dwell, no slew, no
    write throttle, no sigma-delta quantizer.
    """

    def __init__(self, lib,
                 # --- plant (UNVERIFIED; see this class's own docstring)
                 tau=0.13, breakaway_mm_s=25.0, full_duty_mm_s=676.0,
                 # --- firmware shape (UNVERIFIED for a Cutebot; kept
                 # equal to SimRobot's own tovez bake for comparability)
                 track_width=114.2, travel_calib=0.7878,
                 rotational_slip=0.962,
                 accel=400.0, decel=400.0, v_floor=70.0, omega_floor=20.0,
                 lag=0.13, stop_distance=0.0,
                 full_duty_velocity=10795.0, kp=0.0, ki=6.0, i_max=765.6,
                 kaff=0.0, pid_max=1276.0, twist_hold_gain=4.0,
                 # --- board_cutebot.cpp's own placeholder sign bake
                 left_sign=1, right_sign=1,
                 # --- hybrid actuation config (comms/config_fields.h
                 # ordinals 43/44)
                 onboard_pid=0, onboard_floor=200.0,
                 settle_ticks=16, jerk=0.0):
        self.f = lib
        cpm = 10.0 / travel_calib  # [counts/mm]
        self.cpm = cpm
        self.h = lib.scCreate(tau, breakaway_mm_s * cpm, full_duty_mm_s * cpm,
                              left_sign, right_sign)
        lib.scSetGeometry(self.h, track_width, travel_calib, rotational_slip)
        lib.scSetKernelConfig(self.h, 100.0, full_duty_velocity, kp, ki,
                              i_max, kaff, pid_max, twist_hold_gain)
        lib.scSetLimits(self.h, accel, decel, v_floor, omega_floor, lag,
                        stop_distance)
        lib.scSetJerk(self.h, jerk)
        assert lib.scBegin(self.h) == 0, "kernel.begin() refused"
        assert lib.scSetOnboardFloor(self.h, onboard_floor), \
            f"onboard_floor {onboard_floor} refused (must be > 0)"
        assert lib.scSetOnboardMode(self.h, onboard_pid), \
            f"onboard_pid {onboard_pid} refused (must be 0, 1 or 2)"
        self.settle_ticks = settle_ticks  # see SimRobot's own comment
        # (t_s, vl_mm_s, vr_mm_s, duty_l, duty_r, x_mm, y_mm, h_deg, active)
        self.trace = []
        self.t = 0.0

    def close(self):
        self.f.scDestroy(self.h)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- pose, in the units the reports use -----------------------------
    @property
    def x(self):
        return self.f.scPoseX(self.h)      # [mm]

    @property
    def y(self):
        return self.f.scPoseY(self.h)      # [mm]

    @property
    def heading_deg(self):
        return math.degrees(self.f.scPoseHeading(self.h))

    # ---- hybrid actuation readback ---------------------------------------
    @property
    def pwm_frames(self):
        return self.f.scFrameCount(self.h)          # 0x10 frames shipped

    @property
    def onboard_frames(self):
        return self.f.scOnboardFrameCount(self.h)   # 0x80 frames shipped

    @property
    def engage_count(self):
        return self.f.scEngageCount(self.h)

    @property
    def release_count(self):
        return self.f.scReleaseCount(self.h)

    @property
    def onboard_active(self):
        """Whether the LAST frame shipped was `0x80` -- read this after
        the tour's final tick to confirm it ended on PWM/zero, not a
        leftover onboard setpoint."""
        return bool(self.f.scOnboardActive(self.h))

    def move_x(self, distance_mm, rotation_deg, cruise, timeout_ms=20000):
        """One `MOVE_X`, then tick to completion. Returns ticks run --
        see `SimRobot.move_x()`'s own comment on why the settle ticks
        after the move goes inactive are not padding."""
        self.f.scMoveX(self.h, float(distance_mm),
                       math.radians(rotation_deg), float(cruise),
                       int(timeout_ms))
        n = 0
        limit = int(timeout_ms * 1000 / _TICK_US) + 200
        while n < limit:
            active = self.f.scTick(self.h, _TICK_US)
            self._record(active)
            n += 1
            if not active:
                break
        for _ in range(self.settle_ticks):   # coast to rest
            a = self.f.scTick(self.h, _TICK_US)
            self._record(a)
        return n

    def _record(self, active=1):
        self.t += _TICK_US / 1e6
        self.trace.append((
            self.t,
            self.f.scWheelVelocity(self.h, 0) / self.cpm,
            self.f.scWheelVelocity(self.h, 1) / self.cpm,
            self.f.scAppliedDuty(self.h, 0),
            self.f.scAppliedDuty(self.h, 1),
            self.x, self.y, self.heading_deg, active,
        ))


#: The Cutebot analogue of SQUARE, same route (NE -> NW -> SW -> SE ->
#: NE) but DIFFERENT cruises, chosen deliberately so this one tour
#: proves both halves of the both-wheels eligibility story at once: the
#: four straight legs cruise at 250 mm/s, above the default
#: `onboard_floor` (200 mm/s, design doc S1.5), so modes 1/2 are
#: ELIGIBLE to hand them to the onboard loop; the four pivots cruise at
#: 100 mm/s, below the floor on both wheels (a pivot's two wheels share
#: one magnitude), so they must NEVER be handed off regardless of mode.
#: SQUARE's own 150/100 cruises would not exercise this at all -- both
#: sit under any sane floor, so nothing above mode 0 would ever engage.
CUTEBOT_SQUARE = [(1000.0, 0.0, 250), (0.0, 90.0, 100),
                  (600.0, 0.0, 250), (0.0, 90.0, 100),
                  (1000.0, 0.0, 250), (0.0, 90.0, 100),
                  (600.0, 0.0, 250), (0.0, 90.0, 100)]

#: The closure pass bar this ticket's own tests hold the Cutebot square
#: to. NOT a fresh number: it is `test_sim_profile_tracking.py`'s own
#: `assert closure < 160.0` for a Nezha SQUARE tour on this SAME sim
#: tier (host kernel+engine over a simulated brick, unfitted plant) --
#: reused rather than re-derived because that is exactly the "existing
#: host-sim pass bar" this ticket's own acceptance criteria refer to.
#: MEASURED this session (`uv run python tests/host/sim_tour.py --board
#: cutebot-pro`): closures of 118.9 mm (onboard_pid 0), 57.2 mm
#: (onboard_pid 1) and 58.1 mm (onboard_pid 2) against CUTEBOT_SQUARE's
#: own faster cruises -- all comfortably inside this bound, with the
#: hybrid modes closing TIGHTER than pure PWM on this particular model
#: (a property of this plant, not a claim about real hardware).
CUTEBOT_CLOSURE_PASS_MM = 160.0


def run_cutebot_square(lib, onboard_pid=0, onboard_floor=200.0, **kw):
    """Drive CUTEBOT_SQUARE at one `onboard_pid` mode and return a dict
    carrying the same closure/heading numbers `run_square()` returns
    PLUS the hybrid-path counters this ticket asks `sim_tour.py` to
    report: PWM (`0x10`) vs onboard (`0x80`) frames shipped, the
    engage/release handoff counts, and whether the FINAL frame shipped
    was onboard (`final_onboard` -- must be `False`: a tour ends on a
    neutral tick, and `CutebotActuationPolicy::decide()` forces PWM on
    every neutral tick regardless of mode, so this is confirming that
    contract held for the whole tour, not merely reading a flag)."""
    with SimCutebotRobot(lib, onboard_pid=onboard_pid,
                         onboard_floor=onboard_floor, **kw) as r:
        x0, y0, h0 = r.x, r.y, r.heading_deg
        bounds = []
        per_move = []
        for dist, rot, cruise in CUTEBOT_SQUARE:
            ax, ay, ah = r.x, r.y, r.heading_deg
            onboard_before, pwm_before = r.onboard_frames, r.pwm_frames
            t_start = len(r.trace)
            r.move_x(dist, rot, cruise)
            seg = r.trace[t_start:]
            bounds.append((t_start, len(r.trace)))
            moved = math.hypot(r.x - ax, r.y - ay)
            per_move.append({
                "cmd_dist": dist, "cmd_rot": rot, "cruise": cruise,
                "moved_mm": moved,
                "dheading": (r.heading_deg - ah + 540) % 360 - 180,
                "peak_l": max((abs(s[1]) for s in seg), default=0.0),
                "peak_r": max((abs(s[2]) for s in seg), default=0.0),
                # Per-move frame deltas -- what lets a test assert "this
                # SPECIFIC leg shipped an 0x80" rather than only "the
                # tour shipped one somewhere" (the global counters
                # above can't localize it to a leg).
                "onboard_frames": r.onboard_frames - onboard_before,
                "pwm_frames": r.pwm_frames - pwm_before,
            })
        closure = math.hypot(r.x - x0, r.y - y0)
        net = (r.heading_deg - h0 + 540) % 360 - 180
        return {
            "onboard_pid": onboard_pid,
            "onboard_floor": onboard_floor,
            "closure_mm": closure,
            "net_heading_deg": net,
            "per_move": per_move,
            "trace": r.trace,
            "bounds": bounds,
            "pwm_frames": r.pwm_frames,
            "onboard_frames": r.onboard_frames,
            "engage_count": r.engage_count,
            "release_count": r.release_count,
            "handoffs": r.engage_count + r.release_count,
            "final_onboard": r.onboard_active,
        }


# dataviz reference palette, same pair tools/tour_chart.py uses so a sim
# chart and a hardware chart read as one family.
_S1, _S2, _S3, _S4 = "#2a78d6", "#eb6834", "#2e9e6b", "#8a5cd6"
_INK, _MUTED, _GRID = "#0b0b0b", "#52514e", "#d8d6d0"


def chart(runs, out_png, pivot_bounds=None,
          headline="jerk limited (jerk 800)"):
    """Three panels: the configs' ground tracks against the commanded
    rectangle, wheel speeds across the whole tour, and a zoom on the
    first pivot -- which is where the reversal dwell and the twist-hold
    response actually show up.

    Fixed axis limits, no autoscale: two runs must be comparable by eye
    and, later, pixel-wise against a golden (radio-robot-elite's
    system-test charter).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(17.5, 6.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.25, 1.0], wspace=0.28)
    ax1, ax2, ax3 = (fig.add_subplot(gs[0]), fig.add_subplot(gs[1]),
                     fig.add_subplot(gs[2]))
    colors = [_S1, _S2, _S3, _S4]

    # ---- panel 1: ground track vs the commanded 100x60 rectangle
    for (label, closure, net, trace), c in zip(runs, colors):
        ax1.plot([s[5] for s in trace], [s[6] for s in trace],
                 color=c, lw=2.0, zorder=3,
                 label=f"{label}\n    closure {closure:.0f} mm, "
                       f"net {net:+.1f} deg")
        ax1.plot(trace[-1][5], trace[-1][6], "o", color=c, ms=7, zorder=4)
    # Commanded shape drawn ON TOP, dashed and light: it is the
    # reference the eye compares against, so it must not be buried.
    ax1.plot([0, 1000, 1000, 0, 0], [0, 0, 600, 600, 0], "--",
             color=_INK, lw=1.3, alpha=0.55, zorder=6,
             label="commanded 100x60 cm")
    ax1.plot(0, 0, "o", color=_INK, ms=8, zorder=7)
    ax1.annotate("start", (0, 0), textcoords="offset points",
                 xytext=(8, -16), fontsize=9, color=_INK)
    ax1.set_aspect("equal")
    ax1.set_xlim(-300, 1250)
    ax1.set_ylim(-320, 820)
    ax1.set_xlabel("x [mm]", color=_MUTED)
    ax1.set_ylabel("y [mm]", color=_MUTED)
    ax1.set_title("Ground track -- 8 moves, open loop", color=_INK,
                  fontsize=11, loc="left")
    ax1.grid(True, color=_GRID, lw=0.6)
    ax1.legend(fontsize=7.6, loc="upper center",
               bbox_to_anchor=(0.5, -0.13), framealpha=0.0, ncol=1,
               handlelength=1.6, labelspacing=0.75)

    # ---- panel 2: wheel speeds, whole tour, headline config
    label, closure, net, trace = next(r for r in runs if r[0] == headline)
    ts = [s[0] for s in trace]
    ax2.plot(ts, [s[1] for s in trace], color=_S1, lw=1.3, label="left wheel")
    ax2.plot(ts, [s[2] for s in trace], color=_S2, lw=1.3, label="right wheel")
    ax2.axhline(0, color=_MUTED, lw=0.8)
    for v, lbl in ((150, "leg cruise 150"), (100, "pivot cruise 100"),
                   (-100, None)):
        ax2.axhline(v, color=_MUTED, lw=0.7, ls=":", alpha=0.7)
        if lbl:
            ax2.annotate(lbl, (max(ts) * 0.995, v + 6), fontsize=7.5,
                         color=_MUTED, ha="right")
    ax2.set_xlim(0, max(ts))
    ax2.set_ylim(-230, 240)
    ax2.set_xlabel("time [s]", color=_MUTED)
    ax2.set_ylabel("wheel speed [mm/s]", color=_MUTED)
    ax2.set_title(f"Wheel speeds -- {label}", color=_INK, fontsize=11,
                  loc="left")
    ax2.grid(True, color=_GRID, lw=0.6)
    ax2.legend(fontsize=8.5, loc="lower right", framealpha=0.95)

    if pivot_bounds:
        lo, hi = pivot_bounds
        seg = trace[lo:hi]
        t0 = seg[0][0]
        ax3.plot([s[0] - t0 for s in seg], [s[1] for s in seg],
                 color=_S1, lw=1.8, label="left (reversing)")
        ax3.plot([s[0] - t0 for s in seg], [s[2] for s in seg],
                 color=_S2, lw=1.8, label="right (forward)")
        ax3.axhline(100, color=_MUTED, lw=0.9, ls=":")
        ax3.axhline(-100, color=_MUTED, lw=0.9, ls=":")
        ax3.annotate("commanded +-100", (0.02, 106), fontsize=8,
                     color=_MUTED)
        ax3.axhline(0, color=_MUTED, lw=0.8)
        ax3.set_xlim(0, seg[-1][0] - t0)
        ax3.set_ylim(-230, 240)
        ax3.set_xlabel("time into pivot [s]", color=_MUTED)
        ax3.set_ylabel("wheel speed [mm/s]", color=_MUTED)
        ax3.set_title("Pivot 1, zoomed", color=_INK, fontsize=11,
                      loc="left")
        ax3.grid(True, color=_GRID, lw=0.6)
        ax3.legend(fontsize=8.5, loc="lower right", framealpha=0.95)

    fig.suptitle("tovez square tour -- HOST SIM: real port + kernel + "
                 "engine + shaper over a simulated Nezha brick    "
                 "(plant tau/breakaway NOT fitted to tovez -- mechanism, "
                 "not values)",
                 color=_INK, fontsize=12, x=0.008, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    pathlib.Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    print(f"chart {out_png}")
    return out_png


def parse_args(argv=None):
    """CLI surface: `--board` (default `nezha`, unchanged behavior) plus
    the Cutebot-only knobs. Choices spell `nezha`/`cutebot-pro` the same
    way `tools/make_deploy.py`'s own `_BOARD_BAKE_LITERALS` does, per
    this ticket's own instruction to reuse that naming."""
    p = argparse.ArgumentParser(
        description="Host-sim square tour: real port(s) + kernel + "
                     "engine (+ shaper/hybrid policy) over a simulated "
                     "brick. --board nezha (default) is unchanged from "
                     "before this flag existed; --board cutebot-pro "
                     "runs the hybrid actuation path instead.")
    p.add_argument("--board", choices=("nezha", "cutebot-pro"),
                   default="nezha",
                   help="which board's port/device stack to compose "
                        "(default: nezha)")
    p.add_argument("--onboard-pid", type=int, choices=(0, 1, 2),
                   default=None,
                   help="cutebot-pro only: run a single onboard_pid "
                        "mode (0 off / 1 threshold / 2 plateau) instead "
                        "of all three in turn")
    p.add_argument("--onboard-floor", type=float, default=200.0,
                   help="cutebot-pro only: onboard_floor [mm/s] "
                        "(design doc's own 200 mm/s source reading, "
                        "S1.5; default 200.0)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.board == "cutebot-pro":
        return main_cutebot(args)
    return main_nezha()


def main_cutebot(args):
    lib = _bind_cutebot(build_cutebot())
    print("cutebot-pro square tour, host sim -- real device/port(s) + "
          "tap + policy + kernel + engine over a simulated 0x10 slave")
    print("(plant tau/breakaway/full_duty_mm_s UNVERIFIED -- no Cutebot "
          "Pro has been fitted yet; mechanism, not values)\n")
    pids = [args.onboard_pid] if args.onboard_pid is not None else [0, 1, 2]
    header = (f"{'onboard_pid':>11s} {'closure':>9s} {'net h':>8s}  "
              f"{'0x10':>6s} {'0x80':>6s} {'handoffs':>8s} {'final':>6s}")
    print(header)
    print("-" * len(header))
    results = []
    for pid in pids:
        result = run_cutebot_square(lib, onboard_pid=pid,
                                    onboard_floor=args.onboard_floor)
        results.append(result)
        final = "0x80" if result["final_onboard"] else "PWM"
        print(f"{pid:11d} {result['closure_mm']:7.1f}mm "
              f"{result['net_heading_deg']:+7.2f}  "
              f"{result['pwm_frames']:6d} {result['onboard_frames']:6d} "
              f"{result['handoffs']:8d} {final:>6s}")
    return 0


def main_nezha():
    lib = _bind(build())
    print("square tour, host sim -- real port + kernel + engine + shaper")
    print("(plant tau/breakaway NOT fitted to tovez -- mechanism, not values)\n")
    header = (f"{'config':30s} {'closure':>9s} {'net h':>8s}   "
              f"{'pivots, camera deg':<30s}")
    print(header)
    print("-" * len(header))
    keep = {}
    for_chart = []
    for label, kw in [
        ("jerk limited (jerk 800)", dict(jerk=800.0)),
        ("current controller (jerk 0)", {}),
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
        if len(for_chart) < 4:
            for_chart.append((label, closure, net, trace))
        print(f"{label:30s} {closure:7.1f}mm {net:+7.2f}   "
              + " ".join(f"{p:+6.2f}" for p in pivots))

    # The mechanism, per tick. Pivot 1 is move index 1; `duty1`/`duty2`
    # are what was actually WRITTEN to the brick -- post-quantizer,
    # post-deadband, post-slew, post-throttle, post-dwell -- so a wheel
    # held by the reversal dwell shows a literal 0.00 while its partner
    # is already driving.
    for label in ("jerk limited (jerk 800)", "current controller (jerk 0)"):
        moves, trace, bounds = keep[label]
        lo, hi = bounds[1]
        print(f"\n  pivot 1 -- {label}")
        print(f"    {'t':>6s} {'vl':>8s} {'vr':>8s} {'duty1':>7s} {'duty2':>7s}")
        t0 = trace[lo][0]
        for s in trace[lo:min(lo + 14, hi)]:
            print(f"    {s[0]-t0:6.2f} {s[1]:+8.1f} {s[2]:+8.1f} "
                  f"{s[3]:+7.2f} {s[4]:+7.2f}")

    out = _REPO / "reports" / "tovez-sim-square-20260906" / "sim-square.png"
    chart(for_chart, out, pivot_bounds=keep[
        "jerk limited (jerk 800)"][2][1])
    subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    sys.exit(main())
