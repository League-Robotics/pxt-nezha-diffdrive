"""v6 telemetry parser. `thdr` binds columns by name; `t` rows decode
against the last header. Wire units: x/y/ox/oy mm; h/oh centideg;
vl/vr mm/s; dutl/dutr percent x100.

The single place a v6 wire column is decoded and the single place a
wire-to-engineering-unit scale factor is written, plus three fail-loud
guards that make "the instrument returned nothing" an immediate
failure instead of a silent empty CSV.

Wire shape (protocol.md S5.2):

    thdr <col> <col> ...          -- column header, re-emitted every
                                     kHeaderRefreshFrames (20) frames,
                                     ~1 Hz at the 20 Hz frame rate
    t <val> <val> ...             -- one frame, in the header's order

Two column sets exist and can appear in the SAME capture:

    POSE (12 cols): seq now flags x y h ox oy oh vl vr i2cf
    FULL (20 cols): seq now flags x y h ox oy oh vl vr i2cf cyc posl
                    posr dutl dutr lexc wrng cycovr

Binding by NAME rather than by index is what makes a mid-stream switch
between the two -- or a firmware upgrade that adds a column -- free.

MEASURED tovez 2026-08-24, line widths on real hardware (see
clasi/issues/retrofit-bench-tooling-onto-the-v6-telemetry-stream.md's
"Bench confirmation" and "Realistic-value capture" sections): POSE
thdr 44 B / idle `t` 29 B; FULL thdr 85 B / live `t` 75 B (flags=31
hex, vl=-122, dutl=-1300, all real non-zero magnitudes). The host
suite's predicted worst-case FULL `t` line is 138 B and
`RadioTransport::kMaxPayloadBytes` is 200 B, so `TlmStream.feed()`
imposes no line-length ceiling of its own: a legitimate line under the
radio cap is never rejected for its length, and a line the radio layer
truncated is caught by the arity check instead (too few values, not
merely a long line).

`ox`/`oy`/`oh` are legitimately 0 on any OTOS-less robot (most of the
fleet, tovez included). A zero OTOS column is valid data, never
missing data and never a fault.

`feed()` recognises only the `thdr`/`t` tags. Every other line sharing
the link -- `ack`/`nack`, STATUS, VER, GET, err -- returns None and is
counted nowhere. That is deliberate filtering, not a gap: a caller
that only speaks `feed()` never has to know the reliability line's
shape.

Import `TlmStream`, `require_stream()`, `write_tlm_csv()`,
`read_meta_sidecar()`, `write_pose_csv()`/`read_pose_csv()` (the one
header-keyed on-disk pose schema -- see the pose-CSV codec section at
the foot of this module), and the
`pose_cm()`/`otos_cm()`/`wheels_mms()`/`duty_pct()` converters. See
tools/DESIGN.md's "Telemetry (`tlm.py`)" section for this module's
place in the bench tooling architecture.
"""
import csv
import json
import pathlib


# --- wire-format constants --------------------------------------------

# seq_ wraps (seq_ + 1) & 0x7F -- src/comms/wire_adapter.cpp:580. A 7-bit
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
# Wire units, confirmed against src/comms/wire_adapter.cpp's buildSnapshot()
# and tests/host/golden_telemetry.py:
#   x, y, ox, oy   -- already millimetres (poseX()/poseY() are [mm];
#                     otosGet() is 0.1 mm and buildSnapshot() itself
#                     divides by 10 before it ever reaches the wire)
#   h, oh          -- centidegrees (poseHeading() is [cdeg]; otosGet(2)
#                     is already centidegrees)
#   vl, vr         -- already millimetres/second (wheelSpeed() is
#                     [mm/s], passed straight through with no scaling)
#   dutl, dutr     -- percent, multiplied by 100 TWICE over:
#                     NezhaMotorPort::appliedDuty() is a fraction
#                     [-1, 1]; diffdrive.cpp multiplies by 100 to
#                     publish Output.appliedDutyLeft/Right as PERCENT
#                     (diffdrive.h's own [%] doc); shims.cpp's
#                     diagValue(12)/(13) multiplies by 100 AGAIN before
#                     the wire. So probe(12)/dutl reads 10000 at 100%
#                     duty, not 100 -- see duty_pct() below, the one
#                     place that scale is undone.

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


def duty_pct(row):
    """Applied motor duty from a decoded frame, in true percent
    (-100 to 100).

    The wire's dutl/dutr columns are percent multiplied by 100 a SECOND
    time (see this module's header comment above for the full
    fraction -> percent -> wire chain) -- probe(12)/dutl reads 10000 at
    100% duty. This function divides that back down to true percent so
    every OTHER caller only has to reason about one scale, kept as a
    real function (rather than inlined `row['dutl'] / 100.0` at each
    call site) so this stays the one place that double-x100 fact is
    asserted, mirroring wheels_mms()'s own reasoning above.
    """
    return {'dutl': row['dutl'] / 100.0, 'dutr': row['dutr'] / 100.0}


# --- fail-loud guard 1: a dead instrument must not cost a run -----------

def require_stream(link, timeout=3.0, stream=None):
    """Subscribe to POSE telemetry and block until a `t` frame arrives.

    Sends `TLM POSE` once, then reads `link.lines(timeout)` (the same
    send()/lines() surface `robotlink.Link` and this ticket's test
    fake both expose) until a `t` line decodes into a real frame, or
    the timeout is exhausted. Raises DeadTelemetryError immediately on
    timeout -- BEFORE the caller's very next step, which is always a
    run-triggering command (SUC-001: a dead instrument must not cost a
    run). The reliability keepalive (`ack`/`nack`, a per-line reply,
    not a periodic broadcast -- sprint 024 ticket 001) never satisfies
    this wait -- feed() does not count it as a frame, so a link that is
    alive but has no working telemetry still raises, exactly as it
    should.

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


# --- the pose-CSV codec: ONE on-disk pose schema, bound by name ---------
# Sprint 034 ticket 004. Three tools used to write three different pose
# CSVs -- wire units (mm/centidegrees), cm/degrees, and cm/degrees plus
# wheel speeds -- and `tour_chart.py` picked its reader by COUNTING
# COLUMNS (`len(pose_all[0]) >= 5`, `>= 8`) while assuming wire units
# throughout. A cm/degree CSV happens to have eight columns too, so it
# was ACCEPTED: plotted 10x too small, heading divided by 100, the OTOS
# series read off the wrong columns, under a confident "closure N mm"
# title. Nothing raised.
#
# The fix is the rule this module already applies to the wire: bind
# every column BY NAME, never by position or by count, and refuse a
# header that is not recognised rather than guess at it.
#
# The surviving schema is `tour_capture.py`'s -- wire units, the wire's
# own quantities, one column per quantity:
#
#     t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg
#
# plus the OPTIONAL wheel-speed pair `vl_mms,vr_mms` for recorders that
# carry the frame's own vl/vr (`tour_practice.py`). Optional means
# optional to WRITE; nothing about reading changes, because the reader
# binds by name and simply reports the pair as absent.
#
# The CSV column names keep their `_mm`/`_cdeg`/`_mms` suffixes on
# purpose: `.claude/rules/no-units-in-identifiers.md` exempts wire field
# names, and the suffix is what makes this header self-describing to the
# reader that binds against it. Python identifiers in this section carry
# their unit in a trailing comment instead, per the same rule.

#: The required columns, in write order.
POSE_CSV_COLUMNS = ('t_host', 't_dev_ms', 'x_mm', 'y_mm', 'h_cdeg',
                    'ox_mm', 'oy_mm', 'oh_cdeg')

#: The optional wheel-speed pair, appended in this order when a
#: recorder asks for it (`write_pose_csv(..., wheels=True)`).
POSE_CSV_WHEEL_COLUMNS = ('vl_mms', 'vr_mms')

#: Schema name `read_pose_csv()` reports for the surviving schema.
POSE_CSV_SCHEMA = 'pose-csv wire units (mm, centidegrees, mm/s)'

# CSV column -> the key that quantity carries in a DECODED TELEMETRY
# FRAME (TlmStream.feed()'s own dict). This mapping is what lets a
# caller hand write_pose_csv() a frame straight off the stream, and lets
# read_pose_csv() hand a CSV row back in the shape pose_cm()/otos_cm()/
# wheels_mms() already take -- so the CSV path reuses this module's
# single set of scale factors instead of growing a second one.
# `t_host` is the exception: host arrival time is not a wire column at
# all, and it keeps its own name on both sides.
_POSE_CSV_FRAME_KEY = {
    't_host': 't_host',   # [s] host wall clock, not a wire column
    't_dev_ms': 'now',    # [ms] the device's own clock
    'x_mm': 'x', 'y_mm': 'y', 'h_cdeg': 'h',
    'ox_mm': 'ox', 'oy_mm': 'oy', 'oh_cdeg': 'oh',
    'vl_mms': 'vl', 'vr_mms': 'vr',
}

# The one frame key that is a real (fractional) time rather than an
# integer wire quantity -- see _pose_row_from_raw() for why the rest are
# read back as ints.
_POSE_CSV_REAL_KEYS = frozenset({'t_host'})

# The headers this repo's own tools wrote before ticket 004, each an
# entry of (name, required columns, plan, optional plans) where a plan
# maps a frame key to (source column, factor). Two of the three are
# cm/degrees, so their factors are the inverse of pose_cm()/otos_cm()'s
# -- written HERE, beside those, so this module stays the one place any
# wire <-> engineering-unit scale factor lives. An OPTIONAL plan is
# applied only when every column it names is present, which is how the
# same recorder's with-wheels and without-wheels recordings (and its
# cm/s and mm/s wheel spellings) are all read by one entry instead of
# one entry each.
#
# Headers surveyed off this working tree's own recordings, 2026-09-06,
# not invented: `captures/` carries the ox/oy/oh-unsuffixed wire-unit
# variant below, and `.tmp/` carries the with- and without-wheel
# cm/degree ones.
#
# One real historical shape is deliberately NOT converted: the
# five-column `t_host,t_dev_ms,x_mm,y_mm,h_cdeg` written before the OTOS
# columns existed. Its OTOS quantities are ABSENT, not zero, and
# fabricating them here would put a sensor that said nothing on a chart
# as a fix at the origin -- the exact "a series that was asked for and
# is absent must be labelled absent" failure `tour_chart.py` already
# guards against. It is refused, by name, like any other header this
# codec does not recognise.
_LEGACY_POSE_SCHEMAS = (
    (
        "tour_watch cm/deg "
        "(t,dev_ms,enc_*_cm,enc_h_deg,otos_*_cm,otos_h_deg)",
        ('t', 'dev_ms', 'enc_x_cm', 'enc_y_cm', 'enc_h_deg',
         'otos_x_cm', 'otos_y_cm', 'otos_h_deg'),
        {'t_host': ('t', 1.0), 'now': ('dev_ms', 1.0),
         'x': ('enc_x_cm', 10.0), 'y': ('enc_y_cm', 10.0),
         'h': ('enc_h_deg', 100.0),
         'ox': ('otos_x_cm', 10.0), 'oy': ('otos_y_cm', 10.0),
         'oh': ('otos_h_deg', 100.0)},
        (),
    ),
    (
        "tour_practice cm/deg (t,enc_*,otos_*,dev_ms[,vl_mms/vl_cms])",
        ('t', 'enc_x', 'enc_y', 'enc_h', 'otos_x', 'otos_y', 'otos_h',
         'dev_ms'),
        {'t_host': ('t', 1.0), 'now': ('dev_ms', 1.0),
         'x': ('enc_x', 10.0), 'y': ('enc_y', 10.0),
         'h': ('enc_h', 100.0),
         'ox': ('otos_x', 10.0), 'oy': ('otos_y', 10.0),
         'oh': ('otos_h', 100.0)},
        (
            {'vl': ('vl_mms', 1.0), 'vr': ('vr_mms', 1.0)},
            {'vl': ('vl_cms', 10.0), 'vr': ('vr_cms', 10.0)},
        ),
    ),
    (
        "tour_capture wire units, OTOS columns unsuffixed "
        "(t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox,oy,oh)",
        ('t_host', 't_dev_ms', 'x_mm', 'y_mm', 'h_cdeg', 'ox', 'oy', 'oh'),
        {'t_host': ('t_host', 1.0), 'now': ('t_dev_ms', 1.0),
         'x': ('x_mm', 1.0), 'y': ('y_mm', 1.0), 'h': ('h_cdeg', 1.0),
         'ox': ('ox', 1.0), 'oy': ('oy', 1.0), 'oh': ('oh', 1.0)},
        (),
    ),
)


class PoseCsvSchemaError(TlmError):
    """read_pose_csv() met a header it does not recognise, or a row it
    cannot decode; or write_pose_csv() was handed a row missing a
    column the schema requires."""


def write_pose_csv(rows, path, wheels: bool = False) -> int:
    """Write `rows` to `path` as the one pose-CSV schema, and return the
    number of data rows written.

    Each row is a DECODED TELEMETRY FRAME (a `TlmStream.feed()` dict,
    keys `x`/`y`/`h`/`ox`/`oy`/`oh`, optionally `vl`/`vr`, and the
    device clock's `now`) with one host-side key added: `t_host`, the
    host arrival time [s]. `dict(frame, t_host=time.time())` is the
    whole call-site idiom -- values pass through in the wire's own
    units, so a recorder never applies a scale factor of its own and
    the CSV cannot disagree with the `_tlm.csv` written beside it.
    Extra keys a frame carries (`seq`, `flags`, `i2cf`, the FULL-only
    columns) are ignored, not written.

    `wheels=True` appends the optional `vl_mms,vr_mms` pair, for a
    recorder whose chart plots the frame's own wheel speeds.

    Fail-loud, in write_tlm_csv()'s style: a row missing a required key
    raises PoseCsvSchemaError naming the key and the row number rather
    than writing a blank cell that reads downstream as a real zero.

    A zero-row capture is NOT refused here -- unlike write_tlm_csv(),
    whose CSV is the capture-quality record itself, this file is a
    derived view of a stream whose emptiness that guard (and its
    `.meta.json` sidecar, checked at read time by read_meta_sidecar())
    already refuses loudly and in one place.
    """
    columns = list(POSE_CSV_COLUMNS)
    if wheels:
        columns.extend(POSE_CSV_WHEEL_COLUMNS)
    written = 0
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(columns)
        for row in rows:
            out = []
            for column in columns:
                key = _POSE_CSV_FRAME_KEY[column]
                if key not in row:
                    raise PoseCsvSchemaError(
                        'refusing to write {path}: row {n} has no {key!r} '
                        '(the {column!r} column) -- a pose CSV with a '
                        'blank cell reads downstream as a real zero'
                        .format(path=path, n=written, key=key,
                                column=column))
                value = row[key]
                out.append(round(value, 3) if column == 't_host' else value)
            w.writerow(out)
            written += 1
    return written


def read_pose_csv(path):
    """Read a pose CSV and return `(rows, schema)`.

    `rows` is a list of dicts in the SAME shape `TlmStream.feed()`
    produces -- `x`/`y`/`h`/`ox`/`oy`/`oh` in wire units, `now` the
    device clock [ms], `t_host` the host arrival time [s], plus
    `vl`/`vr` when the file carried the optional wheel-speed pair -- so
    `pose_cm()`/`otos_cm()`/`wheels_mms()` apply to a CSV row exactly as
    they do to a live frame. `schema` names the header that was found,
    for a caller that wants to say so on its console or chart.

    Columns are bound BY NAME. Position and column count are never
    consulted: that is the whole defect this codec exists to fix (see
    this section's header comment). A file whose header carries the
    required columns in any order is read; unrecognised EXTRA columns
    beside a complete set are ignored rather than guessed at.

    The legacy headers this repo's own tools wrote before sprint 034
    ticket 004 are CONVERTED, not refused -- their cm/degree values are
    scaled back into wire units by `_LEGACY_POSE_SCHEMAS` above and
    rounded to the integer the wire actually carried, so an existing
    capture under `captures/` still charts correctly instead of being
    lost. (Converting is one of the two outcomes ticket 004 permits; the
    prohibited one is the old behaviour, silently reading cm as mm.) The
    one historical shape that is deliberately refused instead of
    converted is documented on `_LEGACY_POSE_SCHEMAS` itself.

    Anything else raises PoseCsvSchemaError naming the file and the
    header it found. An empty file (no header at all) raises too: a
    capture that recorded nothing is not a schema this reader can pick.
    """
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        if not header:
            raise PoseCsvSchemaError(
                'refusing to read {path}: the file is empty -- it has no '
                'header row, so there is no schema to bind to'
                .format(path=path))
        raw_rows = list(reader)

    present = set(header)
    if present.issuperset(POSE_CSV_COLUMNS):
        columns = list(POSE_CSV_COLUMNS)
        if present.issuperset(POSE_CSV_WHEEL_COLUMNS):
            columns.extend(POSE_CSV_WHEEL_COLUMNS)
        plan = {_POSE_CSV_FRAME_KEY[c]: (c, 1.0) for c in columns}
        return ([_pose_row_from_raw(raw, plan, path, n)
                 for n, raw in enumerate(raw_rows)], POSE_CSV_SCHEMA)

    for name, legacy_header, plan, optional_plans in _LEGACY_POSE_SCHEMAS:
        if not present.issuperset(legacy_header):
            continue
        plan = dict(plan)
        for optional in optional_plans:
            if present.issuperset(column for column, _f in optional.values()):
                plan.update(optional)
                break
        return ([_pose_row_from_raw(raw, plan, path, n)
                 for n, raw in enumerate(raw_rows)], name)

    raise PoseCsvSchemaError(
        'refusing to read {path}: its header is not a pose CSV any tool '
        'in this repo writes -- found [{found}]; expected [{expected}] '
        '(the wire-unit schema, optionally + [{wheels}]), or one of the '
        'legacy headers this codec converts: {legacy}. A header that is '
        'not recognised is refused, never guessed at by column count.'
        .format(path=path, found=','.join(header),
                expected=','.join(POSE_CSV_COLUMNS),
                wheels=','.join(POSE_CSV_WHEEL_COLUMNS),
                legacy='; '.join(entry[0] for entry in
                                 _LEGACY_POSE_SCHEMAS)))


def _pose_row_from_raw(raw, plan, path, n):
    """One CSV row -> one frame-shaped dict, per `plan`: frame key ->
    (source column, factor).

    Every quantity but `t_host` comes back as an int, because that is
    what the wire carries; a converted legacy value is ROUNDED to the
    nearest int, which recovers the original wire integer exactly for
    any value that was written out of a frame in the first place.
    """
    row = {}
    for key, (column, factor) in plan.items():
        text = raw.get(column)
        if text is None or text == '':
            raise PoseCsvSchemaError(
                'refusing to read {path}: row {n} has no value in the '
                '{column!r} column -- a blank cell would read downstream '
                'as a real zero'.format(path=path, n=n, column=column))
        try:
            value = float(text)
        except ValueError as e:
            raise PoseCsvSchemaError(
                'refusing to read {path}: row {n} column {column!r} is '
                '{text!r}, which is not a number'
                .format(path=path, n=n, column=column, text=text)) from e
        row[key] = (value * factor if key in _POSE_CSV_REAL_KEYS
                    else int(round(value * factor)))
    return row
