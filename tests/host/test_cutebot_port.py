"""tests/host/test_cutebot_port.py -- host coverage for
`diffDrive::CutebotDevice`/`diffDrive::CutebotMotorPort`
(src/platform/cutebot_port.h/.cpp, sprint 040 ticket 002), the Cutebot
Pro's raw-PWM `DiffDrive::Motor` port, over a simulated 0x10 slave
(sim_cutebot_bus.h).

WHY THIS EXISTS. `docs/design/cutebot-pro-support.md` S3.A: a Cutebot
port has to prove "the same category of correctness the Nezha port
already has, one board level down" -- exact wire bytes, the coalesced
one-frame-per-cycle write, the degrees-to-counts conversion, and the
held-sampleTime-on-a-failed-read contract every `DiffDrive::Motor`
implementation in this repo must honour
(`src/DESIGN.md` S7). Unlike `nezha_port.cpp` (host-tested indirectly,
through a real kernel, via `sim_tour.py`), this ticket's job is the
port ITSELF, so this file drives `CutebotDevice`/`CutebotMotorPort`
directly -- no kernel in the link.

SOURCE READING, not MEASURED: every wire-protocol assertion here
encodes what `cutebot_port.h`/`sim_cutebot_bus.h` both cite as read
from ELECFREAKS' own extension; nothing has run on real Cutebot
hardware.

Run with::

    uv run pytest tests/host/test_cutebot_port.py
"""

import ctypes
import pathlib
import subprocess

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_HERE = pathlib.Path(__file__).resolve().parent

_SOURCES = [
    _HERE / "cutebot_port_shim.cpp",
    _SRC_DIR / "platform" / "cutebot_port.cpp",
    # Sprint 040 ticket 004: cutebot_port.cpp's stageDuty() now calls
    # CutebotActuationPolicy::decide() once both wheels have staged
    # (serviceCycle()) -- linking this TU is required from this ticket
    # on, even for tests that never touch onboard_pid/onboard_floor
    # directly (mode defaults to 0, so decide() always returns kPwm and
    # every pre-existing test in this file stays byte-identical).
    _SRC_DIR / "platform" / "cutebot_actuation_policy.cpp",
]

# WiringResult's own values (cutebot_port.h) -- pinned here as plain
# ints since ctypes cannot bind a C++ enum class directly.
_WIRING_OK = 0
_WIRING_UNIMPLEMENTED = 1


def _compile(tmp_path_factory):
    build_dir = tmp_path_factory.mktemp("cutebot_port_build")
    lib_path = build_dir / "libcutebotport.so"
    objects = []
    for index, source in enumerate(_SOURCES):
        obj = build_dir / f"{source.stem}.{index}.o"
        cmd = ["/usr/bin/c++", "-std=c++11", "-Wall", "-Wextra", "-fPIC",
               "-O0", "-DDIFFDRIVE_HOST_BUILD", "-c"]
        if not source.resolve().is_relative_to(_SRC_DIR.resolve()):
            cmd += ["-I", str(_SRC_DIR), "-I", str(_HERE)]
        cmd += [str(source), "-o", str(obj)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, (
            f"host compile failed for {source}:\ncommand: {' '.join(cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        objects.append(obj)
    link_cmd = (["/usr/bin/c++", "-shared", "-fPIC", "-o", str(lib_path)]
               + [str(o) for o in objects])
    result = subprocess.run(link_cmd, capture_output=True, text=True)
    assert result.returncode == 0, (
        f"host link failed:\ncommand: {' '.join(link_cmd)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return lib_path


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = _compile(tmp_path_factory)
    f = ctypes.CDLL(str(path))
    P = ctypes.c_void_p
    F = ctypes.c_float
    U64 = ctypes.c_ulonglong

    f.cpCreate.argtypes = [F, F, F]; f.cpCreate.restype = P
    f.cpDestroy.argtypes = [P]; f.cpDestroy.restype = None
    f.cpBegin.argtypes = [P, ctypes.c_int]; f.cpBegin.restype = ctypes.c_int
    f.cpRequestSample.argtypes = [P, ctypes.c_int]; f.cpRequestSample.restype = None
    f.cpSetDuty.argtypes = [P, ctypes.c_int, F]; f.cpSetDuty.restype = None
    f.cpTick.argtypes = [P, ctypes.c_int, U64]; f.cpTick.restype = None
    f.cpPosition.argtypes = [P, ctypes.c_int]; f.cpPosition.restype = F
    f.cpVelocity.argtypes = [P, ctypes.c_int]; f.cpVelocity.restype = F
    f.cpAppliedDuty.argtypes = [P, ctypes.c_int]; f.cpAppliedDuty.restype = F
    f.cpConnected.argtypes = [P, ctypes.c_int]; f.cpConnected.restype = ctypes.c_int
    f.cpSampleTime.argtypes = [P, ctypes.c_int]; f.cpSampleTime.restype = U64
    f.cpRebaseline.argtypes = [P, ctypes.c_int]; f.cpRebaseline.restype = None
    f.cpWedged.argtypes = [P, ctypes.c_int]; f.cpWedged.restype = ctypes.c_int
    f.cpWedgeSuspect.argtypes = [P, ctypes.c_int]; f.cpWedgeSuspect.restype = ctypes.c_int
    f.cpEmergencyStop.argtypes = [P, ctypes.c_int]; f.cpEmergencyStop.restype = None
    f.cpConfigureWiring.argtypes = [P, ctypes.c_int, ctypes.c_uint, ctypes.c_int]
    f.cpConfigureWiring.restype = ctypes.c_int
    f.cpWiredPort.argtypes = [P, ctypes.c_int]; f.cpWiredPort.restype = ctypes.c_uint
    f.cpWiredSign.argtypes = [P, ctypes.c_int]; f.cpWiredSign.restype = ctypes.c_int
    f.cpDiagValue.argtypes = [P, ctypes.c_int]; f.cpDiagValue.restype = ctypes.c_int
    f.cpBeginDevice.argtypes = [P]; f.cpBeginDevice.restype = ctypes.c_int
    f.cpIsV2.argtypes = [P]; f.cpIsV2.restype = ctypes.c_int
    f.cpHardwareClearEncoder.argtypes = [P, ctypes.c_int]
    f.cpHardwareClearEncoder.restype = ctypes.c_int
    f.cpFrameCount.argtypes = [P]; f.cpFrameCount.restype = ctypes.c_uint
    f.cpClearCount.argtypes = [P]; f.cpClearCount.restype = ctypes.c_uint
    f.cpProbeCount.argtypes = [P]; f.cpProbeCount.restype = ctypes.c_uint
    f.cpArmNack.argtypes = [P]; f.cpArmNack.restype = None
    f.cpStepPhysics.argtypes = [P, F]; f.cpStepPhysics.restype = None
    f.cpBusDuty.argtypes = [P, ctypes.c_int]; f.cpBusDuty.restype = F
    f.cpLastWheelFrame.argtypes = [P, ctypes.c_int]
    f.cpLastWheelFrame.restype = ctypes.c_uint
    return f


class Handle:
    """Thin Python wrapper -- side is always 0 (left) or 1 (right)."""

    def __init__(self, lib, tau=0.0, breakaway=0.0, duty_vel_max=100.0):
        self.lib = lib
        self.ptr = lib.cpCreate(tau, breakaway, duty_vel_max)

    def close(self):
        self.lib.cpDestroy(self.ptr)

    def begin(self, side):
        return bool(self.lib.cpBegin(self.ptr, side))

    def begin_both(self):
        return self.begin(0), self.begin(1)

    def request_sample(self, side):
        self.lib.cpRequestSample(self.ptr, side)

    def set_duty(self, side, duty):
        self.lib.cpSetDuty(self.ptr, side, duty)

    def tick(self, side, now_us):
        self.lib.cpTick(self.ptr, side, now_us)

    def cycle(self, now_us):
        """One kernel cycle: requestSample+tick for BOTH sides, left
        then right -- matches core/diffdrive.cpp's own step() order,
        though nothing here relies on that particular order being the
        one that ships (see cutebot_port.h's own header comment)."""
        self.request_sample(0)
        self.tick(0, now_us)
        self.request_sample(1)
        self.tick(1, now_us)

    def position(self, side):
        return self.lib.cpPosition(self.ptr, side)

    def velocity(self, side):
        return self.lib.cpVelocity(self.ptr, side)

    def applied_duty(self, side):
        return self.lib.cpAppliedDuty(self.ptr, side)

    def connected(self, side):
        return bool(self.lib.cpConnected(self.ptr, side))

    def sample_time(self, side):
        return self.lib.cpSampleTime(self.ptr, side)

    def rebaseline(self, side):
        self.lib.cpRebaseline(self.ptr, side)

    def wedged(self, side):
        return bool(self.lib.cpWedged(self.ptr, side))

    def wedge_suspect(self, side):
        return bool(self.lib.cpWedgeSuspect(self.ptr, side))

    def emergency_stop(self, side):
        self.lib.cpEmergencyStop(self.ptr, side)

    def configure_wiring(self, side, port, sign):
        return self.lib.cpConfigureWiring(self.ptr, side, port, sign)

    def wired_port(self, side):
        return self.lib.cpWiredPort(self.ptr, side)

    def wired_sign(self, side):
        return self.lib.cpWiredSign(self.ptr, side)

    def diag_value(self, ordinal):
        return self.lib.cpDiagValue(self.ptr, ordinal)

    def begin_device(self):
        return bool(self.lib.cpBeginDevice(self.ptr))

    def is_v2(self):
        return bool(self.lib.cpIsV2(self.ptr))

    def hardware_clear_encoder(self, side):
        return bool(self.lib.cpHardwareClearEncoder(self.ptr, side))

    def frame_count(self):
        return self.lib.cpFrameCount(self.ptr)

    def clear_count(self):
        return self.lib.cpClearCount(self.ptr)

    def probe_count(self):
        return self.lib.cpProbeCount(self.ptr)

    def arm_nack(self):
        self.lib.cpArmNack(self.ptr)

    def step_physics(self, dt):
        self.lib.cpStepPhysics(self.ptr, dt)

    def bus_duty(self, side):
        return self.lib.cpBusDuty(self.ptr, side)

    def last_wheel_frame(self):
        """(wheel, absL, absR, dirbits) of the last shipped 0x10 frame."""
        return tuple(self.lib.cpLastWheelFrame(self.ptr, i) for i in range(4))


@pytest.fixture
def handle(lib):
    h = Handle(lib)
    yield h
    h.close()


# ---------------------------------------------------------------------
# Revision probe at begin().
# ---------------------------------------------------------------------

def test_revision_probe_runs_once_and_reports_v2(handle):
    assert handle.probe_count() == 0
    assert handle.begin(0) is True
    assert handle.probe_count() == 1
    assert handle.is_v2() is True
    # The OTHER wheel's begin() must not re-probe -- cached for the
    # session (cutebot_port.h's own header comment).
    assert handle.begin(1) is True
    assert handle.probe_count() == 1


def test_begin_device_directly_is_idempotent(handle):
    assert handle.begin_device() is True
    assert handle.begin_device() is True
    assert handle.probe_count() == 1


# ---------------------------------------------------------------------
# Frame bytes and direction bits.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "left_duty,right_duty,expected_dirbits",
    [
        (0.5, 0.3, 0b00),   # both forward
        (0.5, -0.3, 0b10),  # left forward, right reverse
        (-0.5, 0.3, 0b01),  # left reverse, right forward
        (-0.5, -0.3, 0b11), # both reverse
    ],
)
def test_frame_bytes_for_all_four_sign_combinations(
    handle, left_duty, right_duty, expected_dirbits
):
    """fwdSign_ is left at its default +1/+1 here -- this test is about
    CutebotDevice::shipFrame()'s own dirbit/abs% encoding of a COMMANDED
    duty's sign, independent of the sign-flip path (see the
    configureWiring tests below for that)."""
    handle.begin_both()
    handle.set_duty(0, left_duty)
    handle.set_duty(1, right_duty)
    handle.cycle(now_us=1000)
    assert handle.frame_count() == 1
    wheel, abs_l, abs_r, dirbits = handle.last_wheel_frame()
    assert wheel == 2  # "both"
    assert abs_l == 50
    assert abs_r == 30
    assert dirbits == expected_dirbits


def test_fwd_sign_flips_the_wire_dirbit_for_the_same_commanded_duty(handle):
    handle.begin_both()
    assert handle.configure_wiring(0, handle.wired_port(0), -1) == _WIRING_OK
    handle.set_duty(0, 0.4)   # commanded FORWARD (caller-space)
    handle.set_duty(1, 0.4)
    handle.cycle(now_us=1000)
    _, abs_l, abs_r, dirbits = handle.last_wheel_frame()
    assert abs_l == 40 and abs_r == 40
    # Left is sign-flipped -> its WIRE direction is reverse (bit 0);
    # right is untouched -> forward (bit 1 clear).
    assert dirbits == 0b01


# ---------------------------------------------------------------------
# Exactly one 0x10 frame per kernel cycle.
# ---------------------------------------------------------------------

def test_exactly_one_frame_per_cycle_for_the_pair(handle):
    handle.begin_both()
    assert handle.frame_count() == 0
    handle.set_duty(0, 0.2)
    handle.set_duty(1, 0.2)
    handle.cycle(now_us=1000)
    assert handle.frame_count() == 1
    handle.cycle(now_us=2000)
    assert handle.frame_count() == 2


def test_ticking_only_one_side_never_ships(handle):
    handle.begin_both()
    handle.set_duty(0, 0.2)
    handle.request_sample(0)
    handle.tick(0, 1000)
    assert handle.frame_count() == 0  # only ONE side staged so far
    handle.request_sample(1)
    handle.tick(1, 1000)
    assert handle.frame_count() == 1  # the second side completes the pair


# ---------------------------------------------------------------------
# Degrees -> counts conversion, exact, both directions.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("duty,expected_counts", [(1.0, 100.0), (-1.0, -100.0)])
def test_degrees_to_counts_conversion_is_exact(lib, duty, expected_counts):
    # tau=0 (no lag), breakaway=0 (no stiction), dutyVelMax=100 counts/s
    # -- a fully deterministic linear plant so the degrees<->counts
    # round trip (through the wire's own truncating integer division)
    # lands on an EXACT value with no floating slack to explain away.
    h = Handle(lib, tau=0.0, breakaway=0.0, duty_vel_max=100.0)
    try:
        h.begin_both()
        h.set_duty(0, duty)
        h.cycle(now_us=0)             # ships this cycle's duty; reads 0
        h.step_physics(dt=1.0)        # 100 counts/s for 1.0 s -> 100 counts
        h.cycle(now_us=1_000_000)     # 1 s later: reads the moved position
        assert h.position(0) == pytest.approx(expected_counts, abs=1e-6)
    finally:
        h.close()


# ---------------------------------------------------------------------
# rebaseline(): software-only, no bus traffic.
# ---------------------------------------------------------------------

def test_rebaseline_is_software_only(handle):
    handle.begin_both()
    handle.set_duty(0, 1.0)
    handle.cycle(now_us=0)
    handle.step_physics(dt=1.0)
    handle.cycle(now_us=1_000_000)
    assert handle.position(0) != 0.0

    frames_before = handle.frame_count()
    clears_before = handle.clear_count()
    handle.rebaseline(0)
    assert handle.position(0) == 0.0
    assert handle.frame_count() == frames_before
    assert handle.clear_count() == clears_before


# ---------------------------------------------------------------------
# emergencyStop(): immediate, unstaged, single-wheel zero.
# ---------------------------------------------------------------------

def test_emergency_stop_bytes_and_applied_duty(handle):
    handle.begin_both()
    handle.set_duty(0, 0.8)
    handle.set_duty(1, 0.8)
    handle.emergency_stop(0)
    wheel, abs_l, abs_r, dirbits = handle.last_wheel_frame()
    assert (wheel, abs_l, abs_r, dirbits) == (0, 0, 0, 0)  # LEFT only, zeroed
    assert handle.applied_duty(0) == 0.0
    # The other side's own staged duty is untouched by this call.
    assert handle.frame_count() == 1  # the immediate zero write itself


# ---------------------------------------------------------------------
# A NACK'd encoder read holds connected()/sampleTime(), never a
# fabricated zero velocity.
# ---------------------------------------------------------------------

def test_nack_on_encoder_read_holds_sample_time_and_marks_disconnected(handle):
    handle.begin_both()
    handle.set_duty(0, 0.5)
    handle.cycle(now_us=0)
    handle.step_physics(dt=1.0)
    handle.cycle(now_us=1_000_000)
    assert handle.connected(0) is True
    sample_before = handle.sample_time(0)
    velocity_before = handle.velocity(0)
    position_before = handle.position(0)

    handle.request_sample(0)
    handle.arm_nack()
    handle.tick(0, 2_000_000)

    assert handle.connected(0) is False
    assert handle.sample_time(0) == sample_before
    assert handle.velocity(0) == velocity_before
    assert handle.position(0) == position_before


# ---------------------------------------------------------------------
# wedged()/wedgeSuspect(): no detector yet (minimal shaping).
# ---------------------------------------------------------------------

def test_wedged_and_wedge_suspect_always_false(handle):
    handle.begin_both()
    for _ in range(20):
        handle.cycle(now_us=0)
    assert handle.wedged(0) is False
    assert handle.wedge_suspect(0) is False


# ---------------------------------------------------------------------
# configureWiring(): sign-only accepted, port-changing refused.
# ---------------------------------------------------------------------

def test_configure_wiring_accepts_sign_only_change(handle):
    handle.begin_both()
    assert handle.wired_sign(0) == 1
    result = handle.configure_wiring(0, handle.wired_port(0), -1)
    assert result == _WIRING_OK
    assert handle.wired_sign(0) == -1
    assert handle.wired_port(0) == 1  # port is unchanged -- still "its own"


def test_configure_wiring_refuses_a_port_change(handle):
    handle.begin_both()
    left_port = handle.wired_port(0)
    right_port = handle.wired_port(1)
    assert left_port != right_port

    result = handle.configure_wiring(0, right_port, -1)
    assert result == _WIRING_UNIMPLEMENTED
    # Refused -- NOTHING changed, including the sign that rode along
    # with the refused port request.
    assert handle.wired_port(0) == left_port
    assert handle.wired_sign(0) == 1


def test_configure_wiring_out_of_range_sign_is_a_no_op(handle):
    handle.begin_both()
    result = handle.configure_wiring(0, handle.wired_port(0), 5)
    assert result == _WIRING_OK
    assert handle.wired_sign(0) == 1  # unchanged


def test_configure_wiring_same_value_is_a_free_no_op(handle):
    handle.begin_both()
    frames_before = handle.frame_count()
    result = handle.configure_wiring(0, handle.wired_port(0), 1)
    assert result == _WIRING_OK
    assert handle.frame_count() == frames_before  # no emergencyStop() fired


# ---------------------------------------------------------------------
# hardwareClearEncoder(): a REAL 0x50 write, distinct from rebaseline().
# ---------------------------------------------------------------------

def test_hardware_clear_encoder_is_a_real_bus_write(handle):
    handle.begin_both()
    assert handle.clear_count() == 0
    assert handle.hardware_clear_encoder(0) is True
    assert handle.clear_count() == 1
    assert handle.hardware_clear_encoder(1) is True
    assert handle.clear_count() == 2


# ---------------------------------------------------------------------
# Board-generic diag hook (cutebotBoardDiagValue()): wiring readback
# only; everything else falls through to 0.
# ---------------------------------------------------------------------

def test_diag_value_wiring_ordinals(handle):
    handle.begin_both()
    handle.configure_wiring(0, handle.wired_port(0), -1)
    assert handle.diag_value(35) == handle.wired_port(0)
    assert handle.diag_value(36) == -1
    assert handle.diag_value(37) == handle.wired_port(1)
    assert handle.diag_value(38) == 1
    assert handle.diag_value(21) == 0  # no glitch-armor field exists yet
    assert handle.diag_value(999) == 0  # unknown ordinal falls through
