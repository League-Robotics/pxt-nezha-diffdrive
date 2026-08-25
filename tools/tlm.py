"""tools/tlm.py -- the single v6 telemetry parser, plus the three
fail-loud guards that make "the instrument returned nothing" a loud,
immediate failure instead of a silent empty CSV.

Six tools (`tour_run.py`, `tour_capture.py`, `tour_watch.py`,
`truth_check.py`, `rotation_check.py`, `tour_practice.py`) used to each
parse the retired v5 `TLM:` cleartext line with their own scattered
arity check and scale factor. Two of them were already silently dead
-- `tour_watch.py:202` and `tour_capture.py:70` both hard-coded field
counts that stopped matching the wire line when `vl`/`vr` were added,
and the failure mode was an empty CSV, not a crash. This module is the
fix: ONE place a v6 wire column is decoded and ONE place any
wire-to-engineering-unit scale factor is written. No consumer is
retrofitted here (that is sprint 005 ticket 002's job) -- this module
is only imported.

Wire shape (protocol.md S5.2, confirmed against real hardware --
tovez, 2026-08-24, see
clasi/issues/retrofit-bench-tooling-onto-the-v6-telemetry-stream.md's
"Bench confirmation" and "Realistic-value capture" sections):

    thdr <col> <col> ...          -- column header, re-emitted by
                                      firmware every kHeaderRefreshFrames
                                      (20) frames, ~1 Hz at the 20 Hz
                                      frame rate
    t <val> <val> ...             -- one telemetry frame, values in the
                                      header's column order

Two column sets exist and can appear in the SAME capture:

    POSE (12 cols): seq now flags x y h ox oy oh vl vr i2cf
    FULL (20 cols): seq now flags x y h ox oy oh vl vr i2cf cyc posl
                    posr dutl dutr lexc wrng cycovr

`TlmStream` binds every column by NAME from the most recently seen
`thdr` line -- never by a fixed index or position -- so a mid-stream
switch between the two (or a firmware upgrade that adds a column) is
handled for free.

Measured line widths, real hardware: POSE thdr 44 B / idle `t` 29 B;
FULL thdr 85 B / live `t` 75 B (flags=31 hex, vl=-122, dutl=-1300, all
real non-zero magnitudes). The host test suite's own predicted
worst-case FULL `t` line is 138 B; `RadioTransport::kMaxPayloadBytes`
is 200 B. `TlmStream.feed()` imposes no line-length ceiling of its own
-- a legitimate line anywhere under the 200 B radio cap is never
rejected for its length; a line truncated by the radio layer is caught
by the arity check below instead (a truncated line has too few
values, not merely a long one).

`ox`/`oy`/`oh` are legitimately 0 on any OTOS-less robot (most of the
fleet, tovez included) -- this module never treats a zero OTOS column
as missing data or a fault; it is just a valid integer like any other.

The reliability keepalive (`ack <n> <lastDone> <reason>`, streamed
continuously at 50 ms) and its `nack` counterpart are NOT telemetry.
`TlmStream.feed()` only recognizes the `thdr`/`t` tags; every other
line (including `ack`/`nack`, and any other STATUS/VER/GET/err reply
sharing the same link) is silently ignored -- `feed()` returns None for
it, uncounted anywhere. This is deliberate filtering, not a gap: a
caller that only speaks `feed()` never has to know the reliability
line's own shape.

Import `TlmStream`, `require_stream()`, `write_tlm_csv()`,
`read_meta_sidecar()` (sprint 005 ticket 002's read-side zero-frame
guard for chart tools that did not capture the run they plot), and the
`pose_cm()`/`otos_cm()`/`wheels_mms()` helpers. See tools/DESIGN.md's
"Telemetry (tlm.py)" section for the module's place in the bench
tooling architecture.
"""
import csv
import json
import pathlib


# --- wire-format constants --------------------------------------------

# seq_ wraps (seq_ + 1) & 0x7F -- src/wire_adapter.cpp:580. A 7-bit
# counter at the 20 Hz frame rate is unambiguous up to (128 / 20) =
# 6.4 s of continuous loss; anything longer aliases as a smaller gap
# (or none), a known limitation of a 7-bit counter, not a bug here.
SEQ_MODULUS = 128

# The ONLY column emitted in hex on the wire. Mirrors
# wire_adapter.cpp's buildSnapshot(): every Column is constructed with
# an explicit `hex` flag, and "flags" is the one call site that passes
# `true` -- every other column (including i2cf, and the signed
# duty-cycle/encoder columns) passes `false` and prints plain signed
# base-10 (wire_handler.cpp's emitFrame(): `"%x"` for hex columns,
# `"%ld"` for everything else). This is a wire-format constant fixed by
# the firmware's own emitter, not a per-capture guess -- column
# BINDING is still entirely by name (see TlmStream.feed()); this only
# says how to read the one column whose text is hex instead of decimal.
_HEX_COLUMNS = frozenset({'flags'})


class TlmError(RuntimeError):
    """Base class for tlm.py's fail-loud guard failures."""


class DeadTelemetryError(TlmError):
    """require_stream() found no `t` frame before its timeout."""


class EmptyCaptureError(TlmError):
    """write_tlm_csv() was asked to write zero accumulated frames."""


class TlmStream:
    """Decodes `thdr`/`t` lines against the most recently seen header.

    Public, read-only-in-spirit state (nothing here stops a caller from
    mutating it, but nothing in this module ever needs to):

        columns          -- list[str] | None: the current header's
                             column names, in wire order; None before
                             any `thdr` has been fed.
        frames            -- list[dict[str, int]]: every successfully
                             decoded `t` frame, in arrival order.
        orphan_frames     -- int: `t` frames that arrived before any
                             `thdr` was ever fed. A real, expected state
                             (a late-attaching consumer misses the
                             firmware's periodic re-emit window), not an
                             error -- counted, not raised.
        malformed         -- int: `t` frames whose value count disagreed
                             with the current header's column count (the
                             defense against RadioTransport's 200-byte
                             line truncation), OR whose values failed to
                             parse as integers even though the count
                             matched (a corrupted-but-right-length line
                             gets the same treatment -- both are "this
                             frame cannot be trusted", not two different
                             failure classes a caller has to know
                             about).
        dropped           -- int: frames inferred lost from `seq` gaps
                             between consecutive DECODED frames (orphan/
                             malformed frames do not carry a trustworthy
                             `seq`, so they are not used for gap math).
    """

    def __init__(self):
        self.columns = None
        self.frames = []
        self.orphan_frames = 0
        self.malformed = 0
        self.dropped = 0
        self._last_seq = None

    @property
    def loss_pct(self):
        """Percent of (received + inferred-dropped) frames lost.

        0.0 with nothing accumulated yet -- never a divide-by-zero, and
        never mistaken for "100% loss" (an absent/zero-frame capture is
        write_tlm_csv()'s job to refuse loudly, not this property's job
        to flag).
        """
        total = len(self.frames) + self.dropped
        if total == 0:
            return 0.0
        return 100.0 * self.dropped / total

    @property
    def duration(self):
        """Seconds spanned by accumulated frames, from the wire's own
        device-clock `now` column (milliseconds) -- deliberately NOT
        host wall-clock time, so a slow test or a slow host never
        inflates a run's reported duration, and a replayed/synthetic
        capture (no real elapsed wall time at all) still reports a
        meaningful figure. 0.0 with fewer than two frames.
        """
        if len(self.frames) < 2:
            return 0.0
        first_now = self.frames[0].get('now')
        last_now = self.frames[-1].get('now')
        if first_now is None or last_now is None:
            return 0.0
        return max(0.0, (last_now - first_now) / 1000.0)

    def feed(self, line):
        """Decode one line. Returns the decoded `t`-frame dict on a
        successfully parsed frame, or None for anything else (a
        `thdr` line, an orphan/malformed `t`, or a non-telemetry line
        such as `ack`/`nack`/a command reply sharing the link).

        Never raises -- a malformed or out-of-order line is a counted,
        expected wire condition here, not a parse-time exception. Fail
        loud is require_stream()'s and write_tlm_csv()'s job, once a
        whole capture's worth of these counts is in.
        """
        line = line.strip()
        if not line:
            return None
        parts = line.split()
        tag = parts[0]
        if tag == 'thdr':
            self._feed_header(parts[1:])
            return None
        if tag == 't':
            return self._feed_frame(parts[1:])
        return None  # ack/nack/status/etc. -- not telemetry

    def _feed_header(self, names):
        # Re-feeding an identical header (same names, same order) is a
        # no-op: `columns` keeps its existing identity and nothing else
        # about this stream's state changes. Comparing the parsed name
        # list (not the raw line text) means two headers that differ
        # only in incidental whitespace still count as identical, and
        # a genuinely different column set (a POSE<->FULL mid-stream
        # switch) is always detected, regardless of how the previous
        # header happened to be spaced.
        if self.columns is not None and names == self.columns:
            return
        self.columns = list(names)

    def _feed_frame(self, values):
        if self.columns is None:
            self.orphan_frames += 1
            return None
        if len(values) != len(self.columns):
            self.malformed += 1
            return None
        row = {}
        try:
            for name, raw in zip(self.columns, values):
                row[name] = int(raw, 16) if name in _HEX_COLUMNS else int(raw)
        except ValueError:
            self.malformed += 1
            return None
        if 'seq' in row:
            self._track_seq(row['seq'])
        self.frames.append(row)
        return row

    def _track_seq(self, seq):
        if self._last_seq is not None:
            # Frames arriving with `delta == 1` are the normal
            # back-to-back case (zero loss). A `delta` of N > 1 means
            # N-1 frames were never seen. Modulo arithmetic means a
            # wraparound from 127 back to 0 computes `delta == 1`
            # exactly like any other consecutive pair -- it is NOT
            # miscounted as a 127-frame gap.
            delta = (seq - self._last_seq) % SEQ_MODULUS
            if delta > 1:
                self.dropped += delta - 1
        self._last_seq = seq


# --- unit-conversion helpers --------------------------------------------
# The only place any wire -> engineering-unit scale factor is written.
# Wire units, confirmed against src/wire_adapter.cpp's buildSnapshot()
# and tests/host/golden_telemetry.py:
#   x, y, ox, oy   -- already millimetres (poseX()/poseY() are [mm];
#                     otosGet() is 0.1 mm and buildSnapshot() itself
#                     divides by 10 before it ever reaches the wire)
#   h, oh          -- centidegrees (poseHeading() is [cdeg]; otosGet(2)
#                     is already centidegrees)
#   vl, vr         -- already millimetres/second (wheelSpeed() is
#                     [mm/s], passed straight through with no scaling)

def pose_cm(row):
    """Encoder-odometry pose from a decoded frame, in (cm, cm, deg)."""
    return {'x': row['x'] / 10.0, 'y': row['y'] / 10.0, 'h': row['h'] / 100.0}


def otos_cm(row):
    """OTOS pose from a decoded frame, in (cm, cm, deg).

    Legitimately (0.0, 0.0, 0.0) on a robot with no OTOS fitted --
    that is correct data, not a fault; see this module's docstring.
    """
    return {'x': row['ox'] / 10.0, 'y': row['oy'] / 10.0,
            'h': row['oh'] / 100.0}


def wheels_mms(row):
    """Wheel speeds from a decoded frame, in mm/s.

    The wire already carries mm/s (wheelSpeed()'s own unit) -- this
    function's scale factor is 1:1 today, kept as a real function
    rather than inlined `row['vl']` at each call site so this stays the
    one place that fact is asserted, in case the wire contract ever
    changes.
    """
    return {'vl': row['vl'], 'vr': row['vr']}


# --- fail-loud guard 1: a dead instrument must not cost a run -----------

def require_stream(link, timeout=3.0, stream=None):
    """Subscribe to POSE telemetry and block until a `t` frame arrives.

    Sends `TLM POSE` once, then reads `link.lines(timeout)` (the same
    send()/lines() surface `robotlink.Link` and this ticket's test
    fake both expose) until a `t` line decodes into a real frame, or
    the timeout is exhausted. Raises DeadTelemetryError immediately on
    timeout -- BEFORE the caller's very next step, which is always a
    run-triggering command (SUC-001: a dead instrument must not cost a
    run). The reliability keepalive (`ack`/`nack`, streamed
    continuously) never satisfies this wait -- feed() does not count it
    as a frame, so a link that is alive but has no working telemetry
    still raises, exactly as it should.

    `stream`, if given, is the TlmStream to feed and return -- so a
    caller can pass the SAME stream it will keep feeding for the rest
    of the run, and the liveness-check frame(s) count toward that run's
    own `frames`/`dropped` totals instead of being thrown away. Omit it
    to get a fresh, throwaway stream (what this ticket's own tests do).

    Returns the stream (fresh or passed-in) on success, already primed
    with at least one decoded frame.
    """
    if stream is None:
        stream = TlmStream()
    link.send('TLM POSE')
    for line in link.lines(timeout):
        if stream.feed(line) is not None:
            return stream
    raise DeadTelemetryError(
        'no telemetry frame within {timeout}s of the TLM POSE subscribe '
        '-- instrument is dead; aborting before any run is triggered'
        .format(timeout=timeout))


# --- fail-loud guard 2 & 3: never write a header-only CSV ---------------

def write_tlm_csv(stream, path):
    """Write `stream.frames` to `path` as CSV, plus a `.meta.json`
    capture-quality sidecar next to it (path with its suffix swapped
    for `.meta.json` -- name the CSV `<stem>_tlm.csv` and the sidecar
    lands at `<stem>_tlm.meta.json`, matching this sprint's naming).

    Raises EmptyCaptureError, and writes NEITHER file, if `stream` has
    accumulated zero frames -- never a header-only CSV. An absent file
    is the unambiguous signal of "no data"; a CSV with a header row and
    nothing else looks like a real, if boring, successful run and is
    exactly the confident-wrong-conclusion failure mode this guard
    exists to prevent (SUC-002).

    The CSV's column set is the ORDERED UNION of every key seen across
    all accumulated frames, first-seen order -- almost always just
    `stream.columns`, but if the header changed mid-capture (a POSE<->
    FULL switch), every column any frame carried gets its own CSV
    column, with '' in the rows that did not have it, rather than
    silently dropping data from whichever schema wrote fewer columns.

    Returns the meta dict that was written to the sidecar, so a caller
    can print a loss report immediately without re-reading the file it
    just wrote.
    """
    if not stream.frames:
        raise EmptyCaptureError(
            'zero telemetry frames accumulated -- refusing to write {path} '
            '(orphan_frames={orphan}, malformed={malformed}); an absent '
            'file is the honest signal here, not a header-only CSV'
            .format(path=path, orphan=stream.orphan_frames,
                    malformed=stream.malformed))

    fieldnames = _ordered_union_columns(stream.frames)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval='')
        w.writeheader()
        for row in stream.frames:
            w.writerow(row)

    meta = {
        'frames': len(stream.frames),
        'dropped': stream.dropped,
        'loss_pct': stream.loss_pct,
        'orphan_frames': stream.orphan_frames,
        'malformed': stream.malformed,
        'columns': list(stream.columns) if stream.columns else [],
        'duration': stream.duration,
    }
    meta_path = _meta_path_for(path)
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
        f.write('\n')

    return meta


def _ordered_union_columns(frames):
    seen = []
    seen_set = set()
    for row in frames:
        for key in row:
            if key not in seen_set:
                seen_set.add(key)
                seen.append(key)
    return seen


def _meta_path_for(csv_path):
    return str(pathlib.Path(csv_path).with_suffix('.meta.json'))


# --- fail-loud guard, read side: chart tools that did not capture -------
# the run they are about to plot ------------------------------------------

def read_meta_sidecar(any_csv_path):
    """Read the `<stem>_tlm.meta.json` sidecar for the SAME capture run
    as `any_csv_path` -- any `<stem>_<suffix>.csv` this sprint's tools
    write for one run (`<stem>_pose.csv`, `<stem>_cam.csv`, ...), all
    sharing one stem with the `<stem>_tlm.csv` write_tlm_csv() itself
    wrote. Added in sprint 005 ticket 002 for tour_chart.py/
    practice_chart.py: those tools plot a run's CSVs without being the
    ones that captured them, so they cannot call write_tlm_csv()'s own
    write-time guard -- this is the same "refuse to represent absent
    data as a real result" contract, applied at READ time, with the
    sidecar-naming knowledge kept in this one module rather than
    duplicated into two chart tools.

    Returns the parsed meta dict, or None if no sidecar exists at the
    derived path -- an older capture, or one from a source that never
    wrote one. Absence here is NOT itself an error; it is the caller's
    job to decide whether "no sidecar to check against" is fine (plot
    anyway) or should itself refuse. A sidecar that DOES exist and
    reports `frames == 0` is for the caller to act on (typically
    `raise SystemExit(...)`, this project's own CLI error convention)
    -- this function only reads and returns, it never raises on the
    caller's behalf.
    """
    p = pathlib.Path(any_csv_path)
    name = p.stem  # strips the .csv extension
    stem = name.rsplit('_', 1)[0] if '_' in name else name
    meta_path = p.with_name(stem + '_tlm.meta.json')
    if not meta_path.exists():
        return None
    with open(meta_path) as f:
        return json.load(f)
