#!/usr/bin/env python3
"""Chart one recorded tour. Run under uv (system matplotlib is broken):

  uv run --with numpy --with matplotlib python3 tools/practice_chart.py \
      NAME RUN cam.csv pose.csv out.png
"""
import csv
import math
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DOTS = {'NW': (-50.0, 30.0), 'NE': (50.0, 30.0),
        'SE': (50.0, -30.0), 'SW': (-50.0, -30.0)}
ORDER = ['NW', 'SW', 'SE', 'NE']
RECT = [DOTS['NE'], DOTS['NW'], DOTS['SW'], DOTS['SE'], DOTS['NE']]
TRACK_CM = 12.0
TITLES = {'robot': 'Tour A — robot-relative (local frame, IMU heading)',
          'world': 'Tour B — world goToWorld (camera-seeded, OTOS-guided)',
          'wheels': 'Tour A+B — wheels (open loop)'}
S1, S2 = '#2a78d6', '#eb6834'
INK, INK2, MUTED, BG = '#0b0b0b', '#52514e', '#b9b7b0', '#fcfcfb'


def wrap(d):
    while d <= -180.0:
        d += 360.0
    while d > 180.0:
        d -= 360.0
    return d


def rd(path):
    with open(path) as f:
        r = csv.reader(f)
        hdr = next(r)
        return hdr, [[float(v) for v in row] for row in r if row]


def wheel_speeds(pose, hdr):
    """MEASURED wheel speeds, straight from telemetry.

    Deriving speed by differencing the pose does NOT work at this frame
    rate: odometry advances only on a 24 ms control tick while frames go
    out every ~56 ms (2.33 ticks), so each frame catches 2 or 3 ticks in
    a 2-2-3 pattern and a steady 44 cm/s leg reads as 55/55/84. The
    kernel measures each wheel per tick; those values now ride the
    frame. Falls back to differencing only for older recordings.
    """
    if 'vl_cms' in hdr:
        a, b = hdr.index('vl_cms'), hdr.index('vr_cms')
        return [(p[0], p[a], p[b]) for p in pose]
    if 'vl_mms' in hdr:      # tour_run.py records mm/s; plot in cm/s
        a, b = hdr.index('vl_mms'), hdr.index('vr_mms')
        return [(p[0], p[a] / 10.0, p[b] / 10.0) for p in pose]
    out = []
    for a, b in zip(pose, pose[1:]):
        dt = b[0] - a[0]
        if dt <= 0.02 or dt > 0.5:
            continue
        h = math.radians(a[3])
        fwd = (b[1] - a[1]) * math.cos(h) + (b[2] - a[2]) * math.sin(h)
        ds = math.copysign(math.hypot(b[1] - a[1], b[2] - a[2]), fwd)
        om = math.radians(wrap(b[3] - a[3])) / dt
        v = ds / dt
        out.append((b[0], v - om * TRACK_CM / 2, v + om * TRACK_CM / 2))
    return out


def score(cam):
    """Closest approach to each dot -- but ONLY where the camera was
    actually watching.

    Tracking drops out over parts of this field (measured: 25% of run
    time, concentrated in the north, where two of the four dots are).
    A "closest approach" computed across a blind stretch is not the
    robot's error, it is where tracking happened to die -- one run
    reported SW 31.3 cm when the camera had been blind for 24 s and the
    robot had already been and gone. Corners whose closest sample sits
    beside a gap are reported as UNOBSERVED rather than scored.
    """
    res, used = {}, 0
    gaps = [(a[0], b[0]) for a, b in zip(cam, cam[1:]) if b[0] - a[0] > 0.4]
    for tag in ORDER:
        dx, dy = DOTS[tag]
        best, besti = None, used
        for i in range(used, len(cam)):
            d = math.hypot(cam[i][1] - dx, cam[i][2] - dy)
            if best is None or d < best:
                best, besti = d, i
        # If the best sample abuts a tracking gap, we never saw the
        # approach: refuse to score it.
        t = cam[besti][0]
        blind = any(g0 - 0.5 <= t <= g1 + 0.5 for g0, g1 in gaps)
        res[tag] = None if (blind and best > 3.0) else best
        used = besti
    res['closure'] = math.hypot(cam[-1][1] - cam[0][1],
                                cam[-1][2] - cam[0][2])
    res['endhdg'] = wrap(cam[-1][3] - 180.0)
    span = cam[-1][0] - cam[0][0]
    lost = sum(b[0] - a[0] for a, b in zip(cam, cam[1:]) if b[0] - a[0] > 0.4)
    res['tracked'] = 100.0 * (1 - lost / span) if span > 0 else 0.0
    return res


def main():
    name, run, campath, posepath, out = sys.argv[1:6]
    _, cam = rd(campath)
    phdr, pose = rd(posepath)
    sc = score(cam) if cam else None

    fig = plt.figure(figsize=(12.6, 5.6), facecolor=BG)
    ax = fig.add_subplot(1, 2, 1)
    ax.set_facecolor(BG)
    ax.plot([p[0] for p in RECT], [p[1] for p in RECT], ls='--', lw=1.2,
            color=MUTED, zorder=1, label='target rectangle')
    for tag, (dx, dy) in DOTS.items():
        ax.plot([dx], [dy], 'o', ms=14, color='#f0a35e', mec='white',
                mew=1.5, zorder=2)
        ax.annotate(tag, (dx, dy), textcoords='offset points',
                    xytext=(0, 13), ha='center', color=INK2, fontsize=8)
    if cam:
        ax.plot([c[1] for c in cam], [c[2] for c in cam], lw=2.0,
                color=S2, zorder=4, label='camera (truth)')
        ax.plot([cam[0][1]], [cam[0][2]], 'o', ms=10, color=S2,
                mec='white', mew=1.5, zorder=6, label='start')
        ax.plot([cam[-1][1]], [cam[-1][2]], 's', ms=10, color=S2,
                mec='white', mew=1.5, zorder=6,
                label=(f'end — closure {sc["closure"]:.1f} cm'
                       if sc else 'end'))
    if pose:
        ax.plot([p[4] for p in pose], [p[5] for p in pose], lw=1.5,
                color=S1, zorder=3, label='robot-reported (OTOS)')
    # Closure rides the 'end' legend entry rather than a floating label:
    # it names the marker it describes, and the title already carries
    # the number, so a third copy was only there to collide with things.
    ax.set_xlabel('x [cm]  (+east)', color=INK2)
    ax.set_ylabel('y [cm]  (+north)', color=INK2)
    ax.set_aspect('equal', adjustable='datalim')
    ax.margins(0.16)
    ax.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax.tick_params(colors=INK2)
    for sp in ax.spines.values():
        sp.set_color(MUTED)
    # Centred, not upper-left: the path hugs the perimeter and the
    # corner labels live there, so a corner legend covers the NW dot.
    ax.legend(loc='center', frameon=False, fontsize=9, labelcolor=INK2)
    ax.set_title('Path', color=INK, fontsize=11, loc='left')

    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_facecolor(BG)
    ws = wheel_speeds(pose, phdr)
    if ws:
        t0 = ws[0][0]
        ax2.plot([w[0] - t0 for w in ws], [w[1] for w in ws], lw=1.5,
                 color=S1, label='left')
        ax2.plot([w[0] - t0 for w in ws], [w[2] for w in ws], lw=1.5,
                 color=S2, label='right')
        ax2.legend(loc='lower left', frameon=False, fontsize=9,
                   labelcolor=INK2)
    ax2.axhline(0, lw=1.2, color=MUTED)
    ax2.set_xlabel('time [s]', color=INK2)
    ax2.set_ylabel('wheel speed [cm/s]  (measured)', color=INK2)
    ax2.grid(True, lw=0.5, color=MUTED, alpha=0.5)
    ax2.tick_params(colors=INK2)
    for sp in ax2.spines.values():
        sp.set_color(MUTED)
    ax2.set_title('Wheel speeds', color=INK, fontsize=11, loc='left')

    sub = ''
    if sc:
        seen = [sc[t] for t in ORDER if sc[t] is not None]
        worst = f'{max(seen):.1f} cm' if seen else 'n/a'
        miss = sum(1 for t in ORDER if sc[t] is None)
        sub = (f'worst corner {worst} · closure {sc["closure"]:.1f} cm · '
               f'tracked {sc["tracked"]:.0f}%'
               + (f' · {miss} corner(s) UNOBSERVED' if miss else ''))
    fig.suptitle(f'{TITLES.get(name, name)}  —  run {run}   {sub}',
                 color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=160)
    if sc:
        print('SCORE ' + ' '.join(
            f'{t}=' + ('unobserved' if sc[t] is None else f'{sc[t]:.1f}')
            for t in ORDER)
            + f' closure={sc["closure"]:.1f} tracked={sc["tracked"]:.0f}%')


if __name__ == '__main__':
    main()
