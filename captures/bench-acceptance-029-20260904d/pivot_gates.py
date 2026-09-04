"""stop_distance measurement (design S10.2) then G1 pivot gate (S10.1),
camera-truthed, on tovez over the zilch serial daemon.

Phase A: `SET lag <lag>`, `SET stop_distance 0`, then N alternating
`MOVE_X 0 +-1571 <floor cruise> 6000` pivots. Camera heading at rest
before/after each; overshoot [deg] -> per-wheel coast [mm] via
track/2 = 57.1 mm/rad. stop_distance := mean per-wheel coast.
Phase B: `SET stop_distance <that>`, 12 alternating `MOVE_X 0 +-1571
100 5000` with TLM FULL; mean |err|, sd, and duty sign reversal in the
last 10 ticks of each pivot.

Usage: uv run python pivot_gates.py zilch.local:43671 <lag_s> [floor_cruise]
"""
import sys, time, json, math, pathlib, statistics
sys.path.insert(0, 'tools')
from wire_acceptance import TcpLink
from camlink import Cam

OUT = pathlib.Path(__file__).parent
HALF_TRACK = 114.2 / 2   # [mm/rad] vevov default geometry running on tovez
cam = Cam()

def heading(n=5):
    sy = cy = 0.0; k = 0; end = time.time() + 3
    while k < n and time.time() < end:
        for t in cam.d.get_tags(cam.cam).tags:
            if t.tag.family.value == 'apriltag' and t.tag.number == 52 and t.world is not None:
                sy += math.sin(t.yaw_rad); cy += math.cos(t.yaw_rad); k += 1
        time.sleep(0.1)
    return math.degrees(math.atan2(sy, cy)) if k else None

def frames_from(lines):
    out = []
    for l in lines:
        p = l.split()
        if p and p[0] == 't' and len(p) >= 18:
            out.append({'now': int(p[2]), 'h': int(p[6]), 'vl': int(p[10]), 'vr': int(p[11]),
                        'dutl': int(p[16]), 'dutr': int(p[17])})
    return out

class Session:
    def __init__(self, hostport):
        self.L = TcpLink(hostport); self.sid = 0; self.log = []
    def ask(self, cmd, sec=1.0, seq=True):
        if seq:
            self.sid += 1; cmd = f'{cmd} #{self.sid}'
        r = [l for l in self.L.ask(cmd, sec) if not l.startswith('DBG:') and not l.startswith('t ')]
        self.log.append((cmd, r)); print(cmd, '->', r[:2]); return r
    def move_and_wait(self, cmd, timeout=8.0):
        """Send a sequenced move, collect lines until its ack (completion)."""
        self.sid += 1; cmd = f'{cmd} #{self.sid}'
        self.L.s.sendall(cmd.encode() + b'\n')
        got = []; end = time.time() + timeout; ack = None
        while time.time() < end:
            for l in self.L.read(0.2):
                got.append(l)
                if l.startswith(f'ack {self.sid} '):
                    ack = l
            if ack: break
        self.log.append((cmd, ack))
        return ack, got

def pivots(S, n, cruise, deadline, tlm):
    rows = []
    sign = 1
    for i in range(n):
        h0 = heading()
        ack, lines = S.move_and_wait(f'MOVE_X 0 {sign*1571} {cruise} {deadline}')
        time.sleep(0.8)
        h1 = heading()
        got = (h1 - h0 + 180) % 360 - 180
        err = got - sign*90.0
        fr = frames_from(lines) if tlm else []
        rev = None
        if fr:
            last = fr[-10:]
            rev = any(a['dutl']*b['dutl'] < 0 or a['dutr']*b['dutr'] < 0 for a, b in zip(last, last[1:]))
        rows.append({'i': i, 'cmd_deg': sign*90, 'h0': h0, 'h1': h1, 'got': got, 'err': err,
                     'ack': ack, 'reversal_last10': rev, 'frames': fr})
        print(f'pivot {i:2d} cmd {sign*90:+4d} got {got:+7.2f} err {err:+6.2f}  {ack}  rev={rev}')
        sign = -sign
    return rows

def main(hostport, lag, floor_cruise=70):
    S = Session(hostport)
    S.ask('HELLO', seq=False); S.ask('RUN:clearestop', seq=False); S.ask('STATUS', seq=False)
    S.ask('SET accel 400'); S.ask('SET decel 400'); S.ask('SET twist_hold_gain 2'); S.ask('GET twist_hold_gain')
    S.ask(f'SET lag {lag}'); S.ask('SET stop_distance 0'); S.ask('GET lag'); S.ask('GET stop_distance')
    S.ask('GET v_floor'); S.ask('GET omega_floor')
    # warm-up pivot pair
    S.move_and_wait('MOVE_X 0 785 100 4000'); time.sleep(0.5)
    S.move_and_wait('MOVE_X 0 -785 100 4000'); time.sleep(0.5)

    print('\n=== Phase A: stop_distance at floor cruise', floor_cruise)
    A = pivots(S, 10, floor_cruise, 8000, tlm=False)
    errs = [r['err'] for r in A]
    signed_coast = [r['err'] * (1 if r['cmd_deg'] > 0 else -1) for r in A]  # + = overshoot
    coast_mm = [math.radians(e) * HALF_TRACK for e in signed_coast]
    sd_mm = statistics.mean(coast_mm)
    print(f'overshoot per pivot [deg, +=long]: {[round(e,2) for e in signed_coast]}')
    print(f'per-wheel coast [mm]: mean {sd_mm:.2f} sd {statistics.pstdev(coast_mm):.2f} '
          f'(CW mean {statistics.mean([c for c,r in zip(coast_mm,A) if r["cmd_deg"]<0]):.2f}, '
          f'CCW mean {statistics.mean([c for c,r in zip(coast_mm,A) if r["cmd_deg"]>0]):.2f})')
    stop_distance = max(0.0, round(sd_mm, 2))
    S.ask(f'SET stop_distance {stop_distance}'); S.ask('GET stop_distance')

    print('\n=== Phase B: G1, 12 alternating 90 deg pivots at cruise 100, TLM FULL')
    S.ask('TLM FULL', 0.5)
    B = pivots(S, 12, 100, 5000, tlm=True)
    S.ask('TLM OFF', 0.5); S.L.read(0.5)
    e = [r['err'] for r in B]
    ae = [abs(x) for x in e]
    print(f'G1: mean|err| {statistics.mean(ae):.2f} deg, sd {statistics.pstdev(e):.2f} deg, '
          f'mean signed {statistics.mean(e):+.2f}, CCW mean {statistics.mean([r["err"] for r in B if r["cmd_deg"]>0]):+.2f}, '
          f'CW mean {statistics.mean([r["err"] for r in B if r["cmd_deg"]<0]):+.2f}, '
          f'reversals {sum(1 for r in B if r["reversal_last10"])}/12, '
          f'acks {[ (r["ack"] or "").split()[-1] for r in B]}')
    S.ask('STATUS', seq=False)
    S.L.close()
    (OUT / 'pivot-gates.json').write_text(json.dumps(
        {'lag': lag, 'floor_cruise': floor_cruise, 'phaseA': A, 'stop_distance_mm': stop_distance,
         'phaseB': B, 'log': S.log}, indent=1))

if __name__ == '__main__':
    main(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 70)
