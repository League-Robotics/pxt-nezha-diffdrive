"""tests/host/test_kernel_harness.py -- the native host test harness for
DiffDrive::DifferentialDrive (src/diffdrive.h/.cpp).

This is this repo's first test suite. Its whole job is to prove the
host-compile + fake-port + pytest pipeline works end to end against code
that already exists and is already portable -- `src/diffdrive.h`/`.cpp`
depend on nothing but `<cstdint>`/`<cmath>`/`<algorithm>` and their own
four ports (Motor/Clock/Sleeper/FiberLauncher). It does NOT touch the
wire grammar or the motion engine -- those land in later sprint 003
tickets, which extend this same harness (`compile_shared_lib()` below,
and `tests/host/fake_ports.h`) rather than inventing their own.

Modeled on radio-robot-lib/tests/protocol/{mock_adapter.h,
protocol_shim.cpp} and tools/sim/README.md's build recipe -- same
`/usr/bin/c++ -std=c++20 ... -shared -fPIC` pattern, no CMake -- except
the shared library is compiled ONCE per pytest session (see the
`kernel_lib` fixture) rather than once per test function: every ticket
after this one adds more tests against the same handful of translation
units, and re-invoking the compiler per test would make the whole
sprint's suite slow to run.

Run with::

    uv run pytest
"""

import ctypes
import pathlib
import subprocess

import pytest

# tests/host/test_kernel_harness.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TEST_DIR = pathlib.Path(__file__).resolve().parent

_SHIM_SOURCES = [
    _SRC_DIR / "diffdrive.cpp",
    _TEST_DIR / "kernel_shim.cpp",
]

# DiffDrive::DifferentialDrive::Status's DECLARATION order (src/diffdrive.h)
# -- the shim passes/returns this ordinal, never anything else. Mirrors
# radio-robot-lib/tests/protocol/test_protocol_harness.py's own RESULT_*
# constants pattern.
STATUS_OK = 0
STATUS_REFUSED_UNCONFIGURED = 1
STATUS_REFUSED_NOT_BEGUN = 2
STATUS_REFUSED_ESTOPPED = 3
STATUS_REFUSED_NON_FINITE = 4
STATUS_CADENCE_PRESERVED = 5

LEFT = 0
RIGHT = 1


def compile_shared_lib(tmp_path_factory, sources=None, include_dirs=None,
                        out_name="libkernel_shim.so"):
    """Compile `sources` (default: diffdrive.cpp + kernel_shim.cpp) into a
    shared library under a fresh session-scoped tmp dir and return its
    path. Mirrors radio-robot-lib/tests/protocol/test_protocol_harness.py's
    own `_compile_shared_lib` -- same compiler invocation, no CMake --
    factored out here (rather than inlined in a fixture) so a later
    ticket's own test file can import it and compile ITS OWN shim against
    a different source list without duplicating the subprocess plumbing.
    """
    sources = sources or _SHIM_SOURCES
    include_dirs = include_dirs or [_SRC_DIR, _TEST_DIR]
    build_dir = tmp_path_factory.mktemp("host_shim_build")
    lib_path = build_dir / out_name
    cmd = ["/usr/bin/c++", "-std=c++20", "-Wall", "-Wextra", "-shared", "-fPIC"]
    for d in include_dirs:
        cmd += ["-I", str(d)]
    cmd += [str(s) for s in sources] + ["-o", str(lib_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"host build failed:\ncommand: {' '.join(cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return lib_path


def _bind(lib):
    """Attach ctypes argtypes/restype for every kernel_shim.cpp export."""
    lib.kdCreate.argtypes = []
    lib.kdCreate.restype = ctypes.c_void_p
    lib.kdDestroy.argtypes = [ctypes.c_void_p]
    lib.kdDestroy.restype = None

    for name in (
        "kdSetMaxDuty", "kdSetFullDutyVelocity", "kdSetKp", "kdSetKi",
        "kdSetIMax", "kdSetKaff", "kdSetPidMax", "kdSetTwistHoldGain",
        "kdSetSpeedFloor", "kdSetPositionErrorMax",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_float]
        fn.restype = None
    lib.kdSetCyclePeriod.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.kdSetCyclePeriod.restype = None

    lib.kdBegin.argtypes = [ctypes.c_void_p]
    lib.kdBegin.restype = ctypes.c_int
    lib.kdStart.argtypes = [ctypes.c_void_p]
    lib.kdStart.restype = ctypes.c_int
    lib.kdDrive.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.kdDrive.restype = ctypes.c_int
    lib.kdDriveDuty.argtypes = [
        ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_uint32,
    ]
    lib.kdDriveDuty.restype = ctypes.c_int
    lib.kdNeutral.argtypes = [ctypes.c_void_p]
    lib.kdNeutral.restype = None
    lib.kdEstop.argtypes = [ctypes.c_void_p]
    lib.kdEstop.restype = None
    lib.kdEstopClear.argtypes = [ctypes.c_void_p]
    lib.kdEstopClear.restype = None
    lib.kdClearStallLatch.argtypes = [ctypes.c_void_p]
    lib.kdClearStallLatch.restype = None
    lib.kdRebasePosition.argtypes = [ctypes.c_void_p]
    lib.kdRebasePosition.restype = None
    lib.kdStep.argtypes = [ctypes.c_void_p]
    lib.kdStep.restype = None
    lib.kdLastError.argtypes = [ctypes.c_void_p]
    lib.kdLastError.restype = ctypes.c_int

    for name in (
        "kdOutVelocity", "kdOutTwist", "kdOutPositionLeft",
        "kdOutPositionRight", "kdOutVelocityLeft", "kdOutVelocityRight",
        "kdOutAppliedDutyLeft", "kdOutAppliedDutyRight",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_float
    for name in (
        "kdOutReady", "kdOutEstopped", "kdOutLeaseExpired",
        "kdOutStallHalted", "kdOutSatLeft", "kdOutSatRight",
        "kdOutConnectedLeft", "kdOutConnectedRight",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = ctypes.c_int
    lib.kdOutCycleCount.argtypes = [ctypes.c_void_p]
    lib.kdOutCycleCount.restype = ctypes.c_uint32

    lib.kdMotorArmPosition.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_float, ctypes.c_uint64,
    ]
    lib.kdMotorArmPosition.restype = None
    lib.kdMotorSetCollectSucceeds.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    ]
    lib.kdMotorSetCollectSucceeds.restype = None
    lib.kdMotorSetVelocity.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_float]
    lib.kdMotorSetVelocity.restype = None
    lib.kdMotorSetConnected.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.kdMotorSetConnected.restype = None
    lib.kdMotorSetWedged.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.kdMotorSetWedged.restype = None
    lib.kdMotorSetWedgeSuspect.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.kdMotorSetWedgeSuspect.restype = None

    lib.kdMotorPosition.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdMotorPosition.restype = ctypes.c_float
    lib.kdMotorSampleTime.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdMotorSampleTime.restype = ctypes.c_uint64
    lib.kdMotorAppliedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdMotorAppliedDuty.restype = ctypes.c_float
    lib.kdMotorLastStagedDuty.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.kdMotorLastStagedDuty.restype = ctypes.c_float

    for name in (
        "kdMotorSetDutyCalls", "kdMotorTickCalls", "kdMotorBeginCalls",
        "kdMotorEmergencyStopCalls", "kdMotorRebaselineCalls",
        "kdMotorRequestSampleCalls", "kdMotorEmergencyStopped",
    ):
        fn = getattr(lib, name)
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
        fn.restype = ctypes.c_int

    lib.kdClockSetNow.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    lib.kdClockSetNow.restype = None
    lib.kdClockNow.argtypes = [ctypes.c_void_p]
    lib.kdClockNow.restype = ctypes.c_uint64

    lib.kdSleeperSleepCalls.argtypes = [ctypes.c_void_p]
    lib.kdSleeperSleepCalls.restype = ctypes.c_int
    lib.kdSleeperYieldCalls.argtypes = [ctypes.c_void_p]
    lib.kdSleeperYieldCalls.restype = ctypes.c_int
    lib.kdSleeperLastSleepMillis.argtypes = [ctypes.c_void_p]
    lib.kdSleeperLastSleepMillis.restype = ctypes.c_uint32

    lib.kdLauncherLaunchCalls.argtypes = [ctypes.c_void_p]
    lib.kdLauncherLaunchCalls.restype = ctypes.c_int

    return lib


@pytest.fixture(scope="session")
def kernel_lib(tmp_path_factory):
    """Compile diffdrive.cpp + kernel_shim.cpp exactly once for the whole
    pytest session and bind every ctypes signature once. Every test in
    this file gets a fully-bound library handle from this fixture instead
    of re-invoking the compiler.
    """
    lib_path = compile_shared_lib(tmp_path_factory)
    return _bind(ctypes.CDLL(str(lib_path)))


class Kernel:
    """Thin Pythonic wrapper around one kdCreate()/kdDestroy() handle --
    keeps test bodies readable without bare ctypes calls everywhere,
    mirroring test_protocol_harness.py's own habit of wrapping the raw
    shim rather than calling it inline in every test."""

    def __init__(self, lib):
        self._lib = lib
        self._handle = lib.kdCreate()

    def close(self):
        self._lib.kdDestroy(self._handle)
        self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    # ---- config ----
    def set_max_duty(self, value):
        self._lib.kdSetMaxDuty(self._handle, value)

    def set_full_duty_velocity(self, value):
        self._lib.kdSetFullDutyVelocity(self._handle, value)

    # ---- commands ----
    def begin(self):
        return self._lib.kdBegin(self._handle)

    def start(self):
        return self._lib.kdStart(self._handle)

    def drive(self, velocity, twist, lease_ms):
        return self._lib.kdDrive(self._handle, velocity, twist, lease_ms)

    def neutral(self):
        self._lib.kdNeutral(self._handle)

    def estop(self):
        self._lib.kdEstop(self._handle)

    def rebase_position(self):
        self._lib.kdRebasePosition(self._handle)

    def step(self):
        self._lib.kdStep(self._handle)

    # ---- fake clock ----
    def set_clock(self, now_us):
        self._lib.kdClockSetNow(self._handle, now_us)

    # ---- fake motor control ----
    def arm_motor_sample(self, side, position, sample_time_us):
        self._lib.kdMotorArmPosition(self._handle, side, position, sample_time_us)

    def motor_last_staged_duty(self, side):
        return self._lib.kdMotorLastStagedDuty(self._handle, side)

    def motor_set_duty_calls(self, side):
        return self._lib.kdMotorSetDutyCalls(self._handle, side)

    def motor_rebaseline_calls(self, side):
        return self._lib.kdMotorRebaselineCalls(self._handle, side)

    def motor_position(self, side):
        return self._lib.kdMotorPosition(self._handle, side)

    def motor_sample_time(self, side):
        return self._lib.kdMotorSampleTime(self._handle, side)

    def launcher_launch_calls(self):
        return self._lib.kdLauncherLaunchCalls(self._handle)

    # ---- output ----
    @property
    def out_velocity(self):
        return self._lib.kdOutVelocity(self._handle)

    @property
    def out_twist(self):
        return self._lib.kdOutTwist(self._handle)


def test_smoke_drive_and_step_reports_expected_duty_and_velocity(kernel_lib):
    """The ticket's required smoke test (SUC-002/SUC-003): construct the
    kernel over FakeMotors, begin(), drive(velocity, twist, lease), then
    step(), and confirm (a) the FakeMotors received the expected staged
    duty and (b) output() reports the expected commanded velocity/twist.

    diffdrive.cpp's own refreshSample() only starts reporting a nonzero
    MEASURED velocity on the second sample it ever collects ("velocity
    stays 0 until a second genuine sample exists") -- so this test arms
    one baseline encoder sample before the drive() call and a second,
    consistent-with-the-commanded-velocity sample after it, matching
    that contract instead of fighting it. The two samples are one
    control-period (0.1 s) apart and advance by exactly
    `velocity * interval`, so the delta refreshSample() computes lands
    on the commanded velocity by construction.
    """
    with Kernel(kernel_lib) as k:
        max_duty = 100.0              # [%]
        full_duty_velocity = 1000.0   # [counts/s] wheel rate at 100% duty
        velocity = 500.0              # [counts/s] commanded
        twist = 0.0                   # [counts/s] commanded

        k.set_max_duty(max_duty)
        k.set_full_duty_velocity(full_duty_velocity)
        assert k.begin() == STATUS_OK

        base_us = 1_000_000
        k.set_clock(base_us)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=base_us)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=base_us)
        k.step()  # baseline sample: velocity stays 0 after this one

        assert k.drive(velocity, twist, 5000) == STATUS_OK

        interval_s = 0.1
        next_us = base_us + int(interval_s * 1e6)
        next_position = velocity * interval_s
        k.set_clock(next_us)
        k.arm_motor_sample(LEFT, position=next_position, sample_time_us=next_us)
        k.arm_motor_sample(RIGHT, position=next_position, sample_time_us=next_us)
        k.step()

        expected_duty = velocity / full_duty_velocity
        assert k.motor_last_staged_duty(LEFT) == pytest.approx(expected_duty)
        assert k.motor_last_staged_duty(RIGHT) == pytest.approx(expected_duty)
        assert k.out_velocity == pytest.approx(velocity, rel=1e-3)
        assert k.out_twist == pytest.approx(twist, abs=1e-6)


def test_drive_refused_before_begin(kernel_lib):
    """SUC-002's "the harness proves the pipeline, not just the happy
    path": drive() before begin() must refuse (kRefusedNotBegun) and
    never stage a nonzero duty on either FakeMotor -- the kernel's own
    gate, exercised end to end through the shim."""
    with Kernel(kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(1000.0)

        assert k.drive(500.0, 0.0, 5000) == STATUS_REFUSED_NOT_BEGUN

        k.set_clock(0)
        k.step()

        assert k.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert k.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_neutral_returns_duty_to_zero_after_a_drive(kernel_lib):
    """neutral() must take effect on the very next step() -- a bare
    regression guard that the fake ports round-trip commands both ways,
    not just "drive up"."""
    with Kernel(kernel_lib) as k:
        k.set_max_duty(100.0)
        k.set_full_duty_velocity(1000.0)
        assert k.begin() == STATUS_OK

        k.set_clock(0)
        k.arm_motor_sample(LEFT, position=0.0, sample_time_us=0)
        k.arm_motor_sample(RIGHT, position=0.0, sample_time_us=0)
        k.step()

        assert k.drive(500.0, 0.0, 5000) == STATUS_OK
        k.set_clock(100_000)
        k.arm_motor_sample(LEFT, position=50.0, sample_time_us=100_000)
        k.arm_motor_sample(RIGHT, position=50.0, sample_time_us=100_000)
        k.step()
        assert k.motor_last_staged_duty(LEFT) == pytest.approx(0.5)

        k.neutral()
        k.set_clock(200_000)
        k.step()

        assert k.motor_last_staged_duty(LEFT) == pytest.approx(0.0)
        assert k.motor_last_staged_duty(RIGHT) == pytest.approx(0.0)


def test_rebaseline_issues_no_bus_traffic(kernel_lib):
    """diffdrive.md §2.1: "rebaseline() is a software re-anchor and must
    issue no bus traffic." Proven here at the fake-port level: after a
    committed sample, requesting a kernel rebase and stepping WITHOUT
    arming a new sample leaves the FakeMotor's own position/sampleTime
    completely unchanged (only the kernel's internal tracking resets;
    the port itself does nothing but count the call), even though
    rebaseline() was in fact invoked exactly once per wheel.
    """
    with Kernel(kernel_lib) as k:
        k.set_clock(1_000_000)
        k.arm_motor_sample(LEFT, position=42.0, sample_time_us=1_000_000)
        k.step()
        position_before = k.motor_position(LEFT)
        sample_time_before = k.motor_sample_time(LEFT)
        assert position_before == pytest.approx(42.0)

        k.rebase_position()
        k.step()  # this is the step that actually invokes rebaseline()

        assert k.motor_rebaseline_calls(LEFT) == 1
        assert k.motor_position(LEFT) == pytest.approx(position_before)
        assert k.motor_sample_time(LEFT) == sample_time_before
