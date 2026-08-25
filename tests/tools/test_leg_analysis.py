"""tests/tools/test_leg_analysis.py -- pins `tools/leg_analysis.py`'s
per-leg believed-vs-target classification (sprint 011 ticket 002).

**Why this exists.** The residual intermittent leg fault issue
(`clasi/sprints/011-hardware-validation-otos-world-pose-tours-and-the-
residual-leg-fault/issues/intermittent-cw-pivot-abort-wheel-reversal.md`)
names its own first "next probe" as per-leg believed-vs-target logging
at move end. `tools/leg_analysis.py` is that tool: a pure
`classify_leg()` core (distance/heading in, a classification and BOTH
error figures out -- never one collapsed pass/fail bit) plus an impure
CSV-segmentation layer that turns a `tour_capture.py` pose CSV into the
`commanded`/`believed` pairs the core classifies.

This ticket's own acceptance criteria restrict testing to synthetic
CSV fixtures -- "no robot, no real capture file, required to pass this
ticket's tests" -- so every fixture below is hand-built, not a saved
capture. Each pose CSV fixture mirrors `tour_capture.py`'s own writer
shape exactly (t_host, t_dev_ms, x_mm, y_mm, h_cdeg, ox_mm, oy_mm,
oh_cdeg) and encodes one leg as "hold, then a ramp of changing
samples, then hold again" -- the same shape `test/test.ts`'s tours
produce for real (each `logFix()` between legs pauses for an OTOS
read, and telemetry keeps streaming through the pause), which is what
`segment_legs()` uses to find leg boundaries (see its docstring in
`tools/leg_analysis.py`).

Run with::

    uv run pytest tests/tools/test_leg_analysis.py
"""
import csv
import json
import pathlib
import sys

import pytest

# tests/tools/test_leg_analysis.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import leg_analysis  # noqa: E402  (path must be set up first)


# --- fixture helpers --------------------------------------------------

def _ramp(start, end, n):
    """`n` samples (inclusive of both ends) linearly interpolated from
    `start` to `end`, each an (x_mm, y_mm, h_cdeg) int triple -- the
    "leg is moving" portion of a synthetic capture."""
    out = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        out.append(tuple(round(s + (e - s) * t) for s, e in zip(start, end)))
    return out


def _write_pose_csv(path, samples, otos_samples=None):
    """Write `samples` (a list of (x_mm, y_mm, h_cdeg) int triples) as
    a `tour_capture.py`-shaped pose CSV. `otos_samples`, if given, is a
    parallel list of (ox_mm, oy_mm, oh_cdeg) triples; omitted, OTOS
    columns are zero throughout -- a robot with no OTOS fitted, per
    `tlm.py`'s own "legitimately (0,0,0)" contract, exercised
    deliberately so this tool's default path is proven against the
    common (no-OTOS) case."""
    if otos_samples is None:
        otos_samples = [(0, 0, 0)] * len(samples)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(list(leg_analysis.POSE_CSV_FIELDS))
        for i, ((x_mm, y_mm, h_cdeg), (ox_mm, oy_mm, oh_cdeg)) in enumerate(
                zip(samples, otos_samples)):
            w.writerow([round(i * 0.05, 3), i * 50, x_mm, y_mm, h_cdeg,
                        ox_mm, oy_mm, oh_cdeg])


def _single_leg_samples(end_mm_cdeg, hold=2, move_n=6):
    """A one-leg capture: `hold` samples at the origin, a ramp to
    `end_mm_cdeg`, then `hold` samples held there (the believed pose at
    move end)."""
    ramp = _ramp((0, 0, 0), end_mm_cdeg, move_n)
    return [(0, 0, 0)] * hold + ramp + [end_mm_cdeg] * hold


# --- classify_leg(): the pure core -------------------------------------

def test_on_target_when_distance_and_heading_both_within_tolerance():
    commanded = leg_analysis.LegSpec(distance_cm=100.0, heading_deg=0.0)
    believed = leg_analysis.LegSpec(distance_cm=101.0, heading_deg=2.0)

    result = leg_analysis.classify_leg(commanded, believed)

    assert result.classification == leg_analysis.ON_TARGET
    assert result.distance_error_cm == pytest.approx(1.0)
    assert result.heading_error_deg == pytest.approx(2.0)


def test_straight_overrun_when_distance_exceeds_commanded_by_a_margin():
    commanded = leg_analysis.LegSpec(distance_cm=100.0, heading_deg=0.0)
    believed = leg_analysis.LegSpec(distance_cm=112.0, heading_deg=2.0)

    result = leg_analysis.classify_leg(commanded, believed)

    assert result.classification == leg_analysis.STRAIGHT_OVERRUN
    assert result.distance_error_cm == pytest.approx(12.0)
    # the residual-fault signature: heading still closed even though
    # distance did not.
    assert abs(result.heading_error_deg) < leg_analysis.DEFAULT_HEADING_TOL_DEG


def test_mid_leg_truncation_when_distance_falls_short_of_commanded():
    commanded = leg_analysis.LegSpec(distance_cm=100.0, heading_deg=0.0)
    believed = leg_analysis.LegSpec(distance_cm=70.0, heading_deg=1.0)

    result = leg_analysis.classify_leg(commanded, believed)

    assert result.classification == leg_analysis.MID_LEG_TRUNCATION
    assert result.distance_error_cm == pytest.approx(-30.0)


def test_distance_error_and_heading_error_are_reported_as_separate_fields():
    # The whole point: a residual-fault leg (distance missed, heading
    # closed) must be distinguishable from an already-fixed-class leg
    # (both missed) by READING the two fields, not by one pass/fail bit.
    residual = leg_analysis.classify_leg(
        leg_analysis.LegSpec(100.0, 0.0), leg_analysis.LegSpec(112.0, 1.0))
    already_fixed_class = leg_analysis.classify_leg(
        leg_analysis.LegSpec(100.0, 0.0), leg_analysis.LegSpec(112.0, 35.0))

    assert residual.distance_error_cm == pytest.approx(
        already_fixed_class.distance_error_cm)
    # same distance miss, but heading tells them apart.
    assert abs(residual.heading_error_deg) < leg_analysis.DEFAULT_HEADING_TOL_DEG
    assert abs(already_fixed_class.heading_error_deg) > leg_analysis.DEFAULT_HEADING_TOL_DEG
    # classification alone (both straight-overrun, since both missed
    # distance the same way) would NOT surface this -- the separate
    # fields are what does.
    assert residual.classification == already_fixed_class.classification


def test_exactly_at_tolerance_boundary_counts_as_on_target():
    tol_d = leg_analysis.DEFAULT_DISTANCE_TOL_CM
    tol_h = leg_analysis.DEFAULT_HEADING_TOL_DEG
    commanded = leg_analysis.LegSpec(distance_cm=100.0, heading_deg=0.0)
    believed = leg_analysis.LegSpec(distance_cm=100.0 + tol_d,
                                    heading_deg=tol_h)

    result = leg_analysis.classify_leg(commanded, believed)

    assert result.classification == leg_analysis.ON_TARGET


def test_ground_truth_adds_informational_error_without_changing_classification():
    commanded = leg_analysis.LegSpec(distance_cm=100.0, heading_deg=0.0)
    believed = leg_analysis.LegSpec(distance_cm=112.0, heading_deg=2.0)
    ground_truth = leg_analysis.LegSpec(distance_cm=111.5, heading_deg=1.8)

    result = leg_analysis.classify_leg(commanded, believed, ground_truth)

    assert result.classification == leg_analysis.STRAIGHT_OVERRUN
    assert result.gt_distance_error_cm == pytest.approx(0.5)
    assert result.gt_heading_error_deg == pytest.approx(0.2)


def test_ground_truth_omitted_leaves_gt_fields_none():
    result = leg_analysis.classify_leg(
        leg_analysis.LegSpec(100.0, 0.0), leg_analysis.LegSpec(101.0, 1.0))

    assert result.gt_distance_error_cm is None
    assert result.gt_heading_error_deg is None


# --- segment_legs(): pure leg-boundary detection ------------------------

def test_segment_legs_finds_hold_move_hold_as_one_leg():
    poses = [(0, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0),
             (3, 0, 0), (3, 0, 0)]

    legs = leg_analysis.segment_legs(poses)

    assert legs == [((0, 0, 0), (3, 0, 0))]


def test_segment_legs_uses_the_last_sample_when_capture_ends_mid_move():
    # No trailing hold -- the capture is cut off while still moving.
    # This is the segmentation-level shape of "a tour truncating
    # mid-leg": the last thing recorded IS the believed pose.
    poses = [(0, 0, 0), (0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]

    legs = leg_analysis.segment_legs(poses)

    assert legs == [((0, 0, 0), (3, 0, 0))]


def test_segment_legs_splits_two_legs_on_the_intervening_hold():
    poses = [(0, 0, 0), (0, 0, 0),           # start hold
             (1, 0, 0), (2, 0, 0),            # leg 1 move
             (2, 0, 0), (2, 0, 0),            # inter-leg hold
             (2, 1, 0), (2, 2, 0),            # leg 2 move
             (2, 2, 0), (2, 2, 0)]            # trailing hold

    legs = leg_analysis.segment_legs(poses)

    assert legs == [((0, 0, 0), (2, 0, 0)), ((2, 0, 0), (2, 2, 0))]


def test_segment_legs_returns_empty_for_a_single_sample():
    assert leg_analysis.segment_legs([(0, 0, 0)]) == []


# --- read_pose_rows(): the tlm.py leaf-consumer boundary -----------------

def test_read_pose_rows_uses_tlm_scale_factors(tmp_path):
    pose_csv = tmp_path / 'scale_pose.csv'
    _write_pose_csv(pose_csv, [(500, -300, 1234)])
    # Patch in non-zero OTOS values for this one row directly (the
    # helper above always zeros them) to prove otos_cm() is exercised
    # too, not just pose_cm().
    with open(pose_csv, newline='') as f:
        rows = list(csv.reader(f))
    rows[1][5:8] = ['10', '20', '500']
    with open(pose_csv, 'w', newline='') as f:
        csv.writer(f).writerows(rows)

    [row] = leg_analysis.read_pose_rows(pose_csv)

    assert row['x_cm'] == pytest.approx(50.0)
    assert row['y_cm'] == pytest.approx(-30.0)
    assert row['h_deg'] == pytest.approx(12.34)
    assert row['otos_x_cm'] == pytest.approx(1.0)
    assert row['otos_y_cm'] == pytest.approx(2.0)
    assert row['otos_h_deg'] == pytest.approx(5.0)


# --- detect_otos_staleness(): the OTOS frozen-cache cross-check ----------
# Bench finding (vevov, over radio, camera-verified 20 cm drive): the
# telemetry ox/oy/oh columns read byte-identical (386, 345, -16504)
# start to finish across a whole move on that firmware -- a frozen
# cache, not a live reading. otos_cm() must never be trusted blindly;
# this detector is how a leg's OTOS data is told apart from a robot
# that genuinely never moved.

def test_detect_otos_staleness_true_when_frozen_at_a_real_nonzero_fix():
    # The bench finding's own shape: OTOS cached a genuine fix
    # (38.6, 34.5 cm / -165.04 deg, from ox/oy/oh = 386, 345, -16504)
    # and never updated it while the encoders clearly moved.
    encoder = leg_analysis.LegSpec(distance_cm=20.0, heading_deg=0.0)
    otos_start = (38.6, 34.5, -165.04)
    otos_end = (38.6, 34.5, -165.04)

    assert leg_analysis.detect_otos_staleness(
        encoder, otos_start, otos_end) is True


def test_detect_otos_staleness_false_when_both_genuinely_stationary():
    # A leg that truly never moved: both sources agree at ~0, so there
    # is nothing stale to report.
    encoder = leg_analysis.LegSpec(distance_cm=0.02, heading_deg=0.0)
    otos_start = otos_end = (38.6, 34.5, -165.04)

    assert leg_analysis.detect_otos_staleness(
        encoder, otos_start, otos_end) is False


def test_detect_otos_staleness_false_when_otos_also_tracks_movement():
    # OTOS's own live read agreeing (within noise) with the encoders --
    # the bench finding's "OTOS chip's own RUN:fix/OCAL read" case.
    encoder = leg_analysis.LegSpec(distance_cm=20.0, heading_deg=0.0)
    otos_start = (0.0, 0.0, 0.0)
    otos_end = (19.15, 0.0, 0.3)

    assert leg_analysis.detect_otos_staleness(
        encoder, otos_start, otos_end) is False


def test_detect_otos_staleness_false_when_otos_never_fitted():
    # tlm.py's own documented contract: (0, 0, 0) is the legitimate
    # "no OTOS fitted" reading (most of the fleet, tovez included), not
    # a fault -- flagging every leg on an OTOS-less robot would bury
    # the real signal in noise, so a leg whose OTOS pose is null at
    # BOTH ends is never flagged, no matter how far the encoders moved.
    encoder = leg_analysis.LegSpec(distance_cm=101.0, heading_deg=0.0)
    otos_start = otos_end = (0.0, 0.0, 0.0)

    assert leg_analysis.detect_otos_staleness(
        encoder, otos_start, otos_end) is False


# --- analyze_pose_csv(): the full CSV -> LegRow pipeline ------------------
# These are this ticket's three headline acceptance-criteria fixtures.

def test_csv_fixture_straight_overrun_classifies_as_straight_overrun(
        tmp_path):
    pose_csv = tmp_path / 'overrun_pose.csv'
    # 112.0 cm travelled, 2.00 deg heading -- overruns a 100 cm/0 deg
    # commanded leg by 12 cm (past the 6 cm tolerance), heading close.
    _write_pose_csv(pose_csv, _single_leg_samples((1120, 0, 200)))

    [leg] = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert leg.result.classification == leg_analysis.STRAIGHT_OVERRUN
    assert leg.result.distance_error_cm > 0
    assert abs(leg.result.heading_error_deg) < leg_analysis.DEFAULT_HEADING_TOL_DEG


def test_csv_fixture_mid_leg_truncation_classifies_as_mid_leg_truncation(
        tmp_path):
    pose_csv = tmp_path / 'truncate_pose.csv'
    # 70.0 cm travelled against a 100 cm commanded leg -- the move ends
    # 30 cm short (past the 6 cm tolerance).
    _write_pose_csv(pose_csv, _single_leg_samples((700, 0, 100)))

    [leg] = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert leg.result.classification == leg_analysis.MID_LEG_TRUNCATION
    assert leg.result.distance_error_cm < 0


def test_csv_fixture_on_target_classifies_as_on_target(tmp_path):
    pose_csv = tmp_path / 'ontarget_pose.csv'
    # 101.0 cm / 2.00 deg -- both within tolerance of a 100 cm/0 deg leg.
    _write_pose_csv(pose_csv, _single_leg_samples((1010, 0, 200)))

    [leg] = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert leg.result.classification == leg_analysis.ON_TARGET


def test_csv_fixture_two_legs_segmented_and_classified_independently(
        tmp_path):
    pose_csv = tmp_path / 'twoleg_pose.csv'
    samples = (
        [(0, 0, 0)] * 2
        + _ramp((0, 0, 0), (1010, 0, 200), 6)      # leg 1: on-target
        + [(1010, 0, 200)] * 2                     # inter-leg hold
        + _ramp((1010, 0, 200), (1010, 1150, 9200), 6)  # leg 2: overrun
        + [(1010, 1150, 9200)] * 2
    )
    _write_pose_csv(pose_csv, samples)
    targets = [(100.0, 0.0), (101.0, 100.0)]

    legs = leg_analysis.analyze_pose_csv(pose_csv, targets)

    assert [r.leg for r in legs] == [1, 2]
    assert legs[0].result.classification == leg_analysis.ON_TARGET
    assert legs[1].result.classification == leg_analysis.STRAIGHT_OVERRUN
    # leg 2's target is reported against ITS OWN commanded geometry,
    # not leg 1's.
    assert legs[1].target_x_cm == pytest.approx(101.0)
    assert legs[1].target_y_cm == pytest.approx(100.0)


def test_analyze_pose_csv_drops_legs_beyond_the_target_list(tmp_path):
    pose_csv = tmp_path / 'extra_leg_pose.csv'
    samples = (
        [(0, 0, 0)] * 2
        + _ramp((0, 0, 0), (1010, 0, 200), 6)
        + [(1010, 0, 200)] * 2
        + _ramp((1010, 0, 200), (1010, 1150, 200), 6)
        + [(1010, 1150, 200)] * 2
    )
    _write_pose_csv(pose_csv, samples)

    legs = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert len(legs) == 1


def test_analyze_pose_csv_ground_truth_list_matches_legs_in_order(tmp_path):
    pose_csv = tmp_path / 'gt_pose.csv'
    _write_pose_csv(pose_csv, _single_leg_samples((1120, 0, 200)))

    [leg] = leg_analysis.analyze_pose_csv(
        pose_csv, [(100.0, 0.0)], ground_truth_cm=[(111.5, 0.3, 1.8)])

    assert leg.ground_truth_x_cm == pytest.approx(111.5)
    assert leg.result.gt_distance_error_cm is not None


def test_analyze_pose_csv_flags_a_leg_with_frozen_otos_during_real_movement(
        tmp_path):
    pose_csv = tmp_path / 'otos_stale_pose.csv'
    encoder_samples = _single_leg_samples((1010, 0, 200))  # travels 101 cm
    # Byte-identical OTOS columns for every sample -- the bench
    # finding's frozen-cache shape, injected here as a synthetic
    # fixture (no robot, no real capture file).
    frozen_otos = (386, 345, -16504)
    otos_samples = [frozen_otos] * len(encoder_samples)
    _write_pose_csv(pose_csv, encoder_samples, otos_samples=otos_samples)

    [leg] = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert leg.otos_stale is True
    assert leg.otos_distance_cm == pytest.approx(0.0)
    # The primary classification is driven by ENCODER data only, and
    # is unaffected by the stale OTOS flag riding alongside it.
    assert leg.result.classification == leg_analysis.ON_TARGET


def test_analyze_pose_csv_does_not_flag_otos_when_it_also_moves(tmp_path):
    pose_csv = tmp_path / 'otos_live_pose.csv'
    encoder_samples = _single_leg_samples((1010, 0, 200))
    # OTOS tracks the same move (close, not identical, to the encoder
    # path) -- a live sensor, not a frozen cache.
    otos_samples = _ramp((0, 0, 0), (1005, 0, 195), len(encoder_samples))
    _write_pose_csv(pose_csv, encoder_samples, otos_samples=otos_samples)

    [leg] = leg_analysis.analyze_pose_csv(pose_csv, [(100.0, 0.0)])

    assert leg.otos_stale is False


def test_cli_table_and_csv_surface_the_otos_stale_flag(
        tmp_path, monkeypatch, capsys):
    pose_csv = tmp_path / 'otos_stale_run_pose.csv'
    encoder_samples = _single_leg_samples((1010, 0, 200))
    otos_samples = [(386, 345, -16504)] * len(encoder_samples)
    _write_pose_csv(pose_csv, encoder_samples, otos_samples=otos_samples)
    out_csv = tmp_path / 'legs.csv'
    monkeypatch.setattr(sys, 'argv', [
        'leg_analysis.py', str(pose_csv),
        '--corners', '100,0', '--out', str(out_csv)])

    leg_analysis.main()

    captured = capsys.readouterr()
    assert leg_analysis.OTOS_STALE in captured.out
    with open(out_csv, newline='') as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['otos_stale'] == 'True'


# --- CLI ---------------------------------------------------------------

def test_cli_prints_classification_and_writes_out_csv(
        tmp_path, monkeypatch, capsys):
    pose_csv = tmp_path / 'run_pose.csv'
    _write_pose_csv(pose_csv, _single_leg_samples((1010, 0, 200)))
    out_csv = tmp_path / 'legs.csv'
    monkeypatch.setattr(sys, 'argv', [
        'leg_analysis.py', str(pose_csv),
        '--corners', '100,0', '--out', str(out_csv)])

    leg_analysis.main()

    captured = capsys.readouterr()
    assert leg_analysis.ON_TARGET in captured.out
    assert out_csv.exists()
    with open(out_csv, newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['classification'] == leg_analysis.ON_TARGET


def test_cli_default_corners_match_test_ts_four_corner_geometry():
    # test/test.ts CORNERS_X/CORNERS_Y: [-50,-50,50,50] / [30,-30,-30,30]
    assert leg_analysis.DEFAULT_CORNERS_CM == [
        (-50.0, 30.0), (-50.0, -30.0), (50.0, -30.0), (50.0, 30.0)]


def test_cli_corners_csv_overrides_the_default_target_list(
        tmp_path, monkeypatch, capsys):
    pose_csv = tmp_path / 'run_pose.csv'
    _write_pose_csv(pose_csv, _single_leg_samples((700, 0, 100)))
    corners_csv = tmp_path / 'corners.csv'
    corners_csv.write_text('x_cm,y_cm\n100,0\n')
    monkeypatch.setattr(sys, 'argv', [
        'leg_analysis.py', str(pose_csv), '--corners-csv', str(corners_csv)])

    leg_analysis.main()

    captured = capsys.readouterr()
    assert leg_analysis.MID_LEG_TRUNCATION in captured.out


def test_cli_refuses_a_zero_frame_telemetry_sidecar(tmp_path, monkeypatch):
    pose_csv = tmp_path / 'dead_pose.csv'
    _write_pose_csv(pose_csv, _single_leg_samples((1010, 0, 200)))
    # tlm.read_meta_sidecar() derives '<stem>_tlm.meta.json' from
    # '<stem>_pose.csv' -- same naming this project's other tour tools
    # (tour_chart.py) already rely on.
    (tmp_path / 'dead_tlm.meta.json').write_text(json.dumps({'frames': 0}))
    monkeypatch.setattr(sys, 'argv', ['leg_analysis.py', str(pose_csv)])

    with pytest.raises(SystemExit):
        leg_analysis.main()


def test_cli_no_legs_detected_prints_a_message_instead_of_crashing(
        tmp_path, monkeypatch, capsys):
    pose_csv = tmp_path / 'still_pose.csv'
    _write_pose_csv(pose_csv, [(0, 0, 0)] * 4)  # never moves -- no legs
    monkeypatch.setattr(sys, 'argv', ['leg_analysis.py', str(pose_csv)])

    leg_analysis.main()

    assert 'no legs detected' in capsys.readouterr().out
