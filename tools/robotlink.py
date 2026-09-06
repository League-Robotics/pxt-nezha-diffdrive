"""Robot link: one object that talks to the robot over USB or radio.

The bench (USB) and the playfield (radio) are not interchangeable:
the robot's wheels are off the ground on the bench stand, so anything
that needs real motion -- which is everything involving the OTOS --
has to run untethered over the zavaz relay.

Both carriers deliver the same ASCII lines, so every tool here takes
`--radio` and otherwise behaves identically.

  link = open_link(port, radio=True, robot='vevov')   # zavaz relay
  link.send('RUN:probe')
  for line in link.lines(timeout=60): ...

**Sprint 029 (TL-01): the relay address is no longer a hardcoded
constant.** The old `ZAVAZ_CHANNEL = 4, ZAVAZ_GROUP = 10` was stale
since vevov's 2026-08-30 move to 37/43
(`.claude/rules/playfield-testing.md`) -- a hardcoded pair silently
goes stale on every board reassignment, with nothing in the code to say
so. `radio_address(robot)` replaces it: `field_calibration.json`'s
explicit `radio_channel`/`radio_group` override for `robot` when
present, else the same base-5 `!N` name derivation the relay itself
uses (`make_deploy.derive_radio_from_name`,
`radio-address-derived-from-board-name`). `open_link(radio=True)` now
requires a `robot=` argument to resolve this -- there is no longer a
constant default to silently fall back to.
"""
import json
import pathlib
import time

import serial

import link as linklib
from make_deploy import derive_radio_from_name

_HERE = pathlib.Path(__file__).resolve().parent
CALIBRATION_PATH = _HERE / 'field_calibration.json'


def load_calibration(path=CALIBRATION_PATH):
    """`field_calibration.json`'s parsed content -- the one
    calibration of record (TL-02/TL-01)."""
    return json.loads(pathlib.Path(path).read_text())


def radio_address(robot, calibration=None):
    """`(channel, group)` for `robot`: `field_calibration.json`'s
    explicit `radio_channel`/`radio_group` override for `robot` when
    BOTH are present, else the base-5 name derivation
    `make_deploy.derive_radio_from_name()` uses to assign fleet radio
    addresses in the first place.

    `calibration`, when given, is an already-loaded calibration dict
    (dependency injection for tests); omitted, this loads
    `field_calibration.json` fresh.

    Raises `ValueError` -- naming the robot and what was tried -- when
    neither an override nor a valid name-derivation is available. A
    silent wrong answer here is exactly the TL-01 defect this function
    replaces: the old stale `ZAVAZ_CHANNEL=4`/`ZAVAZ_GROUP=10`
    constants pointed at nothing after vevov's 2026-08-30 move, with no
    error anywhere to say so.
    """
    cal = calibration if calibration is not None else load_calibration()
    entry = cal.get('robots', {}).get(robot, {})
    channel, group = entry.get('radio_channel'), entry.get('radio_group')
    if channel is not None and group is not None:
        return channel, group
    if channel is not None or group is not None:
        # A HALF-migrated entry is a config error, not a default --
        # same reasoning as make_deploy._read_robot_radio_group()'s own
        # refusal of a channel with no matching group.
        raise ValueError(
            f"field_calibration.json's {robot!r} entry sets only one "
            f"of radio_channel/radio_group ({channel!r}/{group!r}) -- "
            f"set both, or neither (to derive from the name)")
    derived = derive_radio_from_name(robot)
    if derived is None:
        raise ValueError(
            f"no radio address for robot {robot!r}: no explicit "
            f"radio_channel/radio_group in {CALIBRATION_PATH}, and "
            f"{robot!r} is not a valid 5-letter micro:bit name to "
            f"derive one from")
    return derived


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
    the overhead camera is streaming -- that is a USB device too (the
    measurement was taken against the camera-subprocess `camlink.py`
    that sprint 034 ticket 008 folded in-process; the USB contention it
    describes is the daemon holding the camera, which has not changed),
    and every tour starts the camera before opening
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


# Verbs the firmware sequences (wire_handler.cpp kCommandTable).
# An unsequenced line parses as #0 and is dropped; a verb listed here
# that the robot does NOT sequence burns an id and stalls the stream.
_V6_VERBS = frozenset((
    'GET', 'SET', 'TLM', 'STOP', 'RUN',
    'WHEELS_X', 'WHEELS_V', 'MOVE_X', 'MOVE_V', 'GO_TO_R', 'GO_TO_W',
))


class Link:
    """A serial (or serial-shaped) port plus the shared protocol.

    The transport stays here -- `self.p` is a pyserial port, or
    `WifiSerial` wearing the three methods this class calls. The
    sequencing and the line reassembly are `tools/link.py`'s
    (sprint 034 ticket 006).
    """

    def __init__(self, port, radio):
        self.radio = radio
        self.p = port
        self._sequencer = linklib.Sequencer(_V6_VERBS)
        self._lines = linklib.LineBuffer()

    # `_seq` is the tested, written-to surface of this class (tests set
    # it to simulate a prior session, and read it to assert HELLO's
    # reset). It is now a view onto the shared Sequencer's counter
    # rather than a field of its own.
    @property
    def _seq(self):
        return self._sequencer.seq

    @_seq.setter
    def _seq(self, value):
        self._sequencer.seq = value

    def _is_wire(self, line):
        return self._sequencer.is_sequenced(line)

    def _format(self, line):
        """Attach a sequence id to a v6 wire verb; pass cleartext through."""
        return self._sequencer.format(line)

    def sync_seq(self, timeout=1.5):
        """Set _seq from a live reply: `ack N` -> N, `nack N` -> N-1
        ("send me N next"). Not used by open_link(); nothing streams
        passively to read.
        """
        end = time.time() + timeout
        while time.time() < end:
            raw = self.p.readline()
            if not raw:
                continue
            text = self._lines.line(raw)
            if text is None:
                continue
            got = self._sequencer.observe_reply(text)
            if got is not None:
                return got
        return None

    def hello(self, timeout=1.0):
        """Session RESET, not a liveness probe: HELLO sets the robot to
        expectedNext_=1 and answers the boot banner. _seq becomes 0
        whether or not the banner is read.

        `timeout` bounds only the wait for HELLO's OWN reply, so it is
        deliberately shorter than `sync_seq()`'s default -- the two are
        not interchangeable and `open_link()` uses this one.
        """
        self.send('HELLO')
        banner = None
        for line in self.lines(timeout):
            if line.startswith('device '):
                banner = line
                break
        self._sequencer.reset()
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
        """Yield stripped lines until `timeout` s, or `until` matches.

        `self.p.readline()` already delivers one line at a time, so the
        shared buffer is used for its decode/strip/'< '-prefix rules
        rather than for reassembly -- one definition of "what a line
        is", shared with every socket carrier.
        """
        end = time.time() + timeout
        while time.time() < end:
            raw = self.p.readline()
            if not raw:
                continue
            s = self._lines.line(raw)
            if s is None:
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


def open_link(port=None, radio=False, wifi=None, robot=None):
    """Open a link. radio=True does the full zavaz data-plane handshake;
    wifi='<name>' (or an IP) connects to the robot's own WiFi TCP server
    instead -- the untethered carrier since 2026-09-02, with no relay and
    no channel to tune. The v6 radio link is OFF by default in the test
    program (tools/make_deploy.py --radio-link turns it on), so a tool
    that still asks for radio=True against a default build gets silence.

    `robot` (a board name, e.g. `'vevov'`) is REQUIRED when `radio=True`
    -- it is how the zavaz relay's channel/group get resolved
    (`radio_address()`, above). There is no default: the old
    `ZAVAZ_CHANNEL`/`ZAVAZ_GROUP` constants this replaces (TL-01) were
    stale for months with nothing to say so, and a silent wrong default
    here would reproduce exactly that.

    The relay drops back to its control plane whenever its serial port
    closes, so the handshake is redone on every open -- never cached.
    """
    if wifi:
        link = Link(WifiSerial(wifi), False)
        link.wifi = wifi
        link.hello()
        return link
    if radio:
        if robot is None:
            raise ValueError(
                "open_link(radio=True) needs robot=<name> to resolve the "
                "zavaz relay's channel/group -- the old ZAVAZ_CHANNEL/"
                "ZAVAZ_GROUP constants are gone (TL-01: they were stale "
                "since vevov's 2026-08-30 move to 37/43). Pass "
                "robot='vevov' (or whichever board you're driving).")
        channel, group = radio_address(robot)
        path = port or probe_port('zavaz')
        if path is None:
            raise SystemExit(
                'zavaz relay not found by `mbdeploy probe` -- is it plugged '
                'in? (never hard-code a port; it moves on replug. last known: '
                + ZAVAZ_PORT_FALLBACK + ')')
        p = serial.Serial(path, 115200, timeout=0.3)
        time.sleep(1.8)          # DTR reset -> clean control plane
        p.reset_input_buffer()
        for cmd in linklib.relay_setup_lines(channel, group):
            p.write(cmd.encode() + b'\n')
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
    # ticket 002) -- deliberately NOT sync_seq(): sync_seq reads
    # passively, and since ticket 001 removed the firmware's
    # free-running reliability beacon there is nothing periodic left for
    # it to find, so it would degrade into a dead wait on every connect.
    # tests/tools/test_robotlink.py pins this.
    link.hello()
    return link
