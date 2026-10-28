"""tests/tools/test_mb50.py -- tools/mb50.py's parsing and scoring on
canned wire lines (no robot, no serial port).

Run with::

    uv run pytest tests/tools/test_mb50.py
"""
import pathlib
import sys

import pytest

_TOOLS = pathlib.Path(__file__).resolve().parents[2] / 'tools'
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import mb50  # noqa: E402

STATUS_LIVE = ('status ready=1 active=1 connL=1 connR=1 otos=0 wedge=0 flags=31 '
               'i2cf=1068 cyc=21114 tlm=full next=5 done=4 reason=none wifi=0 '
               'radio=0 channel=60 group=64 posmove=1')
STATUS_IDLE = STATUS_LIVE.replace('active=1', 'active=0').replace(
    'posmove=1', 'posmove=0').replace('reason=none', 'reason=stop')
STATUS_OLD = 'status ready=1 active=0 reason=stop'    # a build without posmove


def test_parse_status_reads_posmove_live_and_idle():
    assert mb50.posmove_of(mb50.parse_status(STATUS_LIVE)) == 1
    idle = mb50.parse_status(STATUS_IDLE)
    assert mb50.posmove_of(idle) == 0
    assert idle['reason'] == 'stop'
    assert idle['i2cf'] == '1068'


def test_posmove_absent_is_none_not_zero():
    assert mb50.posmove_of(mb50.parse_status(STATUS_OLD)) is None
    assert mb50.posmove_of(None) is None


@pytest.mark.parametrize('line', ['ack 3 9 stop', 'pong 12', 'get a 1', ''])
def test_parse_status_ignores_other_lines(line):
    assert mb50.parse_status(line) is None


def test_parse_get():
    assert mb50.parse_get('get wheel_diameter 90.899002') == ('wheel_diameter', 90.899002)
    assert mb50.parse_get('ack 5 3 stop') is None
    assert mb50.parse_get('get x notanumber') is None


def test_mm_per_count_is_a_tenth_of_a_degree_of_shaft():
    assert mb50.mm_per_count(90.899) == pytest.approx(0.079322, abs=1e-5)


def test_wheel_errors_forward_and_reverse_follow_command_direction():
    pc = 0.1
    tl, tr, el, er = mb50.wheel_errors((1000, 2000), (1000 + 5004, 2000 + 4996), 500, pc)
    assert (tl, tr) == (pytest.approx(500.4), pytest.approx(499.6))
    assert (el, er) == (pytest.approx(0.4), pytest.approx(-0.4))
    tl, tr, el, er = mb50.wheel_errors((6000, 7000), (6000 - 4990, 7000 - 5010), -500, pc)
    assert (el, er) == (pytest.approx(-1.0), pytest.approx(1.0))


def test_integrate_wheels_trapezoid_over_device_clock():
    frames = [{'now': 0, 'vl': 0, 'vr': 0},
              {'now': 1000, 'vl': 100, 'vr': 200},
              {'now': 2000, 'vl': 100, 'vr': 200},
              {'now': 3000, 'vl': 0, 'vr': 0}]
    assert mb50.integrate_wheels(frames) == (pytest.approx(200.0), pytest.approx(400.0))


def test_summarize_groups_by_cruise_direction_wheel():
    rows = [
        {'cruise': 250, 'mm': 500, 'err_l_mm': 0.2, 'err_r_mm': -0.2, 'ms_host': 1000},
        {'cruise': 250, 'mm': 500, 'err_l_mm': 0.4, 'err_r_mm': -0.6, 'ms_host': 1100},
        {'cruise': 250, 'mm': -500, 'err_l_mm': -1.0, 'err_r_mm': 0.1, 'ms_host': 1200},
    ]
    table = mb50.summarize(rows)
    fwd_l = next(r for r in table if r['dir'] == 'fwd' and r['wheel'] == 'l')
    assert fwd_l['n'] == 2 and fwd_l['mean'] == pytest.approx(0.3)
    assert fwd_l['worst'] == pytest.approx(0.4) and fwd_l['ms_host'] == 1050
    rev_l = next(r for r in table if r['dir'] == 'rev' and r['wheel'] == 'l')
    assert rev_l['n'] == 1 and rev_l['sd'] == 0.0 and rev_l['worst'] == -1.0
    assert len(table) == 4
