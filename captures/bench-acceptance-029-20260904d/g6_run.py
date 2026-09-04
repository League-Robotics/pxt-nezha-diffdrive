"""G6 square-tour closure on tovez over zilch, south corridor, host-driven.

Same verbs test.ts's squareTour() issues (tickedMove(side,0) then
tickedMove(0,90), four times), sent from the host as MOVE_X so the run
stays on the STATUS-polled, geofenced path used by every other gate in
this session (the RUN: fiber is a different dispatch path). Side 200 mm,
left turns, from a start facing +x in the corridor's south-west. Closure
= camera distance between the start and end poses at rest, plus the
heading residual. 3 laps.
Usage: g6_run.py host:port lag stop_distance rotational_slip [side_mm]
"""
import sys, time, math, json, statistics, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam

OUT = 'captures/bench-acceptance-029-20260904d/'
LIMX = 55.0; YMIN, YMAX = -33.0, -8.0
HARDX, HARDYN, HARDYS = 61.0, -3.0, -40.0
SIDE = int(sys.argv[5]) if len(sys.argv) > 5 else 200   # [mm]
cam = Cam()
def one():
    for t in cam.d.get_tags(cam.cam).tags:
        if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
            return t.world.x, t.world.y, math.degrees(t.yaw_rad)
    return None
def pose(n=5):
    xs = ys = sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        r = one()
        if r:
            xs += r[0]; ys += r[1]; sy += math.sin(math.radians(r[2])); cy += math.cos(math.radians(r[2])); k += 1
        time.sleep(0.1)
    return (xs/k, ys/k, math.degrees(math.atan2(sy, cy))) if k else None
L = TcpLink(sys.argv[1]); sid = 0; LOG = []
def ask(c, sec=0.8, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:') and not l.startswith('t ') and not l.startswith('thdr')]
    LOG.append((c, r)); print(c, '->', r[:2]); return r
def run_move(cmd, limit=10.0):
    global sid
    sid += 1; cmd = f'{cmd} #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    seen1 = False; tdone = None; reason = None; estop = False
    while time.time() - t0 < limit:
        for l in L.read(0.12):
            if l.startswith('status '):
                a = re.search(r'active=(\d)', l).group(1); rs = re.search(r'reason=(\w+)', l).group(1)
                dn = int(re.search(r'done=(\d+)', l).group(1))
                if a == '1': seen1 = True
                if dn == sid and tdone is None: tdone = round(time.time() - t0, 2); reason = rs; seen1 = True
        if tdone is not None and time.time() - t0 > tdone + 0.5: break
        r = one()
        if r and (abs(r[0]) > HARDX or r[1] > HARDYN or r[1] < HARDYS):
            L.s.sendall(b'ESTOP\n'); estop = True; print(f'!!! GEOFENCE ESTOP at ({r[0]:.1f},{r[1]:.1f})'); break
        L.s.sendall(b'STATUS\n')
    LOG.append((cmd, {'done_s': tdone, 'reason': reason, 'estop': estop}))
    return {'done_s': tdone, 'reason': reason, 'estop': estop, 'started': seen1}
def face(target_deg):
    for attempt in range(3):
        p = pose(); d = (target_deg - p[2] + 180) % 360 - 180
        if abs(d) <= 2.5: return p
        run_move(f'MOVE_X 0 {int(round(math.radians(d)*1000))} 100 6000'); time.sleep(0.5)
    return pose()
def goto_xy(tx, ty):
    p = pose(); brg = math.degrees(math.atan2(ty - p[1], tx - p[0])); d = math.hypot(tx - p[0], ty - p[1])
    if d < 3: return p
    face(brg); run_move(f'MOVE_X {int(round(d*10))} 0 120 8000'); time.sleep(0.5); return pose()

ask('HELLO', seq=False); ask('RUN:clearestop', seq=False); ask('STATUS', seq=False)
for c in ('SET accel 400', 'SET decel 400', 'SET twist_hold_gain 2', f'SET lag {sys.argv[2]}',
          f'SET stop_distance {sys.argv[3]}', f'SET rotational_slip {sys.argv[4]}', 'GET lag', 'GET rotational_slip'):
    ask(c)
# start at the SW of the corridor box: square spans x [sx, sx+side], y [sy, sy+side] (left turns)
sx, sy = -42.0, -31.0
side_cm = SIDE / 10
assert YMIN <= sy and sy + side_cm <= YMAX and abs(sx) <= LIMX and abs(sx + side_cm) <= LIMX
p = goto_xy(sx, sy); p = face(0.0); print('square start pose', p)
laps = []
for lap in range(3):
    p0 = pose(); corners = [p0]; ok = True
    for i in range(4):
        m = run_move(f'MOVE_X {SIDE} 0 150 8000')
        if m['estop'] or not m['started']: ok = False; print('leg aborted', m); break
        time.sleep(0.4)
        m = run_move('MOVE_X 0 1571 100 5000')
        if m['estop'] or not m['started']: ok = False; print('pivot aborted', m); break
        time.sleep(0.4); corners.append(pose())
    p1 = pose()
    closure = math.hypot(p1[0]-p0[0], p1[1]-p0[1]) * 10; dh = (p1[2]-p0[2]+180) % 360 - 180
    laps.append({'lap': lap, 'p0': p0, 'p1': p1, 'corners': corners, 'closure_mm': closure, 'heading_residual_deg': dh, 'ok': ok})
    print(f'lap {lap}: closure {closure:.0f} mm, heading residual {dh:+.1f} deg, ok={ok}; corners {[(round(c[0],1), round(c[1],1), round(c[2],1)) for c in corners]}')
    if not ok: break
    # re-square to the start for the next lap
    p = goto_xy(sx, sy); face(0.0)
ask('STATUS', seq=False); L.close()
if laps:
    print(f'G6: closure {[round(l["closure_mm"]) for l in laps]} mm, mean {statistics.mean(l["closure_mm"] for l in laps):.0f} mm; '
          f'heading residual {[round(l["heading_residual_deg"],1) for l in laps]} deg')
json.dump({'args': sys.argv[1:], 'side_mm': SIDE, 'laps': laps, 'log': LOG}, open(OUT + 'g6-run.json', 'w'), indent=1)
