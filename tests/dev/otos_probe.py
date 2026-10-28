"""Which pose source is right after each move: encoders, OTOS, or encoder distance on OTOS heading?

Zeroes the pose frame at the start, runs an open-loop MOVE_X rectangle,
and at every rest point scores, against the camera:
  odom   -- the firmware's encoder odometry (x, y, h)
  otos   -- the OTOS's own pose (ox, oy, oh)
  hybrid -- encoder distance increments integrated along the OTOS heading
            (computed here from the TLM stream)
"""
import argparse
import json
import math
import sys
import time

from devlink import Cam, open_serial, settled, wrap

GUARD_X, GUARD_Y = 58.0, 36.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--robot', default='vevov')
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--legs', default='80,40,80,40')
    ap.add_argument('--turn', type=float, default=90.0)
    ap.add_argument('--laps', type=int, default=1)
    ap.add_argument('--drive', type=int, default=100)
    ap.add_argument('--pivot', type=int, default=60)
    ap.add_argument('--log', default=None)
    a = ap.parse_args()

    cam = Cam(tag=a.tag).start()
    link = open_serial(a.robot)
    hdr, samples = [], []

    def pump(secs):
        status = ''
        for s in link.lines(secs):
            f = s.split()
            if not f:
                continue
            if f[0] == 'thdr':
                hdr[:] = f[1:]
            elif f[0] == 't' and len(f) - 1 == len(hdr):
                try:
                    samples.append(dict(zip(hdr, (float(v) for v in f[1:]))))
                except ValueError:
                    pass
            elif f[0] == 'status':
                status = s
        return status

    c0 = settled(cam, 25)
    link.send('SET rebase 1')
    pump(1.0)
    link.send('TLM POSE')
    pump(1.5)
    h0 = math.radians(c0[2])

    def to_frame(p):
        dx, dy = p[0] - c0[0], p[1] - c0[1]
        return ((dx * math.cos(h0) + dy * math.sin(h0)) * 10, (-dx * math.sin(h0) + dy * math.cos(h0)) * 10,
                wrap(p[2] - c0[2]))

    hyb = [0.0, 0.0]
    used = [len(samples)]

    def integrate():
        for i in range(max(used[0], 1), len(samples)):
            s0, s1 = samples[i - 1], samples[i]
            dx, dy = s1['x'] - s0['x'], s1['y'] - s0['y']
            hm = math.radians((s0['h'] + s1['h']) / 200.0)
            ds = dx * math.cos(hm) + dy * math.sin(hm)
            ho = math.radians((s0['oh'] + s1['oh']) / 200.0)
            hyb[0] += ds * math.cos(ho)
            hyb[1] += ds * math.sin(ho)
        used[0] = len(samples)

    rows = []

    def score(label):
        pump(1.0)
        integrate()
        q = settled(cam, 25)
        pump(0.5)
        integrate()
        cx, cy, ch = to_frame(q)
        s = samples[-1]
        r = dict(label=label, cam=(cx, cy, ch), odom=(s['x'], s['y'], s['h'] / 100), otos=(s['ox'], s['oy'], s['oh'] / 100),
                 hybrid=(hyb[0], hyb[1], s['oh'] / 100))
        msg = [label]
        for k in ('odom', 'otos', 'hybrid'):
            e = math.hypot(r[k][0] - cx, r[k][1] - cy) / 10
            eh = wrap(r[k][2] - ch)
            r[k + '_err'] = (e, eh)
            msg.append(f'{k} {e:5.2f} cm {eh:+5.2f} deg')
        print('  '.join(msg))
        rows.append(r)

    def move(mm, deg, cruise):
        link.send('STATUS')
        before = pump(0.5).partition(' done=')[2].split(' ')[0]
        link.send(f'MOVE_X {int(round(mm))} {int(round(math.radians(deg) * 1000))} {cruise} 20000')
        t_end = time.time() + 25
        started = False
        while time.time() < t_end:
            q = cam.latest
            if q and (abs(q[0]) > GUARD_X or abs(q[1]) > GUARD_Y):
                link.send('STOP')
                save()
                sys.exit(f'STOPPED: robot at ({q[0]:.1f},{q[1]:.1f}) left the guard box')
            link.send('STATUS')
            st = pump(0.3)
            if ' active=1 ' in st or st.partition(' done=')[2].split(' ')[0] not in ('', before):
                started = True
            if started and ' active=0 ' in st:
                break

    def save():
        if a.log:
            json.dump(dict(zero=c0, rows=rows, samples=samples, args=vars(a)), open(a.log, 'w'), indent=1)

    score('start')
    legs = [float(v) for v in a.legs.split(',')]
    for lap in range(a.laps):
        for i, cm in enumerate(legs):
            move(cm * 10, 0, a.drive)
            score(f'L{lap + 1}.{i + 1} drive {cm:.0f}')
            move(0, a.turn, a.pivot)
            score(f'L{lap + 1}.{i + 1} turn {a.turn:+.0f}')
    link.send('TLM OFF')
    save()
    link.close()
    cam.close()


if __name__ == '__main__':
    main()
