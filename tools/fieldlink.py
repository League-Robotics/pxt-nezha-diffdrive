"""Robot links for field/bench tools: a lossy radio carrier and a
lossless TCP carrier, both exposing the SAME sequenced-wire interface
(`unseq`/`seqd`/`hello`/`close`) so a caller like `field_dance.py`
does not care which one it is driving over.

`FieldLink` -- through the torture relay pool. LOSSY -- 66-83%
per-line delivery measured -- so every request retries and the absence
of a reply is never evidence of absence. Sequenced verbs carry their
#id and are resent with the SAME id, because a resend that takes a
fresh one presents as a numeric gap and stalls the stream on purpose.

`TcpFieldLink` -- direct TCP to a farm node's serial daemon (e.g. a Pi
riding on the robot, such as `zilch` on tovez), a raw LOSSLESS byte
pipe to the board's USB serial. Sprint 029 ticket 007 (2026-09-04d
session): tovez's bench sessions had been using the torture relay
(lossy, off-robot) even though a lossless on-robot carrier was
available and already verified answering PING/STATUS/GET. Retries and
the `#id` sequencing contract stay identical either way -- a lossless
transport still benefits from the same retry-until-ack shape, it just
needs fewer retries in practice.
"""
import re
import socket
import time


class _SequencedLink:
    """Shared unseq/seqd/hello/close protocol logic. Subclasses provide
    `__init__` (how the socket gets opened/tuned) and must set
    `s.sock`, `s.buf = b''`, `s._seq = 0` before returning."""

    def read(s, sec):
        end = time.time() + sec
        got = []
        s.sock.settimeout(0.25)
        while time.time() < end:
            try:
                c = s.sock.recv(4096)
            except socket.timeout:
                continue
            if not c:
                break
            s.buf += c
            while b'\n' in s.buf:
                r, s.buf = s.buf.split(b'\n', 1)
                t = r.decode('ascii', 'replace').strip()
                if t.startswith('< '):
                    t = t[2:]
                if t:
                    got.append(t)
        return got

    def send_raw(s, line):
        s.sock.sendall(line.encode() + b'\n')

    def unseq(s, cmd, pat, tries=6, sec=1.5):
        rx = re.compile(pat)
        for _ in range(tries):
            s.send_raw(cmd)
            for t in s.read(sec):
                if rx.match(t):
                    return t
        return None

    def seqd(s, cmd, tries=6, sec=2.0):
        """Sequenced verb. The id is fixed for all retries of THIS call."""
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        rx = re.compile(r'^(ack|err)\s+%d\b' % s._seq)
        for _ in range(tries):
            s.send_raw(wire)
            for t in s.read(sec):
                if rx.match(t):
                    return t
        return None

    def hello(s):
        r = s.unseq('HELLO', r'^device ')
        s._seq = 0          # HELLO resets the robot's expectedNext_ to 1
        return r

    def close(s):
        try:
            s.sock.close()
        except Exception:
            pass


class FieldLink(_SequencedLink):
    def __init__(s, channel, group, host='torture', port=8760):
        s.sock = socket.create_connection((host, port), timeout=15)
        s.buf = b''
        s._seq = 0
        time.sleep(1.0)
        s.read(1.5)
        s.send_raw(f'!CG {channel} {group}')
        time.sleep(0.4)
        s.read(0.8)
        s.send_raw('!GO')
        time.sleep(0.4)
        s.read(0.8)


class TcpFieldLink(_SequencedLink):
    """`hostport` is `'<host>:<port>'`, e.g. `'zilch.local:43671'` --
    a farm node's serial daemon, resolved fresh each session (the port
    is dynamic; see `.claude/rules/connecting-to-a-robot.md`). No relay
    tuning: this is a direct pipe to the board, so there is no
    channel/group to select and opening the socket does not reset the
    board (unlike opening a USB serial port directly)."""

    def __init__(s, hostport):
        host, _, port = hostport.rpartition(':')
        s.sock = socket.create_connection((host, int(port)), timeout=15)
        s.buf = b''
        s._seq = 0
        time.sleep(0.5)
        s.read(0.5)
