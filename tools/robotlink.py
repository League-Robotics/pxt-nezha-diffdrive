"""Robot link: one object that talks to the robot over USB or radio.

The bench (USB) and the playfield (radio) are not interchangeable:
the robot's wheels are off the ground on the bench stand, so anything
that needs real motion -- which is everything involving the OTOS --
has to run untethered over the zavaz relay.

Both carriers deliver the same ASCII lines, so every tool here takes
`--radio` and otherwise behaves identically.

  link = open_link(port, radio=True)   # zavaz relay, channel 4
  link.send('RUN:8')
  for line in link.lines(timeout=60): ...
"""
import time

import serial

# zavaz is vevov's relay (channel 4). getez lives on channel 3 and
# belongs to another robot -- never retune it here.
ZAVAZ_PORT = '/dev/cu.usbmodem2121302'
ZAVAZ_CHANNEL = 4
ZAVAZ_GROUP = 10


class Link:
    def __init__(self, port, radio):
        self.radio = radio
        self.p = port

    def send(self, line, repeat=None):
        """Send a line. Over radio it is repeated by default.

        The robot's inbound radio path is a single-slot buffer: a second
        message completing before the firmware drains the first is
        dropped, and measured inbound loss over the relay is real
        (tracked upstream as inbound-command-loss). Repeats are spaced
        past one drain interval. RUN verbs are idempotent in practice --
        test.ts's `touring` guard makes a duplicate a no-op while a test
        is already running.
        """
        n = repeat if repeat is not None else (3 if self.radio else 1)
        for i in range(n):
            self.p.write((line + '\n').encode())
            if i + 1 < n:
                time.sleep(0.25)

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
        path = port or ZAVAZ_PORT
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
        return Link(p, True)

    if port is None:
        raise ValueError('USB link needs an explicit port')
    p = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(1.5)
    p.reset_input_buffer()
    return Link(p, False)
