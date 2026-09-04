#!/usr/bin/env python3
"""Chart a sensor_run.py result: camera truth vs the traced line, and the
robot's own odometry trace (start-anchored to the camera start pose).
usage: chart_sensor.py run.json path.json out.png"""
import sys, json, math, bisect, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
rj, pj, out = sys.argv[1:4]
run = json.load(open(rj)); path = json.load(open(pj))
P = np.array(path['points'])/10.0; cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
cam = np.array(run['camera']); tr = np.array(run['trace']) if run['trace'] else np.zeros((0,6))
t0 = run['t_start']
# window camera to the run
endt = t0 + (float(run['end'].split(':')[3])/1000 if run.get('end') else 1e9) + 1.0
cam = cam[(cam[:,0] >= t0 - 1.0) & (cam[:,0] <= endt)]
def nearest(x, y, s_hint, win=40.0):
    lo = max(bisect.bisect_left(cum, s_hint - win*0.25), 0); hi = bisect.bisect_right(cum, s_hint + win)
    seg = P[lo:hi+1]
    if len(seg) < 1: seg = P; lo = 0
    d = np.hypot(seg[:,0]-x, seg[:,1]-y); i = int(np.argmin(d)); return cum[lo+i], d[i]
s = 0.0; errs = []; ss = []
for x, y in cam[:,1:3]:
    s, e = nearest(x, y, s); errs.append(e); ss.append(s)
errs = np.array(errs); ss = np.array(ss)
# odometry trace -> field, anchored on the camera start pose
if len(tr) and len(cam):
    x0, y0, h0 = cam[0,1], cam[0,2], math.radians(cam[0,3])
    ox, oy, oh = tr[:,3], tr[:,4], np.radians(tr[:,5])
    rot = h0 - oh[0]; c, sn = math.cos(rot), math.sin(rot)
    fx = x0 + (ox-ox[0])*c - (oy-oy[0])*sn; fy = y0 + (ox-ox[0])*sn + (oy-oy[0])*c
else: fx = fy = np.array([])
print('camera cross-track: mean %.2f cm, p95 %.2f, max %.2f (n=%d); reached s=%.0f of %.0f cm; end: %s' % (errs.mean(), np.percentile(errs,95), errs.max(), len(errs), ss.max(), cum[-1], run.get('end')))
BLUE, ORANGE, INK, MUT, GRID = '#2a78d6', '#d95926', '#0b0b0b', '#52514e', '#e4e2dc'
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), facecolor='#faf9f5', gridspec_kw={'width_ratios':[1.6,1]})
for ax in (ax1, ax2):
    ax.set_facecolor('#faf9f5'); ax.grid(True, color=GRID, lw=0.7); ax.tick_params(colors=MUT, labelsize=9)
    for sp in ('top','right'): ax.spines[sp].set_visible(False)
ax1.plot(P[:,0], P[:,1], color=MUT, lw=6, alpha=0.25, label='line (camera trace)'); ax1.plot(P[:,0], P[:,1], color=MUT, lw=1, ls=(0,(4,3)))
if len(fx): ax1.plot(fx, fy, color=ORANGE, lw=1.2, label='robot odometry')
ax1.plot(cam[:,1], cam[:,2], color=BLUE, lw=1.6, label='camera truth')
ax1.add_patch(plt.Rectangle((-67.15,-44.65),134.3,89.3, fill=False, ec=GRID, lw=1)); ax1.set_aspect('equal')
ax1.set_xlabel('x [cm]', color=MUT); ax1.set_ylabel('y [cm]', color=MUT); ax1.legend(frameon=False, fontsize=9, labelcolor=MUT, loc='lower left')
ax1.set_title('Trackbit line following, vevov: %s' % run['cmd'], color=INK, fontsize=11, loc='left')
ax2.plot(ss, errs, color=BLUE, lw=1.2); ax2.axhline(1.25, color=GRID, lw=1); ax2.text(2, 1.35, 'half line width', color=MUT, fontsize=8)
ax2.set_xlabel('distance along the line [cm]', color=MUT); ax2.set_ylabel('camera cross-track of the robot centre [cm]', color=MUT)
ax2.set_title('mean %.1f cm, max %.1f cm' % (errs.mean(), errs.max()), color=INK, fontsize=10.5, loc='left')
fig.tight_layout(); fig.savefig(out, dpi=150); print('chart', out)
