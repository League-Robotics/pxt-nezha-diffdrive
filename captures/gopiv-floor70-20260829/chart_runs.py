"""Four-panel wheel-speed chart: three individual runs of the legs-and-turn
sequence, plus their average.

    python3 chart_runs.py runs.json out.png "title"

Average: each phase (leg150, leg200, turn360) is aligned across runs on its
own motion onset, resampled to a 20 ms grid and averaged; phases are then
placed at their mean offset from the run's first onset, so the average is
not smeared by host-side pause jitter between phases.
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

SURF, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
LEFT, RIGHT = '#2a78d6', '#eb6834'
PHASES = ('leg150', 'leg200', 'turn360')
GRID_DT = 0.02
GLITCH = 500.0   # mm/s: a single-frame sample beyond this is an encoder glitch, not motion


def live(frames):
    out, pc = [], None
    for f in frames:
        if pc is None or f['cyc'] > pc:
            out.append(f)
        pc = f['cyc']
    return out


def phase_segments(d, run):
    """{phase: (t_abs, vl, vr, t_onset)} for one run, from live frames."""
    fr, ev = live(d['frames']), d['events']
    segs = {}
    for i, e in enumerate(ev):
        if e.get('run') != run or e['phase'] not in PHASES:
            continue
        t_next = ev[i + 1]['t_send'] if i + 1 < len(ev) else fr[-1]['host_t'] + 1
        seg = [f for f in fr if e['t_send'] - 0.2 <= f['host_t'] < t_next]
        on = next((f for f in seg if f['host_t'] >= e['t_send'] and
                   (abs(f['vl']) > 20 or abs(f['vr']) > 20)), None)
        if on is None:
            continue
        t = np.array([f['host_t'] for f in seg])
        vl = np.array([f['vl'] for f in seg], float)
        vr = np.array([f['vr'] for f in seg], float)
        vl[np.abs(vl) > GLITCH] = np.nan   # break the line, never draw a glitch as motion
        vr[np.abs(vr) > GLITCH] = np.nan
        segs[e['phase']] = (t, vl, vr, on['host_t'])
    return segs


def style(ax, title):
    ax.set_facecolor(SURF)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_title(title, loc='left', fontsize=11, color=INK, pad=6)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_ylabel('wheel speed [mm/s]', color=INK2, fontsize=9)


def main():
    path, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
    d = json.load(open(path))
    runs = sorted({e['run'] for e in d['events'] if e['run'] > 0})
    fig, axes = plt.subplots(4, 1, figsize=(13, 12.5), facecolor=SURF, sharex=True)
    per_run = {}
    for ax, run in zip(axes[:3], runs):
        segs = phase_segments(d, run)
        per_run[run] = segs
        t0 = segs['leg150'][3]
        for ph in PHASES:
            if ph not in segs:
                continue
            t, vl, vr, on = segs[ph]
            ax.plot(t - t0, vl, color=LEFT, linewidth=2, label='left' if ph == 'leg150' else None)
            ax.plot(t - t0, vr, color=RIGHT, linewidth=2, label='right' if ph == 'leg150' else None)
            ax.annotate(ph.replace('leg', 'leg ').replace('turn360', '360° turn'),
                        (on - t0, 290), xytext=(2, 0), textcoords='offset points',
                        fontsize=8.5, color=INK2, va='top')
        style(ax, f'run {run}')
        ax.set_ylim(-260, 320)
        ax.legend(loc='upper right', fontsize=8.5, frameon=False, labelcolor=INK)
    # averaged panel: per-phase alignment
    ax = axes[3]
    for ph in PHASES:
        offs, grids = [], []
        for run in runs:
            segs = per_run[run]
            if ph not in segs:
                continue
            t, vl, vr, on = segs[ph]
            offs.append(on - segs['leg150'][3])
            tt = t - on
            g = np.arange(-0.2, tt.max(), GRID_DT)
            okl, okr = ~np.isnan(vl), ~np.isnan(vr)
            grids.append((g, np.interp(g, tt[okl], vl[okl]), np.interp(g, tt[okr], vr[okr])))
        n = min(len(g[0]) for g in grids)
        g = grids[0][0][:n]
        vl = np.mean([x[1][:n] for x in grids], axis=0)
        vr = np.mean([x[2][:n] for x in grids], axis=0)
        off = float(np.mean(offs))
        ax.plot(g + off, vl, color=LEFT, linewidth=2, label='left' if ph == 'leg150' else None)
        ax.plot(g + off, vr, color=RIGHT, linewidth=2, label='right' if ph == 'leg150' else None)
        ax.annotate(ph.replace('leg', 'leg ').replace('turn360', '360° turn'), (off, 290),
                    xytext=(2, 0), textcoords='offset points', fontsize=8.5, color=INK2, va='top')
    style(ax, f'average of runs {runs[0]}–{runs[-1]} (each phase aligned on its own onset)')
    ax.set_ylim(-260, 320)
    ax.legend(loc='upper right', fontsize=8.5, frameon=False, labelcolor=INK)
    ax.set_xlabel('time since first leg onset [s]', color=INK2, fontsize=9)
    fig.suptitle(title, x=0.01, ha='left', fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=130, facecolor=SURF)
    print('wrote', out)


if __name__ == '__main__':
    main()
