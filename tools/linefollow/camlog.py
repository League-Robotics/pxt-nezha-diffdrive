#!/usr/bin/env python3
"""Log the camera-measured centre of rotation of vevov (tag 53, raw, corrected
host-side with tools/field_calibration.json) to a CSV at the daemon's rate.
Diagnostic only: nothing here reaches the robot.  Usage: camlog.py out.csv"""
import sys, time, math, json, pathlib
from aprilcam.mcp import connection as _conn
REPO = pathlib.Path(__file__).resolve().parents[2]
CAL = json.loads((REPO / 'tools/field_calibration.json').read_text())
_ROBOT = 'vevov'; _E = CAL['robots'][_ROBOT]  # these tools are vevov-on-the-KIPR-mat tools; sprint 029 robots: schema
HOFF = 90.0 + _E['mount_yaw_residual_deg']  # robot heading = raw tag yaw + 90 (fixed AprilCam convention) + residual
LEVER = _E['lever_cm']; CAM = _E['camera']; TAG = _E['tag_number']; K = _E['parallax_k']; NADIR = (3.057, -2.799)
def daemon():
    for n in dir(_conn):
        o = getattr(_conn, n)
        if isinstance(o, type) and hasattr(o, 'resolve') and hasattr(o, 'call'): return o().resolve()
D = daemon()
out = open(sys.argv[1], 'w'); out.write('t,x_cm,y_cm,heading_deg,tag_x,tag_y,tag_yaw_deg,true_x_cm,true_y_cm\n'); out.flush()
last = None; n = 0
try:
    for frame in D.stream_tags(CAM):
        for r in frame.tags or ():
            if r.tag.number != TAG or r.tag.family.value != 'apriltag' or r.world is None: continue
            key = (r.world.x, r.world.y, r.yaw_rad)
            if key == last: continue
            last = key
            t = r.yaw_rad
            cx = r.world.x - (math.cos(t)*LEVER[0] - math.sin(t)*LEVER[1])
            cy = r.world.y - (math.sin(t)*LEVER[0] + math.cos(t)*LEVER[1])
            h = (math.degrees(t) + HOFF + 180) % 360 - 180
            out.write('%.3f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n' % (time.time(), cx, cy, h, r.world.x, r.world.y, math.degrees(t), NADIR[0]+(cx-NADIR[0])/K, NADIR[1]+(cy-NADIR[1])/K))
            n += 1; out.flush()
except KeyboardInterrupt:
    pass
finally:
    out.flush(); out.close()
