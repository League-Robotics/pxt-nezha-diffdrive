"""tests/host/test_shims_cpp_accelerometer.py -- the micro:bit accelerometer
read in the real src/shims.cpp behind TLM FULL's ax/ay/az/apk columns.

Run with::

    uv run pytest tests/host/test_shims_cpp_accelerometer.py
"""
import pathlib
import re

from shims_cpp_rig import DIAG_ACCEL_PEAK, DIAG_ACCEL_X, DIAG_ACCEL_Y, DIAG_ACCEL_Z
from test_bus_guard_source_pin import _strip_comments

_PROTOCOL = _strip_comments(
    (pathlib.Path(__file__).resolve().parents[2] / "src" / "comms" / "protocol.cpp").read_text())


def _sense(rig, x, y, z):
    rig.setAccel(x, y, z)
    rig.advance_us(20000)
    rig.accelSense()


def _axes(rig):
    return rig.diag(DIAG_ACCEL_X), rig.diag(DIAG_ACCEL_Y), rig.diag(DIAG_ACCEL_Z)


def test_axes_pass_through_in_milli_g(make_rig):
    rig = make_rig()
    _sense(rig, 12, -34, -987)
    assert _axes(rig) == (12, -34, -987)


def test_first_read_sets_no_peak(make_rig):
    rig = make_rig()
    _sense(rig, 0, 0, -1000)
    assert rig.diag(DIAG_ACCEL_PEAK) == 0


def test_peak_is_the_largest_per_axis_jump_and_clears_on_read(make_rig):
    rig = make_rig()
    _sense(rig, 0, 0, -1000)
    _sense(rig, 40, 0, -1000)
    _sense(rig, 40, -300, -1000)
    _sense(rig, 40, -300, -900)
    assert rig.diag(DIAG_ACCEL_PEAK) == 300
    assert rig.diag(DIAG_ACCEL_PEAK) == 0
    _sense(rig, 40, -300, -650)
    assert rig.diag(DIAG_ACCEL_PEAK) == 250


def test_reads_are_rate_limited_to_50_hz(make_rig):
    rig = make_rig()
    _sense(rig, 0, 0, -1000)
    rig.setAccel(500, 0, -1000)
    rig.advance_us(10000)
    rig.accelSense()
    assert _axes(rig) == (0, 0, -1000)
    rig.advance_us(10000)
    rig.accelSense()
    assert _axes(rig) == (500, 0, -1000)


def test_protocol_reads_the_accelerometer_every_pass_moving_or_not():
    loop = re.search(r"while \(true\) \{\s*serviceOnce\(\);\s*accelSense\(\);", _PROTOCOL)
    assert loop
