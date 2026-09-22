"""tests/host/test_board_seam_source_pin.py -- source-level pins for
sprint 040 ticket 001's board-composition seam
(docs/design/cutebot-pro-support.md S2.1/S4): `platform/board.h`,
`platform/board_nezha.cpp`, and the call sites in `shims.cpp`/
`comms/protocol.cpp`/`platform/nezha_port.cpp` that moved behind it.

WHY SOURCE-PIN, NOT A COMPILED TEST. `shims.cpp`, `board_nezha.cpp` and
`protocol.cpp` all reach `pxt.h` (directly or, for `board_nezha.cpp`,
via its `NezhaBoard` singleton's target-only default `I2CBus`
argument) and so cannot be compiled on the host at all -- see
`tests/DESIGN.md`'s "Translation units nothing on the host compiles"
table. This is the same technique `test_wire_constants_drift.py` and
the `test_set*precedence_source_pin.py` family already use for the
same reason.

WHAT THIS PROVES, AND WHAT `test_board_nezha_diag.py` PROVES INSTEAD.
This file pins that the ordinal-to-hook WIRING is present and has not
regressed (each of the eleven ordinals still reaches `boardDiagValue`,
`configureMotor()` no longer names `NezhaMotorPort`, the emergency-stop
frame exists in exactly one place). `test_board_nezha_diag.py` proves
the ACTUAL FIELD MAPPING behind that wiring is unchanged, by compiling
and running `nezhaBoardDiagValue()` directly. Together they cover the
same ground the old, single, host-uncompilable `diagValue()` switch
case bodies did before this ticket -- neither file alone would.

Run with::

    uv run pytest tests/host/test_board_seam_source_pin.py
"""

import pathlib
import re

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"

_SHIMS_CPP = (_SRC_DIR / "shims.cpp").read_text()
_BOARD_H = (_SRC_DIR / "platform" / "board.h").read_text()
_BOARD_NEZHA_CPP = (_SRC_DIR / "platform" / "board_nezha.cpp").read_text()
_NEZHA_PORT_CPP = (_SRC_DIR / "platform" / "nezha_port.cpp").read_text()
_PROTOCOL_CPP = (_SRC_DIR / "comms" / "protocol.cpp").read_text()


# ---------------------------------------------------------------------
# board.h: the one literal, defaulting to Nezha.
# ---------------------------------------------------------------------

def test_board_h_defines_both_board_literals():
    assert re.search(r"#define DIFFDRIVE_BOARD_NEZHA\s+1\b", _BOARD_H)
    assert re.search(r"#define DIFFDRIVE_BOARD_CUTEBOT_PRO\s+2\b", _BOARD_H)


def test_board_h_defaults_to_nezha():
    """Absent a build-supplied -DDIFFDRIVE_BOARD, board.h must select
    Nezha -- the whole "existing fleet build unaffected" guarantee
    hinges on this default, per docs/design/cutebot-pro-support.md
    S4."""
    match = re.search(
        r"#ifndef DIFFDRIVE_BOARD\s*\n#define DIFFDRIVE_BOARD (\w+)",
        _BOARD_H,
    )
    assert match, "board.h: no '#ifndef DIFFDRIVE_BOARD / #define DIFFDRIVE_BOARD <x>' default found"
    assert match.group(1) == "DIFFDRIVE_BOARD_NEZHA", (
        f"board.h's default DIFFDRIVE_BOARD is {match.group(1)!r}, "
        f"expected DIFFDRIVE_BOARD_NEZHA"
    )


def test_board_h_declares_the_composition_hooks():
    for sig in ("BoardMotors boardMotors()", "MotorWiring boardWiring(int side)",
               "void boardConfigureWiring(int side, uint8_t port, int8_t sign)",
               "int boardDiagValue(int ordinal)"):
        assert sig in _BOARD_H, f"board.h: missing declaration {sig!r}"


def test_board_h_declares_the_hybrid_actuation_hooks():
    for sig in ("WheelCommandTap* boardWheelCommandTap()", "int boardOnboardMode()",
               "bool boardSetOnboardMode(int mode)", "float boardOnboardFloor()",
               "bool boardSetOnboardFloor(float floor)"):
        assert sig in _BOARD_H, f"board.h: missing declaration {sig!r}"


# ---------------------------------------------------------------------
# board_nezha.cpp: the hybrid-actuation hooks are a documented no-op --
# Nezha has no onboard loop for them to mean anything on.
# ---------------------------------------------------------------------

def test_board_nezha_cpp_wheel_command_tap_is_a_null_hook():
    assert "WheelCommandTap* boardWheelCommandTap() { return nullptr; }" in _BOARD_NEZHA_CPP


def test_board_nezha_cpp_onboard_mode_reports_zero_and_refuses_set():
    assert "int boardOnboardMode() { return 0; }" in _BOARD_NEZHA_CPP
    assert "bool boardSetOnboardMode(int) { return false; }" in _BOARD_NEZHA_CPP


def test_board_nezha_cpp_onboard_floor_reports_zero_and_refuses_set():
    assert "float boardOnboardFloor() { return 0.0f; }" in _BOARD_NEZHA_CPP
    assert "bool boardSetOnboardFloor(float) { return false; }" in _BOARD_NEZHA_CPP


# ---------------------------------------------------------------------
# shims.cpp: no concrete NezhaMotorPort left in Rig or configureMotor();
# every moved diag ordinal reaches boardDiagValue().
# ---------------------------------------------------------------------

def test_shims_cpp_includes_board_header():
    assert '#include "platform/board.h"' in _SHIMS_CPP


def test_shims_cpp_no_longer_declares_nezha_motor_port_members():
    """The whole point of the seam: Rig's own members and
    configureMotor()'s own locals must not be a concrete
    NezhaMotorPort -- a reference in EXPLANATORY prose (Rig's own
    wiring-history comment, which predates the seam and is left as
    measured history) is fine; a declaration naming the type is not."""
    for pattern in ("NezhaMotorPort left{1, -1};", "NezhaMotorPort right{2, +1};",
                   "NezhaMotorPort& target", "NezhaMotorPort& other"):
        assert pattern not in _SHIMS_CPP, (
            f"shims.cpp still contains {pattern!r} -- the board-"
            f"composition seam is supposed to make this file board-generic"
        )
    assert '#include "platform/nezha_port.h"' not in _SHIMS_CPP


def test_rig_composes_board_motors():
    assert "BoardMotors motors = boardMotors();" in _SHIMS_CPP
    assert "DiffDrive::Motor& left = motors.left;" in _SHIMS_CPP
    assert "DiffDrive::Motor& right = motors.right;" in _SHIMS_CPP


def test_ensure_installs_the_boards_wheel_command_tap():
    assert "rig->engine.setWheelCommandTap(boardWheelCommandTap());" in _SHIMS_CPP


def test_onboard_config_accessors_forward_to_the_board_hooks():
    for pattern in (
        "boardOnboardMode()",
        "boardSetOnboardMode(static_cast<int>(std::lround(v)))",
        "boardOnboardFloor()",
        "boardSetOnboardFloor(v)",
    ):
        assert pattern in _SHIMS_CPP, (
            f"shims.cpp: onboard config accessors no longer call {pattern!r}"
        )


def _diag_value_cases():
    match = re.search(r"int diagValue\(int what\) \{(.*?)\n\}", _SHIMS_CPP,
                      re.DOTALL)
    assert match, "shims.cpp: diagValue() function body not found"
    body = match.group(1)
    cases = {}
    matches = list(re.finditer(r"case (\d+):", body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        cases[int(m.group(1))] = body[start:end]
    return cases


_BOARD_HOOKED_ORDINALS = (21, 22, 23, 24, 27, 35, 36, 37, 38, 39, 40)


def test_every_board_diag_ordinal_calls_the_hook():
    cases = _diag_value_cases()
    missing = []
    wrong = []
    for ordinal in _BOARD_HOOKED_ORDINALS:
        if ordinal not in cases:
            missing.append(ordinal)
        elif "boardDiagValue(what)" not in cases[ordinal]:
            wrong.append((ordinal, cases[ordinal].strip()))
    assert not missing, (
        f"shims.cpp's diagValue() switch has no case for ordinal(s) "
        f"{missing} -- these used to read a NezhaMotorPort field "
        f"directly and must now delegate to boardDiagValue()"
    )
    assert not wrong, (
        f"shims.cpp's diagValue() switch case(s) no longer call "
        f"boardDiagValue(what) (ordinal, actual body): {wrong}"
    )


def test_configure_motor_uses_board_wiring_hooks():
    match = re.search(
        r"void configureMotor\(int side, int port, int fwdSign\) \{(.*?)\n\}",
        _SHIMS_CPP, re.DOTALL,
    )
    assert match, "shims.cpp: configureMotor() not found"
    body = match.group(1)
    assert "boardWiring(side)" in body
    assert "boardWiring(otherSide)" in body
    assert "boardConfigureWiring(otherSide," in body
    assert "boardConfigureWiring(side," in body
    # The sequencing this function's own acceptance criterion protects:
    # stop before any wiring write, guard acquired before either write,
    # released after both.
    assert body.index("r.softStop();") < body.index("busGuard.acquire")
    assert body.index("busGuard.acquire") < body.index("boardConfigureWiring(otherSide,")
    assert body.index("boardConfigureWiring(otherSide,") < body.index("boardConfigureWiring(side,")
    assert body.index("boardConfigureWiring(side,") < body.index("busGuard.release")


# ---------------------------------------------------------------------
# board_nezha.cpp: owns the exact construction that used to be inline
# in shims.cpp's Rig, and the fault-context emergency-stop frame moved
# from nezha_port.cpp.
# ---------------------------------------------------------------------

def test_board_nezha_cpp_guarded_by_the_board_literal():
    assert "#if DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA" in _BOARD_NEZHA_CPP
    assert _BOARD_NEZHA_CPP.rstrip().endswith(
        "#endif  // DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA"
    )


def test_board_nezha_cpp_owns_the_tracked_motor_construction():
    assert "NezhaMotorPort left{1, -1};" in _BOARD_NEZHA_CPP
    assert "NezhaMotorPort right{2, +1};" in _BOARD_NEZHA_CPP


def test_board_nezha_cpp_defines_the_emergency_stop_frame():
    assert 'extern "C" void diffdrive_emergency_motor_stop() {' in _BOARD_NEZHA_CPP
    assert "kRegMotorRun" in _BOARD_NEZHA_CPP
    assert "kDirCw" in _BOARD_NEZHA_CPP


def test_nezha_port_cpp_no_longer_defines_the_emergency_stop_frame():
    """nezha_port.cpp must keep a forward declaration (the fault
    handlers below still call it) but must not ALSO define it -- two
    definitions would be a link error on a real build, invisible to
    every host test since this file is hex-checkpoint-only for that
    half."""
    assert 'extern "C" void diffdrive_emergency_motor_stop();' in _NEZHA_PORT_CPP
    assert 'extern "C" void diffdrive_emergency_motor_stop() {' not in _NEZHA_PORT_CPP


# ---------------------------------------------------------------------
# protocol.cpp: kRole gated on DIFFDRIVE_BOARD, Nezha branch unchanged.
# ---------------------------------------------------------------------

def test_protocol_cpp_gates_krole_on_diffdrive_board():
    assert '#include "../platform/board.h"' in _PROTOCOL_CPP
    assert "#if DIFFDRIVE_BOARD == DIFFDRIVE_BOARD_NEZHA" in _PROTOCOL_CPP
    # The exact pinned literal test_setdevicerole_precedence_source_pin.py
    # also checks -- restated here because THIS test is the one that
    # documents why it now sits inside an #if.
    assert 'constexpr const char* kRole = "NEZHA2";' in _PROTOCOL_CPP
