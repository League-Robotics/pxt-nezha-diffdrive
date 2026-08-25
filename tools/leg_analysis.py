#!/usr/bin/env python3
"""tools/leg_analysis.py -- per-leg believed-vs-target analysis for
Square Tour telemetry (sprint 011 ticket 002).

The residual intermittent leg fault
(`clasi/sprints/011-hardware-validation-otos-world-pose-tours-and-the-
residual-leg-fault/issues/intermittent-cw-pivot-abort-wheel-reversal.md`)
was, until sprint 006's fixes, a wheel-reversal/turn-overshoot bug.
That class is fixed. What remains is smaller and different-shaped:
"occasional distance-leg errors (a straight overrunning, or a tour
truncating mid-leg) ... heading usually still closes." The issue's own
first "next probe" is per-leg believed-vs-target logging at move end:
what did the move think it hit, versus the commanded target? This
module is that tool.

**A leaf consumer of `tools/tlm.py`.** This tool never decodes a wire
line itself -- it reads the pose CSV `tools/tour_capture.py` already
wrote (`<prefix>_pose.csv`: t_host, t_dev_ms, x_mm, y_mm, h_cdeg,
ox_mm, oy_mm, oh_cdeg -- the SAME wire-unit columns `tlm.TlmStream`
decodes into a frame dict's x/y/h/ox/oy/oh keys) and hands each row to
`tlm.pose_cm()`/`tlm.otos_cm()` for the one-and-only wire-to-
engineering-unit conversion, exactly the relationship sprint 005's six
retrofitted consumers already have (see `tools/DESIGN.md`'s "Tour
family" section and this sprint's `design/tools-root-DESIGN.md`'s
"Campaign tooling" section). `tlm.read_meta_sidecar()` is consulted for
the capture-quality `.meta.json` sidecar, the same SUC-002 zero-frame
refusal `tour_chart.py` already applies.

**`otos_cm()` is not trusted blindly.** A real bench run (vevov, over
radio, camera-verified 20 cm drive) found the telemetry ox/oy/oh
columns byte-identical start to finish across a whole move -- a frozen
cache, not a live reading, on that firmware build. `believed` (the
figure `classify_leg()` actually classifies against `commanded`) is
ALWAYS the encoder x/y/h columns, never OTOS; `detect_otos_staleness()`
cross-checks the OTOS columns against that same encoder movement and
flags the leg (`otos_stale`, carried through to every `LegRow`/CSV row
and the printed table) when OTOS reads ~0 displacement while the
encoders clearly moved. See the "OTOS staleness guard" section below
for the scope limit (observed on at least one firmware build; not
confirmed either way on current master's 20-column frame).

**Two layers, on purpose** (the same "pure decision function, unit-
tested against synthetic fixtures" shape `make_deploy.py`'s
`classify_attempt()` established -- sprint 008 precedent):

1. `classify_leg(commanded, believed, ground_truth=None) -> LegResult`
   -- pure, no I/O. Takes a leg's commanded distance/heading and its
   believed (telemetry-derived) distance/heading and returns a
   classification plus SEPARATE distance and heading error figures.
   The issue's own distinguishing signal for the residual fault versus
   the already-fixed class is "heading usually still closes" while
   distance does not -- collapsing this into one pass/fail bit would
   destroy exactly the signal this tool exists to surface, so
   `LegResult` always carries both errors, regardless of which way (if
   any) the leg missed.
2. Everything else (`read_pose_rows()`, `segment_legs()`,
   `analyze_pose_csv()`, `main()`) -- the impure CSV-reading, leg-
   segmentation, and CLI/reporting layer that turns a real capture into
   the `commanded`/`believed` pairs the pure core classifies.

**Leg segmentation.** `tour_chart.py` has no leg-boundary detector of
its own to reuse (checked -- it plots one continuous trajectory, never
splits it). `test/test.ts`'s tours (`tourWorld()`/`tourRobot()`/
`tourWheels()`) call `logFix()` between legs, which pauses briefly for
an OTOS read -- and telemetry keeps streaming throughout, so that pause
shows up as one or more REPEATED pose samples (same x/y/h) in the
capture. `segment_legs()` uses exactly that: a run of samples that
changes is a MOVE (one leg); a sample that does not change from its
predecessor extends a HOLD. This requires at least one held sample
between legs to separate them -- true of every real capture (the
OTOS read after each `logFix()` call takes measurable time relative to
the ~20 Hz telemetry rate) and guaranteed by construction in this
ticket's synthetic fixtures (`tests/tools/test_leg_analysis.py`, which
is the only thing this ticket's acceptance criteria require to pass --
"no robot, no real capture file").

**Heading convention, a documented simplification.** For a corner-
target leg, "commanded heading" is computed as the geometric bearing
from the leg's start point to its target (`atan2(dy, dx)`, 0 deg = +x/
east, positive turning toward +y/north -- the pose CSV's own x/y sign
convention, `test/test.ts`'s "+x east, +y north"). This is a reasonable
proxy for "the heading needed to point at the target," not a verified
match to the firmware's own internal steering math -- treat
`heading_error_deg` as directional evidence, not a certified figure,
consistent with the issue's own observation that headings generally
close regardless of which distance fault (if any) a leg hit.

Usage::

    uv run python3 tools/leg_analysis.py .tmp/tour_pose.csv
    uv run python3 tools/leg_analysis.py .tmp/tour_pose.csv \\
        --corners "-50,30;-50,-30;50,-30;50,30" --out .tmp/legs.csv
"""
import argparse
import csv
import dataclasses
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tlm


# --- classification verdicts --------------------------------------------

ON_TARGET = 'on-target'
STRAIGHT_OVERRUN = 'straight-overrun'
MID_LEG_TRUNCATION = 'mid-leg-truncation'

# 60 mm is the tour-closure "near-miss" threshold the residual-fault
# issue itself quotes ("tours complete ~70% with near-misses at the
# 60 mm threshold"); 8 deg gives a little slack over the same issue's
# "headings close within ~7 deg consistently" post-fix figure.
DEFAULT_DISTANCE_TOL_CM = 6.0
DEFAULT_HEADING_TOL_DEG = 8.0

# test/test.ts's own four-corner world-tour geometry (CORNERS_X/
# CORNERS_Y), A1-centred cm, +x east +y north:
#   NW (-50, 30) -> SW (-50, -30) -> SE (50, -30) -> NE (50, 30)
DEFAULT_CORNERS_CM = [(-50.0, 30.0), (-50.0, -30.0),
                      (50.0, -30.0), (50.0, 30.0)]

# tour_capture.py's own pose CSV header (see its main()) -- this is the
# ONE place that column shape is assumed.
POSE_CSV_FIELDS = ('t_host', 't_dev_ms', 'x_mm', 'y_mm', 'h_cdeg',
                    'ox_mm', 'oy_mm', 'oh_cdeg')

# --- OTOS staleness guard -------------------------------------------------
# Bench finding (vevov, over radio, camera-verified 20 cm drive): the
# telemetry ox/oy/oh columns read BYTE-IDENTICAL (386, 345, -16504)
# start to finish across the whole move -- a frozen cache, not a live
# reading, while the camera (19.34 cm), the OTOS chip's OWN live
# RUN:fix/OCAL read (19.15 cm), and the encoders (20.1 cm) all agreed
# the robot actually moved. `otos_cm()` must never be silently trusted
# as ground truth here -- it is one of several pose sources, and this
# one can go stale mid-move.
#
# SCOPE LIMIT: vevov was running OLDER firmware (12-column POSE frame,
# no STATUS). Current master emits the 20-column FULL frame and has
# NOT been confirmed to freeze the same way -- this guard is "observed
# frozen on at least one firmware build", not "always frozen", and is
# applied uniformly (there is no per-firmware branch here) because a
# false-positive stale flag costs a glance at a CSV column; a silent
# false OTOS reading costs a wrong conclusion about a real fault.
OTOS_STALE = 'otos-stale'
OTOS_FROZEN_EPS_CM = 0.1          # "moved" less than a mm -- frozen
OTOS_STALE_MIN_ENCODER_CM = 2.0   # encoders must show a real leg, not noise


# --- pure core: LegSpec / LegResult / classify_leg -----------------------

@dataclasses.dataclass(frozen=True)
class LegSpec:
    """One leg's straight-line distance and heading, in cm/deg.

    `commanded`, `believed`, and `ground_truth` (when present) are all
    this same shape -- "how far, and which way, did this leg's start
    point end up relating to some end point" -- so `classify_leg()` can
    compare any pair of them with the same subtraction.
    """
    distance_cm: float
    heading_deg: float


@dataclasses.dataclass(frozen=True)
class LegResult:
    """`classify_leg()`'s verdict. `distance_error_cm` and
    `heading_error_deg` are ALWAYS both populated, regardless of
    `classification` -- the residual-fault signature ("heading usually
    still closes") is only visible if a caller can see a small heading
    error next to a large distance error, not a single collapsed bit.
    """
    classification: str
    distance_error_cm: float
    heading_error_deg: float
    gt_distance_error_cm: float = None
    gt_heading_error_deg: float = None


def _wrap_deg(delta):
    """Wrap a heading difference to (-180, 180]."""
    return (delta + 180.0) % 360.0 - 180.0


def commanded_leg_spec(start_xy, target_xy):
    """The commanded leg: straight-line distance to `target_xy` from
    `start_xy`, and the bearing that points at it. Pure geometry -- see
    the module docstring's "Heading convention" note."""
    dx = target_xy[0] - start_xy[0]
    dy = target_xy[1] - start_xy[1]
    return LegSpec(distance_cm=math.hypot(dx, dy),
                    heading_deg=math.degrees(math.atan2(dy, dx)))


def observed_leg_spec(start_xy, end_pose):
    """An observed leg (believed or ground-truth): straight-line
    displacement from `start_xy` to `end_pose`'s position, and
    `end_pose`'s OWN reported heading -- "what the move thinks it
    hit", not "which way it pointed while getting there". `end_pose`
    is an (x_cm, y_cm, h_deg) triple."""
    ex, ey, eh = end_pose
    dx = ex - start_xy[0]
    dy = ey - start_xy[1]
    return LegSpec(distance_cm=math.hypot(dx, dy), heading_deg=eh)


def classify_leg(commanded, believed, ground_truth=None,
                  distance_tol_cm=DEFAULT_DISTANCE_TOL_CM,
                  heading_tol_deg=DEFAULT_HEADING_TOL_DEG):
    """Classify one leg. Pure function, no I/O -- unit-tested directly
    against synthetic `LegSpec` fixtures and, at a higher level,
    against synthetic CSV fixtures via `analyze_pose_csv()`
    (`tests/tools/test_leg_analysis.py`).

    `commanded`/`believed`/`ground_truth` are `LegSpec`s (see above).
    `ground_truth` is optional -- AprilCam truth is not always
    available -- and, when given, only adds the `gt_*` informational
    error fields; it never changes `classification`, which is always
    decided from `believed` (telemetry) vs `commanded` (what was
    asked), matching the issue's own framing: "what did the move think
    it hit, versus the commanded target?"

    `distance_error_cm` is signed: positive means the leg traveled
    FARTHER than commanded (an overrun tendency), negative means it
    fell SHORT (a truncation tendency). A leg counts `on-target` only
    when BOTH distance and heading are within tolerance; otherwise the
    classification is decided by the sign of the distance error alone
    -- `heading_error_deg` is still reported either way, which is what
    lets a caller see "distance missed, heading still closed" (the
    residual signature) as distinct from "both missed" (the
    already-fixed class) rather than as one flattened bit.
    """
    distance_error_cm = believed.distance_cm - commanded.distance_cm
    heading_error_deg = _wrap_deg(believed.heading_deg - commanded.heading_deg)

    if (abs(distance_error_cm) <= distance_tol_cm
            and abs(heading_error_deg) <= heading_tol_deg):
        classification = ON_TARGET
    elif distance_error_cm > 0:
        classification = STRAIGHT_OVERRUN
    else:
        classification = MID_LEG_TRUNCATION

    gt_distance_error_cm = gt_heading_error_deg = None
    if ground_truth is not None:
        gt_distance_error_cm = believed.distance_cm - ground_truth.distance_cm
        gt_heading_error_deg = _wrap_deg(
            believed.heading_deg - ground_truth.heading_deg)

    return LegResult(
        classification=classification,
        distance_error_cm=distance_error_cm,
        heading_error_deg=heading_error_deg,
        gt_distance_error_cm=gt_distance_error_cm,
        gt_heading_error_deg=gt_heading_error_deg,
    )


def _is_null_otos_pose(pose, eps=1e-6):
    """True if an (x_cm, y_cm, h_deg) OTOS pose is the universal
    `(0, 0, 0)` `tlm.py` documents as "legitimately 0 on any OTOS-less
    robot ... never treated as missing data or a fault" -- e.g. tovez,
    most of the fleet. This is NOT the frozen-cache bug (that freezes
    at whatever non-zero fix OTOS last cached, e.g. the bench finding's
    `(386, 345, -16504)`); it is the ordinary, expected reading on a
    robot that never had OTOS to freeze in the first place."""
    return abs(pose[0]) <= eps and abs(pose[1]) <= eps and abs(pose[2]) <= eps


def detect_otos_staleness(encoder_believed, otos_start_pose, otos_end_pose,
                          frozen_eps_cm=OTOS_FROZEN_EPS_CM,
                          min_encoder_cm=OTOS_STALE_MIN_ENCODER_CM):
    """True if the OTOS pose over a leg is ~unchanged while the
    encoders clearly moved -- a frozen OTOS cache, not a robot that
    genuinely never moved. Pure function, no I/O.

    `encoder_believed` is the leg's encoder-based `LegSpec` (see
    `observed_leg_spec()`); `otos_start_pose`/`otos_end_pose` are the
    RAW (x_cm, y_cm, h_deg) OTOS poses at the leg's start/end samples
    (not a `LegSpec` -- a `LegSpec` only carries relative displacement,
    and telling "frozen at the real cached fix" apart from "no OTOS
    fitted" needs the ABSOLUTE position; see `_is_null_otos_pose()`).

    A leg whose OTOS pose is the universal `(0, 0, 0)` null value at
    BOTH ends is read as "no OTOS fitted" and never flagged, regardless
    of how far the encoders moved -- flagging every leg on every
    OTOS-less robot would bury the real signal in noise. Only a leg
    whose OTOS pose is constant AND anchored at a genuine (non-null)
    fix counts as frozen.

    A frozen source is only distinguishable from a genuinely stationary
    robot by cross-source disagreement -- OTOS reading ~0 displacement
    while the encoders clearly moved is exactly that disagreement.
    OTOS reading ~0 while the encoders ALSO read ~0 (a leg that truly
    never moved) is not flagged either: both sources agree, so there is
    nothing stale to report.
    """
    if _is_null_otos_pose(otos_start_pose) and _is_null_otos_pose(otos_end_pose):
        return False
    otos_believed = observed_leg_spec(otos_start_pose[:2], otos_end_pose)
    return (otos_believed.distance_cm <= frozen_eps_cm
            and encoder_believed.distance_cm >= min_encoder_cm)


# --- leg segmentation ------------------------------------------------------

def _pose_close(a, b, motion_eps_cm, motion_eps_deg):
    return (abs(a[0] - b[0]) <= motion_eps_cm
            and abs(a[1] - b[1]) <= motion_eps_cm
            and abs(_wrap_deg(a[2] - b[2])) <= motion_eps_deg)


def _segment_leg_index_pairs(poses, motion_eps_cm=0.05, motion_eps_deg=0.1):
    """The real segmentation logic -- returns `(start_idx, end_idx)`
    pairs indexing into `poses`. `segment_legs()` below is a thin
    pose-tuple-returning wrapper around this kept as the public/tested
    surface; `analyze_pose_csv()` calls this directly because it also
    needs to look up the OTOS pose at the SAME indices (for the
    staleness cross-check above), not just the encoder pose.

    A sample within `motion_eps_cm`/`motion_eps_deg` of its predecessor
    extends a HOLD; anything farther starts/extends a MOVE. Each
    detected MOVE run becomes one leg: `start_idx` is the last sample
    of the preceding HOLD (or the run's own first sample, if the
    capture opens already in motion), `end_idx` is the first sample of
    the FOLLOWING hold (or the capture's last index, if data ends
    mid-move -- exactly the "tour truncating mid-leg" case this tool
    exists to catch, and the last thing recorded IS the believed pose
    at truncation).

    Requires at least one held sample between legs to tell them apart
    (see the module docstring) -- a capture with no pause anywhere
    between corners is read as one single leg, not silently
    mis-split.
    """
    n = len(poses)
    if n < 2:
        return []

    moving = [False] * n
    for i in range(1, n):
        moving[i] = not _pose_close(poses[i - 1], poses[i],
                                    motion_eps_cm, motion_eps_deg)

    pairs = []
    i = 1
    while i < n:
        if moving[i]:
            start_idx = i - 1
            while i < n and moving[i]:
                i += 1
            end_idx = i if i < n else n - 1
            pairs.append((start_idx, end_idx))
        else:
            i += 1
    return pairs


def segment_legs(poses, motion_eps_cm=0.05, motion_eps_deg=0.1):
    """Split an ordered `[(x_cm, y_cm, h_deg), ...]` sample sequence
    into per-leg `(start_pose, end_pose)` pairs. A thin wrapper around
    `_segment_leg_index_pairs()` -- see that function's docstring for
    the actual segmentation rule."""
    pairs = _segment_leg_index_pairs(poses, motion_eps_cm, motion_eps_deg)
    return [(poses[s], poses[e]) for s, e in pairs]


# --- CSV ingestion: the tlm.py leaf-consumer boundary ----------------------

def read_pose_rows(pose_csv_path):
    """Read a `tour_capture.py`-produced pose CSV and return one dict
    per sample: `{'t_dev_ms': int, 'x_cm', 'y_cm', 'h_deg', 'otos_x_cm',
    'otos_y_cm', 'otos_h_deg'}`.

    Every wire-unit -> engineering-unit conversion is delegated to
    `tlm.pose_cm()`/`tlm.otos_cm()` -- this tool's whole reason for
    existing as a `tlm.py` LEAF consumer (see the module docstring).
    `tour_capture.py`'s pose CSV columns (x_mm/y_mm/h_cdeg/ox_mm/oy_mm/
    oh_cdeg) are the SAME wire units `tlm.TlmStream` decodes into a
    frame dict's x/y/h/ox/oy/oh keys, so building an equivalent dict
    per CSV row and handing it to `pose_cm()`/`otos_cm()` is direct
    reuse, not a coincidence.
    """
    rows = []
    with open(pose_csv_path, newline='') as f:
        for raw in csv.DictReader(f):
            frame = {
                'x': int(float(raw['x_mm'])),
                'y': int(float(raw['y_mm'])),
                'h': int(float(raw['h_cdeg'])),
                'ox': int(float(raw['ox_mm'])),
                'oy': int(float(raw['oy_mm'])),
                'oh': int(float(raw['oh_cdeg'])),
            }
            pose = tlm.pose_cm(frame)
            otos = tlm.otos_cm(frame)
            rows.append({
                't_dev_ms': int(float(raw['t_dev_ms'])),
                'x_cm': pose['x'], 'y_cm': pose['y'], 'h_deg': pose['h'],
                'otos_x_cm': otos['x'], 'otos_y_cm': otos['y'],
                'otos_h_deg': otos['h'],
            })
    return rows


# --- per-leg reporting row --------------------------------------------------

@dataclasses.dataclass(frozen=True)
class LegRow:
    """One printable/writable row of the per-leg table: commanded
    target, believed pose at move end, AprilCam ground truth where
    available, the classification result, and the OTOS staleness flag
    (see `detect_otos_staleness()`). `otos_stale`/`otos_distance_cm`
    are reported for every leg, not just stale ones -- a downstream
    campaign reading this table sees the OTOS evidence either way,
    never just a silent absence."""
    leg: int
    target_x_cm: float
    target_y_cm: float
    believed_x_cm: float
    believed_y_cm: float
    believed_h_deg: float
    commanded: LegSpec
    believed: LegSpec
    result: LegResult
    ground_truth_x_cm: float = None
    ground_truth_y_cm: float = None
    ground_truth_h_deg: float = None
    otos_stale: bool = False
    otos_distance_cm: float = None


def analyze_pose_csv(pose_csv_path, targets_cm, ground_truth_cm=None,
                      distance_tol_cm=DEFAULT_DISTANCE_TOL_CM,
                      heading_tol_deg=DEFAULT_HEADING_TOL_DEG):
    """The full pipeline: read the pose CSV, segment it into legs,
    classify each leg against its corner target, and return one
    `LegRow` per detected leg (up to `len(targets_cm)` -- a leg with no
    matching target is dropped, and reported by the CLI, not raised
    here, so a partial/short capture is still usable).

    `ground_truth_cm`, if given, is a list of `(x_cm, y_cm, h_deg)`
    AprilCam fixes, one per leg, in leg order -- "where available"
    (the description's own phrase): omit it, or make it shorter than
    `targets_cm`, and the legs beyond it simply get no ground-truth
    comparison.

    Every `LegRow` also carries an OTOS staleness check
    (`detect_otos_staleness()`): the SAME leg's OTOS ox/oy/oh columns
    (via `tlm.otos_cm()`) are compared against the encoder columns this
    leg's `believed` pose already used, at the SAME start/end sample
    indices -- a leg-index_pairs pass, not `segment_legs()`'s own
    pose-tuple return, precisely so the OTOS lookup lands on the exact
    samples the encoder segmentation chose. `otos_cm()` is never used
    as the leg's `believed` pose or compared against `commanded` --
    see the module's "OTOS staleness guard" section for why.
    """
    rows = read_pose_rows(pose_csv_path)
    poses = [(r['x_cm'], r['y_cm'], r['h_deg']) for r in rows]
    otos_poses = [(r['otos_x_cm'], r['otos_y_cm'], r['otos_h_deg'])
                  for r in rows]
    index_pairs = _segment_leg_index_pairs(poses)

    leg_rows = []
    for i, (start_idx, end_idx) in enumerate(index_pairs):
        if i >= len(targets_cm):
            break
        start_pose, end_pose = poses[start_idx], poses[end_idx]
        target = targets_cm[i]
        commanded = commanded_leg_spec(start_pose[:2], target)
        believed = observed_leg_spec(start_pose[:2], end_pose)

        otos_start, otos_end = otos_poses[start_idx], otos_poses[end_idx]
        otos_believed = observed_leg_spec(otos_start[:2], otos_end)
        otos_stale = detect_otos_staleness(believed, otos_start, otos_end)

        gt_spec = None
        gt_pose = None
        if ground_truth_cm is not None and i < len(ground_truth_cm):
            gt_pose = ground_truth_cm[i]
            gt_spec = observed_leg_spec(start_pose[:2], gt_pose)

        result = classify_leg(commanded, believed, gt_spec,
                              distance_tol_cm=distance_tol_cm,
                              heading_tol_deg=heading_tol_deg)

        leg_rows.append(LegRow(
            leg=i + 1,
            target_x_cm=target[0], target_y_cm=target[1],
            believed_x_cm=end_pose[0], believed_y_cm=end_pose[1],
            believed_h_deg=end_pose[2],
            commanded=commanded, believed=believed, result=result,
            ground_truth_x_cm=gt_pose[0] if gt_pose is not None else None,
            ground_truth_y_cm=gt_pose[1] if gt_pose is not None else None,
            ground_truth_h_deg=gt_pose[2] if gt_pose is not None else None,
            otos_stale=otos_stale,
            otos_distance_cm=otos_believed.distance_cm,
        ))
    return leg_rows


# --- CLI ---------------------------------------------------------------

def _parse_corners_string(s):
    pairs = []
    for chunk in s.replace(';', ' ').split():
        x_str, y_str = chunk.split(',')
        pairs.append((float(x_str), float(y_str)))
    return pairs


def _is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def _read_points_csv(path, n_fields):
    """Read a bare or headered CSV of `n_fields`-tuples of floats
    (used for both `--corners-csv` (2 fields) and `--ground-truth-csv`
    (3 fields))."""
    with open(path, newline='') as f:
        rows = [row for row in csv.reader(f) if row]
    if rows and not _is_number(rows[0][0]):
        rows = rows[1:]  # skip header
    return [tuple(float(v) for v in row[:n_fields]) for row in rows]


def _resolve_targets(a):
    if a.corners_csv:
        return _read_points_csv(a.corners_csv, 2)
    if a.corners:
        return _parse_corners_string(a.corners)
    return list(DEFAULT_CORNERS_CM)


def print_table(leg_rows):
    print(f"{'leg':>3}  {'target(cm)':>14}  {'believed(cm,deg)':>22}  "
          f"{'dist_err':>9}  {'head_err':>9}  classification")
    for r in leg_rows:
        target = f"({r.target_x_cm:.1f},{r.target_y_cm:.1f})"
        believed = (f"({r.believed_x_cm:.1f},{r.believed_y_cm:.1f},"
                    f"{r.believed_h_deg:.1f})")
        # OTOS staleness is surfaced right next to the classification it
        # rides along with -- never a silently dropped extra column a
        # downstream reader could miss.
        flag = f'  [{OTOS_STALE}]' if r.otos_stale else ''
        print(f"{r.leg:>3}  {target:>14}  {believed:>22}  "
              f"{r.result.distance_error_cm:>+8.1f}  "
              f"{r.result.heading_error_deg:>+8.1f}  "
              f"{r.result.classification}{flag}")


def write_csv(leg_rows, path):
    fieldnames = ['leg', 'target_x_cm', 'target_y_cm',
                  'believed_x_cm', 'believed_y_cm', 'believed_h_deg',
                  'commanded_distance_cm', 'commanded_heading_deg',
                  'believed_distance_cm', 'believed_heading_deg',
                  'distance_error_cm', 'heading_error_deg',
                  'classification',
                  'ground_truth_x_cm', 'ground_truth_y_cm',
                  'ground_truth_h_deg',
                  'gt_distance_error_cm', 'gt_heading_error_deg',
                  'otos_distance_cm', 'otos_stale']
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval='')
        w.writeheader()
        for r in leg_rows:
            w.writerow({
                'leg': r.leg,
                'target_x_cm': r.target_x_cm, 'target_y_cm': r.target_y_cm,
                'believed_x_cm': r.believed_x_cm,
                'believed_y_cm': r.believed_y_cm,
                'believed_h_deg': r.believed_h_deg,
                'commanded_distance_cm': r.commanded.distance_cm,
                'commanded_heading_deg': r.commanded.heading_deg,
                'believed_distance_cm': r.believed.distance_cm,
                'believed_heading_deg': r.believed.heading_deg,
                'distance_error_cm': r.result.distance_error_cm,
                'heading_error_deg': r.result.heading_error_deg,
                'classification': r.result.classification,
                'ground_truth_x_cm': r.ground_truth_x_cm,
                'ground_truth_y_cm': r.ground_truth_y_cm,
                'ground_truth_h_deg': r.ground_truth_h_deg,
                'gt_distance_error_cm': r.result.gt_distance_error_cm,
                'gt_heading_error_deg': r.result.gt_heading_error_deg,
                'otos_distance_cm': r.otos_distance_cm,
                'otos_stale': r.otos_stale,
            })


def build_arg_parser():
    ap = argparse.ArgumentParser(
        description="Per-leg believed-vs-target analysis for a "
                    "tour_capture.py pose CSV.")
    ap.add_argument('pose_csv',
                    help="tour_capture.py's <prefix>_pose.csv")
    ap.add_argument('--corners', default=None,
                    help="per-corner target list as 'x1,y1;x2,y2;...' "
                          "(cm, A1-centred, +x east +y north). Default: "
                          "test.ts's own four-corner world tour "
                          "(CORNERS_X/CORNERS_Y).")
    ap.add_argument('--corners-csv', default=None,
                    help='per-corner target list as a 2-column CSV '
                          '(x_cm,y_cm; header optional) -- overrides '
                          '--corners')
    ap.add_argument('--ground-truth-csv', default=None,
                    help='optional AprilCam per-leg ground truth CSV '
                          '(x_cm,y_cm,h_deg per leg, header optional, '
                          'in leg order)')
    ap.add_argument('--distance-tol-cm', type=float,
                    default=DEFAULT_DISTANCE_TOL_CM)
    ap.add_argument('--heading-tol-deg', type=float,
                    default=DEFAULT_HEADING_TOL_DEG)
    ap.add_argument('--out', default=None,
                    help='optional path to write the per-leg table as CSV')
    return ap


def main(argv=None):
    a = build_arg_parser().parse_args(argv)

    # SUC-002: refuse to analyze a run whose capture recorded zero
    # telemetry frames -- the same fail-loud guard tour_chart.py
    # applies, via the SAME tlm.py sidecar reader. A missing sidecar
    # (older capture, or a source that never wrote one) is not itself
    # refused here.
    meta = tlm.read_meta_sidecar(a.pose_csv)
    if meta is not None and meta.get('frames', 0) == 0:
        raise SystemExit(
            f'refusing to analyze {a.pose_csv}: its capture\'s telemetry '
            f'sidecar reports frames=0 -- no telemetry was recorded for '
            f'this run')

    targets = _resolve_targets(a)
    ground_truth = (_read_points_csv(a.ground_truth_csv, 3)
                    if a.ground_truth_csv else None)

    leg_rows = analyze_pose_csv(
        a.pose_csv, targets, ground_truth_cm=ground_truth,
        distance_tol_cm=a.distance_tol_cm,
        heading_tol_deg=a.heading_tol_deg)

    if not leg_rows:
        print('no legs detected (capture too short, or never held '
              'still between moves -- see segment_legs() in the module '
              'docstring)')
        return

    print_table(leg_rows)
    if a.out:
        write_csv(leg_rows, a.out)
        print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
