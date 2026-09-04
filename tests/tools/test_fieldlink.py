"""tests/tools/test_fieldlink.py -- pins `tools/fieldlink.py`'s two
carriers, `FieldLink` (lossy torture relay) and `TcpFieldLink` (direct
lossless TCP to a farm node's serial daemon, e.g. tovez's on-robot
`zilch` Pi -- sprint 029 ticket 007, 2026-09-04d session).

Both must expose the SAME sequenced-wire contract
(`unseq`/`seqd`/`hello`/`close`) so a caller like `field_dance.py` can
pick either one via `--tcp host:port` without any other code branching
on which carrier it is driving over. This file proves that contract
against a real loopback TCP socket -- no robot, no relay -- by running
a tiny fake line-server in a background thread that answers the exact
handshake each carrier performs, then exercising `unseq`/`seqd`/
`hello`.

Run with::

    uv run pytest tests/tools/test_fieldlink.py
"""
import pathlib
import socket
import sys
import threading
import time

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / 'tools'
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from fieldlink import FieldLink, TcpFieldLink  # noqa: E402


class _FakeLineServer:
    """A loopback TCP server that speaks the same newline-delimited
    ASCII protocol as the torture relay / a farm serial daemon.
    `responder(line) -> str | None` decides what (if anything) to send
    back for each received line; it may also return a list of lines."""

    def __init__(self, responder):
        self._responder = responder
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self.received = []
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        self._sock.settimeout(0.2)
        conn = None
        while not self._stop:
            if conn is None:
                try:
                    conn, _ = self._sock.accept()
                    conn.settimeout(0.1)
                except socket.timeout:
                    continue
            try:
                buf = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not buf:
                conn = None
                continue
            for raw in buf.decode('ascii', 'replace').splitlines():
                line = raw.strip()
                if not line:
                    continue
                self.received.append(line)
                reply = self._responder(line)
                if reply is None:
                    continue
                if isinstance(reply, str):
                    reply = [reply]
                for r in reply:
                    try:
                        conn.sendall((r + '\n').encode())
                    except OSError:
                        pass

    def close(self):
        self._stop = True
        self._thread.join(timeout=2)
        self._sock.close()


def test_tcpfieldlink_connects_with_no_relay_tuning():
    """TcpFieldLink is a direct pipe: it must NOT send `!CG`/`!GO`
    relay-tuning lines the way FieldLink does -- those are meaningless
    (and would just be unrecognized junk) to a farm serial daemon."""
    srv = _FakeLineServer(lambda line: None)
    try:
        link = TcpFieldLink(f'127.0.0.1:{srv.port}')
        time.sleep(0.3)
        link.close()
    finally:
        srv.close()
    assert not any(l.startswith('!CG') or l.startswith('!GO')
                   for l in srv.received)


def test_tcpfieldlink_hello_resets_seq_and_returns_device_line():
    def responder(line):
        if line == 'HELLO':
            return 'device NEZHA2 robot tovez 1234567890'
        return None

    srv = _FakeLineServer(responder)
    try:
        link = TcpFieldLink(f'127.0.0.1:{srv.port}')
        link._seq = 7  # simulate a prior session's counter
        reply = link.hello()
        assert reply == 'device NEZHA2 robot tovez 1234567890'
        assert link._seq == 0
        link.close()
    finally:
        srv.close()


def test_tcpfieldlink_seqd_reuses_id_across_retries_until_ack():
    """A resend must reuse its ORIGINAL id -- a resend with a fresh id
    presents as a numeric gap and stalls the stream on purpose
    (.claude/rules/playfield-testing.md)."""
    seen_ids = []
    attempt = {'n': 0}

    def responder(line):
        if line.startswith('SET '):
            # record the id used, drop the first two attempts (simulate
            # loss), then ack on the third.
            wire_id = line.rsplit('#', 1)[-1]
            seen_ids.append(wire_id)
            attempt['n'] += 1
            if attempt['n'] < 3:
                return None
            return f'ack {wire_id} stop'
        return None

    srv = _FakeLineServer(responder)
    try:
        link = TcpFieldLink(f'127.0.0.1:{srv.port}')
        result = link.seqd('SET lag 0.1', tries=5, sec=0.5)
        link.close()
    finally:
        srv.close()

    assert result == 'ack 1 stop'
    # every retry (including the eventually-acked one) used the SAME id
    assert seen_ids == ['1', '1', '1']


def test_fieldlink_still_sends_relay_tuning_handshake():
    """FieldLink (the torture relay carrier) is unchanged by the
    refactor that introduced TcpFieldLink -- it must still send its
    `!CG <channel> <group>` / `!GO` handshake on connect."""
    srv = _FakeLineServer(lambda line: None)
    try:
        link = FieldLink(55, 108, host='127.0.0.1', port=srv.port)
        time.sleep(1.2)
        link.close()
    finally:
        srv.close()
    assert '!CG 55 108' in srv.received
    assert '!GO' in srv.received


def test_unseq_matches_first_line_satisfying_pattern():
    def responder(line):
        if line == 'STATUS':
            return 'status ready=1 next=1'
        return None

    srv = _FakeLineServer(responder)
    try:
        link = TcpFieldLink(f'127.0.0.1:{srv.port}')
        reply = link.unseq('STATUS', r'^status ', tries=3, sec=0.5)
        link.close()
    finally:
        srv.close()
    assert reply == 'status ready=1 next=1'
