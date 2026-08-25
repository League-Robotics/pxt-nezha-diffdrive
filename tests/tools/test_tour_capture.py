"""tests/tools/test_tour_capture.py -- pins the `RUN:tour:<name>` verb
`tools/tour_capture.py` sends after sprint 011 ticket 001's retarget
off the dead numeric `RUN:<n>` vocabulary.

**Why this exists.** `tour_capture.py` used to select a tour with
`--run <n>` and send a bare `RUN:<n>` (`link.send_until(f'RUN:{a.run}',
...)`). Current firmware's `test.ts` registers only named
`diffDrive.onRun(...)` handlers -- no numeric name is registered
anywhere -- so `RUN:1` (or any other number) was a silent no-op against
current hardware: the tool ran to completion and wrote CSVs, but the
robot never moved. `tour_run.py` already speaks the named
`RUN:tour:{world,robot,wheels}` vocabulary; this ticket brings
`tour_capture.py` to the same shape.

This file cannot run the firmware, so it cannot prove the robot moves.
What it CAN prove, with no robot and no serial port, is the one thing
that was silently false before: that `tour_capture.py`'s own
RUN-sending code path actually calls `link.send_until()` with the
exact `RUN:tour:<name>` string current firmware's `onRun()` dispatch
answers to -- not a numeric string no handler will ever match.

The telemetry-parsing path (`tlm.require_stream`/`tlm.write_tlm_csv`)
is out of this ticket's scope (untouched by its diff), so it is
stubbed out here rather than exercised -- this file only asserts what
the ticket changed: argument parsing and the `RUN:` verb construction.

Run with::

    uv run pytest tests/tools/test_tour_capture.py
"""
import pathlib
import sys

import pytest

# tests/tools/test_tour_capture.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import tour_capture  # noqa: E402  (path must be set up first)


class FakePort:
    """Minimal serial-port double for `link.p` -- `tour_capture.main()`
    only ever calls `readline()` on it, and an empty read is a valid,
    common case (no line ready yet) that the real loop already handles
    via `if not line: continue`."""

    def readline(self):
        return b''


class FakeLink:
    """Minimal double for `robotlink.Link` -- just enough surface for
    `tour_capture.main()` to run to completion: `.p` (the fake port
    above), `send_until()` (records what it was called with, exactly
    as the real implementation's send-then-wait shape would receive
    it), and `close()`."""

    def __init__(self):
        self.sent_until = []
        self.p = FakePort()

    def send(self, line, repeat=1):
        pass

    def send_until(self, line, expect, tries=3, wait=5.0, echo=True):
        self.sent_until.append(line)
        return []

    def close(self):
        pass


class FakeStream:
    def feed(self, line):
        return None


def _run_main(monkeypatch, tmp_path, argv_tail):
    fake = FakeLink()
    monkeypatch.setattr(tour_capture, 'open_link', lambda *a, **k: fake)
    monkeypatch.setattr(tour_capture.tlm, 'require_stream',
                        lambda link, timeout=3.0: FakeStream())
    monkeypatch.setattr(
        tour_capture.tlm, 'write_tlm_csv',
        lambda stream, path: {'frames': 0, 'dropped': 0, 'loss_pct': 0.0})
    monkeypatch.setattr(
        sys, 'argv',
        ['tour_capture.py', '--radio', '--timeout', '0.01',
         '--out-prefix', str(tmp_path / 'tour')] + argv_tail)

    tour_capture.main()
    return fake


def test_default_tour_sends_run_tour_world_not_bare_run_1(
        monkeypatch, tmp_path):
    fake = _run_main(monkeypatch, tmp_path, [])

    assert fake.sent_until == ['RUN:tour:world']


@pytest.mark.parametrize('tour', ['world', 'robot', 'wheels'])
def test_tour_flag_sends_the_matching_named_run_tour_verb(
        tour, monkeypatch, tmp_path):
    fake = _run_main(monkeypatch, tmp_path, ['--tour', tour])

    assert fake.sent_until == [f'RUN:tour:{tour}']
    # the old numeric vocabulary must never resurface alongside the
    # named form
    assert not any(s.startswith('RUN:') and s.split(':', 1)[1].isdigit()
                   for s in fake.sent_until)


def test_unknown_tour_name_is_rejected_by_argparse(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, 'argv',
        ['tour_capture.py', '--radio', '--tour', 'bogus'])

    with pytest.raises(SystemExit):
        tour_capture.main()
