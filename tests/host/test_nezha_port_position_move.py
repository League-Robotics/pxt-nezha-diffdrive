"""tests/host/test_nezha_port_position_move.py -- sprint 042 ticket 004.

The real `NezhaMotorPort` (src/platform/nezha_port.cpp) against the
simulated brick (sim_nezha_bus.h, ticket 003) through
sim_nezha_port_shim.cpp: one port on M1, the test plays the kernel (a
setDuty() then a tick() per 24 ms cycle).

Frame bytes are those of docs/knowledge/2026-10-27-nezha-brick-opcodes.md
section 4 ("the opcode doc"); behaviour rules cite its section 3. The
simulator is a model fitted to that doc, so nothing here is a hardware
result of this sprint.
"""

import ctypes
import pathlib
import subprocess

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_SRC = _HERE.parent.parent / "src"

# Frame layout: FF F9 <port> <dir> <op> <hi> <mode> <lo>
SPEED = lambda dps, port=1: bytes(
    [0xFF, 0xF9, port, 0x00, 0x77, dps >> 8, 0x00, dps & 0xFF])
MOVE = lambda deg, rev=False, port=1: bytes(
    [0xFF, 0xF9, port, 2 if rev else 1, 0x70, deg >> 8, 0x02, deg & 0xFF])
STOP5F = bytes([0xFF, 0xF9, 0x01, 0x00, 0x5F, 0x00, 0xF5, 0x00])
RUN0 = bytes([0xFF, 0xF9, 0x01, 0x01, 0x60, 0x00, 0xF5, 0x00])


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    build = tmp_path_factory.mktemp("nezha_port_pos_build")
    objs = []
    for i, src in enumerate([_HERE / "sim_nezha_port_shim.cpp",
                             _SRC / "platform" / "nezha_port.cpp"]):
        obj = build / f"{src.stem}.{i}.o"
        # Production port stays C++11; the test scaffolding (the sim bus
        # ODR-uses a static constexpr member) builds as C++17.
        std = "-std=c++11" if src.resolve().is_relative_to(_SRC.resolve()) \
            else "-std=c++17"
        cmd = ["/usr/bin/c++", std, "-Wall", "-Wextra", "-fPIC",
               "-O0", "-DDIFFDRIVE_HOST_BUILD", "-c"]
        if not src.resolve().is_relative_to(_SRC.resolve()):
            cmd += ["-I", str(_SRC), "-I", str(_HERE)]
        cmd += [str(src), "-o", str(obj)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        objs.append(obj)
    so = build / "libnezhaportpos.so"
    r = subprocess.run(["/usr/bin/c++", "-shared", "-fPIC", "-o", str(so)]
                       + [str(o) for o in objs], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    f = ctypes.CDLL(str(so))
    P, F, I, U32 = (ctypes.c_void_p, ctypes.c_float, ctypes.c_int,
                    ctypes.c_uint32)
    f.npCreate.argtypes = [F, I]; f.npCreate.restype = P
    for n in ("npDestroy", "npBegin", "npTick", "npEmergencyStop", "npClearLog"):
        getattr(f, n).argtypes = [P]
    f.npSetDuty.argtypes = [P, F]
    f.npBeginMove.argtypes = [P, F, F]; f.npBeginMove.restype = I
    f.npFreeze.argtypes = [P, I]
    for n in ("npHardStop", "npMoveLive", "npDriven", "npSupports", "npWedged",
              "npWedgeSuspect", "npBusMoveLive"):
        getattr(f, n).argtypes = [P]; getattr(f, n).restype = I
    for n in ("npQuantum", "npLastMoveCounts", "npPosition", "npVelocity",
              "npApplied", "npWheelPos", "npWheelVel"):
        getattr(f, n).argtypes = [P]; getattr(f, n).restype = F
    for n in ("npFrameCount", "npFrames60", "npFrames60WhileLive",
              "npViolations1D", "npGlitchCount"):
        getattr(f, n).argtypes = [P]; getattr(f, n).restype = U32
    f.npFrame.argtypes = [P, U32, ctypes.POINTER(ctypes.c_uint8)]
    f.npFrame.restype = I
    return f


class Rig:
    def __init__(self, lib, tau=0.0, fwd=1):
        self.lib, self.h = lib, lib.npCreate(tau, fwd)
        lib.npBegin(self.h)
        lib.npClearLog(self.h)

    def close(self):
        self.lib.npDestroy(self.h)

    def tick(self, n=1, duty=0.0):
        """n kernel cycles; the kernel calls setDuty(duty) every cycle."""
        for _ in range(n):
            self.lib.npSetDuty(self.h, duty)
            self.lib.npTick(self.h)

    def until(self, pred, limit=2000, duty=0.0):
        for i in range(limit):
            if pred():
                return i
            self.tick(1, duty)
        raise AssertionError("condition not reached")

    def cmds(self):
        """Command frames (0x77 / 0x70 / 0x5F / 0x60), in order; the
        0x46 encoder selects are left out."""
        out = []
        buf = (ctypes.c_uint8 * 8)()
        for i in range(self.lib.npFrameCount(self.h)):
            self.lib.npFrame(self.h, i, buf)
            b = bytes(buf)
            if b[4] in (0x77, 0x70, 0x5F, 0x60):
                out.append(b)
        return out

    def live(self):
        return self.lib.npMoveLive(self.h) == 1


@pytest.fixture()
def rig(lib):
    r = Rig(lib)
    yield r
    r.close()


def test_position_move_seam(rig, lib):
    assert lib.npSupports(rig.h) == 1
    assert lib.npQuantum(rig.h) == 10.0


def test_frames_byte_exact_speed_then_move(rig, lib):
    # 1234 counts rounds to 123 degrees (1230 counts); 300 deg/s = 0x012C.
    assert lib.npBeginMove(rig.h, 1234.0, 300.0) == 1
    assert rig.cmds() == [SPEED(300), MOVE(123)]
    assert lib.npLastMoveCounts(rig.h) == 1230.0
    assert lib.npMoveLive(rig.h) == 1 and lib.npDriven(rig.h) == 1
    # Brick side: the sim stored 300 deg/s and holds a position target.
    assert lib.npBusMoveLive(rig.h) == 1


def test_speed_written_once_per_change_per_port(rig, lib):
    assert lib.npBeginMove(rig.h, 500.0, 300.0) == 1
    rig.until(lambda: not rig.live())
    assert lib.npBeginMove(rig.h, 500.0, 300.0) == 1  # same speed
    rig.until(lambda: not rig.live())
    assert lib.npBeginMove(rig.h, 500.0, 450.0) == 1  # changed speed
    speeds = [f for f in rig.cmds() if f[4] == 0x77]
    moves = [f for f in rig.cmds() if f[4] == 0x70]
    assert speeds == [SPEED(300), SPEED(450)]
    assert len(moves) == 3


def test_negative_delta_uses_reverse_direction_byte(rig, lib):
    assert lib.npBeginMove(rig.h, -400.0, 200.0) == 1
    assert rig.cmds()[-1] == MOVE(40, rev=True)
    assert lib.npLastMoveCounts(rig.h) == -400.0


def test_fwd_sign_minus_one_flips_direction_byte(lib):
    r = Rig(lib, fwd=-1)
    try:
        # Robot-forward on a mirror-mounted wheel is raw-negative.
        assert lib.npBeginMove(r.h, 300.0, 200.0) == 1
        assert r.cmds()[-1] == MOVE(30, rev=True)
        r.until(lambda: not r.live())
        assert lib.npPosition(r.h) == pytest.approx(300.0, abs=10.0)
    finally:
        r.close()


def test_refused_moves_write_nothing_and_set_no_latch(rig, lib):
    assert lib.npBeginMove(rig.h, 4.0, 300.0) == 0     # under one degree
    assert lib.npBeginMove(rig.h, 500.0, 0.0) == 0     # no speed
    assert rig.cmds() == []
    assert lib.npMoveLive(rig.h) == 0 and lib.npDriven(rig.h) == 0
    assert lib.npLastMoveCounts(rig.h) == 0.0


def test_f3_kernel_zero_duty_every_tick_does_not_cancel_live_move(rig, lib):
    """Review F3 regression. The kernel calls setDuty(0) every tick; the
    old stopNotTaken path re-wrote 0x60 0 each tick while the wheel read
    above rest, which on the brick ramps the move down and drops its
    target (opcode doc section 3 rule 1). With the latch live there must
    be ZERO 0x60 frames and the move must reach its target."""
    assert lib.npBeginMove(rig.h, 3600.0, 300.0) == 1
    fast = 0
    for _ in range(400):
        if not rig.live():
            break
        rig.tick(1, duty=0.0)
        if abs(lib.npVelocity(rig.h)) > 102.0:
            fast += 1
    assert fast > 10, "the wheel must actually read above rest"
    assert lib.npFrames60(rig.h) == 0
    assert lib.npFrames60WhileLive(rig.h) == 0
    assert not rig.live()
    assert lib.npWheelPos(rig.h) == pytest.approx(3600.0, abs=1.0)
    assert lib.npPosition(rig.h) == pytest.approx(3600.0, abs=20.0)
    assert lib.npDriven(rig.h) == 0
    # After completion the kernel's setDuty(0) still writes nothing.
    rig.tick(20, duty=0.0)
    assert lib.npFrames60(rig.h) == 0


def test_control_without_latch_zero_duty_rewrites_0x60(lib):
    """The F3 test above is not vacuous: with no move live the same
    stopNotTaken path still re-writes 0x60 0 while the wheel runs on."""
    r = Rig(lib, tau=0.3)
    try:
        r.tick(40, duty=0.5)
        r.lib.npClearLog(r.h)
        r.tick(10, duty=0.0)
        assert r.lib.npFrames60(r.h) >= 2
    finally:
        r.close()


def test_set_duty_is_a_no_op_while_live(rig, lib):
    assert lib.npBeginMove(rig.h, 2000.0, 300.0) == 1
    rig.tick(10, duty=0.8)
    assert lib.npFrames60(rig.h) == 0
    assert lib.npApplied(rig.h) == 0.0
    assert lib.npMoveLive(rig.h) == 1


def test_hard_stop_emits_one_5f_clears_latch_and_holds(rig, lib):
    assert lib.npBeginMove(rig.h, 3600.0, 300.0) == 1
    rig.tick(15)
    assert lib.npVelocity(rig.h) > 102.0
    assert lib.npHardStop(rig.h) == 1
    assert [f for f in rig.cmds() if f[4] == 0x5F] == [STOP5F]
    assert lib.npMoveLive(rig.h) == 0 and lib.npDriven(rig.h) == 0
    # The kernel's setDuty(0) while the wheel is still coasting down must
    # not turn the hard stop into a 0x60 ramp.
    rig.tick(30, duty=0.0)
    assert lib.npFrames60(rig.h) == 0
    assert [f for f in rig.cmds() if f[4] == 0x5F] == [STOP5F]
    assert lib.npBusMoveLive(rig.h) == 0
    assert abs(lib.npWheelVel(rig.h)) < 1.0
    # hard stop holds within 5 degrees (opcode doc section 3 rule 4)
    assert lib.npWheelPos(rig.h) < 3600.0


def test_emergency_stop_live_sends_5f_then_0x60_zero(rig, lib):
    assert lib.npBeginMove(rig.h, 3600.0, 300.0) == 1
    rig.tick(10)
    lib.npClearLog(rig.h)
    lib.npEmergencyStop(rig.h)
    assert rig.cmds() == [STOP5F, RUN0]
    assert lib.npMoveLive(rig.h) == 0


def test_emergency_stop_not_live_is_unchanged(rig, lib):
    rig.tick(10, duty=0.4)
    lib.npClearLog(rig.h)
    lib.npEmergencyStop(rig.h)
    assert rig.cmds() == [RUN0]


def test_frozen_counter_mid_move_is_still_a_wedge(rig, lib):
    assert lib.npBeginMove(rig.h, 36000.0, 300.0) == 1
    rig.tick(10)
    assert lib.npWedgeSuspect(rig.h) == 0
    lib.npFreeze(rig.h, 1)
    rig.tick(12)
    assert lib.npMoveLive(rig.h) == 1  # not "done": far from the target
    assert lib.npDriven(rig.h) == 1
    assert lib.npWedgeSuspect(rig.h) == 1
    assert lib.npWedged(rig.h) == 1


def test_counter_advancing_while_port_not_commanding_is_accepted(rig, lib):
    """The brick moves the wheel with no 0x60 on the wire; a frozen read
    followed by a jump of a few thousand counts (under the glitch armor's
    5000-count bound) is real motion, not a glitch."""
    assert lib.npBeginMove(rig.h, 36000.0, 900.0) == 1
    rig.tick(5)
    lib.npFreeze(rig.h, 1)
    rig.tick(10)
    lib.npFreeze(rig.h, 0)
    rig.tick(1)
    assert lib.npGlitchCount(rig.h) == 0
    assert lib.npPosition(rig.h) == pytest.approx(lib.npWheelPos(rig.h),
                                                   abs=250.0)


def test_never_emits_0x1d(rig, lib):
    lib.npBeginMove(rig.h, 800.0, 300.0)
    rig.until(lambda: not rig.live())
    lib.npBeginMove(rig.h, -800.0, 300.0)
    rig.tick(5)
    lib.npHardStop(rig.h)
    lib.npEmergencyStop(rig.h)
    assert lib.npViolations1D(rig.h) == 0
    assert all(f[4] != 0x1D for f in rig.cmds())


def test_velocity_path_untouched_when_no_move_live(rig, lib):
    rig.tick(30, duty=0.3)
    assert lib.npFrames60(rig.h) > 0
    assert lib.npApplied(rig.h) == pytest.approx(0.3, abs=0.02)
    assert lib.npDriven(rig.h) == 1
