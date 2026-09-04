"""When does a MOVE_X pivot actually complete? Poll STATUS active=/done=
every 150 ms after the send; ack latency with TLM off vs FULL.
twist_hold_gain restored to the compiled default 2.0 first (the dance
had left it at 8). Camera heading before/after each pivot."""
import sys, time, math, json, re
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam
cam = Cam()
def heading(n=5):
    sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        for t in cam.d.get_tags(cam.cam).tags:
            if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
                sy += math.sin(t.yaw_rad); cy += math.cos(t.yaw_rad); k += 1
        time.sleep(0.1)
    return math.degrees(math.atan2(sy, cy)) if k else None
L = TcpLink(sys.argv[1]); sid = 0
def ask(c, sec=0.8, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:') and not l.startswith('t ') and not l.startswith('thdr')]
    print(c, '->', r[:2]); return r
ask('HELLO', seq=False); ask('RUN:clearestop', seq=False)
ask('SET twist_hold_gain 2'); ask('GET twist_hold_gain'); ask('GET lag'); ask('GET stop_distance')
out = []
for tlm, sign in ((False, 1), (False, -1), (True, 1), (True, -1)):
    if tlm: ask('TLM FULL', 0.4)
    h0 = heading(); sid += 1; cmd = f'MOVE_X 0 {sign*1571} 100 5000 #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    ackt = None; trace = []; frames = []
    while time.time() - t0 < 6.5:
        for l in L.read(0.12):
            if l.startswith(f'ack {sid} ') and ackt is None: ackt = time.time() - t0; trace.append((round(ackt,2), l))
            elif l.startswith('status '): trace.append((round(time.time()-t0,2), re.sub(r'.*(active=\d).*(done=\d+ reason=\w+)', r'\1 \2', l)))
            elif l.startswith('t '): frames.append((round(time.time()-t0,2), l.split()[10:12], l.split()[16:18]))
        L.s.sendall(b'STATUS\n')
    if tlm: ask('TLM OFF', 0.4); L.read(0.3)
    time.sleep(0.5); h1 = heading()
    got = (h1 - h0 + 180) % 360 - 180
    # first time active=0 after being 1
    seen1 = False; tdone = None
    for t, s in trace:
        if s.startswith('active=1'): seen1 = True
        if seen1 and s.startswith('active=0') and tdone is None: tdone = t
    mv = [f for f in frames if any(int(x) for x in f[1]) or any(int(x) for x in f[2])]
    print(f'tlm={tlm} sign={sign:+d}: ack at {ackt}s, active->0 at {tdone}s, camera {got:+.2f} deg (err {got-sign*90:+.2f}), '
          f'frames {len(frames)} moving-window {mv[0][0] if mv else None}..{mv[-1][0] if mv else None}, peak v {max((abs(int(f[1][0])) for f in frames), default=None)}')
    print('   status trace:', [x for x in trace if not x[1].startswith("ack")][:12], '...', [x for x in trace if not x[1].startswith("ack")][-3:])
    out.append({'tlm': tlm, 'sign': sign, 'ack_s': ackt, 'active0_s': tdone, 'got': got, 'trace': trace, 'frames': frames})
ask('STATUS', seq=False); L.close()
json.dump(out, open('captures/bench-acceptance-029-20260904d/pivot-timing.json', 'w'), indent=1)
