"""tests/tools/test_wire_acceptance_radio_link.py -- pins sprint 025
ticket 004's `tools/wire_acceptance.py` changes: `RadioLink` gains an
explicit `group=` parameter (default 10, unchanged behavior for a bare
channel with no robot identity), and `main()` gains a `--robot NAME`
path that derives BOTH `(channel, group)` from
`radio_address.name_to_address()` instead of hardcoding group 10.

**Why `--radio CH` keeps group 10 forever.** Per `docs/radio-
addressing.md`, group is not a function of channel alone -- 125 names
share each channel, with different groups -- so a bare channel number
has no way to recover a SPECIFIC robot's group. `--radio CH` is the
correct tool for manual dialing and un-migrated boards (group 10 by
convention); `--robot NAME` is the only path that can derive a real
robot's actual pair. This file proves both paths keep sending their
own values and never bleed into each other.

No real socket is opened anywhere in this file -- `RadioLink.__init__`
does a real `socket.create_connection()`, so every test monkeypatches
the top-level `socket.create_connection` with a double before
constructing one.

Run with::

    uv run pytest tests/tools/test_wire_acceptance_radio_link.py -v
"""
import pathlib
import socket as socket_module
import sys

# tests/tools/test_wire_acceptance_radio_link.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import radio_address  # noqa: E402  (path must be set up first)
import wire_acceptance  # noqa: E402  (path must be set up first)


class _FakeSocket:
    """Minimal socket double for `RadioLink` -- records every
    `sendall()` call and answers `recv()` with `b''` immediately, so
    `RadioLink.read()`'s real-time-driven loop (it polls `time.time()`
    directly, not `time.sleep()`) breaks out on its very first
    iteration ("connection closed") instead of busy-waiting out its
    full multi-second budget.
    """

    def __init__(self):
        self.sent = []

    def settimeout(self, seconds):
        pass

    def recv(self, n):
        return b''

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        pass


def _patch_common(monkeypatch):
    """Neuter the real socket and the handshake's fixed sleeps -- none
    of that is what these tests exercise -- and return the fake socket
    so callers can inspect what `RadioLink` sent on it."""
    fake = _FakeSocket()
    monkeypatch.setattr(wire_acceptance.time, 'sleep', lambda *a, **k: None)
    monkeypatch.setattr(
        socket_module, 'create_connection', lambda *a, **k: fake)
    return fake


# --- RadioLink: group defaults to 10, an explicit group overrides it ------

def test_radio_link_default_group_is_10(monkeypatch):
    fake = _patch_common(monkeypatch)

    wire_acceptance.RadioLink(4)

    sent = [d.decode() for d in fake.sent]
    assert '!CG 4 10\n' in sent


def test_radio_link_explicit_group_overrides_default(monkeypatch):
    fake = _patch_common(monkeypatch)

    wire_acceptance.RadioLink(37, group=43)

    sent = [d.decode() for d in fake.sent]
    assert '!CG 37 43\n' in sent
    assert not any(s.startswith('!CG 37 10') for s in sent)


# --- main(): --robot derives both values; --radio keeps group 10 ---------

class _SpyLink:
    """Stand-in for `RadioLink` in `main()` tests -- records the exact
    constructor args `main()` passed, and answers `ask()`/`close()` as
    a robot that never replies. That drives `main()` down its
    shortest real path (the "no HELLO banner -- ABORT" branch, `return
    3`) without needing to fake an entire wire-protocol conversation --
    argument resolution and `RadioLink` construction happen before
    that abort check, so this still exercises exactly what these tests
    are pinning.
    """
    calls = []

    def __init__(self, *args, **kwargs):
        _SpyLink.calls.append((args, kwargs))

    def ask(self, *args, **kwargs):
        return []

    def close(self):
        pass


def test_main_robot_flag_derives_channel_and_group(monkeypatch, capsys):
    _SpyLink.calls = []
    monkeypatch.setattr(wire_acceptance, 'RadioLink', _SpyLink)
    monkeypatch.setattr(sys, 'argv', ['wire_acceptance.py', '--robot', 'vevov'])
    expected_channel, expected_group = radio_address.name_to_address('vevov')

    rc = wire_acceptance.main()

    assert rc == 3   # no HELLO banner from the spy -- expected abort path
    assert _SpyLink.calls == [
        ((expected_channel,), {'group': expected_group})]
    out = capsys.readouterr().out
    assert f'radio vevov (ch{expected_channel}/grp{expected_group})' in out


def test_main_radio_flag_keeps_group_10_default(monkeypatch, capsys):
    _SpyLink.calls = []
    monkeypatch.setattr(wire_acceptance, 'RadioLink', _SpyLink)
    monkeypatch.setattr(sys, 'argv', ['wire_acceptance.py', '--radio', '4'])

    rc = wire_acceptance.main()

    assert rc == 3
    # --radio's contract is unchanged: a bare channel, no group kwarg
    # at all -- RadioLink's own group=10 default applies.
    assert _SpyLink.calls == [((4,), {})]
    out = capsys.readouterr().out
    assert 'radio ch4' in out


def test_main_robot_and_radio_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['wire_acceptance.py', '--robot', 'vevov', '--radio', '4'])

    try:
        wire_acceptance.main()
        assert False, 'expected argparse to reject --robot with --radio'
    except SystemExit as e:
        assert e.code == 2   # argparse's usage-error exit code
