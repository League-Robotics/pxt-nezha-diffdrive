"""tests/host/test_config_position_mode_speed_path.py -- sprint 042
ticket 007 (change-plan C6): the `position_mode` (52) and `speed_path`
(53) config ordinals.

Two halves, because shims.cpp itself cannot be compiled on the host
(it includes pxt.h) and board_nezha.cpp is not host-linkable (its ports
take the target-only default I2CBus):

1. Wire round trip through the REAL WireAdapter + descriptor table over
   the wire_motion_verb_shim.cpp test double: both names resolve, default
   to 0, SET/GET round-trips, and the bare GET dump lists them.
2. Source pins on the pieces the double mirrors: shims.cpp's accessors
   (range check, Rig storage, forward through the board hook) and
   board_nezha.cpp / board_cutebot.cpp (both ports set; Cutebot refuses).
"""

import pathlib
import re

import pytest

from test_config_descriptor_table import (  # noqa: F401  (fixtures)
    _ack, descriptor_table_lib, wa)

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
_SHIMS = (_SRC / "shims.cpp").read_text()
_NEZHA = (_SRC / "platform" / "board_nezha.cpp").read_text()
_CUTEBOT = (_SRC / "platform" / "board_cutebot.cpp").read_text()
_FIELDS = (_SRC / "comms" / "config_fields.h").read_text()


def _get(wa, name, id_=2):
    wa.feed(f"GET {name} #{id_}\n".encode())
    reply = wa.take_sink()
    prefix = _ack(id_) + f"get {name} ".encode()
    assert reply.startswith(prefix), reply
    return float(reply[len(prefix):])


def test_ordinals_are_52_and_53():
    assert re.search(r'\{"position_mode", 52, "1"\}', _FIELDS)
    assert re.search(r'\{"speed_path", 53, "1"\}', _FIELDS)


@pytest.mark.parametrize("name", ["position_mode", "speed_path"])
def test_default_is_zero(wa, name):
    assert _get(wa, name, 1) == 0.0


@pytest.mark.parametrize("name,value", [
    ("position_mode", 1), ("position_mode", 2), ("position_mode", 0),
    ("speed_path", 1), ("speed_path", 0),
])
def test_round_trip(wa, name, value):
    wa.feed(f"SET {name} {value} #1\n".encode())
    assert wa.take_sink() == _ack(1)
    assert _get(wa, name) == value


def test_shims_position_mode_is_range_checked_and_stored_on_rig():
    assert "int positionMode = 0;" in _SHIMS
    body = re.search(r"void cfgSetPositionMode\(Rig& r, float v\) \{(.*?)\n\}",
                     _SHIMS, re.DOTALL).group(1)
    assert "v < 0.0f || v > 2.0f" in body
    assert "r.positionMode =" in body
    assert "{52, &cfgGetPositionMode, &cfgSetPositionMode}" in _SHIMS


def test_shims_speed_path_forwards_through_the_board_hook():
    body = re.search(r"void cfgSetSpeedPath\(Rig&, float v\) \{(.*?)\n\}",
                     _SHIMS, re.DOTALL).group(1)
    assert "v != 0.0f && v != 1.0f" in body
    assert "boardSetSpeedPath(" in body
    assert "boardSpeedPath()" in _SHIMS
    assert "{53, &cfgGetSpeedPath, &cfgSetSpeedPath}" in _SHIMS


def test_nezha_board_sets_both_ports():
    body = re.search(r"bool boardSetSpeedPath\(int path\) \{(.*?)\n\}",
                     _NEZHA, re.DOTALL).group(1)
    assert "b.left.setSpeedPath(path)" in body
    assert "b.right.setSpeedPath(path)" in body
    assert "int boardSpeedPath() { return board().left.speedPath(); }" in _NEZHA


def test_cutebot_refuses_and_reads_zero():
    assert "int boardSpeedPath() { return 0; }" in _CUTEBOT
    assert "bool boardSetSpeedPath(int) { return false; }" in _CUTEBOT
