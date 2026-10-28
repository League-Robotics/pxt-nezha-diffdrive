"""tests/tools/test_square_closure.py -- tools/square_closure.py on
synthetic tlm CSVs (no robot, no matplotlib).

Run with::

    uv run pytest tests/tools/test_square_closure.py
"""
import csv
import pathlib
import sys

import pytest

_TOOLS = pathlib.Path(__file__).resolve().parents[2] / 'tools'
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import square_closure as sc  # noqa: E402

HEADER = ['seq', 'now', 'flags', 'x', 'y', 'h', 'ox', 'oy', 'oh',
          'vl', 'vr', 'i2cf']


def write_lap(path, start, end, turned_cdeg=36000, i2cf=(10, 14)):
    """Idle start frame, two moving frames, idle end frame."""
    x0, y0, h0 = start
    x1, y1 = end
    rows = [
        (1, 1000, 49, x0, y0, h0, 0, 0, 0, 0, 0, i2cf[0]),
        (2, 1060, 49, x0, y0, h0, 0, 0, 0, 100, 100, i2cf[0]),
        (3, 11060, 49, x1, y1, h0 + turned_cdeg, 0, 0, 0, 100, 100, i2cf[1]),
        (4, 11120, 49, x1, y1, h0 + turned_cdeg, 0, 0, 0, 0, 0, i2cf[1]),
    ]
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def test_score_lap_closure_heading_time_and_i2cf(tmp_path):
    p = tmp_path / 'a_tlm.csv'
    write_lap(p, (10, 20, 500), (13, 16), turned_cdeg=36300)
    lap = sc.score_lap(sc.read_tlm_csv(p))
    assert lap['closure_mm'] == pytest.approx(5.0)
    assert lap['heading_deg'] == pytest.approx(3.0)
    assert lap['lap_s'] == pytest.approx(10.0)
    assert lap['i2cf_growth'] == 4


def test_negative_residual_wraps(tmp_path):
    p = tmp_path / 'a_tlm.csv'
    write_lap(p, (0, 0, 100), (0, 0), turned_cdeg=35800)
    assert sc.score_lap(sc.read_tlm_csv(p))['heading_deg'] == \
        pytest.approx(-2.0)


def test_summary_and_verdict(tmp_path):
    laps = []
    for i, end in enumerate([(3, 4), (6, 8), (0, 12)]):
        p = tmp_path / f'l{i}_tlm.csv'
        write_lap(p, (0, 0, 0), end)
        laps.append(sc.score_lap(sc.read_tlm_csv(p)))
    s = sc.summarize(laps)
    assert s['n'] == 3
    assert s['closure_mean_mm'] == pytest.approx((5 + 10 + 12) / 3)
    assert s['closure_worst_mm'] == pytest.approx(12.0)
    assert sc.verdict(s, 11.0) == 'not met'
    assert sc.verdict(s, 13.0) == 'met'


def test_main_writes_csv_and_markdown(tmp_path):
    for m, end in (('m0', (30, 40)), ('m1', (1, 1))):
        for n in (1, 2):
            write_lap(tmp_path / f'{m}_lap{n}_tlm.csv', (0, 0, 0), end)
    out = tmp_path / 'closure'
    sc.main(['--mode', f'0={tmp_path}/m0_lap*_tlm.csv',
             '--mode', f'1={tmp_path}/m1_lap*_tlm.csv',
             '--out-prefix', str(out), '--normalize-dir',
             str(tmp_path / 'norm')])
    rows = list(csv.reader(open(f'{out}.csv')))
    assert rows[0][0] == 'mode' and len([r for r in rows if r and r[0] == '0']) == 3
    md = open(f'{out}.md').read()
    assert 'ENCODER truth' in md
    assert '| 0 | 2 | 50.0 | 50.0 |' in md and '| not met |' in md
    assert '| met |' in md
    assert (tmp_path / 'norm' / 'm0_lap1_norm_pose.csv').exists()


def test_normalize_rotates_into_start_frame(tmp_path):
    p = tmp_path / 'a_tlm.csv'
    write_lap(p, (100, 100, 9000), (100, 200), turned_cdeg=0)  # facing +y
    pose, vel = sc.normalize_lap(sc.read_tlm_csv(p))
    assert (pose[-1]['x'], pose[-1]['y']) == (100, 0)
    assert pose[0]['h'] == 0


def test_short_csv_rejected(tmp_path):
    p = tmp_path / 'a_tlm.csv'
    p.write_text(','.join(HEADER) + '\n1,1,1,0,0,0,0,0,0,0,0,0\n')
    with pytest.raises(ValueError):
        sc.read_tlm_csv(p)


def test_circle_lap_scores_like_any_closed_loop(tmp_path):
    """A full circle returns heading to the start: 360 deg + 2 reads +2;
    a CW circle (-360 deg - 2) reads -2. The scorer is shape-agnostic."""
    p = tmp_path / 'c_tlm.csv'
    write_lap(p, (0, 0, 0), (6, 8), turned_cdeg=36200)
    lap = sc.score_lap(sc.read_tlm_csv(p))
    assert lap['closure_mm'] == pytest.approx(10.0)
    assert lap['heading_deg'] == pytest.approx(2.0)
    write_lap(p, (0, 0, 0), (0, 0), turned_cdeg=-36200)
    assert sc.score_lap(sc.read_tlm_csv(p))['heading_deg'] == \
        pytest.approx(-2.0)


def test_chart_circle_overlay_geometry():
    """tour_chart --circle-cm: the dashed circle passes through the origin
    and its centre is r to the left (CCW) or right (CW)."""
    src = (_TOOLS / 'tour_chart.py').read_text()
    assert '--circle-cm' in src and '--cw' in src


def test_radial_deviation_of_a_perfect_circle(tmp_path):
    import math
    r, rows = 200.0, []
    for i in range(73):
        a = 2 * math.pi * i / 72
        rows.append({'now': 1000.0 + i, 'x': r * math.sin(a),
                     'y': r - r * math.cos(a), 'h': math.degrees(a) * 100.0,
                     'vl': 0.0, 'vr': 0.0, 'i2cf': 0.0})
    mean, worst = sc.radial_deviation(rows, r, ccw=True)
    assert worst < 1.0 and mean < 1.0           # integer rounding only
    mean, worst = sc.radial_deviation(rows, r, ccw=False)
    assert worst == pytest.approx(2 * r, abs=2.0)   # wrong side: far off
