"""tests/tools/test_run_verbs.py -- pins the RUN strings five bench
tools send after sprint 005 ticket 006's retarget off the dead numeric
RUN vocabulary.

**Why this exists.** `otos_levercal.py`, `pivot_truth.py`,
`truth_check.py`, `rotation_check.py` and `turn_sweep.py` used to send
`RUN:8`/`RUN:14`/`RUN:10`/`RUN:2`/`RUN:4`/`RUN:5`/`RUN:{57000+rate}`/
`RUN:{58360+deg}` -- numeric commands current firmware's string-keyed
`onRun()` dispatch (`test.ts`) never registers, so every one of these
tools was a silent no-op: it ran to completion, printed numbers, and
measured nothing, because the robot never received a single command.
Two of the five (`otos_levercal.py`'s `RUN:8`/`RUN:14`,
`pivot_truth.py`/`truth_check.py`/`rotation_check.py`'s `RUN:10`) had
real named equivalents already on `test.ts` (`RUN:cal`/`RUN:cal:1`,
`RUN:fix`) and needed only a Python-side rename. The remaining piece --
a relative pivot and a settable turn rate -- needed two new `test.ts`
verbs (`RUN:pivot:<deg>`, `RUN:turnrate:<rate>`), added by this same
ticket.

This file cannot run the firmware, so it cannot prove the robot moves.
What it CAN prove, with no robot and no serial port, is the one thing
that was silently false before: that each tool's own RUN-sending code
path actually calls `link.send()`/`link.send_until()` with the exact
string a `diffDrive.onRun(...)` handler on current `test.ts` answers
to -- not a numeric string no handler will ever match. Every test below
asserts the exact string a fake link received AND that none of the old
dead numeric forms are anywhere in what was sent, so a regression back
to the numeric vocabulary fails loudly instead of silently.

Run with::

    uv run pytest tests/tools/test_run_verbs.py
"""
import pathlib
import sys
import threading

import pytest

# tests/tools/test_run_verbs.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import otos_levercal  # noqa: E402  (path must be set up first)
import pivot_truth  # noqa: E402  (ditto)
import rotation_check  # noqa: E402  (ditto)
import truth_check  # noqa: E402  (ditto)
import turn_sweep  # noqa: E402  (ditto)


class FakeLink:
    """Minimal send()/send_until()/lines() double matching
    robotlink.Link's own surface -- no real serial/radio anywhere in
    this file. `send_until()` mirrors the real implementation exactly
    (send, then scan `lines()` for the expected prefix, resending on a
    miss) so a test exercising it is exercising the same control flow
    the real tools run, not a reimplementation of it.
    """

    def __init__(self, incoming=()):
        self.sent = []
        self._incoming = list(incoming)
        self._pos = 0

    def send(self, line, repeat=1):
        for _ in range(repeat):
            self.sent.append(line)

    def send_until(self, line, expect, tries=3, wait=5.0, echo=True):
        seen = []
        for _attempt in range(tries):
            self.send(line)
            for s in self.lines(wait):
                seen.append(s)
                if s.startswith(expect):
                    return seen
        return seen

    def lines(self, timeout, until=None):
        # A real Link blocks up to `timeout`; this double resolves
        # deterministically from a canned, once-only line queue instead
        # -- no sleeping, no flakiness, and no risk of replaying an
        # already-delivered line the way a naive "yield self._incoming
        # every call" double would.
        while self._pos < len(self._incoming):
            s = self._incoming[self._pos]
            self._pos += 1
            yield s
            if until and s.startswith(until):
                return

    def close(self):
        pass


# The old dead numeric vocabulary this ticket retargets away from --
# asserted ABSENT from every tool's sent lines below, not just that the
# new named form is present. A test that only checks the new string
# would still pass if a stray old one snuck back in alongside it.
DEAD_NUMERIC_FORMS = ('RUN:8', 'RUN:14', 'RUN:10', 'RUN:2', 'RUN:4',
                      'RUN:5')


def _assert_no_dead_numeric_forms(sent):
    for line in sent:
        assert not any(line == dead for dead in DEAD_NUMERIC_FORMS), (
            f'dead numeric RUN form resurfaced: {line!r}')
        assert '57000' not in line and '58360' not in line, (
            f'dead numeric turn-rate/pivot offset resurfaced: {line!r}')


# --- otos_levercal.py: RUN:8/RUN:14 -> RUN:cal/RUN:cal:1 -----------------

# Four pivot fixes on a clean 5 mm-radius circle (cx=cy=0, arm ox=50,
# oy=0 in the OCAL wire's 0.1 mm units) at 0/90/180/270 deg -- enough
# points, well-conditioned, for solve_lstsq() to succeed without ever
# needing this file to care about the fitted numbers themselves. p0 is
# deliberately included (and, per otos_levercal.py's own comment,
# deliberately excluded from the fit) to match a real OCAL:begin..end
# transcript's shape.
OCAL_TRANSCRIPT = [
    'OCAL:begin',
    'OCAL:p0:0:0:0',
    'OCAL:p1:500:0:0',
    'OCAL:p2:0:500:9000',
    'OCAL:p3:-500:0:18000',
    'OCAL:p4:0:-500:27000',
    'OCAL:end',
]


def test_otos_levercal_default_sends_run_cal_not_run8(monkeypatch):
    fake = FakeLink(OCAL_TRANSCRIPT)
    monkeypatch.setattr(otos_levercal, 'open_link', lambda *a, **k: fake)
    monkeypatch.setattr(sys, 'argv', ['otos_levercal.py', '--radio'])

    otos_levercal.main()

    assert fake.sent == ['RUN:cal']
    _assert_no_dead_numeric_forms(fake.sent)


def test_otos_levercal_verify_sends_run_cal_1_not_run14(monkeypatch):
    fake = FakeLink(OCAL_TRANSCRIPT)
    monkeypatch.setattr(otos_levercal, 'open_link', lambda *a, **k: fake)
    monkeypatch.setattr(sys, 'argv',
                        ['otos_levercal.py', '--radio', '--verify'])

    otos_levercal.main()

    assert fake.sent == ['RUN:cal:1']
    _assert_no_dead_numeric_forms(fake.sent)


# --- pivot_truth.py / truth_check.py: RUN:10 -> RUN:fix -------------------
# Both files define their own otos_fix()/send_pivot() (not shared code),
# so both get their own tests -- a shared helper elsewhere could drift
# out of sync with one of the two copies without either test noticing.

OCAL_NOW_LINE = 'OCAL:now:123:45:6789'


def test_pivot_truth_otos_fix_sends_run_fix_not_run10():
    fake = FakeLink([OCAL_NOW_LINE])

    result = pivot_truth.otos_fix(fake)

    assert fake.sent == ['RUN:fix']
    _assert_no_dead_numeric_forms(fake.sent)
    assert result == (12.3, 4.5, 67.89)


def test_truth_check_otos_fix_sends_run_fix_not_run10():
    fake = FakeLink([OCAL_NOW_LINE])

    result = truth_check.otos_fix(fake)

    assert fake.sent == ['RUN:fix']
    _assert_no_dead_numeric_forms(fake.sent)
    assert result == (12.3, 4.5, 67.89)


def test_rotation_check_fix_sends_run_fix_not_run10():
    fake = FakeLink([OCAL_NOW_LINE])

    result = rotation_check.fix(fake)

    assert fake.sent == ['RUN:fix']
    _assert_no_dead_numeric_forms(fake.sent)
    assert result == (12.3, 4.5, 67.89)


# --- pivot_truth.py / truth_check.py / rotation_check.py: the old
# PIVOT_VERB={180:4,-180:5,360:2} lookup -> RUN:pivot:<deg> -----------

@pytest.mark.parametrize('deg', [180, -180, 360, 45])
def test_pivot_truth_send_pivot_sends_the_degree_value_directly(deg):
    fake = FakeLink(['GAP:0'])

    pivot_truth.send_pivot(fake, deg)

    assert fake.sent == [f'RUN:pivot:{deg}']
    _assert_no_dead_numeric_forms(fake.sent)


@pytest.mark.parametrize('deg', [180, -180, 360, 45])
def test_truth_check_send_pivot_sends_the_degree_value_directly(deg):
    fake = FakeLink(['GAP:0'])

    truth_check.send_pivot(fake, deg)

    assert fake.sent == [f'RUN:pivot:{deg}']
    _assert_no_dead_numeric_forms(fake.sent)


@pytest.mark.parametrize('deg', [180, -180, 360, 45])
def test_rotation_check_send_pivot_sends_the_degree_value_directly(deg):
    fake = FakeLink(['GAP:0'])

    rotation_check.send_pivot(fake, deg)

    assert fake.sent == [f'RUN:pivot:{deg}']
    _assert_no_dead_numeric_forms(fake.sent)


def test_pivot_truth_pivot_verb_table_is_gone():
    # This ticket's own implementation note: the new verb takes an
    # arbitrary degree value, so there is no fixed 3-way table left to
    # accidentally reintroduce a numeric-offset lookup into.
    assert not hasattr(pivot_truth, 'PIVOT_VERB')


def test_truth_check_pivot_verb_table_is_gone():
    assert not hasattr(truth_check, 'PIVOT_VERB')


def test_rotation_check_pivots_are_bare_degrees_not_verb_pairs():
    # PIVOTS used to be [(2, 360.0), (4, 180.0), (5, -180.0)] -- pairs
    # of (dead numeric verb, degrees). Confirms it is now just degrees.
    assert rotation_check.PIVOTS == [360.0, 180.0, -180.0]


# --- turn_sweep.py: RUN:{57000+rate}/RUN:{58360+deg} ---------------------
# -> RUN:turnrate:<rate> then RUN:pivot:<deg> ------------------------------

class _FakeCam:
    """Just enough of tools/camproc.py's Cam surface for _yaw_mark():
    a lock and a (possibly empty) samples list. one_turn() sends BOTH
    RUN commands before it ever inspects camera sample counts, so an
    empty/static double is sufficient to observe what got sent -- the
    eventual "not enough camera samples" outcome this produces is not
    what this test is checking.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.samples = []
        self.err = None


def test_one_turn_sends_named_turnrate_then_pivot_not_numeric_offsets(
        monkeypatch):
    monkeypatch.setattr(turn_sweep.time, 'sleep', lambda *a, **k: None)
    fake = FakeLink([])  # no TRN: reply -- matches current firmware
    cam = _FakeCam()

    turn_sweep.one_turn(fake, cam, deg=90, rate=45, settle=0)

    assert fake.sent == ['RUN:turnrate:45', 'RUN:pivot:90']
    _assert_no_dead_numeric_forms(fake.sent)


def test_one_turn_negative_degrees_still_send_the_signed_value(
        monkeypatch):
    monkeypatch.setattr(turn_sweep.time, 'sleep', lambda *a, **k: None)
    fake = FakeLink([])
    cam = _FakeCam()

    turn_sweep.one_turn(fake, cam, deg=-90, rate=180, settle=0)

    assert fake.sent == ['RUN:turnrate:180', 'RUN:pivot:-90']
    _assert_no_dead_numeric_forms(fake.sent)
