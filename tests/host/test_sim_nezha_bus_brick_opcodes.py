"""tests/host/test_sim_nezha_bus_brick_opcodes.py -- sprint 042 ticket 003.

Pins the simulated Nezha brick (`sim_nezha_bus.h`) against what the
2026-10-27 sniff and the micro:bit rig measured, as recorded in
`docs/knowledge/2026-10-27-nezha-brick-opcodes.md` (the "doc" below) and
the CSVs copied to `docs/code-review/2026-10-27/data/`. Nothing here is
a hardware result of this sprint: each assertion compares the SIMULATOR
to a number from the doc, and says which row and file. Where the model
is only fitted to a row (the constants in `sim_nezha_bus.h`), the
tolerance says so; where the doc cites a file that is not in this tree
(doc section 3), the test cites the doc only.

Drives `sim_nezha_brick_shim.cpp` (the bus alone) through ctypes, with
byte-exact I2C frames: `FF F9 <port> <dir> <op> <hi> <mode> <lo>`.
"""

import csv
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_HERE = pathlib.Path(__file__).resolve().parent
_DATA = _HERE.parent.parent / "docs" / "code-review" / "2026-10-27" / "data"
_DOC = "docs/knowledge/2026-10-27-nezha-brick-opcodes.md"

DT = 0.001  # [s] simulated step


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = compile_shared_lib(
        tmp_path_factory,
        sources=[_HERE / "sim_nezha_brick_shim.cpp"],
        out_name="libsimnezhabrick.so",
    )
    f = ctypes.CDLL(str(path))
    P, F, I = ctypes.c_void_p, ctypes.c_float, ctypes.c_int
    U8P = ctypes.POINTER(ctypes.c_uint8)
    f.nbCreate.argtypes = [F, F, F]; f.nbCreate.restype = P
    f.nbDestroy.argtypes = [P]
    f.nbWrite.argtypes = [P, ctypes.c_char_p]; f.nbWrite.restype = I
    f.nbReadCounts.argtypes = [P, ctypes.POINTER(ctypes.c_int32)]
    f.nbReadCounts.restype = I
    f.nbStep.argtypes = [P, F]
    f.nbSetOwnedRunDegPerPercent.argtypes = [P, F]
    for n in ("nbPosition", "nbVelocity"):
        getattr(f, n).argtypes = [P, I]; getattr(f, n).restype = F
    for n in ("nbMoveLive", "nbHasTarget", "nbSpeedStore"):
        getattr(f, n).argtypes = [P, I]; getattr(f, n).restype = I
    f.nbFrameCount.argtypes = [P]; f.nbFrameCount.restype = ctypes.c_uint32
    f.nbFrame.argtypes = [P, ctypes.c_uint32, U8P]; f.nbFrame.restype = I
    for n in ("nbFrames60", "nbFrames60WhileLive"):
        getattr(f, n).argtypes = [P, I]
        getattr(f, n).restype = ctypes.c_uint32
    f.nbViolations1D.argtypes = [P]; f.nbViolations1D.restype = ctypes.c_uint32
    return f


class Brick:
    """One simulated bus. Positions are reported in DEGREES."""

    def __init__(self, lib, owned_run=True, duty_vel_max=11500.0, tau=0.0):
        self.lib = lib
        # dutyVelMax 11500 counts/s = 1150 deg/s at duty 1 (doc section 1:
        # 11.5 deg/s per 0x60 percent).
        self.h = lib.nbCreate(tau, 0.0, duty_vel_max)
        if owned_run:
            lib.nbSetOwnedRunDegPerPercent(self.h, 11.5)

    def close(self):
        self.lib.nbDestroy(self.h)

    def frame(self, port, op, value=0, mode=0, direction=0):
        buf = bytes([0xFF, 0xF9, port, direction, op, (value >> 8) & 0xFF,
                     mode, value & 0xFF])
        return self.lib.nbWrite(self.h, buf)

    # The three frames sprint 042 emits (doc section 4) and 0x60.
    def store(self, port, dps):
        return self.frame(port, 0x77, dps)

    def move_deg(self, port, deg):
        return self.frame(port, 0x70, abs(deg), mode=2,
                          direction=2 if deg < 0 else 1)

    def timed(self, port, n, reverse=False):
        return self.frame(port, 0x70, n, mode=3, direction=2 if reverse else 1)

    def stop(self, port):
        return self.frame(port, 0x5F, 0, mode=0xF5)

    def run(self, port, pct, reverse=False):
        return self.frame(port, 0x60, pct << 8, mode=0xF5,
                          direction=2 if reverse else 1)

    def run_for(self, seconds):
        for _ in range(int(round(seconds / DT))):
            self.lib.nbStep(self.h, DT)

    def pos(self, port=1):
        return self.lib.nbPosition(self.h, port) / 10.0  # counts -> deg

    def vel(self, port=1):
        return self.lib.nbVelocity(self.h, port) / 10.0  # [deg/s]

    def read_deg(self):
        out = ctypes.c_int32()
        assert self.lib.nbReadCounts(self.h, ctypes.byref(out)) == 0
        return out.value / 10.0

    def frames(self):
        out = []
        buf = (ctypes.c_uint8 * 8)()
        for i in range(self.lib.nbFrameCount(self.h)):
            assert self.lib.nbFrame(self.h, i, buf)
            out.append(bytes(buf))
        return out


@pytest.fixture
def brick(lib):
    b = Brick(lib)
    yield b
    b.close()


def _csv(name):
    with open(_DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Doc section 5a -- stop travel, ramp (0x60 0) against hard (0x5F).
# mb_probe_stops1.csv, columns after_stop_deg, how (0 = ramp, 1 = hold).
# ---------------------------------------------------------------------------

def _stop_means():
    rows = _csv("mb_probe_stops1.csv")
    means = {}
    for r in rows:
        key = (int(r["pct"]), int(r["how"]))
        means.setdefault(key, []).append(float(r["after_stop_deg"]))
    return {k: sum(v) / len(v) for k, v in means.items()}


_STOP_MEANS = _stop_means()


def _travel_after_stop(lib, pct, how):
    b = Brick(lib)
    try:
        b.run(1, pct)
        b.run_for(0.8)  # the rig ran 800 ms, then stopped
        before = b.pos()
        if how == 0:
            b.run(1, 0)
        else:
            b.stop(1)
        b.run_for(1.0)
        return b.pos() - before
    finally:
        b.close()


@pytest.mark.parametrize("pct", [8, 15, 30, 60, 100])
def test_5a_ramp_stop_travel(lib, pct):
    """doc 5a, 0x60 0 column: mb_probe_stops1.csv how=0 (mean of 2)."""
    want = _STOP_MEANS[(pct, 0)]
    got = _travel_after_stop(lib, pct, 0)
    # kAccel is a fit to these five rows (v^2/2a): worst row +12 %.
    assert got == pytest.approx(want, rel=0.15, abs=0.5), (
        f"{_DOC} 5a / mb_probe_stops1.csv how=0 pct={pct}")


@pytest.mark.parametrize("pct", [8, 15, 30, 60, 100])
def test_5a_hard_stop_travel(lib, pct):
    """doc 5a, 0x5F column: mb_probe_stops1.csv how=1 (mean of 2)."""
    want = _STOP_MEANS[(pct, 1)]
    got = _travel_after_stop(lib, pct, 1)
    assert got == pytest.approx(want, rel=0.20, abs=0.5), (
        f"{_DOC} 5a / mb_probe_stops1.csv how=1 pct={pct}")


def test_5a_hard_stop_beats_ramp_from_15_percent_up(lib):
    """The 5a finding: 0x5F travels less than 0x60 0, from 15 % up."""
    for pct in (15, 30, 60, 100):
        assert _travel_after_stop(lib, pct, 1) < _travel_after_stop(lib, pct, 0)


# ---------------------------------------------------------------------------
# Doc section 5b -- fine velocity through the brick (0x77 then 0x70 mode 3).
# mb_probe_fine1.csv, `finevel` rows, column velocity_dps.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("row", _csv("mb_probe_fine1.csv"),
                         ids=lambda r: f"{r['test']}-{r['pct']}")
def test_5b_fine_velocity(lib, row):
    if row["test"] != "finevel":
        pytest.skip("supersede rows are covered separately below")
    b = Brick(lib)
    try:
        b.store(1, int(row["pct"]))  # the 'pct' column is the 0x77 value
        assert b.timed(1, 3) == 0  # 2.7 s run, long enough to measure
        b.run_for(0.5)
        first = b.read_deg()
        b.run_for(1.2)  # two 0x46 reads 1.2 s apart (doc 5b)
        second = b.read_deg()
        measured = float(row["velocity_dps"])
        got = (second - first) / 1.2
        # Saturation rows (1000/1100/1200) are 977.8/981.4/990.8 against
        # the model's flat 980: within 2 %.
        assert got == pytest.approx(measured, rel=0.02), (
            f"{_DOC} 5b / mb_probe_fine1.csv finevel {row['pct']}")
    finally:
        b.close()


def test_5b_supersede_rows(lib):
    """Supersede rows of mb_probe_fine1.csv: 300, then 150, then -150."""
    rows = {r["pct"]: r for r in _csv("mb_probe_fine1.csv")
            if r["test"] == "supersede"}
    b = Brick(lib)
    try:
        b.store(1, 300)
        b.timed(1, 6)
        b.run_for(1.0)
        assert b.vel() == pytest.approx(float(rows["300"]["velocity_dps"]),
                                        rel=0.02)
        b.store(1, 150)
        b.timed(1, 6)   # a fresh 0x70 after the 0x77 (doc section 4)
        b.run_for(1.0)
        assert b.vel() == pytest.approx(float(rows["150"]["velocity_dps"]),
                                        rel=0.02)
        b.timed(1, 6, reverse=True)  # reversed direction byte
        b.run_for(1.5)
        assert b.vel() == pytest.approx(float(rows["-150"]["velocity_dps"]),
                                        rel=0.02)
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Doc section 3 behaviour rules (micro:bit rig, run log not copied: cited to
# the doc only). 450 deg/s is "50 %" as RUN brickx sends it (pct x 9).
# ---------------------------------------------------------------------------

def _start_360_at_450(b):
    b.store(1, 450)
    assert b.move_deg(1, 360) == 0
    b.run_for(0.3)  # the rig issued the second command at 300 ms
    assert b.lib.nbHasTarget(b.h, 1) == 1
    return b.pos()


def test_rule1_stop_ramp_during_move_travels_46_and_drops_target(brick):
    at = _start_360_at_450(brick)
    brick.run(1, 0)
    assert brick.lib.nbHasTarget(brick.h, 1) == 0
    brick.run_for(2.0)
    # doc section 3 rule 1: 46 degrees more travel (kMoveStopDecel fit).
    assert brick.pos() - at == pytest.approx(46.0, rel=0.20)
    assert brick.pos() < 300.0  # the 360 target is gone
    final = brick.pos()
    brick.run_for(1.0)
    assert brick.pos() == final and brick.vel() == 0.0


def test_rule2_nonzero_run_takes_over_and_drops_target(lib):
    b = Brick(lib, owned_run=False)  # legacy duty path takes the wheel
    try:
        _start_360_at_450(b)
        b.run(1, 20)
        assert b.lib.nbHasTarget(b.h, 1) == 0
        b.run_for(3.0)
        # doc section 3 rule 2: runs at 20 % until stopped, target gone.
        assert b.vel() == pytest.approx(0.20 * 1150.0, rel=0.02)
        assert b.pos() > 360.0  # ran straight through the old target
    finally:
        b.close()


def test_rule2_nonzero_run_takes_over_with_speed_loop_model(brick):
    _start_360_at_450(brick)
    brick.run(1, 20)
    assert brick.lib.nbHasTarget(brick.h, 1) == 0
    brick.run_for(2.0)
    assert brick.vel() == pytest.approx(20 * 11.5, rel=0.01)  # doc section 1


def test_rule3_second_move_supersedes_from_current_position(brick):
    at = _start_360_at_450(brick)
    brick.move_deg(1, 90)
    brick.run_for(2.0)
    # doc section 3 rule 3: ended 95 deg past the position at the command
    # (the model lands on 90 exactly), and the old 360 target is gone.
    assert brick.pos() - at == pytest.approx(95.0, abs=6.0)
    assert brick.pos() - at == pytest.approx(90.0, abs=0.2)
    assert brick.lib.nbHasTarget(brick.h, 1) == 0


def test_rule4_hard_stop_within_5_degrees_and_drops_target(brick):
    at = _start_360_at_450(brick)
    brick.stop(1)
    assert brick.lib.nbHasTarget(brick.h, 1) == 0
    brick.run_for(1.0)
    travel = brick.pos() - at
    assert 0.0 < travel <= 5.0  # doc section 3 rule 4: 5 degrees more
    assert brick.pos() < 300.0
    assert brick.vel() == 0.0


def test_rule4_hard_stop_from_150_dps_is_near_zero(lib):
    # Doc section 3 rule 4 quotes 0.0 deg from 150 deg/s, citing the
    # `supersede` rows of mb_probe_fine1.csv. Those rows' after_stop_deg
    # column is the integer 0 (never filled -- a measured value reads
    # like '1.7'), so it is not a measurement; the 5a fit predicts
    # 150 x 0.0103 = 1.5 deg, which this test bounds instead.
    b = Brick(lib)
    try:
        b.store(1, 150)
        b.timed(1, 6)
        b.run_for(1.0)
        at = b.pos()
        b.stop(1)
        b.run_for(0.5)
        assert 0.0 <= b.pos() - at <= 2.0
    finally:
        b.close()


def test_rule5_speed_store_is_per_port_and_persists(brick):
    brick.store(1, 300)
    brick.store(2, 450)
    assert brick.lib.nbSpeedStore(brick.h, 1) == 300
    assert brick.lib.nbSpeedStore(brick.h, 2) == 450
    brick.move_deg(1, 30)
    brick.move_deg(2, 30)
    brick.run_for(1.0)
    brick.move_deg(1, 300)  # the store persists across moves
    brick.run_for(0.5)
    assert brick.vel(1) == pytest.approx(300.0, rel=0.01)
    # Port byte 0 means all ports; the most recent write governs.
    assert brick.store(0, 600) == 0
    assert brick.lib.nbSpeedStore(brick.h, 1) == 600
    assert brick.lib.nbSpeedStore(brick.h, 2) == 600
    brick.store(2, 100)
    assert brick.lib.nbSpeedStore(brick.h, 1) == 600
    assert brick.lib.nbSpeedStore(brick.h, 2) == 100


def test_rule6_negative_degrees_mirror(brick):
    brick.store(1, 450)
    brick.move_deg(1, -90)
    brick.run_for(2.0)
    assert brick.pos() == pytest.approx(-90.0, abs=0.2)
    assert brick.read_deg() == pytest.approx(-90.0, abs=0.2)


# ---------------------------------------------------------------------------
# Opcode shapes (doc section 2).
# ---------------------------------------------------------------------------

def test_move_modes_0_1_are_turns_and_2_is_degrees(brick):
    brick.store(1, 900)
    brick.frame(1, 0x70, 1, mode=1, direction=1)  # one turn
    brick.run_for(2.0)
    assert brick.pos() == pytest.approx(360.0, abs=0.2)
    brick.frame(1, 0x70, 1, mode=0, direction=2)  # mode 0: also turns
    brick.run_for(2.0)
    assert brick.pos() == pytest.approx(0.0, abs=0.2)
    brick.move_deg(1, 90)  # integer degrees -> 900 counts (x10)
    brick.run_for(1.0)
    assert brick.lib.nbPosition(brick.h, 1) == pytest.approx(900.0, abs=2.0)


def test_timed_run_lasts_10n_minus_3_hundred_ms(brick):
    brick.store(1, 300)
    brick.timed(1, 1)  # n=1 -> 7 x 100 ms = 0.7 s (doc section 2)
    brick.run_for(0.65)
    assert brick.lib.nbMoveLive(brick.h, 1) == 1
    assert brick.vel() == pytest.approx(300.0, rel=0.01)
    brick.run_for(0.2)   # past 0.7 s plus the ramp-down
    assert brick.vel() == 0.0
    # 300 deg/s for 0.7 s; the ramp-up shortfall and ramp-down overrun
    # cancel (v^2/2a each), so the travel is 210 deg.
    assert brick.pos() == pytest.approx(210.0, abs=3.0)


def test_speed_store_alone_leaves_a_run_and_a_pending_move_unchanged(brick):
    # Running wheel (timed run).
    brick.store(1, 300)
    brick.timed(1, 6)
    brick.run_for(1.0)
    v_before = brick.vel()
    brick.store(1, 900)
    brick.run_for(DT)
    assert brick.vel() == pytest.approx(v_before, abs=1.0)
    brick.run_for(0.5)
    assert brick.vel() == pytest.approx(300.0, rel=0.01)
    assert brick.lib.nbSpeedStore(brick.h, 1) == 900

    # Pending move on the other port.
    brick.store(2, 300)
    brick.move_deg(2, 200)
    brick.run_for(0.3)
    assert brick.lib.nbHasTarget(brick.h, 2) == 1
    v2 = brick.vel(2)
    brick.store(2, 900)
    brick.run_for(DT)
    assert brick.vel(2) == pytest.approx(v2, abs=1.0)
    brick.run_for(2.0)
    assert brick.pos(2) == pytest.approx(200.0, abs=0.2)  # same target


def test_legacy_0x60_without_a_move_is_unchanged(lib):
    """0x60 with no move live is the old duty path, bit for bit: the
    wheel under it equals a bare duty-driven wheel (sim_tour.py's
    numbers depend on that)."""
    b = Brick(lib, owned_run=False, duty_vel_max=11500.0, tau=0.05)
    try:
        b.run(1, 60)
        b.run_for(0.5)
        b.run(1, 0)
        b.run_for(0.5)
        # Closed form of the same first-order lag, stepped identically.
        v = pos = 0.0
        duty = 0.6
        for i in range(1000):
            if i == 500:
                duty = 0.0
            a = DT / (0.05 + DT)
            v += a * (duty * 11500.0 - v)
            pos += v * DT
        assert b.lib.nbPosition(b.h, 1) == pytest.approx(pos, rel=1e-4)
    finally:
        b.close()


# ---------------------------------------------------------------------------
# Frame log and the 0x1D violation counter.
# ---------------------------------------------------------------------------

def test_frame_log_is_byte_exact_and_counts_0x60_per_port(brick):
    brick.store(1, 450)
    brick.move_deg(1, 360)
    brick.run(1, 0)
    brick.run(2, 30)
    brick.stop(1)
    assert brick.frames() == [
        bytes([0xFF, 0xF9, 1, 0, 0x77, 0x01, 0x00, 0xC2]),   # 450 = 0x01C2
        bytes([0xFF, 0xF9, 1, 1, 0x70, 0x01, 0x02, 0x68]),   # 360 = 0x0168
        bytes([0xFF, 0xF9, 1, 1, 0x60, 0x00, 0xF5, 0x00]),
        bytes([0xFF, 0xF9, 2, 1, 0x60, 0x1E, 0xF5, 0x00]),
        bytes([0xFF, 0xF9, 1, 0, 0x5F, 0x00, 0xF5, 0x00]),
    ]
    assert brick.lib.nbFrames60(brick.h, 1) == 1
    assert brick.lib.nbFrames60(brick.h, 2) == 1
    # Only the 0x60 on port 1 arrived while a move was live there.
    assert brick.lib.nbFrames60WhileLive(brick.h, 1) == 1
    assert brick.lib.nbFrames60WhileLive(brick.h, 2) == 0


def test_0x60_frames_while_a_move_is_live_are_counted(brick):
    brick.store(1, 450)
    brick.move_deg(1, 360)
    brick.run_for(0.3)
    for _ in range(5):
        brick.run_for(0.01)
        brick.run(1, 0)
    # First 0x60 0 ends the move's target, but the ramp keeps the port
    # live, so all five land while live.
    assert brick.lib.nbFrames60(brick.h, 1) == 5
    assert brick.lib.nbFrames60WhileLive(brick.h, 1) == 5
    brick.run_for(3.0)
    brick.run(1, 0)
    assert brick.lib.nbFrames60(brick.h, 1) == 6
    assert brick.lib.nbFrames60WhileLive(brick.h, 1) == 5


def test_0x1d_is_rejected_logged_as_a_violation_and_never_forwarded(brick):
    assert brick.lib.nbViolations1D(brick.h) == 0
    brick.store(1, 450)
    brick.move_deg(1, 360)
    brick.run_for(0.2)
    v = brick.vel()
    assert brick.frame(1, 0x1D, 1) != 0   # bus rejects it
    assert brick.lib.nbViolations1D(brick.h) == 1
    assert all(f[4] != 0x1D for f in brick.frames())  # not in the log
    brick.run_for(DT)
    assert brick.vel() == pytest.approx(v, abs=1.0)  # no effect on motion


def test_ordinary_traffic_never_counts_a_0x1d_violation(brick):
    brick.store(0, 450)
    brick.move_deg(1, 90)
    brick.timed(2, 2)
    brick.run(1, 0)
    brick.stop(2)
    brick.run(2, 10)
    assert brick.lib.nbViolations1D(brick.h) == 0
