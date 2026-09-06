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
import os
import re
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import link as linklib  # noqa: E402  (tools/link.py -- the one sequencer)


class _SequencedLink:
    """Shared unseq/seqd/hello/close protocol logic. Subclasses provide
    `__init__` (how the socket gets opened/tuned) and must call
    `s._init_protocol()` before returning.

    The sequencing and the line reassembly are `tools/link.py`'s since
    sprint 034 ticket 006; what stays here is the retry shape (this
    carrier can be lossy) and the socket."""

    def _init_protocol(s):
        s.sequencer = linklib.Sequencer()
        s.buf = linklib.LineBuffer()

    # `_seq` is this class's tested surface (test_fieldlink.py sets it to
    # simulate a prior session and asserts hello() zeroes it); it is now
    # a view onto the shared Sequencer's counter.
    @property
    def _seq(s):
        return s.sequencer.seq

    @_seq.setter
    def _seq(s, value):
        s.sequencer.seq = value

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
            got.extend(s.buf.feed(c))
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
        """Sequenced verb. The id is fixed for all retries of THIS call --
        `format()` runs ONCE, outside the loop, and the identical string
        is resent (a fresh id would present as a numeric gap)."""
        wire = s.sequencer.format(cmd, force=True)
        rx = re.compile(r'^(ack|err)\s+%d\b' % s.sequencer.seq)
        for _ in range(tries):
            s.send_raw(wire)
            for t in s.read(sec):
                if rx.match(t):
                    return t
        return None

    def hello(s):
        r = s.unseq('HELLO', r'^device ')
        s.sequencer.reset()   # HELLO resets the robot's expectedNext_ to 1
        return r

    def close(s):
        try:
            s.sock.close()
        except Exception:
            pass


class FieldLink(_SequencedLink):
    def __init__(s, channel, group,
                 host=linklib.RELAY_HOST, port=linklib.RELAY_PORT):
        s.sock = socket.create_connection((host, port), timeout=15)
        s._init_protocol()
        time.sleep(1.0)
        s.read(1.5)
        # The FULL relay setup, not just `!CG` -- sprint 034 ticket 006.
        # This carrier used to send `!CG`/`!GO` alone on the reasoning
        # that a relay boots at RAW250/power 7/echo off; the relay
        # PERSISTS its config across resets (`!DEFAULTS` exists for
        # exactly that), so a previous session's setting is inherited in
        # silence. See linklib.relay_setup_lines().
        for cmd in linklib.relay_setup_lines(channel, group):
            s.send_raw(cmd)
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
        s._init_protocol()
        time.sleep(0.5)
        s.read(0.5)
