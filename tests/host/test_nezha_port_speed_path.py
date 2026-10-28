"""tests/host/test_nezha_port_speed_path.py -- sprint 042 ticket 005.

`NezhaMotorPort::setSpeedPath()` against the simulated brick through
sim_nezha_port_shim.cpp. Frame bytes and behaviour rules follow
docs/knowledge/2026-10-27-nezha-brick-opcodes.md ("the opcode doc"):
0x77 is deg/s; 0x70 mode 3 is a timed run of (10n - 3) x 100 ms at the
stored speed; a 0x77 alone does not retarget. The 11.5 deg/s per percent
slope is from the ESP32 rig (motor-characterization.md, 2026-10-27) and
is UNVERIFIED through the brick. The simulator is a model, so nothing
here is a hardware result.
"""

import ctypes

import pytest

from test_nezha_port_position_move import (  # noqa: F401  (fixture reuse)
    Rig, lib, SPEED, STOP5F, RUN0)

TIMED = lambda rev=False, port=1: bytes(
    [0xFF, 0xF9, port, 2 if rev else 1, 0x70, 0x00, 0x03, 0x01])
RUN = lambda pct, rev=False, port=1: bytes(
    [0xFF, 0xF9, port, 2 if rev else 1, 0x60, pct, 0xF5, 0x00])

# speed_path 0 reference-ramp pin, captured from the code BEFORE this
# ticket's change (tau 0.05, duty 0 x3 ticks, 0.6 x60, 0 x40): slew-
# stepped 0x60 writes 0/25/50/60, then the stop re-written while the
# wheel still reads motion (stopNotTaken).
PIN_PATH0 = ([RUN(0), RUN(25), RUN(50), RUN(60)] + [RUN(0)] * 12)


@pytest.fixture(autouse=True)
def _argtypes(lib):
    lib.npSetSpeedPath.argtypes = [ctypes.c_void_p, ctypes.c_int]


def ramp(r, ticks=((0.0, 3), (0.6, 60), (0.0, 40))):
    for duty, n in ticks:
        r.tick(n, duty)


def test_speed_path_zero_frame_log_is_the_pinned_one(lib):
    r = Rig(lib, tau=0.05)
    try:
        ramp(r)
        assert r.cmds() == PIN_PATH0
        assert lib.npViolations1D(r.h) == 0
    finally:
        r.close()


def test_default_speed_path_is_zero(lib):
    r = Rig(lib, tau=0.05)
    try:
        ramp(r)  # no setSpeedPath call at all
        assert r.cmds() == PIN_PATH0
    finally:
        r.close()


def test_ramp_up_and_down_gives_pairs_on_change_and_one_5f(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        ramp(r, ((0.0, 3), (0.6, 12), (0.0, 40)))
        cmds = r.cmds()
        # slew 25 pct/tick: 25, 50, 60 % -> 288, 575, 690 deg/s
        # (11.5 deg/s per percent, UNVERIFIED through the brick).
        pairs = [(SPEED(288), TIMED()), (SPEED(575), TIMED()),
                 (SPEED(690), TIMED())]
        expect = [f for p in pairs for f in p]
        # The zero before the ramp starts is a 0x60 0 (no run to stop).
        assert cmds[0] == RUN0
        assert cmds[1:1 + len(expect)] == expect
        assert cmds[1 + len(expect):] == [STOP5F]
        assert lib.npFrames60(r.h) == 1
        assert lib.npViolations1D(r.h) == 0
    finally:
        r.close()


def test_steady_speed_writes_nothing_new_until_refresh(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        r.tick(4, 0.6)
        n = len(r.cmds())
        r.tick(5, 0.6)  # 120 ms, under the refresh interval
        assert len(r.cmds()) == n
        r.tick(60, 0.6)  # 1.4 s: only 0x70 refreshes, never a 0x77
        extra = r.cmds()[n:]
        assert extra and all(f == TIMED() for f in extra)
        # Every gap stays under the 0.7 s timed run.
        assert len(extra) >= 2
    finally:
        r.close()


def test_wheel_follows_the_modelled_speed_and_stops(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        r.tick(30, 0.6)
        assert lib.npWheelVel(r.h) > 0.0
        r.tick(60, 0.0)
        assert abs(lib.npWheelVel(r.h)) < 1.0
    finally:
        r.close()


def test_reverse_uses_direction_byte_and_dwell(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        r.tick(6, 0.4)
        r.tick(60, -0.4)
        cmds = r.cmds()
        assert STOP5F in cmds  # stop from speed before the flip
        assert TIMED(rev=True) in cmds
        assert cmds.index(STOP5F) < cmds.index(TIMED(rev=True))
        assert lib.npViolations1D(r.h) == 0
    finally:
        r.close()


def test_fwd_sign_minus_one_flips_direction_byte(lib):
    r = Rig(lib, tau=0.05, fwd=-1)
    try:
        lib.npSetSpeedPath(r.h, 1)
        r.tick(4, 0.4)
        assert TIMED(rev=True) in r.cmds()
        assert TIMED() not in r.cmds()
    finally:
        r.close()


def test_stop_from_below_the_floor_stays_0x60_zero(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        r.tick(4, 0.05)  # 5 %: deadband-boosted, below the 8 % floor
        r.tick(6, 0.0)
        cmds = r.cmds()
        assert RUN0 in cmds[1:] and STOP5F not in cmds
    finally:
        r.close()


def test_no_dither_on_the_speed_path(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        # 0.304 -> exactly 30 %, every tick; the carry would alternate.
        r.tick(40, 0.304)
        speeds = [f for f in r.cmds() if f[4] == 0x77]
        assert speeds == [SPEED(345)]
    finally:
        r.close()


def test_position_move_latch_still_wins(lib):
    r = Rig(lib, tau=0.05)
    try:
        lib.npSetSpeedPath(r.h, 1)
        assert lib.npBeginMove(r.h, 3600.0, 300.0) == 1
        n = len(r.cmds())
        r.tick(20, 0.6)
        assert len(r.cmds()) == n  # no speed frames on a live move
    finally:
        r.close()
