import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

import serial

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from robotlink import Link
import tlm


class LoggedPort:
    def __init__(self, endpoint, log):
        self.port = serial.serial_for_url(endpoint, timeout=0.3)
        self.log = log

    def write(self, data):
        self.log.write('> ' + data.decode('ascii'))
        self.log.flush()
        self.port.write(data)

    def readline(self):
        data = self.port.readline()
        if data:
            self.log.write(data.decode('ascii', errors='replace'))
            self.log.flush()
        return data

    def close(self):
        self.port.close()


def capture(endpoint, run):
    output = Path(__file__).resolve().parent
    prefix = 'tour' if run else 'inspect'
    with (output / (prefix + '.log')).open('w') as log:
        link = Link(LoggedPort(endpoint, log), False)
        started = False
        completed = False
        stream = None
        rows = []
        try:
            identity = link.hello(timeout=8)
            print(identity, flush=True)
            if identity != 'device NEZHA2 robot vevov 1198504156':
                raise RuntimeError('Unexpected hardware identity')
            link.send('WHEELS_V 0 0 250')
            print(*link.lines(1), sep='\n', flush=True)
            for command in ('ID', 'GET', 'STATUS'):
                link.send(command)
                replies = list(link.lines(2))
                print(command, *replies, sep='\n', flush=True)
                if not replies:
                    raise RuntimeError('No reply to ' + command)
                if command == 'STATUS' and not any('ready=1' in reply for reply in replies):
                    raise RuntimeError('Board is not ready')
                if command == 'STATUS' and not any('otos=0' in reply for reply in replies):
                    raise RuntimeError('OTOS is not disabled')
            if not run:
                return
            link.send('SET jerk 800')
            print(*link.lines(1), sep='\n', flush=True)
            link.send('GET jerk')
            replies = list(link.lines(1))
            print(*replies, sep='\n', flush=True)
            if not any(reply.startswith('get jerk ') and abs(float(reply.split()[2]) - 800) < 0.001
                       for reply in replies):
                raise RuntimeError('Jerk readback did not match')
            stream = tlm.require_stream(link, timeout=5)
            origin = time.monotonic()
            deadline = origin + 90
            link.send('RUN:tour:wheels')
            started = True
            receipt = False
            while time.monotonic() < deadline:
                for line in link.lines(0.5):
                    now = time.monotonic() - origin
                    frame = stream.feed(line)
                    if frame is not None:
                        rows.append(dict(frame, t_host=now))
                    elif line.startswith('DBG:tour=wheels'):
                        receipt = True
                        print(line, flush=True)
                    elif line.startswith('TOUR:end:'):
                        print(line, flush=True)
                        if line != 'TOUR:end:ok':
                            raise RuntimeError(line)
                        completed = True
                        deadline = time.monotonic() + 2
                    elif line.startswith(('DBG:corner=', 'GAP:', 'err ')):
                        print(line, flush=True)
                if not receipt and time.monotonic() - origin > 8:
                    raise RuntimeError('No tour start receipt')
            if not completed:
                raise RuntimeError('Tour did not finish before timeout')
            link.send('STATUS')
            print(*link.lines(1), sep='\n', flush=True)
        finally:
            if started and not completed:
                link.send('RUN:abort')
                link.send('STOP')
                print(*link.lines(2), sep='\n', flush=True)
            if stream is not None and stream.frames:
                quality = tlm.write_tlm_csv(stream, output / 'tour_tlm.csv')
                tlm.write_pose_csv(rows, output / 'tour_pose.csv')
                with (output / 'tour_vel.csv').open('w') as velocity:
                    writer = csv.writer(velocity)
                    writer.writerow(['t_host', 'vel_l_mmps', 'vel_r_mmps'])
                    for row in rows:
                        wheels = tlm.wheels_mms(row)
                        writer.writerow([row['t_host'], wheels['vl'], wheels['vr']])
                firmware = ROOT / '.tmp/deploy-head/built/binary.hex'
                provenance = dict(board='vevov', date='2026-09-06',
                    surface='farm stand, wheels up; encoder pose only',
                    otos='not sampled by wheels tour', completed=completed,
                    firmware_sha256=hashlib.sha256(firmware.read_bytes()).hexdigest(),
                    telemetry=quality)
                (output / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
                print(json.dumps(provenance, indent=2), flush=True)
            link.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--run', action='store_true')
    arguments = parser.parse_args()
    capture(arguments.endpoint, arguments.run)