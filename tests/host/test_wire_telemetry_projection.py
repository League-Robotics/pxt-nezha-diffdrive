"""tests/host/test_wire_telemetry_projection.py -- sprint 004 ticket 004:
WireAdapter's telemetry projection (`buildSnapshot()`/`telemetryEnabled()`),
the `computeFlags()` function now shared between STATUS and telemetry,
`STATUS`'s new `i2cf=` key, and R-22/WIRE-06's `STATUS otos=`
truthfulness fix.

This is the ticket where the REAL `WireAdapter` + real kernel/FakeMotor
shim (`WaHandle`, tests/host/wire_motion_verb_shim.cpp) is required, per
sprint.md's own handler/projection test split: test_wire_telemetry_frame.py
(ticket 003) is PURE FORMATTING against hand-built Snapshots; this file
is pure PROJECTION -- unit scale, source-of-truth sharing, and the
widest-real-value byte budget.

Canonical spec (read-only, a different repo -- this project conforms to
its grammar, it does not vendor its C++):
radio-robot-lib/docs/design/protocol.md S5.2 (the telemetry frame),
S6.2 (seq wraparound); sprint.md's own Phase B narrative, Design
Rationale, and Open Question 2 (the widest-FULL-frame byte budget).

Reuses test_wire_motion_verbs.py's `motion_verb_lib`/`wa` fixtures and
`WireAdapterHandle` wrapper (widened this ticket with the telemetry
projection surface) -- same "one shim, several pytest files" convention
test_wire_telemetry_frame.py already established for wire_grammar_shim.cpp.

Run with::

    uv run pytest tests/host/test_wire_telemetry_projection.py
"""

import pathlib
import re

import golden_telemetry as golden
from test_wire_motion_verbs import (  # noqa: F401 -- wa/motion_verb_lib re-exported as fixtures
    DIAG_APPLIED_DUTY_LEFT,
    DIAG_APPLIED_DUTY_RIGHT,
    DIAG_CONN_LEFT,
    DIAG_CONN_RIGHT,
    DIAG_CYCLE_COUNT,
    DIAG_CYCLE_OVERRUN_COUNT,
    DIAG_ESTOPPED,
    DIAG_I2C_FAULT,
    DIAG_LEASE_EXPIRED,
    DIAG_LEASE_EXPIRY_COUNT,
    DIAG_POSITION_LEFT,
    DIAG_POSITION_RIGHT,
    DIAG_READY,
    DIAG_STALL_HALTED,
    DIAG_WEDGE_LEFT,
    DIAG_WEDGE_RIGHT,
    DIAG_WRONG_WAY_COUNT,
    STATUS_OK,
    TLM_AUTO,
    TLM_BUFFER,
    TLM_FULL,
    TLM_POSE,
    WireAdapterHandle,
    motion_verb_lib,
    wa,
)

_SRC_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "src"

# Wire::Result's DECLARATION-ORDER ordinal (wire_handler.h) -- NOT the wire
# error code resultCode() maps it to (kUnimplemented -> wire code 6). Not
# imported from test_wire_motion_verbs.py: that file only defines
# RESULT_OK..RESULT_RANGE (0..3) today, and this file's own convention
# (TLM_*/DIAG_* above) is already re-declaring these small ordinal tables
# per file rather than growing a shared import surface for a couple of
# constants.
RESULT_UNIMPLEMENTED = 5


def _column_map(snapshot):
    return {name: (value, hexflag) for name, value, hexflag in snapshot.columns()}


# ---------------------------------------------------------------------------
# Source-text invariant: otosRead() must appear NOWHERE in wire_adapter.cpp.
# otosGet() reads a CACHE; an I2C transaction interposed in the Nezha
# encoder's select->read window destroys the sample (Phase F) -- a
# one-careless-line-away, catastrophic, SILENT failure mode with no
# runtime host-testable signature (no real I2C bus in this link), so the
# enforcement is a source-text check instead.
# ---------------------------------------------------------------------------


def test_otos_read_never_appears_in_wire_adapter_cpp():
    text = (_SRC_DIR / "wire_adapter.cpp").read_text()
    assert "otosRead" not in text


# ---------------------------------------------------------------------------
# Six scale tests (verbatim from the issue's Verification table) -- each
# setter below takes RAW shim units, so the test is not tautological.
# Negatives specifically on oy/vr so a static_cast<uint32_t> slip shows.
# ---------------------------------------------------------------------------


def test_scale_otos_01mm_to_mm(wa):
    wa.set_otos_raw(1234, -5678, 9000)
    cols = _column_map(wa.build_snapshot())
    assert cols["ox"] == (123, False)
    # Plain integer division truncates toward zero: -5678/10 == -567,
    # NOT the round-half -568 a std::lround-style conversion would give
    # -- this is the issue's own named trap ("round-half -> -568").
    assert cols["oy"] == (-567, False)


def test_scale_pose_passthrough(wa):
    wa.set_pose_raw(123, -45, 6789)
    cols = _column_map(wa.build_snapshot())
    assert cols["x"] == (123, False)
    assert cols["y"] == (-45, False)


def test_scale_heading_both_cdeg_no_deg_conversion(wa):
    wa.set_pose_raw(0, 0, 9000)
    wa.set_otos_raw(0, 0, 9000)
    cols = _column_map(wa.build_snapshot())
    # 9000 cdeg (90.00 deg) must stay 9000, not become 90 via an
    # accidental extra /100 or a deg conversion.
    assert cols["h"] == (9000, False)
    assert cols["oh"] == (9000, False)


def test_scale_wheel_speed_passthrough(wa):
    wa.set_wheel_speed(440, -440)
    cols = _column_map(wa.build_snapshot())
    # No x10 quantum copied from radio-robot-lib's own reference
    # telemetry convention (sprint.md Design Rationale: this project
    # stays v5-compatible plain integers).
    assert cols["vl"] == (440, False)
    assert cols["vr"] == (-440, False)


def test_scale_flags_hex_not_decimal(wa):
    # 0x2A = 0b0010_1010 = kFlagEstopped(bit1) | kFlagLeaseExpired(bit3)
    # | kFlagConnRight(bit5) -- any real combination works; only the
    # PRINTED FORM (lowercase hex, no 0x prefix) is under test here.
    wa.set_diag_override(DIAG_READY, 0)
    wa.set_diag_override(DIAG_ESTOPPED, 1)
    wa.set_diag_override(DIAG_STALL_HALTED, 0)
    wa.set_diag_override(DIAG_LEASE_EXPIRED, 1)
    wa.set_diag_override(DIAG_CONN_LEFT, 0)
    wa.set_diag_override(DIAG_CONN_RIGHT, 1)
    wa.set_diag_override(DIAG_WEDGE_LEFT, 0)
    wa.set_diag_override(DIAG_WEDGE_RIGHT, 0)
    cols = _column_map(wa.build_snapshot())
    assert cols["flags"] == (0x2A, True)


def test_scale_i2cf_decimal_not_hex(wa):
    wa.set_diag_override(DIAG_I2C_FAULT, 26)
    cols = _column_map(wa.build_snapshot())
    # Catches a copy-pasted `hex` bit: 26 staying 26, not becoming
    # "1a"'s underlying value 26 printed with hex=True.
    assert cols["i2cf"] == (26, False)


# ---------------------------------------------------------------------------
# seq wraps 127 -> 0 over 130 frames (adapter-side -- the handler only
# prints whatever value it is given).
# ---------------------------------------------------------------------------


def test_seq_wraps_127_to_0_over_130_frames(wa):
    seqs = [_column_map(wa.build_snapshot())["seq"][0] for _ in range(130)]
    assert seqs[0] == 1      # 1st call: (0+1) & 0x7F
    assert seqs[126] == 127  # 127th call
    assert seqs[127] == 0    # 128th call: wraps
    assert seqs[129] == 2    # 130th call


# ---------------------------------------------------------------------------
# The widest FULL frame's formatted byte length vs. RadioTransport's
# 200-byte silent-truncation cap (sprint.md Open Question 2) -- through
# the REAL projection, with REALISTIC-BUT-LARGE values for every one of
# the 20 columns, not a synthetic all-INT32_MIN frame (that pathological
# case is already pinned, at 239 bytes, by
# test_wire_telemetry_frame.py's own
# test_widest_pathological_int32_min_frame_confirms_open_question_2 --
# this test answers the DIFFERENT, previously-unverified question of
# what a REAL robot can actually project).
#
# Per-column reasoning for "realistic-but-large" (not a guess -- see
# this ticket's own final report for the full derivation):
#   - `flags` realistically maxes at 0xFF (255): computeFlags() wires
#     exactly 8 boolean bits and never more, so the 0xffffffff ticket
#     003's own pure-formatting test used (a valid worst case for
#     ARBITRARY hex columns in general) can never actually be produced
#     by THIS adapter. Using the true ceiling here is itself part of
#     this ticket's "can real values reach that magnitude" answer.
#   - `dutl`/`dutr` realistically reach +-10000: diagValue()'s own
#     `appliedDutyLeft * 100.0f` doubles a percentage that is ITSELF
#     already `fraction * 100` (diffdrive.cpp), so 100% duty (a normal,
#     routine operating condition -- a stalled or heavily loaded wheel
#     commands full duty constantly, not just pathologically) reads
#     back as 10000, not 100.
#   - `vl`/`vr`: the tovez bake's default fullDutyVelocity (10795
#     counts/s) times travelCalib_ (0.8102 mm/deg) times 0.1 deg/count
#     caps real wheel speed at ~875 mm/s; -1000 stays a safely-rounded
#     realistic ceiling above that measured bound.
#   - `posl`/`posr`/`i2cf`/`cyc`: long-session magnitudes -- ~100 m of
#     cumulative travel (~12.3 counts/mm), several hours of an
#     unnoticed wedged I2C bus (~1 fault per ~24 ms kernel cycle), and
#     roughly a day of continuous uptime (~24 ms/cycle), respectively.
#   - `x`/`y`/`ox`/`oy`/`h`/`oh`: mirror this project's own
#     "realistic-but-large" convention already pinned in
#     test_wire_telemetry_frame.py's sibling test, so the two tickets'
#     numbers stay comparable.
# ---------------------------------------------------------------------------

_REALISTIC_FULL_DIAG_OVERRIDES = {
    # All eight flags bits set -> flags = 0xFF, the TRUE realistic
    # ceiling (not the hypothetical 0xffffffff a generic hex column
    # could otherwise reach).
    DIAG_READY: 1,
    DIAG_ESTOPPED: 1,
    DIAG_STALL_HALTED: 1,
    DIAG_LEASE_EXPIRED: 1,
    DIAG_CONN_LEFT: 1,
    DIAG_CONN_RIGHT: 1,
    DIAG_WEDGE_LEFT: 1,
    DIAG_WEDGE_RIGHT: 1,
    DIAG_I2C_FAULT: 999999,
    DIAG_LEASE_EXPIRY_COUNT: 9999,
    DIAG_POSITION_LEFT: -1234567,
    DIAG_POSITION_RIGHT: -1234567,
    DIAG_APPLIED_DUTY_LEFT: -10000,
    DIAG_APPLIED_DUTY_RIGHT: -10000,
    DIAG_CYCLE_COUNT: 12345678,
    DIAG_CYCLE_OVERRUN_COUNT: 9999,
    DIAG_WRONG_WAY_COUNT: 9999,
}


def test_widest_realistic_full_frame_fits_under_radio_cap(wa):
    wa.on_tlm(TLM_FULL)
    for ordinal, value in _REALISTIC_FULL_DIAG_OVERRIDES.items():
        wa.set_diag_override(ordinal, value)
    wa.set_pose_raw(-123456, -123456, -18000)
    wa.set_otos_raw(-1234560, -1234560, -18000)  # -> /10 == -123456 mm
    wa.set_wheel_speed(-1000, -1000)
    wa.set_now_ms(123456789)

    snapshot = wa.build_snapshot()
    assert snapshot.count == 20  # POSE's 12 plus FULL's 8

    wa.emit_telemetry(snapshot)
    lines = wa.take_sink().split(b"\n")
    thdr_line = lines[0] + b"\n"
    t_line = lines[1] + b"\n"

    # Measured, not guessed -- pinned here as a regression, and this
    # ticket's own final report restates the exact numbers for ticket
    # 005's bench handoff notes to re-state to the stakeholder in turn.
    assert len(thdr_line) == 86
    assert len(t_line) == 138
    assert len(t_line) < 200  # RadioTransport::kMaxPayloadBytes


# ---------------------------------------------------------------------------
# STATUS otos= truthfulness (R-22/WIRE-06) -- a settable OTOS-connected
# test double proves the value is 0 when disconnected and 1 when
# connected, not unconditionally 0.
# ---------------------------------------------------------------------------


def test_status_otos_reflects_real_connectivity_disconnected(wa):
    wa.set_otos_connected(False)
    wa.feed(b"STATUS #1\n")
    assert b"otos=0" in wa.take_sink()


def test_status_otos_reflects_real_connectivity_connected(wa):
    wa.set_otos_connected(True)
    wa.feed(b"STATUS #1\n")
    assert b"otos=1" in wa.take_sink()


# ---------------------------------------------------------------------------
# STATUS i2cf= (SUC-005) -- decimal, from the SAME diagValue(8) source
# the telemetry `i2cf` column reads.
# ---------------------------------------------------------------------------


def test_status_i2cf_decimal_from_shared_diag_source(wa):
    wa.set_diag_override(DIAG_I2C_FAULT, 26)
    wa.feed(b"STATUS #1\n")
    reply = wa.take_sink()
    assert b"i2cf=26 " in reply
    assert b"i2cf=1a" not in reply  # wrong `hex` bit would produce this


# ---------------------------------------------------------------------------
# STATUS cyc= (sprint 010 ticket 003,
# unpowered-nezha-brick-wedges-program-at-boot.md's 2026-08-24
# correction) -- same-source guarantee, mirroring i2cf's own test
# immediately above: STATUS's `cyc=` and FULL telemetry's `cyc` column
# both read diagValue(kDiagCycleCount), so the two can never disagree.
# Unlike the i2cf test above, this one deliberately does NOT use
# set_diag_override() -- it steps a REAL kernel (no canned value
# anywhere) so a bug that wired status()'s `cyc` to a different ordinal,
# or to a stale/cached read, would show up as a genuine mismatch instead
# of two overridable stubs that merely happen to share one array.
# ---------------------------------------------------------------------------


def test_status_cyc_matches_live_telemetry_cyc_column(wa):
    wa.set_max_duty(100.0)
    wa.set_full_duty_velocity(1000.0)
    assert wa.begin() == STATUS_OK
    wa.on_tlm(TLM_FULL)  # cyc is a FULL-only column (POSE's 12 lack it)
    for _ in range(3):
        wa.step()

    wa.feed(b"STATUS #1\n")
    reply = wa.take_sink()
    match = re.search(rb"cyc=(\d+)", reply)
    assert match is not None, reply
    status_cyc = int(match.group(1))

    snapshot = wa.build_snapshot()
    cols = {name: value for name, value, _ in snapshot.columns()}
    telemetry_cyc = cols["cyc"]

    # Never-ticked would be 0 -- this kernel really stepped, so both
    # readings must be the SAME nonzero value, not just equal-because-
    # both-are-zero.
    assert status_cyc == 3
    assert telemetry_cyc == 3
    assert status_cyc == telemetry_cyc


# ---------------------------------------------------------------------------
# Golden frame: known raw shim inputs through the REAL WaHandle, asserted
# byte-exact against tests/host/golden_telemetry.py's shared fixture --
# the same fixture sprint 005's future Python parser test will import,
# so the emitter and the (future) parser cannot silently drift apart.
# ---------------------------------------------------------------------------


def test_golden_pose_frame_matches_shared_fixture(wa):
    wa.set_pose_raw(golden.RAW_POSE_X_MM, golden.RAW_POSE_Y_MM,
                     golden.RAW_POSE_HEADING_CDEG)
    wa.set_otos_raw(golden.RAW_OTOS_X_01MM, golden.RAW_OTOS_Y_01MM,
                     golden.RAW_OTOS_HEADING_CDEG)
    wa.set_wheel_speed(golden.RAW_WHEEL_SPEED_LEFT_MMS,
                        golden.RAW_WHEEL_SPEED_RIGHT_MMS)
    wa.set_now_ms(golden.RAW_NOW_MS)
    wa.set_diag_override(DIAG_READY, golden.RAW_DIAG_BOOLEANS["ready"])
    wa.set_diag_override(DIAG_ESTOPPED, golden.RAW_DIAG_BOOLEANS["estopped"])
    wa.set_diag_override(DIAG_STALL_HALTED,
                          golden.RAW_DIAG_BOOLEANS["stall_halted"])
    wa.set_diag_override(DIAG_LEASE_EXPIRED,
                          golden.RAW_DIAG_BOOLEANS["lease_expired"])
    wa.set_diag_override(DIAG_CONN_LEFT, golden.RAW_DIAG_BOOLEANS["conn_left"])
    wa.set_diag_override(DIAG_CONN_RIGHT,
                          golden.RAW_DIAG_BOOLEANS["conn_right"])
    wa.set_diag_override(DIAG_WEDGE_LEFT, golden.RAW_DIAG_BOOLEANS["wedge_left"])
    wa.set_diag_override(DIAG_WEDGE_RIGHT,
                          golden.RAW_DIAG_BOOLEANS["wedge_right"])
    wa.set_diag_override(DIAG_I2C_FAULT, golden.RAW_I2C_FAULT_COUNT)

    snapshot = wa.build_snapshot()
    assert snapshot.columns() == golden.EXPECTED_COLUMNS

    wa.emit_telemetry(snapshot)
    lines = wa.take_sink().split(b"\n")
    thdr_line = lines[0] + b"\n"
    t_line = lines[1] + b"\n"
    reliability_line = lines[2] + b"\n"

    assert thdr_line == golden.EXPECTED_THDR_LINE
    assert t_line == golden.EXPECTED_T_LINE
    assert reliability_line == golden.EXPECTED_RELIABILITY_LINE


# ---------------------------------------------------------------------------
# TLM AUTO/BUFFER column-set semantics (sprint 008 ticket 005, closing
# tlm-auto-buffer-column-set-undefined.md): before this ticket, kAuto and
# kBuffer both silently fell through to POSE's 12-column set with no
# decision recorded anywhere. The decision made here: kAuto is a
# documented ALIAS for kPose (same columns, same cadence); kBuffer
# REFUSES (kUnimplemented, wire err 6) at the TLM verb itself, before
# mode_ is ever touched -- no buffering mechanism exists anywhere in this
# codebase to give "buffer" real, narrower semantics yet. Sprint 004's own
# note is that the `thdr` line is what a host actually binds to, so that
# is what gets pinned below, not just an internal mode_ flag.
# ---------------------------------------------------------------------------


def test_tlm_auto_thdr_byte_identical_to_pose(motion_verb_lib):
    """Two INDEPENDENT handles, each getting its own first-ever thdr.
    Switching a SINGLE handle from POSE to AUTO would never re-emit
    thdr at all (identical column names/count/hex-ness -- headerChanged()
    would see no change), which would prove nothing about what AUTO's
    thdr looks like on its own; two fresh handles avoid that trap."""
    with WireAdapterHandle(motion_verb_lib) as pose_handle, \
            WireAdapterHandle(motion_verb_lib) as auto_handle:
        assert pose_handle.on_tlm(TLM_POSE) == 0  # Wire::Result::kOk
        assert auto_handle.on_tlm(TLM_AUTO) == 0  # Wire::Result::kOk

        pose_handle.emit_telemetry(pose_handle.build_snapshot())
        auto_handle.emit_telemetry(auto_handle.build_snapshot())

        pose_thdr = pose_handle.take_sink().split(b"\n", 1)[0] + b"\n"
        auto_thdr = auto_handle.take_sink().split(b"\n", 1)[0] + b"\n"

        assert pose_thdr.startswith(b"thdr ")
        assert auto_thdr == pose_thdr


def test_tlm_auto_snapshot_is_poses_12_columns(wa):
    """AUTO's own buildSnapshot() output -- 12 columns, same names in the
    same order POSE uses (wire_adapter.cpp's own column list) -- not just
    the thdr line derived from it."""
    wa.on_tlm(TLM_AUTO)
    snapshot = wa.build_snapshot()
    assert snapshot.count == 12
    names = [snapshot.name(i) for i in range(snapshot.count)]
    assert names == [
        "seq", "now", "flags", "x", "y", "h", "ox", "oy", "oh", "vl", "vr",
        "i2cf",
    ]


def test_tlm_buffer_refused_via_direct_on_tlm(wa):
    """WireAdapter::onTlm() called directly (bypasses the wire grammar,
    same convention as this project's other on_tlm() tests) -- returns
    kUnimplemented's own declaration-order ordinal (5), which resultCode()
    maps to wire code 6."""
    assert wa.on_tlm(TLM_BUFFER) == RESULT_UNIMPLEMENTED


def test_tlm_buffer_refused_leaves_a_prior_mode_untouched(wa):
    """A BUFFER refusal must not silently switch mode_ away from
    whatever was already active -- 'merits rejections don't change
    state', the same convention sprint 008 ticket 001 already
    established for the six motion verbs' timeout refusals. Proven on
    the LIVE surface a host would actually observe (still subscribed,
    still POSE's 12 columns), not just an internal flag."""
    assert wa.on_tlm(TLM_POSE) == 0  # Wire::Result::kOk
    assert wa.has_live_telemetry()

    assert wa.on_tlm(TLM_BUFFER) == RESULT_UNIMPLEMENTED

    assert wa.has_live_telemetry()  # still subscribed -- BUFFER had no effect
    snapshot = wa.build_snapshot()
    assert snapshot.count == 12  # still POSE's columns, unchanged


def test_tlm_buffer_refused_over_the_wire_acks_then_err_6(wa):
    """The full wire path (protocol.md S8.2's own 'ack unconditionally,
    then err on top of a merits refusal' shape) -- err 6 is
    ERR_UNIMPLEMENTED (wire_handler.h's Result::kUnimplemented ->
    resultCode() -> 6). Before this ticket's wire_handler.cpp fix,
    execTlm() hardcoded errCode = 0 and this could never appear on the
    wire for ANY TLM outcome, real or mocked."""
    wa.feed(b"TLM BUFFER #1\n")
    assert wa.take_sink() == b"ack 1 0 none\nerr 6 #1\n"


def test_tlm_buffer_never_emits_a_thdr_or_t_frame(wa):
    """TLM BUFFER's own wire reply carries no thdr/t line -- only
    ack+err (asserted byte-exact above) -- and telemetryEnabled()
    (has_live_telemetry()) stays false with no prior mode already
    active, the SAME flag protocol.cpp's real fiber loop gates
    buildSnapshot()/emitTelemetry() on every tick (see
    telemetryEnabled()'s own doc comment, wire_adapter.h). A driver
    honoring that gate therefore never builds or emits a frame for this
    refused request at all."""
    wa.feed(b"TLM BUFFER #1\n")
    reply = wa.take_sink()
    assert b"thdr" not in reply
    assert b"\nt " not in reply
    assert not reply.startswith(b"t ")

    assert not wa.has_live_telemetry()
