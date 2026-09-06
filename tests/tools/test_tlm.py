"""tests/tools/test_tlm.py -- pins `tools/tlm.py`'s v6 telemetry
parser (`TlmStream`) and its three fail-loud guards (`require_stream`,
`write_tlm_csv`, and the `.meta.json` zero-frame refusal built into
it).

**Why this exists.** Sprint 005 ticket 001
(`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
tickets/001-...md`) replaces six tools' worth of scattered, silently-
broken v5 `TLM:` parsing with one shared v6 `thdr`/`t` parser.
`tour_watch.py:202` and `tour_capture.py:70` both hard-coded a field
count that stopped matching the wire line the moment `vl`/`vr` were
added -- and nobody noticed, because the failure mode was an empty
CSV, not a crash. This file exists so `tools/tlm.py` cannot regress
the same way silently: every counter (`frames`/`orphan_frames`/
`malformed`/`dropped`) and every guard is pinned against both
synthetic lines AND real captured hardware frames, not just a
spec-shaped double.

**Fixtures are real captured hardware, not invented.** `FULL_THDR_LIVE`
/`FULL_T_LIVE` and `POSE_THDR_IDLE`/`POSE_T_IDLE` below are verbatim
lines captured from tovez (USB serial, hex built from master at
`4e14817`) -- see
`clasi/sprints/005-retrofit-bench-tooling-onto-the-v6-telemetry-stream/
issues/retrofit-bench-tooling-onto-the-v6-telemetry-stream.md`'s
"Bench confirmation" and "Realistic-value capture" sections, which are
this ticket's own stated authority. `golden_telemetry.py`'s
POSE-shaped hand-checkable vector is imported here too (as PARSER
INPUT -- the same fixture `test_wire_telemetry_projection.py` uses as
expected EMITTED wire bytes), so the emitter and this parser are
pinned against one shared source of truth and cannot silently drift
apart from each other.

**Tests are written to discriminate, not just to pass.** Per this
ticket's own instructions and the standing lesson from sprints 007/008
(a test that passes against a double mirroring the wrong contract is
worse than no test): `test_different_header_after_frames_switches_
columns` proves the no-op re-read logic is not simply "always a
no-op"; `test_seq_gap_...` and `test_seq_wraparound_...` feed the SAME
kind of "numbers far apart" input to prove the modulo-based gap math,
not a naive subtraction, is what is actually running;
`test_ack_and_nack_lines_are_not_telemetry` proves the reliability
keepalive is filtered rather than merely never appearing in a
fixture; and `test_require_stream_raises_...`/`test_require_stream_
returns_normally_...` are a matched raising/non-raising pair against
the SAME fake link shape, not two differently-shaped doubles.

**Sprint 005 ticket 002** (the six-consumer retrofit) added one more
piece of real decision logic to `tlm.py` itself, not just to a thin
consumer wrapper: `read_meta_sidecar()`, the read-time counterpart to
`write_tlm_csv()`'s sidecar, used by `tour_chart.py`/`practice_chart.py`
to refuse plotting a zero-frame run without duplicating the sidecar's
naming convention into two chart tools. The three tests below pin its
three outcomes (missing sidecar, present with real frames, present
reporting `frames == 0`) the same way the fail-loud guards above are
pinned -- against `tmp_path`, no chart tool or matplotlib involved.

Run with::

    uv run pytest tests/tools/test_tlm.py
"""
import csv
import json
import pathlib
import sys

import pytest

# tests/tools/test_tlm.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
_HOST_TESTS_DIR = _REPO_ROOT / 'tests' / 'host'
for _p in (_TOOLS_DIR, _HOST_TESTS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import tlm  # noqa: E402  (path must be set up first)
import golden_telemetry as golden  # noqa: E402  (ditto)


# --- fixtures ---------------------------------------------------------

POSE_THDR = 'thdr seq now flags x y h ox oy oh vl vr i2cf'

# Real capture, tovez, 2026-08-24, the robot's Nezha brick not yet
# reporting connected (every column legitimately zero -- this is the
# "Bench confirmation" section's shape/cadence proof, kept here as its
# own fixture rather than only synthesized).
POSE_T_IDLE = 't 1 37973 0 0 0 0 0 0 0 0 0 0'

FULL_THDR = ('thdr seq now flags x y h ox oy oh vl vr i2cf cyc posl posr '
             'dutl dutr lexc wrng cycovr')

# Real capture, tovez, 2026-08-24, "Realistic-value capture" section --
# the widest-observed-with-live-values FULL frame (75 B), kernel awake
# and the robot driving. flags=0x31 (ready+connLeft+connRight), real
# negative values (vl=-122, dutl=-1300), and zero OTOS columns on a
# robot with no OTOS fitted (ox=oy=oh=0 -- correct data, not a fault).
FULL_T_LIVE = ('t 25 988992 31 142 -16 11737 0 0 0 -122 126 3 101 286 '
               '3319 -1300 1800 0 0 0')

# The reliability keepalive -- a per-line reply, not a periodic
# broadcast (sprint 024 ticket 001 deleted the firmware's free-running
# emitReliability() call; see clasi/issues/reliability-line-free-runs-
# at-20-hz-on-the-radio-with-no-host.md) -- and is NOT telemetry either
# way (this ticket's own framing). Shape from wire_handler.cpp's
# `"ack %lu %lu %s\n"`/`"nack %lu %lu %s\n"`.
ACK_LINE = 'ack 0 0 none'
NACK_LINE = 'nack 5 0 none'


def _pose_t_line(seq, now=1000):
    """A synthetic POSE `t` line with a chosen `seq`, everything else
    zero -- for the seq-gap tests, where the interesting variable is
    `seq` alone."""
    return 't {seq} {now} 0 0 0 0 0 0 0 0 0 0'.format(seq=seq, now=now)


class FakeLink:
    """Minimal send()/lines() double matching robotlink.Link's own
    surface -- no real serial/radio anywhere in this file. Per this
    ticket's Implementation Notes: require_stream() is deliberately
    NOT tested against a real Link/serial object here."""

    def __init__(self, incoming=()):
        self.sent = []
        self._incoming = list(incoming)

    def send(self, line, repeat=1):
        self.sent.append(line)

    def lines(self, timeout, until=None):
        # A real Link blocks up to `timeout`; this double resolves
        # deterministically from a canned line list instead -- no
        # sleeping, no flakiness.
        for line in self._incoming:
            yield line


# --- header tracking ----------------------------------------------------


def test_fresh_header_sets_columns_by_name():
    stream = tlm.TlmStream()
    assert stream.columns is None
    stream.feed(POSE_THDR)
    assert stream.columns == [
        'seq', 'now', 'flags', 'x', 'y', 'h', 'ox', 'oy', 'oh', 'vl',
        'vr', 'i2cf',
    ]


def test_reread_identical_header_is_a_noop():
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    columns_before = stream.columns

    stream.feed(POSE_THDR)  # identical re-read

    assert stream.columns is columns_before  # same object -- true no-op
    assert stream.orphan_frames == 0
    assert stream.malformed == 0
    assert stream.frames == []


def test_reread_after_20_frames_is_still_a_noop():
    """The firmware's own re-emit cadence (kHeaderRefreshFrames = 20) --
    a header re-read after a batch of frames must behave identically to
    an immediate re-read."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    for i in range(20):
        stream.feed(_pose_t_line(seq=i % tlm.SEQ_MODULUS))
    columns_before = stream.columns

    stream.feed(POSE_THDR)

    assert stream.columns is columns_before
    assert len(stream.frames) == 20


def test_different_header_after_frames_switches_columns():
    """Discriminates the no-op logic above: a GENUINELY different
    column set (a POSE -> FULL mid-stream switch) must never be
    swallowed as a no-op."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(POSE_T_IDLE)
    pose_columns = stream.columns

    stream.feed(FULL_THDR)

    assert stream.columns != pose_columns
    assert stream.columns == FULL_THDR.split()[1:]
    # And frames decoded after the switch use the NEW column set, by
    # name -- not the old positions.
    row = stream.feed(FULL_T_LIVE)
    assert row['cyc'] == 101
    assert len(stream.frames) == 2  # the POSE frame plus this FULL one


# --- orphan / malformed classification -----------------------------------


def test_t_before_any_header_counts_orphan_not_frame():
    stream = tlm.TlmStream()
    result = stream.feed(POSE_T_IDLE)
    assert result is None
    assert stream.orphan_frames == 1
    assert stream.malformed == 0
    assert stream.frames == []


def test_arity_mismatch_after_header_is_malformed_not_orphan():
    """Discriminates malformed from orphan: once a header IS present,
    a short line (RadioTransport's 200-byte truncation) must land in
    `malformed`, never `orphan_frames`."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)

    result = stream.feed('t 1 37973 0 0 0 0 0')  # 7 values, header wants 12

    assert result is None
    assert stream.malformed == 1
    assert stream.orphan_frames == 0
    assert stream.frames == []


def test_non_numeric_value_with_correct_arity_is_also_malformed():
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)

    result = stream.feed('t 1 37973 0 0 0 0 0 0 0 0 0 GARBAGE')  # 12 tokens

    assert result is None
    assert stream.malformed == 1
    assert stream.frames == []


def test_malformed_frame_does_not_raise():
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    # Neither of these must raise -- fail-loud is require_stream()'s
    # and write_tlm_csv()'s job, not feed()'s.
    stream.feed('t 1 2 3')
    stream.feed('t 1 2 3 4 5 6 7 8 9 10 11 NOTANUMBER')
    assert stream.malformed == 2


def test_ack_and_nack_lines_are_not_telemetry():
    """The reliability keepalive must be filtered outright -- not
    counted as malformed, not counted as an orphan frame, not decoded
    as a row."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)

    assert stream.feed(ACK_LINE) is None
    assert stream.feed(NACK_LINE) is None

    assert stream.frames == []
    assert stream.malformed == 0
    assert stream.orphan_frames == 0


# --- seq-gap loss tracking -------------------------------------------------


def test_consecutive_seq_has_zero_loss():
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    for seq in (5, 6, 7):
        stream.feed(_pose_t_line(seq))
    assert stream.dropped == 0
    assert stream.loss_pct == 0.0


def test_seq_gap_increments_dropped_by_missing_frame_count():
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(_pose_t_line(10))
    stream.feed(_pose_t_line(15))  # 11, 12, 13, 14 never arrived

    assert stream.dropped == 4
    assert stream.loss_pct == pytest.approx(100.0 * 4 / (2 + 4))


def test_seq_wraparound_127_to_0_is_not_miscounted_as_loss():
    """Discriminates against a naive `new_seq - old_seq` implementation:
    127 -> 0 is numerically a huge negative delta, but it is the
    NORMAL consecutive case for a 7-bit wrapping counter."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(_pose_t_line(127))
    stream.feed(_pose_t_line(0))

    assert stream.dropped == 0


def test_seq_gap_straddling_the_wrap_boundary_is_still_counted():
    """A real gap that happens to cross 127 -> 0 must still count --
    wraparound tolerance must not become a blanket exemption."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(_pose_t_line(126))
    stream.feed(_pose_t_line(3))  # 127, 0, 1, 2 never arrived

    assert stream.dropped == 4


# --- unit-conversion helpers, against the shared golden frame -----------


def test_unit_helpers_against_golden_telemetry_fixture():
    """Parser input is the EMITTER's own expected-output fixture
    (tests/host/golden_telemetry.py), not a hand-rolled line -- so this
    test cannot silently disagree with what WireHandler is proven to
    emit."""
    stream = tlm.TlmStream()
    stream.feed(golden.EXPECTED_THDR_LINE.decode('ascii').strip())
    row = stream.feed(golden.EXPECTED_T_LINE.decode('ascii').strip())

    assert row is not None
    assert row['seq'] == golden.EXPECTED_SEQ
    assert row['now'] == golden.RAW_NOW_MS
    assert row['flags'] == golden.EXPECTED_FLAGS_VALUE  # hex-decoded
    assert row['i2cf'] == golden.RAW_I2C_FAULT_COUNT

    assert tlm.pose_cm(row) == {'x': 25.0, 'y': -7.5, 'h': 90.0}
    assert tlm.otos_cm(row) == {'x': 25.0, 'y': -7.5, 'h': 89.55}
    assert tlm.wheels_mms(row) == {
        'vl': golden.RAW_WHEEL_SPEED_LEFT_MMS,
        'vr': golden.RAW_WHEEL_SPEED_RIGHT_MMS,
    }


# --- real captured 75 B FULL frame (ticket's own acceptance criterion) --


def test_real_captured_full_frame_decodes_all_20_columns():
    stream = tlm.TlmStream()
    stream.feed(FULL_THDR)
    row = stream.feed(FULL_T_LIVE)

    assert row == {
        'seq': 25, 'now': 988992, 'flags': 0x31,
        'x': 142, 'y': -16, 'h': 11737,
        'ox': 0, 'oy': 0, 'oh': 0,
        'vl': -122, 'vr': 126, 'i2cf': 3,
        'cyc': 101, 'posl': 286, 'posr': 3319,
        'dutl': -1300, 'dutr': 1800,
        'lexc': 0, 'wrng': 0, 'cycovr': 0,
    }
    assert stream.malformed == 0
    assert stream.orphan_frames == 0


def test_duty_pct_undoes_the_wire_double_x100_scale():
    """The FULL frame's dutl/dutr are percent multiplied by 100 twice
    over (see tlm.py's own header comment for the fraction -> percent
    -> wire derivation) -- pinned against the real captured frame
    above: -1300 -> -13.0%, 1800 -> 18.0%."""
    stream = tlm.TlmStream()
    stream.feed(FULL_THDR)
    row = stream.feed(FULL_T_LIVE)

    assert tlm.duty_pct(row) == {'dutl': -13.0, 'dutr': 18.0}


def test_duty_pct_10000_is_full_duty():
    """The documented anchor point: a raw wire value of 10000 (percent
    x100) is true 100% duty."""
    assert tlm.duty_pct({'dutl': 10000, 'dutr': -10000}) == {
        'dutl': 100.0, 'dutr': -100.0,
    }


def test_real_captured_idle_pose_frame_zero_values_are_not_a_fault():
    """A zero-valued frame (no OTOS, kernel not yet driving) must
    decode as ordinary, valid data -- not raise, not count as
    malformed/orphan."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    row = stream.feed(POSE_T_IDLE)

    assert row == {
        'seq': 1, 'now': 37973, 'flags': 0,
        'x': 0, 'y': 0, 'h': 0, 'ox': 0, 'oy': 0, 'oh': 0,
        'vl': 0, 'vr': 0, 'i2cf': 0,
    }
    assert stream.malformed == 0
    assert stream.orphan_frames == 0


# --- fail-loud guard 1: require_stream() ---------------------------------


def test_require_stream_raises_before_any_run_command_when_dead():
    link = FakeLink(incoming=[ACK_LINE, NACK_LINE, ACK_LINE])  # never a `t`
    with pytest.raises(tlm.DeadTelemetryError):
        tlm.require_stream(link, timeout=3.0)
    # Only the subscribe was ever sent -- no run-triggering command.
    assert link.sent == ['TLM POSE']


def test_require_stream_returns_normally_once_a_frame_arrives():
    link = FakeLink(incoming=[POSE_THDR, POSE_T_IDLE])
    stream = tlm.require_stream(link, timeout=3.0)
    assert isinstance(stream, tlm.TlmStream)
    assert len(stream.frames) == 1
    assert link.sent == ['TLM POSE']


def test_require_stream_feeds_the_caller_supplied_stream():
    """The `stream=` parameter: a caller keeps accumulating in the
    SAME TlmStream across the whole run, rather than throwing away the
    liveness-check frame."""
    existing = tlm.TlmStream()
    link = FakeLink(incoming=[POSE_THDR, POSE_T_IDLE])

    returned = tlm.require_stream(link, timeout=3.0, stream=existing)

    assert returned is existing
    assert len(existing.frames) == 1


# --- fail-loud guards 2 & 3: write_tlm_csv() + .meta.json sidecar -------


def test_write_tlm_csv_raises_on_zero_frames_and_leaves_no_files(tmp_path):
    stream = tlm.TlmStream()
    csv_path = tmp_path / 'run_tlm.csv'

    with pytest.raises(tlm.EmptyCaptureError):
        tlm.write_tlm_csv(stream, str(csv_path))

    assert not csv_path.exists()
    assert not csv_path.with_suffix('.meta.json').exists()


def test_write_tlm_csv_writes_csv_and_meta_matching_fed_data(tmp_path):
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(_pose_t_line(10, now=1000))
    stream.feed(_pose_t_line(15, now=3000))  # 4 dropped in between
    csv_path = tmp_path / 'run_tlm.csv'

    meta = tlm.write_tlm_csv(stream, str(csv_path))

    assert csv_path.exists()
    with open(csv_path, newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]['seq'] == '10'
    assert rows[1]['seq'] == '15'

    meta_path = csv_path.with_suffix('.meta.json')
    assert meta_path.exists()
    with open(meta_path) as f:
        on_disk = json.load(f)

    assert on_disk == meta  # returned dict matches what was written
    assert meta['frames'] == 2
    assert meta['dropped'] == 4
    assert meta['loss_pct'] == pytest.approx(100.0 * 4 / 6)
    assert meta['orphan_frames'] == 0
    assert meta['malformed'] == 0
    assert meta['columns'] == stream.columns
    assert meta['duration'] == pytest.approx(2.0)  # now: 1000 -> 3000 ms


def test_write_tlm_csv_union_header_survives_a_mid_stream_column_switch(
        tmp_path):
    """SUC-002/the ticket's own emphasis on mid-stream switches: a POSE
    frame followed by a FULL frame must not lose the FULL-only columns,
    nor crash on the POSE row's missing keys."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(POSE_T_IDLE)
    stream.feed(FULL_THDR)
    stream.feed(FULL_T_LIVE)
    csv_path = tmp_path / 'run_tlm.csv'

    tlm.write_tlm_csv(stream, str(csv_path))

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    assert 'cyc' in fieldnames and 'dutl' in fieldnames  # FULL-only cols
    assert rows[0]['cyc'] == ''  # the POSE row never had this column
    assert rows[1]['cyc'] == '101'


# --- sprint 005 ticket 002: read_meta_sidecar() ---------------------------
# The read-time counterpart to write_tlm_csv()'s sidecar, for chart tools
# that plot a run's CSVs without being the ones that captured them.


def test_read_meta_sidecar_missing_returns_none_not_an_error(tmp_path):
    """No sidecar at all (an older capture, or a source that never wrote
    one) is not itself refused -- the caller decides what to do with
    None, this function just reports "nothing to check"."""
    pose_csv = tmp_path / 'run_pose.csv'
    pose_csv.write_text('t,x\n')  # the sidecar this derives from a NAME,
    # not file content -- no _tlm.meta.json needs to exist alongside it

    assert tlm.read_meta_sidecar(str(pose_csv)) is None


def test_read_meta_sidecar_finds_the_sidecar_for_a_differently_suffixed_csv(
        tmp_path):
    """The whole point: a chart tool passes `<stem>_pose.csv`, and the
    sidecar actually lives at `<stem>_tlm.meta.json` -- a DIFFERENT
    suffix, written by write_tlm_csv() for `<stem>_tlm.csv`. Proves the
    stem-derivation, not just "a sidecar exists somewhere"."""
    stream = tlm.TlmStream()
    stream.feed(POSE_THDR)
    stream.feed(_pose_t_line(1))
    stream.feed(_pose_t_line(2))
    tlm.write_tlm_csv(stream, str(tmp_path / 'run_tlm.csv'))
    pose_csv = tmp_path / 'run_pose.csv'  # a DIFFERENT suffix, same stem

    meta = tlm.read_meta_sidecar(str(pose_csv))

    assert meta is not None
    assert meta['frames'] == 2


def test_read_meta_sidecar_zero_frames_is_returned_not_raised(tmp_path):
    """This function only READS and reports -- it never raises on the
    caller's behalf (tour_chart.py/practice_chart.py do that, via this
    project's own `raise SystemExit(...)` CLI convention). A sidecar
    that positively reports frames == 0 still comes back as a dict, with
    frames == 0 in it, for the caller to act on."""
    meta_path = tmp_path / 'run_tlm.meta.json'
    meta_path.write_text(json.dumps({
        'frames': 0, 'dropped': 0, 'loss_pct': 0.0, 'orphan_frames': 0,
        'malformed': 0, 'columns': [], 'duration': 0.0,
    }))
    pose_csv = tmp_path / 'run_pose.csv'

    meta = tlm.read_meta_sidecar(str(pose_csv))

    assert meta is not None
    assert meta['frames'] == 0


# --- sprint 034 ticket 004: the pose-CSV codec ---------------------------
# `write_pose_csv()`/`read_pose_csv()` -- ONE on-disk pose schema, bound
# by column NAME.
#
# The defect being pinned against: three tools wrote three pose-CSV
# schemas (wire units; cm/deg; cm/deg + wheel speeds) and `tour_chart.py`
# chose its reader by COUNTING COLUMNS while assuming wire units. The
# cm/deg schema also has eight columns, so it was accepted and plotted
# 10x too small, heading divided by 100, OTOS series read off the wrong
# columns, under a confident "closure N mm" title -- and nothing raised.
# Every test below is written to fail if that behaviour comes back:
# `test_legacy_tour_watch_header_is_converted_not_silently_mis_scaled`
# asserts the ACTUAL numbers, and asserts against the 1/10-scale figure
# by name; `test_read_pose_csv_binds_by_name_not_position` shuffles the
# header so a positional reader cannot pass it; and the consumer tests
# at the end assert the tools route through this codec rather than
# re-deriving the schema.

def _frame(seq, x, y, h, ox=0, oy=0, oh=0, vl=0, vr=0, now=None):
    """One decoded-telemetry-frame-shaped dict, the exact shape
    `TlmStream.feed()` returns and `write_pose_csv()` takes. Carries
    `seq`/`flags`/`i2cf` too, so the "extra frame keys are ignored, not
    written" contract is exercised by every writer test rather than by
    one special case."""
    return {'seq': seq, 'now': 1000 + seq * 50 if now is None else now,
            'flags': 0x31, 'x': x, 'y': y, 'h': h,
            'ox': ox, 'oy': oy, 'oh': oh, 'vl': vl, 'vr': vr, 'i2cf': 0}


def _header_of(path):
    with open(path, newline='') as f:
        return next(csv.reader(f))


def test_write_pose_csv_writes_the_one_wire_unit_header(tmp_path):
    """The surviving schema is `tour_capture.py`'s -- wire units, one
    column per wire quantity, no cm/deg anywhere."""
    path = tmp_path / 'run_pose.csv'

    n = tlm.write_pose_csv([dict(_frame(1, 500, -300, 1234), t_host=0.5)],
                           str(path))

    assert n == 1
    assert _header_of(path) == list(tlm.POSE_CSV_COLUMNS)
    assert _header_of(path) == ['t_host', 't_dev_ms', 'x_mm', 'y_mm',
                                'h_cdeg', 'ox_mm', 'oy_mm', 'oh_cdeg']


def test_pose_csv_round_trip_preserves_wire_units_exactly(tmp_path):
    """Write frames, read them back: same numbers, same units, in the
    same frame shape `pose_cm()`/`otos_cm()` already take -- so the CSV
    path reuses this module's scale factors instead of growing a second
    set of its own."""
    path = tmp_path / 'run_pose.csv'
    frames = [dict(_frame(1, 500, -300, 1234, 10, 20, 500), t_host=0.5),
              dict(_frame(2, 505, -299, 1240, 11, 21, 505), t_host=0.55)]

    tlm.write_pose_csv(frames, str(path))
    rows, schema = tlm.read_pose_csv(str(path))

    assert schema == tlm.POSE_CSV_SCHEMA
    assert [r['x'] for r in rows] == [500, 505]
    assert [r['y'] for r in rows] == [-300, -299]
    assert [r['h'] for r in rows] == [1234, 1240]
    assert [r['ox'] for r in rows] == [10, 11]
    assert [r['oh'] for r in rows] == [500, 505]
    assert [r['now'] for r in rows] == [1050, 1100]
    assert rows[0]['t_host'] == pytest.approx(0.5)
    # ...and the unit helpers apply to a CSV row exactly as to a frame
    assert tlm.pose_cm(rows[0])['x'] == pytest.approx(50.0)
    assert tlm.otos_cm(rows[0])['h'] == pytest.approx(5.0)


def test_pose_csv_round_trip_with_the_optional_wheel_pair(tmp_path):
    """`wheels=True` appends `vl_mms,vr_mms` -- the recorder that plots
    the frame's own wheel speeds (`tour_practice.py`) keeps them, and
    they come back under the frame's own vl/vr keys."""
    path = tmp_path / 'run_pose.csv'
    frames = [dict(_frame(1, 500, -300, 1234, vl=-122, vr=126),
                   t_host=0.5)]

    tlm.write_pose_csv(frames, str(path), wheels=True)
    rows, _schema = tlm.read_pose_csv(str(path))

    assert _header_of(path)[-2:] == ['vl_mms', 'vr_mms']
    assert tlm.wheels_mms(rows[0]) == {'vl': -122, 'vr': 126}


def test_pose_csv_without_the_wheel_pair_reports_it_absent(tmp_path):
    """Optional means optional: a file written without the pair comes
    back WITHOUT vl/vr keys, so a chart can tell "no wheel-speed data"
    from "wheel speeds that happened to be zero" -- never a fabricated
    flat line at 0."""
    path = tmp_path / 'run_pose.csv'
    tlm.write_pose_csv([dict(_frame(1, 1, 2, 3), t_host=0.1)], str(path))

    rows, _schema = tlm.read_pose_csv(str(path))

    assert 'vl' not in rows[0] and 'vr' not in rows[0]


def test_write_pose_csv_ignores_extra_frame_keys(tmp_path):
    """A FULL-header frame carries eight more columns than a pose CSV
    has; they are dropped, not written into a wider file that would
    then disagree with the schema every reader binds against."""
    frame = dict(_frame(1, 1, 2, 3), t_host=0.1, cyc=101, posl=286,
                 dutl=-1300)
    path = tmp_path / 'run_pose.csv'

    tlm.write_pose_csv([frame], str(path))

    assert _header_of(path) == list(tlm.POSE_CSV_COLUMNS)


def test_write_pose_csv_refuses_a_row_missing_a_required_key(tmp_path):
    """Fail loud, in write_tlm_csv()'s style: a blank cell would read
    downstream as a real zero, so the row is refused by name instead."""
    frame = dict(_frame(1, 1, 2, 3), t_host=0.1)
    del frame['oh']
    path = tmp_path / 'run_pose.csv'

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.write_pose_csv([frame], str(path))

    assert "'oh'" in str(e.value) and 'oh_cdeg' in str(e.value)


def test_write_pose_csv_zero_rows_is_a_header_only_file_not_a_raise(
        tmp_path):
    """Deliberately NOT write_tlm_csv()'s zero-frame refusal: this file
    is a derived view of a stream whose emptiness that guard (and the
    `.meta.json` sidecar read back by read_meta_sidecar()) already
    refuses loudly, in one place. Duplicating the refusal here would
    give one run two different "no data" errors."""
    path = tmp_path / 'run_pose.csv'

    assert tlm.write_pose_csv([], str(path)) == 0
    assert _header_of(path) == list(tlm.POSE_CSV_COLUMNS)
    assert tlm.read_pose_csv(str(path)) == ([], tlm.POSE_CSV_SCHEMA)


def test_read_pose_csv_binds_by_name_not_position(tmp_path):
    """The whole point of the ticket. The header below carries the
    required columns in a SHUFFLED order: a reader that binds by
    position (or by counting columns) reads x out of the h column and
    passes anyway; only a name-bound reader gets these numbers right."""
    path = tmp_path / 'shuffled_pose.csv'
    path.write_text(
        'h_cdeg,x_mm,oh_cdeg,t_dev_ms,ox_mm,y_mm,oy_mm,t_host\n'
        '1234,500,500,1050,10,-300,20,0.5\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert schema == tlm.POSE_CSV_SCHEMA
    assert rows[0]['x'] == 500
    assert rows[0]['y'] == -300
    assert rows[0]['h'] == 1234
    assert rows[0]['ox'] == 10 and rows[0]['oy'] == 20
    assert rows[0]['oh'] == 500


def test_read_pose_csv_ignores_an_unrecognised_extra_column(tmp_path):
    """A complete required set plus one column this codec does not know
    is READ, with the extra ignored -- the same "a new column is handled
    for free" property TlmStream's header binding already has. It is an
    unknown HEADER (nothing to bind), not an unknown extra, that is
    refused."""
    path = tmp_path / 'extra_pose.csv'
    path.write_text(
        ','.join(tlm.POSE_CSV_COLUMNS) + ',battery_mv\n'
        '0.5,1050,500,-300,1234,10,20,500,7400\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert schema == tlm.POSE_CSV_SCHEMA
    assert rows[0]['x'] == 500
    assert 'battery_mv' not in rows[0]


# --- the regression that motivates the ticket ----------------------------

#: `tour_watch.py`'s pre-ticket-004 header: eight columns, like the
#: wire-unit schema, but cm and degrees -- the file `tour_chart.py`'s
#: column-count branch accepted and plotted 10x too small.
_LEGACY_WATCH_HEADER = ('t,dev_ms,enc_x_cm,enc_y_cm,enc_h_deg,'
                        'otos_x_cm,otos_y_cm,otos_h_deg')

#: `tour_practice.py`'s pre-ticket-004 header: ten columns, cm/deg,
#: with the device clock in the EIGHTH position rather than the second.
_LEGACY_PRACTICE_HEADER = ('t,enc_x,enc_y,enc_h,otos_x,otos_y,otos_h,'
                           'dev_ms,vl_mms,vr_mms')


def test_legacy_tour_watch_header_is_converted_not_silently_mis_scaled(
        tmp_path):
    """A cm/degree capture written by the old `tour_watch.py`: 50.0 cm,
    -30.0 cm, 12.34 deg. It must come back as the wire integers a
    tour_capture recording of the same motion would have carried --
    500 mm, -300 mm, 1234 cdeg -- and explicitly NOT as 50/-30/12,
    which is the 1/10-and-1/100 mis-scale the column-count branch
    produced while plotting a confident closure figure."""
    path = tmp_path / '01-world_pose.csv'
    path.write_text(_LEGACY_WATCH_HEADER + '\n'
                    '0.5,1050,50.0,-30.0,12.34,1.0,2.0,5.0\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert 'tour_watch' in schema
    assert rows[0]['x'] == 500
    assert rows[0]['y'] == -300
    assert rows[0]['h'] == 1234
    assert rows[0]['ox'] == 10 and rows[0]['oy'] == 20
    assert rows[0]['oh'] == 500
    assert rows[0]['now'] == 1050
    # The defect, named: the cm/deg numbers must NOT survive as if they
    # were already wire units.
    assert rows[0]['x'] != 50
    assert rows[0]['h'] != 12
    # ...and the engineering-unit view agrees with the original capture
    assert tlm.pose_cm(rows[0])['x'] == pytest.approx(50.0)
    assert tlm.pose_cm(rows[0])['h'] == pytest.approx(12.34)


def test_legacy_tour_practice_header_is_converted_including_wheels(
        tmp_path):
    """The ten-column legacy schema, whose device clock sits in the
    EIGHTH column -- a reader that assumed the wire schema's positions
    would read `dev_ms` as an OTOS heading. Wheel speeds were already
    mm/s there and pass through unscaled."""
    path = tmp_path / 'robot-run1_pose.csv'
    path.write_text(_LEGACY_PRACTICE_HEADER + '\n'
                    '0.5,50.0,-30.0,12.34,1.0,2.0,5.0,1050,-122.0,126.0\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert 'tour_practice' in schema
    assert rows[0]['x'] == 500 and rows[0]['h'] == 1234
    assert rows[0]['now'] == 1050
    assert rows[0]['oh'] == 500
    assert tlm.wheels_mms(rows[0]) == {'vl': -122, 'vr': 126}


def test_unknown_header_is_refused_naming_the_file_and_the_header(
        tmp_path):
    """An unrecognised header is refused, not guessed at -- and the
    message names the file and what it found, so the operator is not
    sent hunting for a camera or a robot fault."""
    path = tmp_path / 'mystery_pose.csv'
    path.write_text('t,x,y,h\n0.5,1.0,2.0,3.0\n')

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.read_pose_csv(str(path))

    message = str(e.value)
    assert 'mystery_pose.csv' in message
    assert 't,x,y,h' in message
    assert 'x_mm' in message          # the schema it expected


def test_empty_file_is_refused_naming_the_file(tmp_path):
    """No header at all: there is no schema to bind to, so this is a
    refusal, not an empty list that reads downstream as a real run that
    recorded nothing."""
    path = tmp_path / 'empty_pose.csv'
    path.write_text('')

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.read_pose_csv(str(path))

    assert 'empty_pose.csv' in str(e.value)


def test_a_blank_cell_is_refused_naming_the_row_and_column(tmp_path):
    """A blank cell would read downstream as a real zero -- a robot
    parked at the origin, or an OTOS reporting nothing."""
    path = tmp_path / 'holes_pose.csv'
    path.write_text(','.join(tlm.POSE_CSV_COLUMNS) + '\n'
                    '0.5,1050,500,-300,1234,10,20,\n')

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.read_pose_csv(str(path))

    assert 'oh_cdeg' in str(e.value) and 'holes_pose.csv' in str(e.value)


def test_a_non_numeric_cell_is_refused_naming_the_value(tmp_path):
    path = tmp_path / 'junk_pose.csv'
    path.write_text(','.join(tlm.POSE_CSV_COLUMNS) + '\n'
                    '0.5,1050,nan_x,-300,1234,10,20,500\n')

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.read_pose_csv(str(path))

    assert 'nan_x' in str(e.value) and 'x_mm' in str(e.value)


# --- the consumers actually route through the codec ----------------------
# Text-level, deliberately: `tour_chart.py` and `practice_chart.py`
# import matplotlib at module scope and this project's test venv has no
# matplotlib (it is supplied per-run by `uv run --with matplotlib`), so
# importing them here is not available -- the same constraint
# `tests/tools/test_travel_calib_drift.py` already works within. What
# these can still prove is the thing that was silently false before:
# that no tool re-derives the pose-CSV schema for itself.

def _tool_source(name):
    return (_TOOLS_DIR / name).read_text()


def _tool_code(name):
    """`_tool_source()` with whole-line comments dropped.

    Needed because the tools DOCUMENT the schema defect they were
    migrated off -- `tour_chart.py`'s replacement comment quotes the
    deleted `len(pose_all[0]) >= 5` branch by name, which is exactly the
    kind of "why this is not here any more" note this repo wants kept.
    A guard that cannot tell a citation from a live call would force
    that note to be deleted to stay green."""
    return '\n'.join(line for line in _tool_source(name).splitlines()
                     if not line.lstrip().startswith('#'))


@pytest.mark.parametrize('name', ['tour_capture.py', 'tour_watch.py',
                                  'tour_practice.py'])
def test_every_pose_csv_writer_writes_through_the_codec(name):
    source = _tool_source(name)

    assert 'tlm.write_pose_csv(' in source
    # None of the three legacy headers may be written from a tool again
    for column in ('enc_x_cm', 'otos_h_deg', "'enc_x'", "'otos_h'"):
        assert column not in source


@pytest.mark.parametrize('name', ['tour_chart.py', 'practice_chart.py',
                                  'leg_analysis.py'])
def test_every_pose_csv_reader_reads_through_the_codec(name):
    source = _tool_source(name)

    assert 'tlm.read_pose_csv(' in source
    # ...and no reader restates the schema's column names for itself
    assert "'x_mm'" not in source and "'h_cdeg'" not in source


def test_tour_chart_has_no_column_count_branch_left():
    """The specific line that accepted a cm/degree CSV: `if pose_all and
    len(pose_all[0]) >= 5:` / `wide = len(pose_all[0]) >= 8`."""
    code = _tool_code('tour_chart.py')

    assert 'len(pose_all[0])' not in code
    assert 'wide' not in code


def test_tour_chart_meta_start_world_heading_is_documented_degrees():
    """TL-17: `--meta`'s `start_world_cm[2]` had no documented unit and
    was consumed as radians, while every camera sample in this repo is
    `yaw_deg`. One unit, converted in the code, stated in --help."""
    source = _tool_source('tour_chart.py')

    assert 'math.radians(sw[2])' in source
    assert 'heading_DEG' in source        # the --help text


def test_legacy_tour_practice_header_without_the_wheel_pair_still_reads(
        tmp_path):
    """The same recorder wrote with and without wheel speeds (both
    shapes exist in this tree's own `.tmp/` recordings). The wheel pair
    is OPTIONAL in the legacy entry too, so one entry reads both --
    otherwise the eight-column recordings would be refused for want of
    two columns nothing in the pose track needs."""
    path = tmp_path / 'nowheels_pose.csv'
    path.write_text('t,enc_x,enc_y,enc_h,otos_x,otos_y,otos_h,dev_ms\n'
                    '0.5,50.0,-30.0,12.34,1.0,2.0,5.0,1050\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert 'tour_practice' in schema
    assert rows[0]['x'] == 500 and rows[0]['now'] == 1050
    assert 'vl' not in rows[0]


def test_legacy_tour_practice_cm_per_second_wheels_are_scaled_to_mm(
        tmp_path):
    """An older spelling of the same pair: `vl_cms`/`vr_cms`, in cm/s.
    Read as mm/s it would be a 10x under-report on the wheel-speed
    panel -- the same class of silent mis-scale as the pose columns."""
    path = tmp_path / 'cms_pose.csv'
    path.write_text(
        't,enc_x,enc_y,enc_h,otos_x,otos_y,otos_h,dev_ms,vl_cms,vr_cms\n'
        '0.5,50.0,-30.0,12.34,1.0,2.0,5.0,1050,15.0,15.0\n')

    rows, _schema = tlm.read_pose_csv(str(path))

    assert tlm.wheels_mms(rows[0]) == {'vl': 150, 'vr': 150}


def test_legacy_unsuffixed_otos_columns_are_read_as_wire_units(tmp_path):
    """The variant that actually sits in this repo's `captures/`:
    `t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox,oy,oh` -- already wire units,
    only the OTOS column NAMES differ. A name-bound reader converts it
    by renaming, with no scale factor at all; refusing it would have
    cost seven recorded runs for a suffix."""
    path = tmp_path / 'unsuffixed_pose.csv'
    path.write_text('t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox,oy,oh\n'
                    '0.5,1050,500,-300,1234,10,20,500\n')

    rows, schema = tlm.read_pose_csv(str(path))

    assert 'unsuffixed' in schema
    assert rows[0]['x'] == 500 and rows[0]['h'] == 1234
    assert rows[0]['ox'] == 10 and rows[0]['oh'] == 500


def test_the_pre_otos_five_column_header_is_refused_not_zero_filled(
        tmp_path):
    """`t_host,t_dev_ms,x_mm,y_mm,h_cdeg`, written before the OTOS
    columns existed. Its OTOS quantities are ABSENT, not zero; filling
    them in would draw a sensor that said nothing as a boundary fix at
    the world origin. Refused, naming the file -- the outcome ticket
    004 permits for a header the codec will not convert."""
    path = tmp_path / 'preotos_pose.csv'
    path.write_text('t_host,t_dev_ms,x_mm,y_mm,h_cdeg\n'
                    '0.5,1050,500,-300,1234\n')

    with pytest.raises(tlm.PoseCsvSchemaError) as e:
        tlm.read_pose_csv(str(path))

    assert 'preotos_pose.csv' in str(e.value)
