"""tests/host/test_board_cutebot_source_pin.py -- source-level pins for
sprint 040 ticket 002's Cutebot board composition
(docs/design/cutebot-pro-support.md S2.1/S3.A/S4): `platform/
board_cutebot.cpp` and the `comms/protocol.cpp` kRole branch it shares
with `platform/board_nezha.cpp`'s own seam.

WHY SOURCE-PIN, NOT A COMPILED TEST. `board_cutebot.cpp` and
`protocol.cpp` both reach `pxt.h` (directly, or for `board_cutebot.cpp`
via its `CutebotBoard` singleton's target-only default `I2CBus`
argument) and so cannot be compiled on the host at all -- see
`tests/DESIGN.md`'s "Translation units nothing on the host compiles"
table. Same technique `test_board_seam_source_pin.py` already uses for
`board_nezha.cpp`.

WHAT THIS PROVES, AND WHAT `test_cutebot_port.py` PROVES INSTEAD. This
file pins that `board_cutebot.cpp`'s thin hooks exist, are guarded by
the right `DIFFDRIVE_BOARD` branch, and delegate to `cutebot_port.h`'s
own functions rather than reimplementing anything.
`test_cutebot_port.py` proves the ACTUAL computation those hooks
delegate to (`CutebotMotorPort`/`CutebotDevice`/
`cutebotBoardDiagValue()`) by compiling and running it directly, over a
simulated bus. Together they cover the same ground
`test_board_seam_source_pin.py`/`test_board_nezha_diag.py` cover for
the Nezha half.

Run with::

    uv run pytest tests/host/test_board_cutebot_source_pin.py
"""

import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

_BOARD_CUTEBOT_CPP = (_SRC_DIR / "platform" / "board_cutebot.cpp").read_text()
_CUTEBOT_PORT_H = (_SRC_DIR / "platform" / "cutebot_port.h").read_text()
_NEZHA_PORT_CPP = (_SRC_DIR / "platform" / "nezha_port.cpp").read_text()
_CUTEBOT_PORT_CPP = (_SRC_DIR / "platform" / "cutebot_port.cpp").read_text()
_PROTOCOL_CPP = (_SRC_DIR / "comms" / "protocol.cpp").read_text()


# ---------------------------------------------------------------------
# board_cutebot.cpp: guarded by the board literal, owns the tracked
# construction and the fault-context emergency-stop frame.
# ---------------------------------------------------------------------

def test_board_cutebot_cpp_guarded_by_the_board_literal():
    assert "#if DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_CUTEBOT_PRO" in _BOARD_CUTEBOT_CPP
    assert _BOARD_CUTEBOT_CPP.rstrip().endswith(
        "#endif  // DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_CUTEBOT_PRO"
    )


def test_board_cutebot_cpp_owns_the_tracked_device_and_port_construction():
    assert "CutebotDevice device;" in _BOARD_CUTEBOT_CPP
    assert "CutebotMotorPort left{device, 0, +1};" in _BOARD_CUTEBOT_CPP
    assert "CutebotMotorPort right{device, 1, +1};" in _BOARD_CUTEBOT_CPP


def test_board_cutebot_cpp_declares_all_four_composition_hooks():
    for sig in ("BoardMotors boardMotors()", "MotorWiring boardWiring(int side)",
               "void boardConfigureWiring(int side, uint8_t port, int8_t sign)",
               "int boardDiagValue(int ordinal)"):
        assert sig in _BOARD_CUTEBOT_CPP, (
            f"board_cutebot.cpp: missing hook definition {sig!r}"
        )


def test_board_configure_wiring_delegates_to_the_port_and_discards_the_result():
    match = re.search(
        r"void boardConfigureWiring\(int side, uint8_t port, int8_t sign\) \{"
        r"(.*?)\n\}",
        _BOARD_CUTEBOT_CPP, re.DOTALL,
    )
    assert match, "board_cutebot.cpp: boardConfigureWiring() not found"
    body = match.group(1)
    assert "p.configureWiring(port, sign);" in body


def test_board_diag_value_delegates_to_cutebot_board_diag_value():
    match = re.search(
        r"int boardDiagValue\(int ordinal\) \{(.*?)\n\}",
        _BOARD_CUTEBOT_CPP, re.DOTALL,
    )
    assert match, "board_cutebot.cpp: boardDiagValue() not found"
    assert "cutebotBoardDiagValue(b.left, b.right, ordinal)" in match.group(1)


def test_board_cutebot_cpp_defines_the_emergency_stop_frame():
    assert 'extern "C" void diffdrive_emergency_motor_stop() {' in _BOARD_CUTEBOT_CPP
    assert "CutebotDevice::kCmdWheel" in _BOARD_CUTEBOT_CPP
    assert "CutebotDevice::kWheelBoth" in _BOARD_CUTEBOT_CPP
    assert "CutebotDevice::kAddress" in _BOARD_CUTEBOT_CPP


def test_cutebot_port_cpp_never_defines_the_emergency_stop_frame():
    """cutebot_port.cpp is fully host-portable (cutebot_port.h's own
    header comment) -- the fault-context frame belongs to
    board_cutebot.cpp alone. Two definitions of the same extern "C"
    symbol would be a link error on a real build."""
    assert 'extern "C" void diffdrive_emergency_motor_stop() {' not in _CUTEBOT_PORT_CPP
    assert '#include "pxt.h"' not in _CUTEBOT_PORT_CPP
    assert '#include "pxt.h"' not in _CUTEBOT_PORT_H


def test_nezha_port_cpp_fault_handlers_stay_board_generic():
    """The ARM fault handlers (HardFault_Handler et al.) live in
    nezha_port.cpp regardless of which board is selected -- PXT compiles
    every file in pxt.json's `files` list always (board.h's own header
    comment), so a Cutebot build still links nezha_port.cpp's handlers,
    which call whichever board's diffdrive_emergency_motor_stop() was
    actually compiled in."""
    assert 'extern "C" void diffdrive_emergency_motor_stop();' in _NEZHA_PORT_CPP
    assert "#if DIFFDRIVE_BOARD" not in _NEZHA_PORT_CPP


# ---------------------------------------------------------------------
# cutebot_port.h: the WiringResult refusal-code taxonomy exists and is
# what configureWiring() returns.
# ---------------------------------------------------------------------

def test_cutebot_port_h_declares_wiring_result():
    assert "enum class WiringResult : uint8_t {" in _CUTEBOT_PORT_H
    assert "kOk," in _CUTEBOT_PORT_H
    assert "kUnimplemented," in _CUTEBOT_PORT_H
    assert "WiringResult configureWiring(uint8_t port, int8_t sign);" in _CUTEBOT_PORT_H


# ---------------------------------------------------------------------
# protocol.cpp: kRole gated on DIFFDRIVE_BOARD_CUTEBOT_PRO too, Nezha
# branch still unchanged (test_board_seam_source_pin.py already pins
# the Nezha half; this file pins that the Cutebot branch was ADDED
# rather than replacing it).
# ---------------------------------------------------------------------

def test_protocol_cpp_gates_krole_on_cutebot_pro_too():
    assert "#elif DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_CUTEBOT_PRO" in _PROTOCOL_CPP
    assert 'constexpr const char* kRole = "CUTEBOTPRO";' in _PROTOCOL_CPP
    # The Nezha branch must still exist, unmodified, above the new one.
    assert 'constexpr const char* kRole = "NEZHA2";' in _PROTOCOL_CPP
    nezha_index = _PROTOCOL_CPP.index('kRole = "NEZHA2"')
    cutebot_index = _PROTOCOL_CPP.index('kRole = "CUTEBOTPRO"')
    assert nezha_index < cutebot_index
