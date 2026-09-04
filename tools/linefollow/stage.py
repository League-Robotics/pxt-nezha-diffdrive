#!/usr/bin/env python3
"""Stage vevov at a target TRUE world pose (parallax-corrected) using ONE camera fix (the allowed
start-of-run seed): pivot to the bearing, drive the distance, pivot to the
target heading.  Prints a path check first and refuses anything outside the
12 cm margin.   Usage: stage.py X_CM Y_CM HEADING_DEG"""
import sys, time, math, json, pathlib, statistics
REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools'))
from fieldlink import FieldLink
from aprilcam.mcp import connection as _conn
CAL = json.loads((REPO / 'tools/field_calibration.json').read_text())
LEVER = CAL['lever_cm']; HOFF = CAL['heading_offset_deg']; K = CAL['parallax_k']; CAM = CAL['camera']; TAG = CAL['tag_number']
XL, YL = 67.15-12.0, 44.65-12.0
NADIR = (3.057, -2.799)   # camera nadir (cm); apparent = N + K*(true-N) for the 12 cm tag
tx, ty, th = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
def daemon():
    for n in dir(_conn):
        o = getattr(_conn, n)
        if isinstance(o, type) and hasattr(o, 'resolve') and hasattr(o, 'call'): return o().resolve()
D = daemon()
def pose(n=6):
    xs=[];ys=[];s=c=0.0;last=None
    while len(xs)<n:
        r=None
        for t in D.get_tags(CAM).tags:
            if t.tag.number==TAG and t.tag.family.value=='apriltag': r=(t.world.x,t.world.y,t.yaw_rad)
        if r is None or r==last: time.sleep(0.1); continue
        last=r; t=r[2]
        ax=r[0]-(math.cos(t)*LEVER[0]-math.sin(t)*LEVER[1]); ay=r[1]-(math.sin(t)*LEVER[0]+math.cos(t)*LEVER[1])
        xs.append(NADIR[0]+(ax-NADIR[0])/K); ys.append(NADIR[1]+(ay-NADIR[1])/K)
        s+=math.sin(t); c+=math.cos(t); time.sleep(0.08)
    return statistics.median(xs), statistics.median(ys), (math.degrees(math.atan2(s,c))+HOFF+180)%360-180
def wrap(d): return (d+180)%360-180
x0,y0,h0 = pose(); print('now  (%.1f, %.1f) h=%.1f' % (x0,y0,h0))
print('goal (%.1f, %.1f) h=%.1f' % (tx,ty,th))
if not (abs(tx)<=XL and abs(ty)<=YL): raise SystemExit('goal outside the 12 cm margin -- refusing')
dist = math.hypot(tx-x0, ty-y0); brg = math.degrees(math.atan2(ty-y0, tx-x0))
# drive forward or backward, whichever needs less rotation
if abs(wrap(brg-h0)) <= 90: t1, sgn = wrap(brg-h0), +1
else: t1, sgn = wrap(brg+180-h0), -1
t2 = wrap(th - (h0+t1))
print('plan: pivot %+.1f, drive %+.1f cm, pivot %+.1f  (straight leg %s -> %s, both inside margin: %s)' % (t1, sgn*dist, t2, (round(x0,1),round(y0,1)), (tx,ty), abs(x0)<=XL and abs(y0)<=YL))
if '--dry' in sys.argv: raise SystemExit(0)
L = FieldLink(CAL['radio_channel'], CAL['radio_group']); print('hello:', L.hello())
def go(cmd, wait):
    a = L.seqd(cmd); time.sleep(wait); return a
def pivot_to(target_h, label):
    """Pivot, then VERIFY with the camera; retry the residual once. Never
    trust an ack: a pivot that acked 'timeout' once did not turn at all and
    the following leg drove 27 cm the wrong way (03-stage-run2.txt)."""
    for attempt in range(2):
        _,_,h = pose(); d = wrap(target_h - h)
        if abs(d) <= 3.0: return True
        print(' %s pivot %+.1f:' % (label, d), go('MOVE_X 0 %d 188 9000' % int(round(math.radians(d)*1000)), 1.5 + abs(d)/60))
    _,_,h = pose(); d = wrap(target_h - h)
    print(' %s heading after pivots: %.1f (residual %+.1f)' % (label, h, d))
    return abs(d) <= 8.0
leg_h = brg if sgn > 0 else wrap(brg + 180)
if not pivot_to(leg_h, 'first'):
    L.close(); raise SystemExit('heading not verified -- NOT driving the leg')
xa,ya,ha = pose(); dist = math.hypot(tx-xa, ty-ya)
if dist > 0.5: print(' drive:', go('MOVE_X %d 0 200 15000' % int(round(sgn*dist*10)), 1.5 + dist/15))
pivot_to(th, 'final')
time.sleep(1.0)
x1,y1,h1 = pose(); print('end  (%.1f, %.1f) h=%.1f   error %.1f cm, %.1f deg' % (x1,y1,h1, math.hypot(x1-tx,y1-ty), wrap(h1-th)))
L.close()
