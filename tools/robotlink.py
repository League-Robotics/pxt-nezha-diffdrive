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
# MEASURED on vevov, 2026-08-25, v6 firmware over USB:
#     'TLM POSE'      -> 0 telemetry frames (72 keepalive acks only)
#     'TLM POSE #1'   -> 72 `t` frames + 4 `thdr` frames
# i.e. every v6 command sent through this link without an id was a
# silent no-op. The cleartext `RUN:`/`DIAG` vocabulary is a DIFFERENT
# parser path and is NOT sequenced -- `RUN:tour:wheels` unsequenced
# returns its DBG:tour= receipt normally -- so only these verbs get an
# id appended.
_V6_VERBS = frozenset((
    'VER', 'ID', 'STATUS', 'HELP', 'GET', 'SET', 'TLM', 'STOP', 'ESTOP',
    'MOVE', 'PIVOT', 'WHEELS_V', 'WHEELS_X', 'GO_TO', 'GO_TO_W', 'ARC',
))


class Link:
    def __init__(self, port, radio):
        self.radio = radio
        self.p = port
        # Next id to allocate. expectedNext_ starts at 1 on the robot;
        # sync_seq() corrects this against a live keepalive, because a
        # robot mid-session is already past 1 and a stale counter here
        # opens a numeric GAP, which stalls the stream ON PURPOSE until
        # the missing id arrives.
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
        """Learn the robot's expectedNext_ from a keepalive ack.

        The keepalive is `ack <expectedNext-1> <lastDone> <reason>`, so
        the next id we may legally use is that first field + 1.
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
            m = re.match(r'^(?:ack|nack)\s+(\d+)', t)
            if m:
                self._seq = int(m.group(1))
                return self._seq
        return None

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


def open_link(port=None, radio=False):
    """Open a link. radio=True does the full zavaz data-plane handshake.

    The relay drops back to its control plane whenever its serial port
    closes, so the handshake is redone on every open -- never cached.
    """
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
        link.sync_seq()
        return link

    if port is None:
        raise ValueError('USB link needs an explicit port')
    p = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(1.5)
    p.reset_input_buffer()
    link = Link(p, False)
    # Adopt the robot's own expectedNext_ before the first wire command.
    link.sync_seq()
    return link
