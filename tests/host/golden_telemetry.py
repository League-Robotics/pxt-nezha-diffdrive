"""tests/host/golden_telemetry.py -- the shared golden telemetry-frame
fixture.

One canonical set of RAW shim inputs (what a test double, or the real
shims.cpp, returns for buildSnapshot()'s five forward-declared reads
plus diagValue()'s eight boolean flags ordinals and diagValue(8) for
i2cf), the WIRE-scaled values `WireAdapter::buildSnapshot()` must
produce from them, and the exact `thdr`/`t` byte strings
`Wire::WireHandler` must emit from that Snapshot.

Imported by BOTH the C++-driven host test
(test_wire_telemetry_projection.py, via the real WireAdapter/WaHandle)
AND the Python telemetry-parser test (tests/tools/test_tlm.py) -- so
the emitter and the parser cannot silently drift apart from each
other.

Deliberately POSE-shaped (12 columns), not FULL: the widest-FULL-frame
byte-budget question has its own dedicated test in
test_wire_telemetry_projection.py (test_widest_realistic_full_frame_
fits_under_radio_cap); this fixture's job is a small, hand-checkable,
EXACT byte-for-byte vector -- the kind a human can verify by reading the
numbers once, not a stress case.
"""

# ---------------------------------------------------------------------
# Raw shim inputs -- what buildSnapshot()'s five forward-declared reads
# (poseX/poseY/poseHeading/otosGet/wheelSpeed) and diagValue() return,
# in the SAME raw units the real shims.cpp contract documents.
# ---------------------------------------------------------------------

RAW_POSE_X_MM = 250
RAW_POSE_Y_MM = -75
RAW_POSE_HEADING_CDEG = 9000  # 90.00 degrees

# otosGet(0)/(1) are 0.1 mm (buildSnapshot() divides by 10, truncating
# toward zero); otosGet(2) is ALREADY centidegrees -- no conversion.
RAW_OTOS_X_01MM = 2500  # -> 250 mm
RAW_OTOS_Y_01MM = -755  # -> -75 mm (truncates toward zero, not -76)
RAW_OTOS_HEADING_CDEG = 8955

RAW_WHEEL_SPEED_LEFT_MMS = 120
RAW_WHEEL_SPEED_RIGHT_MMS = -120

RAW_NOW_MS = 5000

RAW_I2C_FAULT_COUNT = 3

# diagValue() ordinals 0-7 (ready, estopped, stallHalted, leaseExpired,
# connLeft, connRight, wedgeLeft, wedgeRight) -- ready plus both
# encoders connected, everything else clear:
#   bit0 (ready) + bit4 (connLeft) + bit5 (connRight)
#   = 0b0011_0001 = 0x31
RAW_DIAG_BOOLEANS = {
    "ready": 1,
    "estopped": 0,
    "stall_halted": 0,
    "lease_expired": 0,
    "conn_left": 1,
    "conn_right": 1,
    "wedge_left": 0,
    "wedge_right": 0,
}
EXPECTED_FLAGS_VALUE = 0x31

# buildSnapshot() advances seq_ BEFORE building each frame -- a freshly
# constructed WireAdapter's very first frame reports seq 1, not 0.
EXPECTED_SEQ = 1

# ---------------------------------------------------------------------
# Expected wire-scaled POSE columns, in order -- (name, value, hex).
# ---------------------------------------------------------------------

EXPECTED_COLUMNS = [
    ("seq", EXPECTED_SEQ, False),
    ("now", RAW_NOW_MS, False),
    ("flags", EXPECTED_FLAGS_VALUE, True),
    ("x", RAW_POSE_X_MM, False),
    ("y", RAW_POSE_Y_MM, False),
    ("h", RAW_POSE_HEADING_CDEG, False),
    ("ox", 250, False),
    ("oy", -75, False),
    ("oh", RAW_OTOS_HEADING_CDEG, False),
    ("vl", RAW_WHEEL_SPEED_LEFT_MMS, False),
    ("vr", RAW_WHEEL_SPEED_RIGHT_MMS, False),
    ("i2cf", RAW_I2C_FAULT_COUNT, False),
]

EXPECTED_COLUMN_NAMES = [c[0] for c in EXPECTED_COLUMNS]

# ---------------------------------------------------------------------
# Exact expected wire bytes -- byte-for-byte, matching
# wire_handler.cpp's own emitHeader()/emitFrame() formatting: space-
# separated, lowercase hex with no "0x" prefix for a hex-flagged column
# (here just `flags`), plain "%ld" decimal for everything else.
# ---------------------------------------------------------------------

EXPECTED_THDR_LINE = b"thdr seq now flags x y h ox oy oh vl vr i2cf\n"
EXPECTED_T_LINE = b"t 1 5000 31 250 -75 9000 250 -75 8955 120 -120 3\n"

# EXPECTED_RELIABILITY_LINE is GONE (2026-08-26, protocol.md S8.5): no
# reliability line follows `t` any more -- an ack/nack is only ever a
# direct reply to an inbound line, never part of a telemetry emission.
