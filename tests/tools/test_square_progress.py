"""tests/tools/test_square_progress.py -- tools/square_progress.py on
synthetic normalized lap CSVs (two sets, two laps each; no robot).

Run with::

    uv run --with numpy --with matplotlib pytest tests/tools/test_square_progress.py
"""
import pathlib
import sys

import pytest

pytest.importorskip('matplotlib')

_TOOLS = pathlib.Path(__file__).resolve().parents[2] / 'tools'
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import square_progress  # noqa: E402


def _lap(path, end):
    pts = [(0, 0), (500, 0), (500, 500), (0, 500), end]
    lines = ['t_host,t_dev_ms,x_mm,y_mm,h_cdeg,ox_mm,oy_mm,oh_cdeg']
    lines += [f'{i},{i},{x},{y},0,0,0,0' for i, (x, y) in enumerate(pts)]
    path.write_text('\n'.join(lines) + '\n')


def test_closures_and_png(tmp_path):
    for name, ends in (('a', [(3, 4), (0, 10)]), ('b', [(0, 0), (6, 8)])):
        d = tmp_path / name
        d.mkdir()
        for n, end in enumerate(ends, 1):
            _lap(d / f'lap{n}_pose.csv', end)
    sets = [square_progress.load_set('A', str(tmp_path / 'a')),
            square_progress.load_set('B', str(tmp_path / 'b'))]
    assert sets[0]['closures'] == pytest.approx([5.0, 10.0])
    assert sets[0]['mean'] == pytest.approx(7.5)
    assert sets[1]['closures'] == pytest.approx([0.0, 10.0])
    assert sets[1]['worst'] == pytest.approx(10.0)
    out = tmp_path / 'p.png'
    square_progress.main(['--set', f'A={tmp_path / "a"}',
                          '--set', f'B={tmp_path / "b"}',
                          '--out', str(out), '--date', '2026-10-27'])
    assert out.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
