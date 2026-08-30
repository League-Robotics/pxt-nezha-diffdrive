"""tests/tools/test_robotlink.py -- pins sprint 024 ticket 002's two
host-side fixes in `tools/robotlink.py`, and how they compose.

**Why this exists.** Two independent bugs in `Link`/`open_link()`
combined to make a stalled radio (or serial) link unrecoverable short
of a robot reboot:

1. `sync_seq()` was off by one on a `nack` line -- it set `_seq = N` for
   BOTH `ack N` and `nack N`, which is correct for `ack` ("N was
   accepted") but wrong for `nack` ("send me N next": the next id to
   allocate must BE N, so `_seq` must land on `N - 1`). A host that
   read a live `nack 5` line used to compute `_seq = 5`, so its next
   `_format()` call allocated `#6` -- a fresh gap on the same wound.
2. `open_link()` never sent `HELLO`, the protocol's own designated
   reconnect-resync (`handleHello()`, `src/comms/wire_handler.cpp:
   640-652`), so nothing in `tools/` could clear a stalled gap.

**The composition trap this file also pins.** Sprint 024 ticket 001
removed the firmware's free-running reliability beacon. Once that
lands, there is normally NOTHING for `sync_seq()`'s passive
read-a-line loop to find immediately after `open_link()` sends `HELLO`
-- so naively calling the (now bug-fixed) `sync_seq()` right after
`HELLO` would silently degrade into a dead wait for its full default
1.5 s timeout on every single connect. `open_link()` instead calls
`Link.hello()`, which sends `HELLO`, best-effort-consumes its banner
reply, and sets `_seq = 0` unconditionally (HELLO's own contract
guarantees `expectedNext_ = 1` on the robot regardless of whether the
host manages to read the banner back). `test_open_link_never_calls_
sync_seq_and_does_not_block_on_it` below is the direct pin for this:
it proves `open_link()` never calls `sync_seq()` at all, and completes
well inside `sync_seq()`'s own default timeout even when nothing
arrives on the wire.

This file cannot run the firmware, so it cannot prove a real gap
recovers on real hardware. What it CAN prove, with no robot and no
serial port anywhere, is the same class of thing `test_run_verbs.py`/
`test_tour_capture.py` already pin in this directory: that the exact
bytes this host code writes, and the exact state it lands in, are
correct -- against a fake serial-port double matching this project's
existing `link.p` double convention (see `test_tour_capture.py`'s own
`FakePort`), extended here with `write()` capture since this file
exercises `open_link()` itself, not just a `Link`/`FakeLink` already
wrapping one.

Run with::

    uv run pytest tests/tools/test_robotlink.py
"""
import pathlib
import sys
import time

import pytest

# tests/tools/test_robotlink.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import radio_address  # noqa: E402  (path must be set up first)
import robotlink  # noqa: E402  (path must be set up first)


class FakePort:
    """Minimal serial-port double for `link.p` -- write()/readline()/
    reset_input_buffer()/close(), matching the pyserial surface
    `robotlink.py` actually calls. `incoming` is a canned, once-only
    queue of raw (undecoded) lines readline() hands back one at a time;
    once exhausted, readline() returns b'' forever -- the same "nothing
    ready yet" case `test_tour_capture.py`'s own FakePort documents,
    extended here with a `writes` log since these tests exercise
    `open_link()`'s own writes, not just a `Link` already wrapping one.
    """

    def __init__(self, incoming=()):
        self.writes = []
        self._incoming = list(incoming)

    def write(self, data):
        self.writes.append(data)

    def readline(self):
        if self._incoming:
            return self._incoming.pop(0)
        return b''

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


BANNER = b'device NEZHA2 robot vevov 1198504156\n'


# --- sync_seq()'s ack/nack branches, independent of open_link() -----------

def test_sync_seq_ack_n_sets_seq_to_n():
    port = FakePort([b'ack 7 0 none\n'])
    link = robotlink.Link(port, radio=False)

    result = link.sync_seq()

    assert result == 7
    assert link._seq == 7


def test_sync_seq_nack_n_sets_seq_to_n_minus_1():
    port = FakePort([b'nack 5 0 none\n'])
    link = robotlink.Link(port, radio=False)

    result = link.sync_seq()

    assert result == 4
    assert link._seq == 4


def test_sync_seq_nack_5_then_next_allocated_id_is_hash5_not_hash6():
    # The sprint's own pinned success criterion (sprint.md Success
    # Criteria and SUC-002's acceptance criteria): a fake link whose
    # next relevant reply is `nack 5 0 none` must yield `#5` as the
    # next allocated command id, not `#6`.
    port = FakePort([b'nack 5 0 none\n'])
    link = robotlink.Link(port, radio=False)

    link.sync_seq()
    formatted = link._format('GET')

    assert formatted == 'GET #5'


def test_sync_seq_strips_relay_prefix_before_matching():
    # The zavaz relay prefixes received frames with '< ' on its control
    # plane (Link.lines() already strips this for its own callers);
    # sync_seq() reads raw off self.p directly, so it must strip it too.
    port = FakePort([b'< nack 5 0 none\n'])
    link = robotlink.Link(port, radio=True)

    result = link.sync_seq()

    assert result == 4


# --- open_link(): HELLO before anything else, on both carriers ------------

def _patch_common(monkeypatch, port):
    # Every open_link() branch sleeps to let the device/relay settle;
    # none of that settling is what this file is testing, so it is
    # neutered to keep these tests fast. Link.hello()/sync_seq()'s own
    # timeout loops use time.time(), not time.sleep(), so this does not
    # defeat the timing assertions below -- it only removes the fixed
    # handshake delays that precede them.
    monkeypatch.setattr(robotlink.time, 'sleep', lambda *a, **k: None)
    monkeypatch.setattr(robotlink.serial, 'Serial', lambda *a, **k: port)


def test_open_link_usb_sends_hello_before_first_sequenced_verb(monkeypatch):
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    link = robotlink.open_link('/dev/fake-usb', radio=False)
    link.send('GET')

    assert port.writes == [b'HELLO\n', b'GET #1\n']


def test_open_link_radio_sends_hello_after_relay_setup_before_seq_verb(
        monkeypatch):
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    link = robotlink.open_link('/dev/fake-zavaz', radio=True)
    link.send('GET')

    # The relay's own control-plane setup (!ECHO OFF/!MODE RAW250/!CG/
    # !P/!GO) are relay commands, not robot wire commands, and must run
    # BEFORE HELLO -- which itself must precede the first sequenced
    # (#-suffixed) verb.
    # 37/43 is vevov's DERIVED pair (radio_address.name_to_address
    # ('vevov'), docs/radio-address-vectors.json) -- open_link()'s
    # default robot='vevov' with no robot= argument passed here, same
    # as the ~10 existing no-robot-argument call sites.
    assert port.writes == [
        b'!ECHO OFF\n',
        b'!MODE RAW250\n',
        b'!CG 37 43\n',
        b'!P 7\n',
        b'!GO\n',
        b'HELLO\n',
        b'GET #1\n',
    ]


def test_open_link_default_robot_is_vevov(monkeypatch):
    # Sprint 025 ticket 004: open_link() gained a robot= parameter,
    # default 'vevov'. The ~10 existing call sites all pass radio=True
    # with no robot name at all, so the default must derive the exact
    # same pair radio_address.name_to_address('vevov') does -- computed
    # here (never hardcoded a second time) so this test tracks the
    # module instead of duplicating its output.
    channel, group = radio_address.name_to_address('vevov')
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    robotlink.open_link('/dev/fake-zavaz', radio=True)

    assert f'!CG {channel} {group}\n'.encode() in port.writes


def test_open_link_robot_parameter_derives_that_robots_pair(monkeypatch):
    # Threading robot= through to a DIFFERENT board proves the pair is
    # actually derived from the argument, not just hardcoded to
    # vevov's under a new name. zetuv is a real fleet robot
    # (docs/radio-addressing.md's fleet table) whose derived pair
    # (27/21) differs from vevov's (37/43).
    channel, group = radio_address.name_to_address('zetuv')
    assert (channel, group) != radio_address.name_to_address('vevov')
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    robotlink.open_link('/dev/fake-zavaz', radio=True, robot='zetuv')

    assert f'!CG {channel} {group}\n'.encode() in port.writes
    assert b'!CG 37 43\n' not in port.writes


@pytest.mark.parametrize('radio', [False, True])
def test_open_link_hello_is_unsequenced(monkeypatch, radio):
    # HELLO's own arity is strict zero-fields (protocol.md S8.3) --
    # _format() must never append a `#<id>` to it, on either carrier.
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    robotlink.open_link('/dev/fake', radio=radio)

    assert b'HELLO\n' in port.writes
    assert not any(b'HELLO #' in w for w in port.writes)


# --- open_link() lands on _seq == 0 after HELLO, banner or not -------------

@pytest.mark.parametrize('radio', [False, True])
def test_open_link_seq_is_zero_after_hello_with_banner(monkeypatch, radio):
    port = FakePort([BANNER])
    _patch_common(monkeypatch, port)

    link = robotlink.open_link('/dev/fake', radio=radio)

    assert link._seq == 0


@pytest.mark.parametrize('radio', [False, True])
def test_open_link_seq_is_zero_after_hello_with_no_banner(monkeypatch,
                                                           radio):
    # HELLO's reset happens on the ROBOT the instant it receives the
    # line -- the host does not need to see the banner back to know
    # _seq = 0 is now correct. Nothing arrives here at all (an idle
    # FakePort, matching a robot that never replies), and _seq must
    # still land on 0, not be left unset or stuck at some other value.
    port = FakePort([])
    _patch_common(monkeypatch, port)

    link = robotlink.open_link('/dev/fake', radio=radio)

    assert link._seq == 0


# --- the composition trap: open_link() must not block on sync_seq() -------

@pytest.mark.parametrize('radio', [False, True])
def test_open_link_never_calls_sync_seq_and_does_not_block_on_it(
        monkeypatch, radio):
    # This is the ticket's own central warning, pinned directly: a
    # naive "HELLO then sync_seq()" composition degrades into a dead
    # wait for sync_seq()'s full default timeout (1.5 s) once there is
    # nothing periodic left on the wire for it to find (sprint 024
    # ticket 001). Proving open_link() never even calls sync_seq() is a
    # stronger, timing-independent pin than a wall-clock assertion
    # alone would be; the wall-clock assertion below is kept too, as a
    # second, honest confirmation that no other blocking path snuck in.
    calls = []
    monkeypatch.setattr(
        robotlink.Link, 'sync_seq',
        lambda self, timeout=1.5: calls.append(timeout))
    port = FakePort([])  # nothing ever arrives on the wire
    _patch_common(monkeypatch, port)

    start = time.time()
    link = robotlink.open_link('/dev/fake', radio=radio)
    elapsed = time.time() - start

    assert calls == [], (
        'open_link() must not call sync_seq() -- see Link.hello()\'s '
        'docstring for why that composition silently degrades into a '
        'dead wait once the firmware beacon is gone')
    assert link._seq == 0
    # hello()'s own timeout (1.0 s, strictly less than sync_seq()'s 1.5
    # s default) bounds the wait for HELLO's own reply when nothing
    # arrives; give real margin under sync_seq()'s default rather than
    # pinning hello()'s exact constant here.
    assert elapsed < 1.5, (
        f'open_link() took {elapsed:.2f}s with nothing on the wire -- '
        'this looks like a block on sync_seq()\'s full default timeout')


def test_hello_timeout_default_is_shorter_than_sync_seq_default():
    # A direct pin on the numeric relationship the trap above depends
    # on: hello()'s own default wait for HELLO's reply must stay
    # strictly shorter than sync_seq()'s default, so a future edit to
    # either constant can't silently reintroduce the dead-wait
    # composition without a test noticing.
    import inspect
    hello_default = inspect.signature(
        robotlink.Link.hello).parameters['timeout'].default
    sync_seq_default = inspect.signature(
        robotlink.Link.sync_seq).parameters['timeout'].default
    assert hello_default < sync_seq_default


# ---- unsequenced verbs (sprint-024 follow-up, 2026-08-27) ----------------

def test_unsequenced_verbs_are_not_given_ids():
    """HELLO/PING/ESTOP/HELP are the firmware's four unsequenced
    exemptions (wire_handler.cpp dispatch()). If robotlink appended an
    id to any of them, _format() would allocate an id the robot never
    consumes -- it neither acks nor advances expectedNext_ -- so the
    NEXT command would present as a numeric gap and stall the stream.
    """
    for verb in ('HELLO', 'PING', 'ESTOP', 'HELP', 'ID', 'VER', 'STATUS'):
        assert verb not in robotlink._V6_VERBS, verb


def test_get_stays_sequenced_despite_being_read_only():
    """GET is order-dependent: SET mutates what it reads, so an
    out-of-order GET would return a pre-SET value indistinguishable from
    a post-SET one. Read-only is NOT the test -- position-dependence is.
    """
    assert 'GET' in robotlink._V6_VERBS
    assert 'SET' in robotlink._V6_VERBS


def test_help_is_not_sequenced_and_does_not_consume_an_id():
    """A HELP sent mid-session must leave the sequence untouched, so the
    following real command still gets the id the robot expects."""
    port = FakePort()
    link = robotlink.Link(port, False)
    link._seq = 4
    link.send('HELP')
    assert port.writes[-1] == b'HELP\n'      # no '#' appended
    assert link._seq == 4                    # nothing consumed
    link.send('GET')
    assert port.writes[-1] == b'GET #5\n'
