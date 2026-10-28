"""Orange-dot square by GO_TO_W, flown blind after one camera zero.

The camera places the tag on the first dot, the pose frame is zeroed
there (SET rebase), and the remaining dots are reached by world-frame
go-tos with no camera feedback. The camera only scores each arrival
and watches for the boards (STOP if the robot leaves the safe box).
"""
import argparse
import json
import math
import sys

from devlink import DOTS, Cam, open_serial, send_move, settled, still_pose
from dots import ROUTE, Placer, check

GUARD_X, GUARD_Y = 58.0, 36.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--robot', default='vevov')
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--start', default='SW')
    ap.add_argument('--laps', type=int, default=1)
    ap.add_argument('--speed', type=int, default=100)
    ap.add_argument('--arrive', type=int, default=5)
    ap.add_argument('--retries', type=int, default=0, help='re-issue GO_TO_W while the robot believes it is off')
    ap.add_argument('--retry-over', type=float, default=2.0, help='[cm] belief error worth a re-issue')
    ap.add_argument('--place-tol', type=float, default=0.5)
    ap.add_argument('--log', default=None)
    a = ap.parse_args()

    cam = Cam(tag=a.tag).start()
    link = open_serial(a.robot)
    tlm = {}
    hdr = []

    def pump(secs):
        status = ''
        for s in link.lines(secs):
            f = s.split()
            if not f:
                continue
            if f[0] == 'thdr':
                hdr[:] = f[1:]
            elif f[0] == 't' and len(f) - 1 == len(hdr):
                tlm.update(zip(hdr, (float(v) if v.lstrip('-').isdigit() else 0.0 for v in f[1:])))
            elif f[0] == 'status':
                status = s
        return status

    order = [n for n, _ in ROUTE]
    k = order.index(a.start)
    route = ROUTE[k:] + ROUTE[:k]
    start_name, start_face = route[0]

    def off(q, dot):
        return math.hypot(q[0] - dot[0], q[1] - dot[1]), q

    Placer(link, cam).park(settled(cam), DOTS[start_name], start_face, a.place_tol, 6)
    c0 = still_pose(cam)
    print(f'zeroed on {start_name}: off {off(c0, DOTS[start_name])[0]:.2f} cm, '
          f'centre ({c0[0]:.2f},{c0[1]:.2f}) hdg {c0[2]:.2f}')

    link.send('SET rebase 1')
    pump(1.0)
    link.send('TLM POSE')
    pump(1.5)
    print(f'  after rebase: odom ({tlm.get("x")},{tlm.get("y")}) h {tlm.get("h")}  otos ({tlm.get("ox")},{tlm.get("oy")}) oh {tlm.get("oh")}')

    h0 = math.radians(c0[2])
    rows = []

    def save():
        if a.log:
            json.dump(dict(start=start_name, zero=c0, rows=rows, args=vars(a)), open(a.log, 'w'), indent=1)

    legs = [route[(i + 1) % 4] for i in range(4)] * a.laps
    for i, (name, _) in enumerate(legs):
        dot = DOTS[name]
        c = dot
        check(*c)
        dx, dy = c[0] - c0[0], c[1] - c0[1]
        fx = (dx * math.cos(h0) + dy * math.sin(h0)) * 10
        fy = (-dx * math.sin(h0) + dy * math.cos(h0)) * 10
        def guard():
            q = cam.latest
            if q and (abs(q[0]) > GUARD_X or abs(q[1]) > GUARD_Y):
                link.send('STOP')
                rows.append(dict(leg=i + 1, dot=name, stopped=q))
                save()
                sys.exit(f'STOPPED: robot at ({q[0]:.1f},{q[1]:.1f}) left the guard box')

        first = None
        for attempt in range(1 + a.retries):
            send_move(link, f'GO_TO_W {int(round(fx))} {int(round(fy))} {a.speed} {a.arrive} 30000', 35, guard)
            q = settled(cam, 25)
            pump(1.0)
            if first is None:
                first = off(q, dot)[0]
            if math.hypot(tlm.get('x', 0) - fx, tlm.get('y', 0) - fy) < a.retry_over * 10:
                break
        err, pt = off(q, dot)
        belief = math.hypot(tlm.get('x', 0) - fx, tlm.get('y', 0) - fy) / 10
        print(f'{i + 1} -> {name}: off {err:.2f} cm (dx {pt[0] - dot[0]:+.2f}, dy {pt[1] - dot[1]:+.2f}); '
              f'first go-to {first:.2f} cm, {attempt + 1} go-to(s); robot thinks {belief:.2f} cm; '
              f'hdg cam {q[2]:.1f} odom {tlm.get("h", 0) / 100 + c0[2]:.1f}')
        rows.append(dict(leg=i + 1, dot=name, err=err, first=first, gotos=attempt + 1, belief=belief, point=pt, pose=q, target=c,
                         odom=(tlm.get('x'), tlm.get('y'), tlm.get('h')), otos=(tlm.get('ox'), tlm.get('oy'), tlm.get('oh'))))
    link.send('TLM OFF')
    save()
    link.close()
    cam.close()


if __name__ == '__main__':
    main()
