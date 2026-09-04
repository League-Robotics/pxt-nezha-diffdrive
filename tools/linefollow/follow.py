#!/usr/bin/env python3
"""World-anchored pure pursuit along a field-frame path, on vevov's own odometry.

Camera use is exactly the allowed pattern: ONE fix at rest before the run to
seed the field->odometry transform, one fix at the end to score. Nothing the
camera sees during the run reaches the robot.

Why not run_tour.py's SPLINE step: it anchors the path to the robot's start
pose and aligns the path tangent with the robot's heading, so a staging error
of e degrees rotates the whole course by e degrees -- 8 deg is 30 cm at the far
end of this 2.3 m open course. Anchoring in the field frame from a camera fix
makes staging error a small cross-track offset the follower steers out.

Camera positions of the tag are parallax-dilated about the camera nadir:
apparent = N + K*(true - N). Everything here converts to TRUE ground coords.

usage: follow.py path.json [--speed 140] [--lookahead 90] [--interval 0.12]
                 [--host nada.local] [--port 44483] [--out DIR]
"""
import sys, time, math, json, statistics, pathlib, argparse
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tests/system')); sys.path.insert(0, str(REPO / 'tools'))
from run_tour import Link, Path2D           # noqa: E402
from aprilcam.mcp import connection as _conn  # noqa: E402

CAL = json.loads((REPO / 'tools/field_calibration.json').read_text())
LEVER, HOFF, K, CAM, TAG = CAL['lever_cm'], CAL['heading_offset_deg'], CAL['parallax_k'], CAL['camera'], CAL['tag_number']
NADIR = (3.057, -2.799)      # daemon camera_position for arducam-ov9782, cm
FIELD_X, FIELD_Y = 60.0, 40.0  # odometry geofence, cm (hard stop)

ap = argparse.ArgumentParser()
ap.add_argument('path'); ap.add_argument('--speed', type=float, default=140)
ap.add_argument('--lookahead', type=float, default=90); ap.add_argument('--interval', type=float, default=0.12)
ap.add_argument('--host', default='nada.local'); ap.add_argument('--port', type=int, default=44483)
ap.add_argument('--out', default=str(pathlib.Path(__file__).parent))
a = ap.parse_args()

def daemon():
    for n in dir(_conn):
        o = getattr(_conn, n)
        if isinstance(o, type) and hasattr(o, 'resolve') and hasattr(o, 'call'): return o().resolve()
D = daemon()

def cam_pose(n=6):
    """TRUE centre of rotation (cm) and heading (deg) from the raw tag, at rest."""
    xs = []; ys = []; s = c = 0.0; last = None; t0 = time.time()
    while len(xs) < n and time.time() - t0 < 15:
        r = None
        for t in D.get_tags(CAM).tags:
            if t.tag.number == TAG and t.tag.family.value == 'apriltag': r = (t.world.x, t.world.y, t.yaw_rad)
        if r is None or r == last: time.sleep(0.1); continue
        last = r; t = r[2]
        ax = r[0] - (math.cos(t)*LEVER[0] - math.sin(t)*LEVER[1]); ay = r[1] - (math.sin(t)*LEVER[0] + math.cos(t)*LEVER[1])
        xs.append(NADIR[0] + (ax - NADIR[0]) / K); ys.append(NADIR[1] + (ay - NADIR[1]) / K)
        s += math.sin(t); c += math.cos(t); time.sleep(0.08)
    if not xs: return None
    return statistics.median(xs), statistics.median(ys), (math.degrees(math.atan2(s, c)) + HOFF + 180) % 360 - 180

path = Path2D(a.path)
log = {'path': a.path, 'speed': a.speed, 'lookahead': a.lookahead, 'interval': a.interval, 'iters': []}

cp = cam_pose()
if cp is None: raise SystemExit('no camera fix')
print('camera start (true): (%.1f, %.1f) cm h=%.1f deg' % cp)

link = Link(a.host, a.port)
print(' ', link.unseq('HELLO', r'^device ')); link._seq = 0
print(' ', link.status())
link.seqd('TLM FULL')
t0 = time.time()
while link.pose() is None and time.time() - t0 < 6: time.sleep(0.1)
op = link.pose()
if op is None: link.close(); raise SystemExit('no telemetry pose')
ox0, oy0, oh0 = op
print('odometry start: (%.0f, %.0f) mm h=%.1f deg' % (ox0, oy0, math.degrees(oh0)))
# field -> odom: odom = o0 + R(rot) * (field - w0)
wx0, wy0 = cp[0]*10, cp[1]*10; hw0 = math.radians(cp[2]); rot = oh0 - hw0
cr, sr = math.cos(rot), math.sin(rot)
def to_odom(fx, fy):
    u, v = fx - wx0, fy - wy0
    return ox0 + u*cr - v*sr, oy0 + u*sr + v*cr
def to_field(x, y):
    u, v = x - ox0, y - oy0
    return wx0 + u*cr + v*sr, wy0 - u*sr + v*cr
def field_heading(h): return h - rot

# where are we relative to the path start?
fx, fy = to_field(ox0, oy0)
cur, err = path.nearest(fx, fy, 0.0, window=400.0)
cur = max(cur, 0.0)   # parked short of the first point: nearest() can return a negative probe
px, py = path.at(cur); qx, qy = path.at(cur + 30)
tang = math.atan2(qy - py, qx - px)
dh = (field_heading(oh0) - tang + math.pi) % (2*math.pi) - math.pi
print('start check: on-path s=%.0f mm, cross-track %.1f cm, heading vs tangent %+.1f deg' % (cur, err/10, math.degrees(dh)))
if err > 80 or abs(dh) > math.radians(45):
    link.seq_fire('MOVE_V 0 0 200'); link.close(); raise SystemExit('start pose too far from the path -- restage')

mark = link.mark(); cursor = cur; total = path.length
dur_ms = int(a.interval * 1000 * 2.2)
deadline = time.time() + total / max(a.speed, 1) * 3.0 + 30
tstart = time.time(); reason = 'end of path'
try:
    while cursor < total - a.lookahead * 0.5:
        if time.time() > deadline: reason = 'deadline'; break
        p = link.pose()
        if p is None: time.sleep(a.interval); continue
        rx, ry, rh = p
        fx, fy = to_field(rx, ry)
        if abs(fx) > FIELD_X*10 or abs(fy) > FIELD_Y*10: reason = 'GEOFENCE at (%.0f,%.0f)' % (fx, fy); break
        cursor, err = path.nearest(fx, fy, cursor, window=300.0); cursor = max(cursor, 0.0)
        ax, ay = path.at(cursor + a.lookahead)
        ax, ay = to_odom(ax, ay)
        dx, dy = ax - rx, ay - ry
        fwd = dx*math.cos(rh) + dy*math.sin(rh); lat = -dx*math.sin(rh) + dy*math.cos(rh)
        L2 = dx*dx + dy*dy
        kappa = 2.0*lat/L2 if L2 > 1.0 else 0.0
        v = a.speed if fwd >= 0 else a.speed*0.35
        omega = kappa * v
        if abs(omega) > 2.5: omega = math.copysign(2.5, omega)
        if abs(omega) > 1.2: v = min(v, a.speed*0.5); omega = kappa * v if abs(kappa*v) < 2.5 else omega
        link.seq_fire('MOVE_V %d %d %d' % (round(v), round(omega*1000), dur_ms))
        log['iters'].append([round(time.time()-tstart, 3), round(rx), round(ry), round(math.degrees(rh), 2), round(fx), round(fy), round(cursor), round(err, 1), round(v), round(omega, 3)])
        time.sleep(a.interval)
finally:
    link.seq_fire('MOVE_V 0 0 200'); time.sleep(0.4)
    try: link.seqd('STOP')
    except Exception: pass
    time.sleep(0.8)
    frames = link.frames(mark)
    wall = time.time() - tstart
    link.close()
print('stopped: %s after %.1f s, %d iterations, cursor %.0f / %.0f mm' % (reason, wall, len(log['iters']), cursor, total))
errs = [it[7] for it in log['iters']]
if errs: print('odometry cross-track: mean %.1f cm, max %.1f cm' % (statistics.mean(errs)/10, max(errs)/10))
time.sleep(1.5)
ce = cam_pose()
if ce:
    cur_e, err_e = path.nearest(ce[0]*10, ce[1]*10, total, window=600.0)
    ex, ey = path.at(total)
    print('camera end (true): (%.1f, %.1f) h=%.1f; distance to path end %.1f cm, cross-track %.1f cm' % (ce[0], ce[1], ce[2], math.hypot(ce[0]*10-ex, ce[1]*10-ey)/10, err_e/10))
log.update({'camera_start': cp, 'camera_end': ce, 'odom_start': [ox0, oy0, oh0], 'rot': rot, 'reason': reason, 'wall_s': wall, 'frames': frames, 'nadir': NADIR, 'K': K})
out = pathlib.Path(a.out) / ('follow-%s.json' % time.strftime('%H%M%S'))
json.dump(log, open(out, 'w')); print('log', out)
