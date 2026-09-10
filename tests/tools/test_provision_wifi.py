"""tests/tools/test_provision_wifi.py -- pins `tools/provision_wifi.py`
(sprint 038 ticket 007): the scripted provisioning path over
`WIFICRED`, and -- the acceptance criterion this file exists to
enforce -- that no passphrase ever reaches this tool's stdout, stderr,
or any value it returns.

No robot and no serial port anywhere: `robotlink.Link` is driven
against the same `FakePort` double `test_robotlink.py` uses, so these
tests exercise the exact bytes this tool writes to the wire and the
exact strings it prints, with nothing live involved.

Run with::

    uv run pytest tests/tools/test_provision_wifi.py
"""
import json
import pathlib
import sys

import pytest

# tests/tools/test_provision_wifi.py -> tools -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import robotlink  # noqa: E402  (path must be set up first)
import provision_wifi  # noqa: E402


class FakePort:
    """Same double `test_robotlink.py` uses: write()/readline()/
    reset_input_buffer()/close() matching the pyserial surface
    `robotlink.py` calls, with a canned once-only `incoming` queue."""

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


class SequencedFakePort(FakePort):
    """A `FakePort` for tests that drive more than one request/reply
    pair over the SAME session. Plain `FakePort`'s `incoming` queue is
    available from the very first `readline()`, so a multi-request test
    against it lets the FIRST request's read window drain every
    canned reply, including ones for requests not sent yet -- which
    cannot happen on real hardware (the robot has nothing to reply to
    until the request arrives). Here each `write()` call unlocks the
    next `batches` entry instead, so a reply is only readable after the
    request that provokes it has actually been sent -- one real
    session's worth of `WIFICRED SET` calls, each waiting only for its
    own reply, the shape `provision_manifest()` is meant to run."""

    def __init__(self, batches):
        super().__init__()
        self._batches = [list(b) for b in batches]
        self._queue = []

    def write(self, data):
        self.writes.append(data)
        if self._batches:
            self._queue.extend(self._batches.pop(0))

    def readline(self):
        if self._queue:
            return self._queue.pop(0)
        return b''


SECRET = 'CorrectHorseBatteryStaple99'


# --- _password_from_args() -------------------------------------------------

class _Args:
    def __init__(self, password_env=None, password_file=None):
        self.password_env = password_env
        self.password_file = password_file


def test_password_from_env_var(monkeypatch):
    monkeypatch.setenv('WIFI_PW_TEST', SECRET)
    assert provision_wifi._password_from_args(
        _Args(password_env='WIFI_PW_TEST')) == SECRET


def test_password_from_missing_env_var_exits(monkeypatch):
    monkeypatch.delenv('WIFI_PW_TEST_MISSING', raising=False)
    with pytest.raises(SystemExit):
        provision_wifi._password_from_args(
            _Args(password_env='WIFI_PW_TEST_MISSING'))


def test_password_from_file(tmp_path):
    p = tmp_path / 'pw.txt'
    p.write_text(SECRET + '\n')
    assert provision_wifi._password_from_args(
        _Args(password_file=str(p))) == SECRET


# --- provision_manifest() ---------------------------------------------------

def test_provision_manifest_sets_every_entry_in_one_session(capsys):
    port = SequencedFakePort([[b'ack 1 0 none\n'], [b'ack 2 0 none\n']])
    link = robotlink.Link(port, False)
    entries = [
        {'slot': 0, 'ssid': 'MyNetwork', 'password': SECRET},
        {'slot': 1, 'ssid': 'SecondNetwork', 'password': 'hunter2example2'},
    ]
    ok = provision_wifi.provision_manifest(link, entries, wait=0.02)
    assert ok is True
    assert port.writes[0] == f'WIFICRED SET 0 MyNetwork {SECRET} #1\n'.encode()
    assert port.writes[1] == b'WIFICRED SET 1 SecondNetwork hunter2example2 #2\n'
    out, err = capsys.readouterr()
    assert SECRET not in out and SECRET not in err
    assert 'hunter2example2' not in out and 'hunter2example2' not in err


def test_provision_manifest_reports_a_rejected_slot(capsys):
    port = FakePort([b'ack 1 0 none\n', b'err 5 #1\n'])
    link = robotlink.Link(port, False)
    ok = provision_wifi.provision_manifest(
        link, [{'slot': 0, 'ssid': 'MyNetwork', 'password': SECRET}], wait=0.05)
    assert ok is False
    out, _err = capsys.readouterr()
    assert 'err 5' in out
    assert SECRET not in out


# --- _report() ---------------------------------------------------------------

def test_report_ok_on_ack_only(capsys):
    assert provision_wifi._report(0, ['ack 1 0 none']) is True
    out, _ = capsys.readouterr()
    assert 'slot 0: ok' in out


def test_report_not_ok_on_err(capsys):
    assert provision_wifi._report(3, ['ack 1 0 none', 'err 2 #1']) is False
    out, _ = capsys.readouterr()
    assert 'slot 3' in out and 'err 2' in out


def test_report_not_ok_on_no_reply(capsys):
    assert provision_wifi._report(0, []) is False


# --- main(): argument wiring and the end-to-end no-leak pin -----------------

def test_main_list_never_prints_a_password(monkeypatch, capsys):
    port = FakePort([
        b'wificred 0 1 MyNetwork\n',
        b'wificred 1 1 SecondNetwork\n',
        b'ack 1 0 none\n',
    ])
    link = robotlink.Link(port, False)
    monkeypatch.setattr(robotlink, 'open_link', lambda **kw: link)
    monkeypatch.setattr(
        sys, 'argv', ['provision_wifi.py', '--usb', '/dev/fake', '--list'])
    rc = provision_wifi.main()
    assert rc == 0
    out, err = capsys.readouterr()
    assert 'MyNetwork' in out
    assert 'password set: True' in out
    assert SECRET not in out and SECRET not in err


def test_main_set_reads_password_from_env_and_never_prints_it(
        monkeypatch, capsys):
    port = FakePort([b'ack 1 0 none\n'])
    link = robotlink.Link(port, False)
    monkeypatch.setattr(robotlink, 'open_link', lambda **kw: link)
    monkeypatch.setenv('WIFI_PW_MAIN_TEST', SECRET)
    monkeypatch.setattr(sys, 'argv', [
        'provision_wifi.py', '--usb', '/dev/fake',
        '--slot', '0', '--ssid', 'MyNetwork',
        '--password-env', 'WIFI_PW_MAIN_TEST',
    ])
    rc = provision_wifi.main()
    assert rc == 0
    assert port.writes[-1] == f'WIFICRED SET 0 MyNetwork {SECRET} #1\n'.encode()
    out, err = capsys.readouterr()
    assert SECRET not in out and SECRET not in err


def test_main_manifest_provisions_the_whole_list_in_one_session(
        monkeypatch, capsys, tmp_path):
    port = SequencedFakePort([[b'ack 1 0 none\n'], [b'ack 2 0 none\n']])
    link = robotlink.Link(port, False)
    monkeypatch.setattr(robotlink, 'open_link', lambda **kw: link)
    manifest = tmp_path / 'creds.json'
    manifest.write_text(json.dumps([
        {'slot': 0, 'ssid': 'MyNetwork', 'password': SECRET},
        {'slot': 1, 'ssid': 'SecondNetwork', 'password': 'hunter2example2'},
    ]))
    monkeypatch.setattr(sys, 'argv', [
        'provision_wifi.py', '--usb', '/dev/fake', '--manifest', str(manifest),
    ])
    rc = provision_wifi.main()
    assert rc == 0
    assert len(port.writes) == 2
    out, err = capsys.readouterr()
    assert SECRET not in out and SECRET not in err


def test_main_clear_sends_the_clear_line(monkeypatch):
    port = FakePort([b'ack 1 0 none\n'])
    link = robotlink.Link(port, False)
    monkeypatch.setattr(robotlink, 'open_link', lambda **kw: link)
    monkeypatch.setattr(
        sys, 'argv', ['provision_wifi.py', '--usb', '/dev/fake', '--clear', '2'])
    rc = provision_wifi.main()
    assert rc == 0
    assert port.writes[-1] == b'WIFICRED CLEAR 2 #1\n'


def test_main_slot_without_ssid_errors(monkeypatch):
    monkeypatch.setattr(
        sys, 'argv',
        ['provision_wifi.py', '--usb', '/dev/fake', '--slot', '0'])
    with pytest.raises(SystemExit):
        provision_wifi.main()
