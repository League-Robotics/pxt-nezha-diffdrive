"""tests/host/test_shims_cpp_i2cf_causes.py -- the real src/shims.cpp and
NezhaMotorPort over a SimNezhaBus: i2cf (cycles where either wheel's
sample did not advance) split into busf, stl and glt.

Run with::

    uv run pytest tests/host/test_shims_cpp_i2cf_causes.py
"""
from shims_cpp_rig import DIAG_BUS_FAIL, DIAG_GLITCH, DIAG_I2C_FAULT, DIAG_STALE


def _causes(rig):
    return rig.diag(DIAG_BUS_FAIL), rig.diag(DIAG_STALE), rig.diag(DIAG_GLITCH)


def _drive(rig, ticks):
    rig.startMove(500, 0, 100, 0)
    for _ in range(ticks):
        rig.tick()


def test_a_driven_wheel_that_does_not_turn_counts_as_stale(make_rig):
    rig = make_rig()
    _drive(rig, 20)
    busf, stl, glt = _causes(rig)
    assert busf == 0 and glt == 0
    assert stl > 0
    assert rig.diag(DIAG_I2C_FAULT) <= stl <= 2 * rig.diag(DIAG_I2C_FAULT)


def test_a_nakd_encoder_read_counts_as_a_bus_failure(make_rig):
    rig = make_rig()
    _drive(rig, 3)
    before = rig.diag(DIAG_I2C_FAULT)
    rig.nezhaFailReads(1)
    rig.tick()
    assert _causes(rig)[0] == 1
    assert rig.diag(DIAG_I2C_FAULT) == before + 1
