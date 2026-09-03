"""Robot link: one object that talks to the robot over USB or radio.

The bench (USB) and the playfield (radio) are not interchangeable:
the robot's wheels are off the ground on the bench stand, so anything
that needs real motion -- which is everything involving the OTOS --
has to run untethered over the zavaz relay.

Both carriers deliver the same ASCII lines, so every tool here takes
`--radio` and otherwise behaves identically.

  link = open_link(port, radio=True)   # zavaz relay, channel 4
  link.send('RUN:probe')
  for line in link.lines(timeout=60): ...
"""
import time

import serial

# zavaz is vevov's relay (channel 4). getez lives on channel 3 and
# belongs to another robot -- never retune it here.
ZAVAZ_CHANNEL = 4
ZAVAZ_GROUP = 10

# DAPLink ports are hub-position-based: they change on every replug, so
# a hard-coded /dev/cu.usbmodem path goes stale silently and the tool
# dies with ENOENT halfway into a session. `mbdeploy probe` is the only
# authority on where a board actually is -- config/devices.json carries
# stale and duplicate entries and must not be used to infer a port.
# The constant below is only a last-resort fallback for the error text.
ZAVAZ_PORT_FALLBACK = '/dev/cu.usbmodem2121302'
MBDEPLOY = '/Users/eric/.local/bin/mbdeploy'


def _probe_once(name):
    import subprocess
    try:
        out = subprocess.run([MBDEPLOY, 'probe'], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        cols = line.split()
        if name not in cols:
            continue
        for c in cols:
            if c.startswith('/dev/'):
                return c
    return None


def probe_port(name, tries=8):
    """The live port for a board NAME, via `mbdeploy probe`, or None.

    `mbdeploy probe` re-enumerates USB, and a board that is genuinely
    present intermittently comes back CONN=no with no port -- MEASURED
    on 2026-08-26 at roughly 1 call in 5 for zavaz, which is enough to
    kill a tour on startup about as often. It is markedly WORSE while
    the overhead camera's `camlink.py` subprocess is running -- that is
    a USB device too, and every tour starts the camera before opening
    the radio link, so the flaky case is the normal case here. A single
    miss means nothing; only a run of them does.

    Returns None rather than raising when the board really is absent or
    mbdeploy is unavailable -- the caller reports it with its own
    context.
    """
    for _ in range(tries):
        got = _probe_once(name)
        if got is not None:
            return got
        time.sleep(0.8)
    return None


# v6 wire verbs (protocol.md S6.1). These are SEQUENCED: the handler
# compares each line's `#<id>` against its own expectedNext_, and an id
# BELOW that is classified as a stale retransmit and deliberately NOT
# executed. An unsequenced line therefore parses as `#0`, which is
# unconditionally < expectedNext_ (it starts at 1 and never goes below),
# so it is silently dropped.
#
# MEASURED on vevov, 2026-08-25, v6 firmware over USB. PRE-SPRINT-024:
# this capture predates sprint 024 ticket 001, which deleted the
# firmware's free-running reliability beacon (the unconditional
# `emitReliability()` call `Protocol::run()` used to make every 50 ms
# on a non-subscribed transport). The "72 keepalive acks" below came
# from that now-removed periodic call, not from any reply to the line
# actually sent -- read this capture as describing pre-024 firmware,
# not re-measured against current firmware:
#     'TLM POSE'      -> 0 telemetry frames (72 keepalive acks only)
#     'TLM POSE #1'   -> 72 `t` frames + 4 `thdr` frames
# i.e. every v6 command sent through this link without an id was a
# silent no-op. The cleartext `RUN:`/`DIAG` vocabulary is a DIFFERENT
# parser path and is NOT sequenced -- `RUN:tour:wheels` unsequenced
# returns its DBG:tour= receipt normally -- so only these verbs get an
# id appended.
# Verbs that carry a mandatory trailing `#<id>`. This set must match the
# firmware's SEQUENCED plane exactly -- a verb listed here that the robot
# treats as unsequenced silently DESYNCS the link: _format() allocates an
# id the robot never consumes (it neither acks nor advances
# expectedNext_), so the very next command presents as a numeric gap and
# stalls the stream on purpose.
#
# The rule (agreed with radio-robot-lib-85, protocol.md's owner,
# 2026-08-27): a verb is SEQUENCED iff its correctness depends on its
# position in the stream -- either executing it twice changes the robot,
# or answering it out of order yields a wrong answer.
#
# HELLO/PING/ESTOP/HELP/ID/VER/STATUS are the firmware's seven
# unsequenced exemptions and are deliberately ABSENT here. ID/VER answer
# session constants (chip-burned name, compile-time version); STATUS is
# the out-of-band diagnostic a DESYNCED host must be able to send -- it
# reports next=/done=/reason=, and gating it behind knowing the right id
# made the one verb that recovers from desync require not being
# desynced. ESTOP was already unsequenced in firmware but was wrongly
# listed here, so every ESTOP a host ever sent silently burned an id.
#
# GET stays sequenced despite being read-only: it is ORDER-dependent,
# because the sequenced plane (SET) mutates what it reads.
_V6_VERBS = frozenset((
    'GET', 'SET', 'TLM', 'STOP',
    'MOVE', 'PIVOT', 'WHEELS_V', 'WHEELS_X', 'GO_TO', 'GO_TO_W', 'ARC',
))


class Link:
    def __init__(self, port, radio):
        self.radio = radio
        self.p = port
        # Next id to allocate. expectedNext_ starts at 1 on the robot,
        # so 0 is the correct starting point here too -- open_link()
        # (sprint 024 ticket 002) reaffirms this explicitly via hello()
        # right after connecting, since HELLO's own contract resets the
        # robot to expectedNext_ = 1 unconditionally. sync_seq() (below)
        # can still correct this against a LIVE ack/nack line for any
        # caller that has one to read outside the connect path; a stale
        # counter here opens a numeric GAP, which stalls the stream ON
        # PURPOSE until the missing id arrives.
        self._seq = 0

    def _is_wire(self, line):
        return line.split(' ', 1)[0] in _V6_VERBS

    def _format(self, line):
        """Attach a sequence id to a v6 wire verb; pass cleartext through.

        Allocates AT MOST ONE id per logical command -- a retransmit must
        reuse its original id, never take a fresh one, or it reads as a
        gap rather than as the resend it is. That is why send_until()
        formats once and resends the identical string.
        """
        if not self._is_wire(line) or '#' in line:
            return line
        self._seq += 1
        return f'{line} #{self._seq}'

    def sync_seq(self, timeout=1.5):
        """Learn the robot's expectedNext_ from a live ack/nack line.

        `ack N` means "N was accepted" -- the next id we may legally
        allocate is N + 1, and `_format()`'s `self._seq += 1` handles
        that increment, so `_seq` itself must land on N. `nack N` means
        something different: "send me N next" -- the next id to
        allocate must BE N, so `_seq` must land on N - 1 (this was
        sprint 024 ticket 002's bug: reading a `nack N` line used to set
        `_seq = N` too, so the next `_format()` call allocated `#(N+1)`,
        a fresh gap on the same wound the `nack` was reporting).

        NOTE (sprint 024 ticket 002): `open_link()` no longer calls this
        method. Once firmware ticket 001 removed the free-running
        reliability beacon, there is normally nothing periodic left for
        a passive read to find immediately after connecting --
        `open_link()` resyncs via `hello()` instead (below), which is
        deterministic and does not block waiting on a keepalive line
        that no longer exists. This method's ack/nack fix stands on its
        own merits regardless: it is still wrong today for any other
        caller that reads a live ack/nack line outside the connect path
        (sprint.md's Design Rationale, alternative (b)), so the fix and
        the method both stay.
        """
        import re
        end = time.time() + timeout
        while time.time() < end:
            raw = self.p.readline()
            if not raw:
                continue
            t = raw.decode('ascii', errors='replace').strip()
            if t.startswith('< '):
                t = t[2:]
            m = re.match(r'^(ack|nack)\s+(\d+)', t)
            if m:
                n = int(m.group(2))
                self._seq = n if m.group(1) == 'ack' else n - 1
                return self._seq
        return None

    def hello(self, timeout=1.0):
        """Send HELLO and consume its banner reply -- the reconnect resync.

        `handleHello()` (`src/comms/wire_handler.cpp:640-652`) is the
        protocol's own designated escape hatch: receiving HELLO
        unconditionally resets whichever handler got it to
        `expectedNext_ = 1`, `gapOutstanding_ = False` (without touching
        motion-completion state), and replies with the same banner as
        the unsolicited boot line (`"device NEZHA2 <name> <serial>"`).
        HELLO is unsequenced (protocol.md S8.3) -- `_format()` never
        appends a `#<id>` to it, matching the firmware's strict
        zero-field arity for this verb.

        That reset happens on the robot the moment it receives the
        line, regardless of whether the host manages to read the banner
        back -- so `_seq` is set to 0 (the correct counterpart to a
        robot now at `expectedNext_ = 1`) unconditionally, not only when
        a banner is actually seen within `timeout`. This is deliberately
        NOT a call to `sync_seq()`: once sprint 024 ticket 001 removed
        the free-running reliability beacon, there is nothing periodic
        left to passively read right after a HELLO, and `sync_seq()`'s
        full default 1.5 s timeout would be a dead wait on every single
        connect. `timeout` here only bounds how long this method waits
        for HELLO's OWN reply -- which, unlike the vanished beacon, the
        robot always sends exactly once in direct response to this
        line -- so it is deliberately shorter than `sync_seq()`'s
        default.

        Returns the banner line, or None if nothing matching arrived
        within `timeout` (e.g. no robot on the other end). Does not
        raise on a miss -- `open_link()` does not treat a missing banner
        as fatal, since the sequence state is established either way.
        """
        self.send('HELLO')
        banner = None
        for line in self.lines(timeout):
            if line.startswith('device '):
                banner = line
                break
        # HELLO's contract guarantees expectedNext_ = 1 on the robot,
        # unconditionally -- the correct host-side counterpart, matching
        # a freshly constructed Link, is _seq = 0.
        self._seq = 0
        return banner

    def send(self, line, repeat=1):
        """Send a line, once by default.

        Do NOT blind-repeat a command that starts motion. The robot's
        inbound path is a single-slot buffer so repeats look tempting,
        but MessageBus events QUEUE and are handled one at a time, each
        after the previous handler returns -- so a repeat does not hit
        a test's own re-entry guard, it runs the test again. Measured
        on vevov: one 3x-repeated RUN:4 ran three consecutive 180 deg
        pivots. Use send_until() instead, which only resends when the
        reply that proves arrival never came.
        """
        wire = self._format(line)
        for i in range(repeat):
            self.p.write((wire + '\n').encode())
            if i + 1 < repeat:
                time.sleep(0.25)

    def send_until(self, line, expect, tries=3, wait=5.0, echo=True):
        """Send `line`; resend only if no reply starting with `expect`.

        Returns the lines seen while waiting (empty if it never
        arrived). Loss-tolerant without ever duplicating work that did
        land -- the reply IS the delivery receipt.
        """
        seen = []
        # Format ONCE: every retry must carry the SAME id. A resend that
        # took a fresh id would present as a numeric gap, which the
        # handler stalls on deliberately -- nacking every subsequent
        # command until the "missing" id it is waiting for arrives.
        wire = self._format(line)
        for attempt in range(tries):
            self.p.write((wire + '\n').encode())
            for s in self.lines(wait):
                seen.append(s)
                if s.startswith(expect):
                    return seen
            if echo:
                print(f'  (no {expect} yet -- resending {line}, '
                      f'attempt {attempt + 2}/{tries})')
        return seen

    def lines(self, timeout, until=None):
        """Yield stripped lines until `timeout` s, or `until` matches."""
        end = time.time() + timeout
        while time.time() < end:
            raw = self.p.readline()
            if not raw:
                continue
            s = raw.decode('ascii', errors='replace').strip()
            # The relay prefixes received frames with '< ' on its
            # control plane; strip it so callers see the robot's line.
            if s.startswith('< '):
                s = s[2:]
            if not s:
                continue
            yield s
            if until and s.startswith(until):
                return

    def close(self):
        self.p.close()


class WifiSerial:
    """The robot's WiFi TCP server (src/comms/wifi_link.h, port 7654)
    wearing the three pyserial methods `Link` uses -- `write()`,
    `readline()` with a read timeout, `close()` -- so every tool built on
    `open_link()` runs over the net unchanged. Resolution is by mDNS
    (`<name>.local`) with a broadcast-HELLO fallback (tools/wifilink.py).
    The connect-time banner is left in the stream for `Link.hello()` to
    consume, exactly like USB."""

    def __init__(self, target, timeout=0.3):
        import os
        import re
        import socket
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wifilink
        host = target if re.match(r'^\d+\.\d+\.\d+\.\d+$', target) \
            else wifilink.discover(target)
        self.host = host
        self.s = socket.create_connection((host, wifilink.ROBOT_PORT), timeout=10)
        self.s.settimeout(timeout)
        self._buf = b''
        self._socket = socket

    def write(self, data):
        self.s.sendall(data)

    def readline(self):
        while b'\n' not in self._buf:
            try:
                c = self.s.recv(4096)
            except self._socket.timeout:
                return b''
            except OSError:
                return b''
            if not c:
                return b''
            self._buf += c
        line, self._buf = self._buf.split(b'\n', 1)
        return line + b'\n'

    def reset_input_buffer(self):
        self._buf = b''

    def close(self):
        self.s.close()


def open_link(port=None, radio=False, wifi=None):
    """Open a link. radio=True does the full zavaz data-plane handshake;
    wifi='<name>' (or an IP) connects to the robot's own WiFi TCP server
    instead -- the untethered carrier since 2026-09-02, with no relay and
    no channel to tune. The v6 radio link is OFF by default in the test
    program (tools/make_deploy.py --radio-link turns it on), so a tool
    that still asks for radio=True against a default build gets silence.

    The relay drops back to its control plane whenever its serial port
    closes, so the handshake is redone on every open -- never cached.
    """
    if wifi:
        link = Link(WifiSerial(wifi), False)
        link.wifi = wifi
        link.hello()
        return link
    if radio:
        path = port or probe_port('zavaz')
        if path is None:
            raise SystemExit(
                'zavaz relay not found by `mbdeploy probe` -- is it plugged '
                'in? (never hard-code a port; it moves on replug. last known: '
                + ZAVAZ_PORT_FALLBACK + ')')
        p = serial.Serial(path, 115200, timeout=0.3)
        time.sleep(1.8)          # DTR reset -> clean control plane
        p.reset_input_buffer()
        for cmd in (b'!ECHO OFF', b'!MODE RAW250',
                    f'!CG {ZAVAZ_CHANNEL} {ZAVAZ_GROUP}'.encode(), b'!P 7'):
            p.write(cmd + b'\n')
            time.sleep(0.3)
            p.reset_input_buffer()
        p.write(b'!GO\n')
        time.sleep(0.8)
        p.reset_input_buffer()
        link = Link(p, True)
        # HELLO is sent (and its banner consumed) only after the
        # relay's own control-plane setup above -- !ECHO OFF/!MODE
        # RAW250/!CG/!P/!GO are relay commands, not robot wire commands,
        # and must still run first so the data plane is actually up
        # before anything robot-directed goes out.
        link.hello()
        return link

    if port is None:
        raise ValueError('USB link needs an explicit port')
    p = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(1.5)
    p.reset_input_buffer()
    link = Link(p, False)
    # Resync via HELLO before anything else robot-directed (sprint 024
    # ticket 002) -- not sync_seq(): see Link.hello()'s own docstring
    # for why calling the old passive-read sync_seq() here would, once
    # the firmware beacon is gone, degrade into a dead wait on every
    # connect.
    link.hello()
    return link
