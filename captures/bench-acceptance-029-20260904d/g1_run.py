"""G1 pivot gate with full-move telemetry: 12 alternating MOVE_X 0 +-1571
100 5000, TLM FULL throughout, completion detected by polling STATUS
(active=1 -> 0) so frames cover the whole pivot and the done reason is
resolved promptly. Also 20 single-sample camera headings at rest first
(the instrument's own noise floor).
Usage: g1_run.py host:port lag stop_distance"""
import sys, time, math, json, statistics, re
sys.path.insert(0, 'tools'); sys.path.insert(0, 'captures/bench-acceptance-029-20260904d')
from wire_acceptance import TcpLink
from camlink import Cam
cam = Cam()
def one():
    for t in cam.d.get_tags(cam.cam).tags:
        if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
            return math.degrees(t.yaw_rad), t.world.x, t.world.y
    return None
def heading(n=5):
    sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        r = one()
        if r: sy += math.sin(math.radians(r[0])); cy += math.cos(math.radians(r[0])); k += 1
        time.sleep(0.1)
    return math.degrees(math.atan2(sy, cy)) if k else None
def frames_from(lines):
    out = []
    for l in lines:
        p = l.split()
        if p and p[0] == 't' and len(p) >= 18:
            out.append({'now': int(p[2]), 'x': int(p[4]), 'y': int(p[5]), 'h': int(p[6]), 'vl': int(p[10]), 'vr': int(p[11]),
                        'dutl': int(p[16]), 'dutr': int(p[17])})
    return out

# camera noise floor
samples = []
for _ in range(20):
    r = one()
    if r: samples.append(r[0])
    time.sleep(0.12)
m = math.degrees(math.atan2(sum(math.sin(math.radians(s)) for s in samples), sum(math.cos(math.radians(s)) for s in samples)))
dev = [((s - m + 180) % 360 - 180) for s in samples]
print(f'camera heading at rest: n={len(samples)} sd={statistics.pstdev(dev):.3f} deg, peak-to-peak {max(dev)-min(dev):.3f} deg')

L = TcpLink(sys.argv[1]); sid = 0
def ask(c, sec=0.8, seq=True):
    global sid
    if seq: sid += 1; c = f'{c} #{sid}'
    r = [l for l in L.ask(c, sec) if not l.startswith('DBG:') and not l.startswith('t ') and not l.startswith('thdr')]
    print(c, '->', r[:2]); return r
ask('HELLO', seq=False); ask('RUN:clearestop', seq=False)
for c in ('SET accel 400', 'SET decel 400', 'SET twist_hold_gain 2', f'SET lag {sys.argv[2]}', f'SET stop_distance {sys.argv[3]}',
          'GET twist_hold_gain', 'GET lag', 'GET stop_distance'):
    ask(c)
ask('TLM FULL', 0.4)
rows = []; sign = 1
for i in range(12):
    pre = frames_from(L.read(0.4))
    h0 = heading()
    pre += frames_from(L.read(0.3))
    sid += 1; cmd = f'MOVE_X 0 {sign*1571} 100 5000 #{sid}'
    t0 = time.time(); L.s.sendall(cmd.encode() + b'\n')
    lines = []; seen1 = False; tdone = None; reason = None
    while time.time() - t0 < 6.5:
        got = L.read(0.12); lines += got
        for l in got:
            if l.startswith('status '):
                a = re.search(r'active=(\d)', l).group(1); rs = re.search(r'reason=(\w+)', l).group(1)
                if a == '1': seen1 = True
                if seen1 and a == '0' and tdone is None: tdone = round(time.time() - t0, 2); reason = rs
        if tdone is not None and time.time() - t0 > tdone + 0.6: break
        L.s.sendall(b'STATUS\n')
    time.sleep(0.5)
    post = frames_from(L.read(0.3))
    h1 = heading()
    fr = frames_from(lines) + post
    cam_delta = (h1 - h0 + 180) % 360 - 180
    odo0 = pre[-1]['h'] / 100.0 if pre else None
    odo1 = fr[-1]['h'] / 100.0 if fr else None
    odo_delta = (odo1 - odo0) if odo0 is not None and odo1 is not None else None
    mv = [f for f in fr if f['vl'] or f['vr']]
    last = mv[-10:]
    rev = any(a['dutl']*b['dutl'] < 0 or a['dutr']*b['dutr'] < 0 for a, b in zip(last, last[1:])) if len(last) > 1 else None
    pk = max((max(abs(f['vl']), abs(f['vr'])) for f in fr), default=None)
    err = cam_delta - sign*90
    rows.append({'i': i, 'cmd': sign*90, 'cam_delta': cam_delta, 'err': err, 'odo_delta': odo_delta, 'done_s': tdone,
                 'reason': reason, 'rev_last10': rev, 'peak_v': pk, 'frames': fr})
    print(f'pivot {i:2d} cmd {sign*90:+4d} cam {cam_delta:+7.2f} err {err:+5.2f} odo {odo_delta if odo_delta is None else round(odo_delta,2):>7} '
          f'done {tdone}s {reason} peak {pk} rev={rev} nfr={len(fr)}')
    sign = -sign
ask('TLM OFF', 0.4); L.read(0.4); ask('STATUS', seq=False); L.close()
e = [r['err'] for r in rows]; oe = [ (r['odo_delta'] - r['cmd']) for r in rows if r['odo_delta'] is not None]
co = [ (r['cam_delta'] - r['odo_delta']) for r in rows if r['odo_delta'] is not None]
print(f'G1 camera: mean|err| {statistics.mean(abs(x) for x in e):.2f} sd {statistics.pstdev(e):.2f} mean {statistics.mean(e):+.2f}')
print(f'odometry vs command: mean {statistics.mean(oe):+.2f} sd {statistics.pstdev(oe):.2f};  camera minus odometry: mean {statistics.mean(co):+.2f} sd {statistics.pstdev(co):.2f}')
print(f'durations {[r["done_s"] for r in rows]} reasons {[r["reason"] for r in rows]} reversals {sum(1 for r in rows if r["rev_last10"])}')
json.dump({'camera_noise_sd': statistics.pstdev(dev), 'lag': sys.argv[2], 'stop_distance': sys.argv[3], 'rows': rows},
          open('captures/bench-acceptance-029-20260904d/g1-run.json', 'w'), indent=1)
