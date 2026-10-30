"""tests/host/test_status_active_through_leg.py -- sprint 044 ticket 015.

STATUS `active` stays 1 from a GO_TO_W's start until its done fires, across
the pivot closure's dwell and correction pivots, the pending straight and
the residual trims. The engine half is played against a true two-wheel robot
through pose_estimator_shim.cpp; the wire half pins that the adapter reads
the engine's leg-live state when the wheels are at rest.

Run with::

    uv run pytest tests/host/test_status_active_through_leg.py
"""


from test_goto_block_regression import _FULL_DUTY_VELOCITY, _PERIOD_MS
from test_pivot_closure import ARRIVE, TIMEOUT_MS, _rig
from test_pivot_closure import lib as pivot_lib  # noqa: F401 -- used as a fixture
from test_pose_estimator import OPTICAL
from test_pose_estimator import lib as estimator_lib  # noqa: F401 -- used as a fixture
from test_straight_steering import DEFAULT_FLOOR, _polar
from test_straight_steering import lib  # noqa: F401 -- used as a fixture
from test_wire_motion_verbs import motion_verb_lib, wa  # noqa: F401 -- fixtures

DIAG_LEG_LIVE = 47


def _setup(lib, closure, trim):
    import ctypes

    lib.peLegLive.argtypes = [ctypes.c_void_p]
    lib.peLegLive.restype = ctypes.c_int
    lib.peLegLiveTicks.argtypes = [ctypes.c_void_p]
    lib.peLegLiveTicks.restype = ctypes.c_uint32
    lib.peLegDeadTicks.argtypes = [ctypes.c_void_p]
    lib.peLegDeadTicks.restype = ctypes.c_uint32
    rig, p = _rig(lib, OPTICAL, 1.05, floor=DEFAULT_FLOOR)
    lib.peOpticalScale(rig.h, 0.98)
    lib.peSetPivotClosure(rig.h, int(closure), 250, 0.25, 45.0, 1.0, 3, 2500)
    lib.peSetSteering(rig.h, int(trim), 150.0, 4.0, 20.0, 0.15)
    lib.peSetResidualTrim(rig.h, int(trim), 30.0, 2.0, 250, 2, 3000)
    return rig, p


def test_leg_is_live_every_tick_of_a_goto_with_corrections_and_trim(lib):
    rig, p = _setup(lib, True, True)
    try:
        x, y = _polar(500.0, 135)
        lib.peGoToW(rig.h, x, y, p["speed"], ARRIVE, TIMEOUT_MS)
        assert lib.peLegLive(rig.h) == 1
        ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 8000)
        assert ticks < 8000
        assert lib.pePivotCorrections(rig.h) >= 1
        assert lib.peTrimCount(rig.h) >= 1
        assert lib.peLegDeadTicks(rig.h) == 0
        assert lib.peLegLiveTicks(rig.h) == ticks
        assert lib.peLegLive(rig.h) == 0
        assert not lib.peMoveActive(rig.h)
    finally:
        rig.close()


def test_a_plain_move_is_never_leg_live(lib):
    rig, p = _setup(lib, False, False)
    try:
        lib.peGoToW(rig.h, *_polar(300.0, 0), p["speed"], ARRIVE, TIMEOUT_MS)
        ticks = lib.peRunMove(rig.h, _FULL_DUTY_VELOCITY, _PERIOD_MS, 8000)
        assert ticks < 8000
        assert lib.peLegLiveTicks(rig.h) == 0
    finally:
        rig.close()


def _status(wa):
    wa.feed(b"STATUS\n")
    line = wa.take_sink()
    return dict(kv.split(b"=") for kv in line.strip().split(b" ")[1:])[b"active"]


def test_status_active_reads_the_leg_with_the_wheels_at_rest(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    wa.begin()
    wa.step()
    wa.set_diag_override(14, 0)
    wa.set_diag_override(15, 0)
    assert _status(wa) == b"0"
    wa.set_diag_override(DIAG_LEG_LIVE, 1)
    assert _status(wa) == b"1"
    wa.set_diag_override(3, 1)
    assert _status(wa) == b"0"
