"""Square-tour closure on the bench, pure odometry.

Everything is open loop: the tour commands 4 legs and 4 pivots and we
score the odometry the robot itself believes. Feeding believed heading
back into the commands would close the figure by construction and
measure nothing, so we never do that.

Heading and position are always sampled AT REST, never through a
"still moving" filter -- a velocity-threshold window clips the tail of
each move, where the last counts land, and that alone made pivots look
6% short when they were in fact 3.5% long.
"""
import argparse, json, math, sys, time
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Volumes-Proj-proj-RobotProjects-pxt-nezha-diffdrive/101bc174-61d3-4a1f-9484-e6f0a191f653/scratchpad')
from tight_tour import Link


def rest(l, settle=1.2):
    m = l.mark(); time.sleep(settle)
    fr = np.array(l.frames(m), float)
    if not len(fr):
        return None
    return dict(x=fr[-1, 3]/10.0, y=fr[-1, 4]/10.0, h=fr[-1, 5]/100.0,
                pl=fr[-1, 13], pr=fr[-1, 14])


def tour(l, leg_mm, cruise, settle=1.2, legs=4):
    l.seqd('TLM FULL')
    a = rest(l, settle)
    hs, poses = [], [a]
    for i in range(legs):
        l.seqd(f'MOVE_X {leg_mm} 0 {cruise} 30000')
        time.sleep(leg_mm/cruise + 1.6)
        poses.append(rest(l, settle))
        l.seqd(f'MOVE_X 0 1571 {cruise} 25000')
        time.sleep(2.4)
        p = rest(l, settle)
        poses.append(p)
        hs.append(p['h'])
    l.seqd('TLM OFF')
    b = poses[-1]
    closure = math.hypot(b['x']-a['x'], b['y']-a['y']) * 10.0   # mm
    net = b['h'] - a['h']
    # per-segment detail: poses alternate rest / after-leg / after-pivot
    detail = []
    for i in range(legs):
        p0, p1, p2 = poses[2*i], poses[2*i+1], poses[2*i+2]
        legmm = math.hypot(p1['x']-p0['x'], p1['y']-p0['y']) * 10.0
        detail.append({'leg_mm': legmm, 'pivot_deg': p2['h']-p1['h'],
                       'leg_dh': p1['h']-p0['h']})
    return closure, net, poses, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--leg', type=int, default=600)
    ap.add_argument('--cruise', type=int, default=300)
    ap.add_argument('--overrun', type=float, default=None)
    ap.add_argument('--shaped', action='store_true')
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--settle', type=float, default=1.2)
    ap.add_argument('--floor', type=float, default=None)
    ap.add_argument('--warmup', type=int, default=0)
    ap.add_argument('--twist', type=float, default=None)
    ap.add_argument('--yawtaper', type=float, default=None)
    ap.add_argument('--tag', default='run')
    a = ap.parse_args()

    l = Link(); l.unseq('HELLO', r'^device '); l.sync_seq()
    if a.shaped:
        cfg = ['SET accel 500', 'SET decel 300', 'SET jerk 4000',
               'SET plateau_min_s 0.15', 'SET max_yaw_rate 90']
    else:
        cfg = ['SET accel 0', 'SET decel 0', 'SET jerk 0',
               'SET plateau_min_s 0', 'SET max_yaw_rate 0']
    for c in cfg:
        l.seqd(c)
    if a.overrun is not None:
        l.seqd(f'SET pivot_overrun {a.overrun}')
    if a.floor is not None:
        l.seqd(f'SET speed_floor {a.floor}')
    if a.twist is not None:
        l.seqd(f'SET twist_hold_gain {a.twist}')
    if a.yawtaper is not None:
        l.seqd(f'SET yaw_taper {a.yawtaper}')

    if a.warmup:
        # Cold pivots are measurably different from warm ones: on gopiv the
        # first few err near 0 and the error then settles ~0.5 deg higher.
        # Tuning or scoring on a cold robot mixes two populations.
        l.seqd('TLM FULL')
        for _ in range(a.warmup):
            l.seqd(f'MOVE_X 0 1571 {a.cruise} 20000')
            time.sleep(2.3)
        l.seqd('TLM OFF')
        print(f'  [{a.tag}] warmed up with {a.warmup} pivots', flush=True)

    out = []
    for r in range(a.repeat):
        cl, net, poses, detail = tour(l, a.leg, a.cruise, a.settle)
        out.append({'closure_mm': cl, 'net_heading': net, 'detail': detail})
        print('     legs  ' + ' '.join(f"{d['leg_mm']:7.1f}" for d in detail)
              + '  legdh ' + ' '.join(f"{d['leg_dh']:+5.2f}" for d in detail)
              + '  pivots ' + ' '.join(f"{d['pivot_deg']:6.2f}" for d in detail), flush=True)
        print(f'  [{a.tag}] run {r+1}: closure {cl:6.1f} mm   net heading {net:7.2f} deg'
              f'   (excess {net-360:+.2f})', flush=True)
    cls = [o['closure_mm'] for o in out]
    nets = [o['net_heading'] for o in out]
    print(f'  [{a.tag}] mean closure {np.mean(cls):.1f} mm (sd {np.std(cls):.1f}), '
          f'mean net heading {np.mean(nets):.2f}')
    json.dump({'args': vars(a), 'runs': out},
              open(f'/private/tmp/claude-501/-Volumes-Proj-proj-RobotProjects-pxt-nezha-diffdrive/101bc174-61d3-4a1f-9484-e6f0a191f653/scratchpad/closure_{a.tag}.json', 'w'))
    l.close()


if __name__ == '__main__':
    main()
