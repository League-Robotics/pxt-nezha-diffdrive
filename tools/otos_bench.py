#!/usr/bin/env python3
"""zeguz OTOS rig console -- drives testrig.ts's RUN:<n> vocabulary.

Chainable subcommands, executed in order:
  begin           probe OTOS               (RUN:20 -> OID:<id>, 95 = OK)
  zero            zero OTOS pose           (RUN:21)
  cal             IMU bias calibration     (RUN:23) -- rig must be STILL
  pin N           servo pin 1|8            (RUN:3300N)
  servo US        servo pulse [us]         (RUN:30000+US)
  drum MMPS       drum surface speed mm/s  (RUN:41000+MMPS; 0 stops)
  streamon        start 30 s OTS stream    (RUN:24)
  streamoff       stop stream              (RUN:26)
  record SEC      read+log for SEC seconds (stream must be on)
  sleep SEC       host-side pause (keeps draining serial)

OTS line: OTS:<ms>:<x 0.1mm>:<y 0.1mm>:<h cdeg>:<vx mm/s>:<vy>:<om cdeg/s>

Example -- gyro check (rotate servo mid-stream):
  python3 tools/otos_bench.py PORT begin zero streamon record 2 \
      servo 2000 record 3 servo 1000 record 3 streamoff --csv out.csv
"""
import argparse
import csv
import sys
import time

import serial


class Rig:
    def __init__(self, port, csv_path):
        self.p = serial.Serial(port, 115200, timeout=0.05)
        time.sleep(1.2)
        self.p.reset_input_buffer()
        self.rows = []          # (t_host, ms, x01mm, y01mm, hcdeg, vx, vy, om)
        self.csv_path = csv_path
        self.t0 = time.time()

    def send(self, n):
        self.p.write(f'RUN:{n}\n'.encode())

    def drain(self, seconds, quiet=False):
        end = time.time() + seconds
        while time.time() < end:
            line = self.p.readline()
            if not line:
                continue
            s = line.decode('ascii', errors='replace').strip()
            if not s:
                continue
            if s.startswith('OTS:'):
                parts = s[4:].split(':')
                if len(parts) == 7:
                    try:
                        self.rows.append(
                            (round(time.time() - self.t0, 3),)
                            + tuple(int(v) for v in parts))
                    except ValueError:
                        pass
                if not quiet:
                    print(s)
            elif not s.startswith('TLM:') and not s.startswith('DIAG:'):
                print(s)   # acks and anything unexpected; TLM/DIAG are
                           # the drive protocol's own chatter -- suppress

    def close(self):
        self.p.close()
        if self.csv_path and self.rows:
            with open(self.csv_path, 'w') as f:
                w = csv.writer(f)
                w.writerow(['t_host', 't_dev_ms', 'x_01mm', 'y_01mm',
                            'h_cdeg', 'vx_mms', 'vy_mms', 'om_cdegs'])
                w.writerows(self.rows)
            print(f'wrote {len(self.rows)} OTS rows -> {self.csv_path}')


def main():
    args = sys.argv[1:]
    csv_path = None
    if '--csv' in args:
        i = args.index('--csv')
        csv_path = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 1
    port, cmds = args[0], args[1:]

    rig = Rig(port, csv_path)
    i = 0
    while i < len(cmds):
        c = cmds[i]
        if c == 'begin':
            rig.send(20)
            rig.drain(1.5)
        elif c == 'zero':
            rig.send(21)
            rig.drain(0.8)
        elif c == 'cal':
            rig.send(23)
            rig.drain(1.5)
        elif c == 'pin':
            i += 1
            rig.send(33000 + int(cmds[i]))
            rig.drain(0.5)
        elif c == 'servo':
            i += 1
            rig.send(30000 + int(cmds[i]))
            rig.drain(0.5)
        elif c == 'drum':
            i += 1
            rig.send(41000 + int(cmds[i]))
            rig.drain(0.5)
        elif c == 'streamon':
            rig.send(24)
        elif c == 'streamoff':
            rig.send(26)
            rig.drain(0.8)
        elif c == 'record':
            i += 1
            rig.drain(float(cmds[i]))
        elif c == 'sleep':
            i += 1
            rig.drain(float(cmds[i]), quiet=True)
        else:
            print(f'unknown subcommand: {c}')
            rig.close()
            return 1
        i += 1
    rig.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
