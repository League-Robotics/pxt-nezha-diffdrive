#!/usr/bin/env python3
"""Run the on-robot Trackbit line follower (RUN:line) over the farm serial
daemon and log everything.  The camera is NOT in the loop: a watchdog thread
only sends RUN:abort if the camera sees the robot's TRUE centre within
GUARD_CM of a rail, and logs truth for scoring.
usage: sensor_run.py ROBOT OUTPREFIX [speed_cm_s] [max_s] [kp]"""
import sys, socket, subprocess, time, re, json, math, threading, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aprilcam.mcp import connection as _conn
REPO = pathlib.Path(__file__).resolve().parents[2]
CAL = json.loads((REPO / 'tools/field_calibration.json').read_text())
_ROBOT = 'vevov'; _E = CAL['robots'][_ROBOT]  # these tools are vevov-on-the-KIPR-mat tools; sprint 029 robots: schema
HOFF = 90.0 + _E['mount_yaw_residual_deg']  # robot heading = raw tag yaw + 90 (fixed AprilCam convention) + residual
LEVER, K, CAM, TAG = _E['lever_cm'], _E['parallax_k'], _E['camera'], _E['tag_number']
NADIR = (3.057, -2.799); XLIM, YLIM = 67.15 - 12.0, 44.65 - 12.0
RADIO = '--radio' in sys.argv
argv = [a for a in sys.argv[1:] if a != '--radio']
robot, out = argv[0], argv[1]
speed = argv[2] if len(argv) > 2 else '8'; max_s = argv[3] if len(argv) > 3 else '90'; kp = argv[4] if len(argv) > 4 else '60'
if RADIO:
    # the torture relay pool, tuned to this robot's channel/group from the
    # calibration file. Lossy (~15-25 % of lines), so the guard repeats itself.
    s = socket.create_connection(('torture', 8760), timeout=15); s.settimeout(0.2)
    time.sleep(1.0); s.recv(65536) if False else None
    for c in ('!CG %d %d' % (_E['radio_channel'], _E['radio_group']), '!GO'):
        s.sendall((c + '\n').encode()); time.sleep(0.5)
    print('radio relay torture:8760 -> channel %d group %d' % (_E['radio_channel'], _E['radio_group']))
else:
    p = subprocess.Popen(['dns-sd', '-L', robot, '_mbserial._tcp', 'local.'], stdout=subprocess.PIPE, text=True)
    time.sleep(3); p.kill(); m = re.search(r'can be reached at (\S+?):(\d+)', p.stdout.read())
    host, port = m.group(1).rstrip('.'), int(m.group(2)); print('serial daemon', host, port)
    s = socket.create_connection((host, port), timeout=10); s.settimeout(0.2)
log = open(out + '.log', 'a'); lines = []; done = threading.Event(); aborted = [None]
def send(c):
    for _ in range(3 if RADIO else 1):
        s.sendall((c + ('\n' if RADIO else '\r\n')).encode())
        if RADIO: time.sleep(0.15)
    log.write('%.3f > %s\n' % (time.time(), c)); log.flush()

def daemon():
    for n in dir(_conn):
        o = getattr(_conn, n)
        if isinstance(o, type) and hasattr(o, 'resolve') and hasattr(o, 'call'): return o().resolve()
D = daemon()
cam = []
def watchdog():
    last = None
    for frame in D.stream_tags(CAM):
        if done.is_set(): break
        for r in frame.tags or ():
            if r.tag.number != TAG or r.tag.family.value != 'apriltag' or r.world is None: continue
            key = (r.world.x, r.world.y, r.yaw_rad)
            if key == last: continue
            last = key; t = r.yaw_rad
            ax = r.world.x - (math.cos(t)*LEVER[0] - math.sin(t)*LEVER[1]); ay = r.world.y - (math.sin(t)*LEVER[0] + math.cos(t)*LEVER[1])
            tx, ty = NADIR[0] + (ax - NADIR[0])/K, NADIR[1] + (ay - NADIR[1])/K
            h = (math.degrees(t) + HOFF + 180) % 360 - 180
            cam.append([time.time(), tx, ty, h])
            if (abs(tx) > XLIM or abs(ty) > YLIM) and aborted[0] is None:
                aborted[0] = (tx, ty); send('RUN:abort'); time.sleep(0.3); send('RUN:abort')   # never ESTOP: the minimal program cannot clear it
                print('!! GEOFENCE: camera true (%.1f, %.1f) -> RUN:abort' % (tx, ty))
wd = threading.Thread(target=watchdog, daemon=True); wd.start()
time.sleep(2.0)
if not cam: print('WARNING: no camera fix yet')
else: print('camera start (true): (%.1f, %.1f) h=%.1f' % tuple(cam[-1][1:]))
buf = b''
def pump(sec):
    end = time.time() + sec; got_end = False
    global buf
    while time.time() < end:
        try: buf += s.recv(65536)
        except socket.timeout: pass
        while b'\n' in buf:
            raw, buf = buf.split(b'\n', 1); t = raw.decode('utf-8', 'replace').strip()
            if t.startswith('< '): t = t[2:]
            if not t: continue
            log.write('%.3f < %s\n' % (time.time(), t)); log.flush(); lines.append((time.time(), t))
            if t.startswith('LINE:end') or t.startswith('DBG:') or t.startswith('status'): print('  <', t)
            if t.startswith('LINE:end'): got_end = True
        if got_end: return True
    return False
send('STATUS'); pump(1.0)
cmd = 'RUN:line:%s:%s:%s' % (speed, max_s, kp); print('>', cmd); t_start = time.time(); send(cmd)
ok = pump(float(max_s) + 8)
if not ok: print('no LINE:end within the limit -- sending RUN:abort'); send('RUN:abort'); pump(3)
done.set(); time.sleep(1.5)
trace = []
for ts, t in lines:
    if t.startswith('LINE:') and not t.startswith('LINE:end'):
        f = t.split(':')
        try: trace.append([ts, int(f[1]), int(f[2]), int(f[3])/10, int(f[4])/10, int(f[5])/10])
        except (ValueError, IndexError): pass
end = next((t for ts, t in lines if t.startswith('LINE:end')), None)
json.dump({'cmd': cmd, 't_start': t_start, 'end': end, 'trace': trace, 'camera': cam, 'geofence_abort': aborted[0]}, open(out + '.json', 'w'))
print('trace rows %d, camera rows %d, end: %s' % (len(trace), len(cam), end))
if cam: print('camera end (true): (%.1f, %.1f) h=%.1f' % tuple(cam[-1][1:]))
s.close(); log.close()
