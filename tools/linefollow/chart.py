#!/usr/bin/env python3
"""Score and chart a follow run: reference path, camera-truthed track (true
ground coords), odometry track mapped into the field frame, and the two
cross-track series.  usage: chart.py follow.json camlog.csv out.png"""
import sys, json, math, csv, bisect
import numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
fj, camcsv, out = sys.argv[1:4]
log = json.load(open(fj)); path = json.load(open(log['path']))
P = np.array(path['points']) / 10.0
cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
def nearest(x, y, s_hint, win=40.0):
    lo = bisect.bisect_left(cum, s_hint - win*0.25); hi = bisect.bisect_right(cum, s_hint + win)
    seg = P[max(lo,0):hi+1]
    if len(seg) < 1: seg = P
    d = np.hypot(seg[:,0]-x, seg[:,1]-y); i = int(np.argmin(d))
    return cum[max(lo,0)+i], d[i]
# camera track (true coords), during the run only
t0 = None
rows = [r for r in csv.DictReader(open(camcsv))]
cam = np.array([[float(r['t']), float(r['true_x_cm']), float(r['true_y_cm']), float(r['heading_deg'])] for r in rows])
it = np.array(log['iters']) if log['iters'] else np.zeros((0,10))
# odometry -> field
ox0, oy0, oh0 = log['odom_start']; rot = log['rot']; wx0, wy0 = log['camera_start'][0], log['camera_start'][1]
cr, sr = math.cos(rot), math.sin(rot)
fr = np.array(log['frames'], float)
if len(fr):
    ox, oy = fr[:,3]/10.0, fr[:,4]/10.0
    u, v = ox - ox0/10.0, oy - oy0/10.0
    fx, fy = wx0 + u*cr + v*sr, wy0 - u*sr + v*cr
else:
    fx = fy = np.array([])
# camera cross-track with a monotone cursor, restricted to the run window (by motion)
s = 0.0; cam_err = []; cam_s = []
moving = np.hypot(np.diff(cam[:,1], prepend=cam[0,1]), np.diff(cam[:,2], prepend=cam[0,2])) > 0.05
first = np.argmax(moving) if moving.any() else 0
# window the camera log to the RUN: from first motion to the follower's wall time
# (+1.5 s settle). Anything after is staging for the next run, not this one.
t_end = cam[first,0] + log.get('wall_s', 1e9) + 1.5
last = int(np.searchsorted(cam[:,0], t_end))
cam = cam[:max(last, first+2)]
for x, y in cam[first:, 1:3]:
    s, e = nearest(x, y, s); cam_err.append(e); cam_s.append(s)
cam_err = np.array(cam_err); cam_s = np.array(cam_s)
odo_err = it[:,7]/10.0 if len(it) else np.array([])
print('camera cross-track: mean %.2f cm, p95 %.2f, max %.2f (n=%d); reached s=%.0f of %.0f cm' % (cam_err.mean(), np.percentile(cam_err,95), cam_err.max(), len(cam_err), cam_s.max(), cum[-1]))
if len(odo_err): print('odometry cross-track: mean %.2f cm, max %.2f' % (odo_err.mean(), odo_err.max()))
BLUE, ORANGE, INK, MUT, GRID = '#2a78d6', '#d95926', '#0b0b0b', '#52514e', '#e4e2dc'
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), facecolor='#faf9f5', gridspec_kw={'width_ratios':[1.6,1]})
for ax in (ax1, ax2):
    ax.set_facecolor('#faf9f5'); ax.grid(True, color=GRID, lw=0.7); ax.tick_params(colors=MUT, labelsize=9)
    for sp in ('top','right'): ax.spines[sp].set_visible(False)
ax1.plot(P[:,0], P[:,1], color=MUT, lw=6, alpha=0.25, label='line (from camera trace)')
ax1.plot(P[:,0], P[:,1], color=MUT, lw=1, ls=(0,(4,3)))
if len(fx): ax1.plot(fx, fy, color=ORANGE, lw=1.3, label='robot odometry (field frame)')
ax1.plot(cam[first:,1], cam[first:,2], color=BLUE, lw=1.6, label='camera truth')
ax1.plot(P[0,0], P[0,1], 'o', color=INK, ms=8); ax1.plot(P[-1,0], P[-1,1], 's', color=INK, ms=7)
ax1.add_patch(plt.Rectangle((-67.15,-44.65),134.3,89.3, fill=False, ec=GRID, lw=1))
ax1.set_aspect('equal'); ax1.set_xlabel('x [cm]', color=MUT); ax1.set_ylabel('y [cm]', color=MUT)
ax1.legend(frameon=False, fontsize=9, labelcolor=MUT, loc='lower left')
ax1.set_title('KIPR line course, vevov, %s' % fj.split('follow-')[-1].split('.')[0], color=INK, fontsize=11, loc='left')
ax2.plot(cam_s, cam_err, color=BLUE, lw=1.2, label='camera')
if len(it): ax2.plot(it[:,6]/10.0, odo_err, color=ORANGE, lw=1.0, label='odometry (what the robot believed)')
ax2.axhline(1.25, color=GRID, lw=1); ax2.text(2, 1.35, 'half line width', color=MUT, fontsize=8)
ax2.set_xlabel('distance along the line [cm]', color=MUT); ax2.set_ylabel('cross-track error [cm]', color=MUT)
ax2.legend(frameon=False, fontsize=9, labelcolor=MUT)
ax2.set_title('cross-track: camera mean %.1f cm, max %.1f cm' % (cam_err.mean(), cam_err.max()), color=INK, fontsize=10.5, loc='left')
fig.tight_layout(); fig.savefig(out, dpi=150); print('chart', out)
