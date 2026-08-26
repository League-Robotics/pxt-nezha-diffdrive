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

# The reliability keepalive -- streams continuously at 50 ms and is NOT
# telemetry (this ticket's own framing). Shape from wire_handler.cpp's
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
