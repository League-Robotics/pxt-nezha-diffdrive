"""MOVE_X vs WHEELS_X travel-scale sweep -- separates a FIXED per-move
deficit from a PROPORTIONAL (travelCalib-shaped) one.

The tour data cannot tell those apart: it has only two leg lengths
(100 and 60 cm) and the within-length scatter is bigger than the
between-length difference. This drives three lengths spanning 4.75:1,
both verbs, at the SAME cruise (120 mm/s -- the tour's), alternating
forward/reverse along the x axis so no pivots enter the measurement.

Commands are sent RAW: no travel correction anywhere in this script.
Every move is projected from a live camera fix and refused if it leaves
the 12 cm field margin.
"""
import json, math, re, socket, subprocess, sys, threading, time

sys.path.insert(0, '/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive/tools')
import park

CAM = 'arducam-ov9782-usb-camera'
RELAY = ('192.168.1.12', 8760); CHANNEL, GROUP = 4, 10
FX, FY = 67.15, 44.65
MX, MY = FX - 12.0, FY - 12.0          # 55.15 / 32.65
CRUISE = 120                            # mm/s, both verbs
DISTS = [20.0, 50.0, 95.0]              # cm
HOME = (45.0, 0.0)                      # start pose, heading 180 deg
OUT = '/private/tmp/claude-501/-Volumes-Proj-proj-RobotProjects-pxt-nezha-diffdrive/2057fadc-023e-478c-99eb-d812c1262594/scratchpad/sweep.json'


def cam_read():
    try:
        out = subprocess.run(['aprilcam', 'camera', 'tags', CAM],
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return None
    m = re.search(r'apriltag 53\s+world=\(\s*(-?[\d.]+),\s*(-?[\d.]+)\)\s+yaw=(-?[\d.]+)', out)
    return (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else None


def fix(n=5):
    """Median of n camera reads, taken AT REST."""
    xs, ys, hs = [], [], []
    for _ in range(n * 2):
        p = cam_read()
        if p:
            xs.append(p[0]); ys.append(p[1]); hs.append(p[2])
        if len(xs) >= n:
            break
        time.sleep(0.15)
    if not xs:
        return None
    md = lambda v: sorted(v)[len(v) // 2]
    return (md(xs), md(ys), md(hs), len(xs))


class Link:
    def __init__(self):
        self.s = socket.create_connection(RELAY, timeout=10); self.s.settimeout(0.3)
        self.lines = []; self.lock = threading.Lock(); self.run = True; self._raw = b''
        self._setup()
        threading.Thread(target=self._reader, daemon=True).start()
        self.seq = 1

    def _pump(self, sec):
        e = time.time() + sec; got = []
        while time.time() < e:
            try:
                c = self.s.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                break
            if not c:
                break
            self._raw += c
            while b'\n' in self._raw:
                r, self._raw = self._raw.split(b'\n', 1)
                t = r.decode('ascii', 'replace').strip()
                if t:
                    got.append((time.time(), t))
        return got

    def _setup(self):
        self._pump(1.5)
        for _ in range(3):
            self.s.sendall(b'!CG %d %d\n' % (CHANNEL, GROUP)); self._pump(1.0)
            self.s.sendall(b'!GO\n'); self._pump(1.0)
            self.s.sendall(b'PING\n')
            if any(t.startswith('pong') for _, t in self._pump(2.0)):
                break
        else:
            raise RuntimeError('radio: no PONG -- robot off or relay wedged')
        self.s.sendall(b'HELLO\n')
        for _, t in self._pump(2.5):
            if 'device' in t.lower():
                print('  link ->', t)

    def _reader(self):
        while self.run:
            for item in self._pump(0.2):
                with self.lock:
                    self.lines.append(item)

    def since(self, mark):
        with self.lock:
            return [x for x in self.lines if x[0] >= mark]

    def send(self, line):
        self.s.sendall((line + '\n').encode())

    def seqd(self, verb, wait=8.0):
        for _ in range(3):
            mark = time.time(); self.send(f'{verb} #{self.seq}')
            e = time.time() + wait; nxt = None; ok = False
            while time.time() < e and not ok:
                for _, t in self.since(mark):
                    m = re.match(r'^ack (\d+)', t)
                    if m:
                        nxt = int(m.group(1)) + 1
                        ok = ok or t.startswith(f'ack {self.seq} ')
                    m = re.match(r'^nack (\d+)', t)
                    if m:
                        nxt = int(m.group(1))
                time.sleep(0.1)
            if nxt is not None:
                self.seq = nxt
            if ok:
                return True
        return False

    def status(self):
        mark = time.time(); self.send('STATUS'); e = time.time() + 3.0
        while time.time() < e:
            for _, t in self.since(mark):
                if t.startswith('status '):
                    return t
            time.sleep(0.1)
        return ''

    def idle(self, maxwait=60.0):
        t0 = time.time()
        while time.time() - t0 < maxwait:
            m = re.search(r'active=(\d+)', self.status())
            if m and m.group(1) == '0':
                return True
            time.sleep(0.4)
        return False

    def close(self):
        self.run = False; time.sleep(0.4)
        try:
            self.s.close()
        except Exception:
            pass


L = Link()
print('STATUS:', L.status())


def preflight(p, cm, label):
    x = p[0] + cm * math.cos(p[2]); y = p[1] + cm * math.sin(p[2])
    if abs(x) > MX or abs(y) > MY:
        print(f'   REFUSED {label}: projects to ({x:+.1f},{y:+.1f}), outside +-{MX:.1f}/+-{MY:.1f}')
        return False
    return True


def move(verb, cm):
    mm = int(round(cm * 10))
    if verb == 'MOVE_X':
        ok = L.seqd(f'MOVE_X {mm} 0 {CRUISE} 60000')
    else:
        ok = L.seqd(f'WHEELS_X {mm} {mm} {CRUISE} 60000')
    if not ok:
        return False
    return L.idle()


def pivot(deg):
    if abs(deg) < 1.5:
        return True
    ok = L.seqd(f'MOVE_X 0 {int(round(math.radians(deg) * 1000))} {CRUISE} 30000')
    return ok and L.idle()


def goto_home():
    """park.plan() to HOME facing 180 deg, one pass, camera-verified."""
    for attempt in range(3):
        p = fix()
        if not p:
            print('  no camera fix'); return None
        pose = (p[0], p[1], math.degrees(p[2]))
        err = math.hypot(p[0] - HOME[0], p[1] - HOME[1])
        dh = abs((math.degrees(p[2]) - 180.0 + 180) % 360 - 180)
        print(f'  at ({p[0]:+.2f},{p[1]:+.2f}) hdg {math.degrees(p[2]):+.1f}  '
              f'-> home err {err:.2f} cm, hdg err {dh:.1f} deg')
        if err <= 2.0 and dh <= 3.0:
            return p
        moves = park.plan(pose, (HOME[0], HOME[1], 180.0), pos_tol=1.5, head_tol=2.5, cross_tol=1.0)
        print('   plan:', moves)
        for kind, val in moves:
            if kind == park.PIVOT:
                if not pivot(val):
                    print('   pivot failed'); return None
            else:
                q = fix()
                if not q or not preflight(q, val, f'home drive {val:+.1f}'):
                    return None
                if not move('MOVE_X', val):
                    print('   drive failed'); return None
            time.sleep(0.8)
    return fix()


print('\n--- repositioning to home (+50, 0) facing 180 deg ---')
home = goto_home()
if not home:
    L.close(); sys.exit('could not reach home -- aborting')

# Prove the robot actually MOVES before trusting any number (playfield
# rule: odometry cannot detect its own failure to move).
print('\n--- motion proof: 10 cm out and back ---')
a = fix()
if not preflight(a, 10.0, 'proof'):
    L.close(); sys.exit('preflight refused the proof move')
move('MOVE_X', 10.0); time.sleep(1.0)
b = fix()
d = math.hypot(b[0] - a[0], b[1] - a[1])
print(f'  camera saw {d:.2f} cm of travel for a commanded 10 cm')
if d < 5.0:
    L.close(); sys.exit('robot did not move -- check power (see playfield rules)')
move('MOVE_X', -10.0); time.sleep(1.0)

runs = []
print('\n--- sweep ---')
print(f"{'verb':9} {'cmd':>7} {'chord':>7} {'err cm':>7} {'err %':>7} {'dhead':>7}")
for d in DISTS:
    for verb in ('MOVE_X', 'WHEELS_X'):
        for sign in (+1, -1):
            cm = d * sign
            p = fix()
            if not p:
                print('   lost the camera, stopping'); break
            # keep the run on the x axis: absorb heading drift when it
            # gets big enough to matter, never for a couple of degrees
            hd = (math.degrees(p[2]) - 180.0 + 180) % 360 - 180
            if abs(hd) > 5.0:
                print(f'   heading {hd:+.1f} deg off axis -- correcting')
                pivot(-hd); time.sleep(0.8); p = fix()
            if not preflight(p, cm, f'{verb} {cm:+.0f}'):
                continue
            t0 = time.time()
            if not move(verb, cm):
                print(f'   {verb} {cm:+.0f} did not complete'); continue
            time.sleep(1.2)
            q = fix()
            if not q:
                print('   lost the camera after the move'); continue
            chord = math.hypot(q[0] - p[0], q[1] - p[1])
            dh = math.degrees((q[2] - p[2] + math.pi) % (2 * math.pi) - math.pi)
            err = chord - abs(cm)
            print(f'{verb:9} {cm:+7.1f} {chord:7.2f} {err:+7.2f} '
                  f'{100*err/abs(cm):+7.2f} {dh:+7.2f}')
            runs.append({'verb': verb, 'cmd_cm': cm, 'chord_cm': round(chord, 3),
                         'err_cm': round(err, 3), 'err_pct': round(100*err/abs(cm), 3),
                         'dhead_deg': round(dh, 3),
                         'start': [round(v, 2) for v in p[:3]],
                         'end': [round(v, 2) for v in q[:3]],
                         'secs': round(time.time() - t0, 1)})
            json.dump(runs, open(OUT, 'w'), indent=1)

L.close()
json.dump(runs, open(OUT, 'w'), indent=1)
print(f'\nwrote {OUT}  ({len(runs)} runs)')
