"""Sort the coloured cubes onto the same-coloured squares of the secondary playfield with tigez.

    uv run python tools/canplay/blocksort.py look [--shot out.png]   list cubes, squares and the robot
    uv run python tools/canplay/blocksort.py play [--max N]          sort, one cube per pick/place, camera between legs
    uv run python tools/canplay/blocksort.py plan                    show the next pick and first leg, no motion
    uv run python tools/canplay/blocksort.py move X,Y,COLOUR          pick the cube at X,Y and place it on a COLOUR square
    uv run python tools/canplay/blocksort.py grip DEG                move the paddles

The hd-usb-camera's deskewed frame is a plain scale of the playfield (7.26 px/cm,
origin at the centre). The robot runs test/canbot.ts; its pose is seeded from
the camera before every leg, in a frame shifted so the leg fits canbot's
built-in fence (sized for the old bb-obstacle mat).
"""
import argparse, glob, json, math, os, sys, threading, time
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from aprilcam.client.discovery import Discovery  # noqa: E402
from aprilcam.types import TagFamily, TagId  # noqa: E402
import canplay  # noqa: E402
from canplay import Robot  # noqa: E402

CAM = "hd-usb-camera"
TAG = 57
PXCM = 7.26
W2, H2 = 55.1, 36.7
NADIR, CAM_H, CUBE_H = (-8.2, -9.2), 136.5, 2.8
CAL = os.path.join(HERE, "blocksort_cal_tigez.json")
STATE = os.path.join(HERE, "blocksort_state.json")
SHOTS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "captures", "blocksort-20261028")

# centre (x, y), long side along x?  measured from the deskewed frame 2026-10-28
SQUARES = [("green", -33.0, 18.1, True), ("orange", -21.0, 18.2, True), ("green", 23.0, 18.1, True),
           ("orange", 35.5, 18.4, True), ("purple", 46.2, 23.8, False), ("green", 46.1, 8.4, False),
           ("blue", 45.7, -8.4, False), ("yellow", 45.4, -23.7, False), ("blue", -33.3, -17.3, True),
           ("red", -22.1, -17.7, True), ("blue", 23.6, -17.6, True), ("red", 35.4, -17.5, True)]
HALF = (3.8, 2.6)

FENCE = (-44.0, 44.0, -27.5, 27.5)     # robot centre, world cm
CB_FENCE = (-53.5, 50.0, -16.0, 25.0)  # canbot's own, in its frame
GRIP_FWD, GRIP_LEFT = 13.22, -1.85
STAGE = 12.0
STOW, RELEASE = 75, 10
OPEN_W = 40        # paddles part-open for the run-in and the release: a ~9 cm V
BACK = 12.0
V_HALF = 4.0       # part-open paddles: half-width round the run-in


def to_px(x, y):
    return int(round((x + W2) * PXCM)), int(round((H2 - y) * PXCM))


def colour_of(h, s, v):
    if s < 90:
        return None
    if h >= 170 or h <= 2:
        return "red"
    if h <= 16:
        return "orange"
    if 20 <= h <= 35:
        return "yellow"
    if 45 <= h <= 85:
        return "green"
    if 95 <= h <= 118:
        return "blue"
    if 122 <= h <= 150:
        return "purple"
    return None


COLOUR_IDS = {c: i + 1 for i, c in enumerate(["red", "orange", "yellow", "green", "blue", "purple"])}


LOOKALIKE = {"red": ("red", "orange"), "orange": ("orange", "red")}


def on_square(x, y, margin=0.0):
    for col, sx, sy, wide in SQUARES:
        hx, hy = HALF if wide else HALF[::-1]
        if abs(x - sx) <= hx + margin and abs(y - sy) <= hy + margin:
            return col, sx, sy
    return None


class Eye:
    def __init__(self):
        self.d = Discovery().connect()

    def frame(self):
        f = self.d.get_frame(CAM, deskewed=True, encoding="png")
        return cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)

    def robot(self, n=10):
        """Median robot pose (x, y, heading deg) over n frames, or None."""
        ps = []
        for _ in range(n * 3):
            t = self.d.get_tag(CAM, TagId(family=TagFamily.APRILTAG, number=TAG))
            if t is not None and t.world is not None:
                ps.append((t.world.x, t.world.y, math.degrees(t.yaw_rad)))
                if len(ps) >= n:
                    break
            time.sleep(0.05)
        if len(ps) < 3:
            return None
        h0 = ps[0][2]
        dh = sorted(canplay.wrap(p[2] - h0) for p in ps)[len(ps) // 2]
        return (float(np.median([p[0] for p in ps])), float(np.median([p[1] for p in ps])), canplay.wrap(h0 + dh))

    def cubes(self, img, robot=None):
        """[(colour, x, y)] for cube-sized blobs on the field, not on the robot. Each colour is
        segmented on its own, so a cube touching another colour stays separate."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        lut = np.array([COLOUR_IDS.get({"orange": "red"}.get(colour_of(i, 255, 255), colour_of(i, 255, 255)), 0)
                        for i in range(256)], np.uint8)
        cls = np.where((s > 90) & (v > 30), lut[h], 0)
        keep = np.full(h.shape, 255, np.uint8)
        if robot is not None:
            rx, ry, rh = robot
            c, s_ = math.cos(math.radians(rh)), math.sin(math.radians(rh))
            for (f0, f1, w) in ((-12.5, 10.5, 12.0), (10.5, 18.0, 6.5)):
                poly = [to_px(rx + f * c - l * s_, ry + f * s_ + l * c) for f, l in ((f0, -w), (f1, -w), (f1, w), (f0, w))]
                cv2.fillPoly(keep, [np.array(poly, np.int32)], 0)
        out = []
        for col, cid in COLOUR_IDS.items():
            if col == "orange":
                continue
            m = ((cls == cid).astype(np.uint8) * 255) & keep
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            n, lab, st, cen = cv2.connectedComponentsWithStats(m)
            for i in range(1, n):
                _, _, w, hh, a = st[i]
                if a < 200 or w < 12 or hh < 12:
                    continue
                if a <= 900 and w <= 40 and hh <= 40:
                    centres = [cen[i]]
                elif a <= 1500 and max(w, hh) <= 64 and min(w, hh) <= 40:
                    pts = np.argwhere(lab == i).astype(np.float32)[:, ::-1]
                    _, _, centres = cv2.kmeans(pts, 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5), 3,
                                               cv2.KMEANS_PP_CENTERS)
                else:
                    continue
                name = col
                if col == "red":
                    b_, g_, r_ = np.median(img[lab == i], axis=0)
                    name = "yellow" if g_ > 0.55 * r_ else "orange" if g_ > 0.05 * r_ else "red"
                for px, py in centres:
                    x, y = px / PXCM - W2, H2 - py / PXCM
                    k = 1 - CUBE_H / 2 / CAM_H
                    x, y = NADIR[0] + (x - NADIR[0]) * k, NADIR[1] + (y - NADIR[1]) * k
                    sq = on_square(x, y, -0.3)
                    if sq and sq[0] in LOOKALIKE.get(name, (name,)):
                        continue
                    sq = on_square(x, y, 3.0)
                    if sq and sq[0] == name and (x, y) != (sq[1], sq[2]):
                        continue
                    if abs(x) <= 52 and abs(y) <= 34 and not (abs(x) > 44 and abs(y) > 30):
                        out.append((name, float(x), float(y)))
        return out

    def snap(self, path, img, robot, cubes, note=""):
        out = img.copy()
        for col, sx, sy, wide in SQUARES:
            hx, hy = HALF if wide else HALF[::-1]
            cv2.rectangle(out, to_px(sx - hx, sy + hy), to_px(sx + hx, sy - hy), (255, 255, 255), 1)
        for col, x, y in cubes:
            px, py = to_px(x, y)
            cv2.rectangle(out, (px - 13, py - 13), (px + 13, py + 13), (0, 0, 0), 2)
            cv2.putText(out, col[0], (px - 4, py - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        if robot:
            rx, ry, rh = robot
            gx, gy = grip_point(robot)
            cv2.circle(out, to_px(rx, ry), 5, (0, 0, 255), -1)
            cv2.line(out, to_px(rx, ry), to_px(gx, gy), (0, 0, 255), 2)
        cv2.putText(out, note, (10, 525), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        cv2.imwrite(path, out)


def grip_point(p, fwd=None, left=None):
    fwd = GRIP_FWD if fwd is None else fwd
    left = GRIP_LEFT if left is None else left
    c, s = math.cos(math.radians(p[2])), math.sin(math.radians(p[2]))
    return p[0] + fwd * c - left * s, p[1] + fwd * s + left * c


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def in_fence(x, y, f=FENCE):
    return f[0] <= x <= f[1] and f[2] <= y <= f[3]


BODY_R = 10.0      # robot centre to any cube, everywhere on a path
NOSE, REACH = 8.0, 17.0   # paddle segment ahead of the centre
PAD = 4.0          # paddle segment to any cube
STEP_MAX = 35.0
GRID = 6.0


def drive_ok(a, b, others):
    h = math.atan2(b[1] - a[1], b[0] - a[0])
    u = (math.cos(h), math.sin(h))
    n0 = (a[0] + NOSE * u[0], a[1] + NOSE * u[1])
    n1 = (b[0] + REACH * u[0], b[1] + REACH * u[1])
    return all(seg_dist(o, a, b) >= BODY_R and seg_dist(o, n0, n1) >= PAD for o in others)


def pivot_ok(p, h0, delta, others):
    if any(math.dist(o, p) < BODY_R for o in others):
        return False
    k = max(1, int(abs(delta) / 5))
    for i in range(k + 1):
        h = math.radians(h0 + delta * i / k)
        u = (math.cos(h), math.sin(h))
        a = (p[0] + NOSE * u[0], p[1] + NOSE * u[1])
        b = (p[0] + REACH * u[0], p[1] + REACH * u[1])
        if any(seg_dist(o, a, b) < PAD for o in others):
            return False
    return True


def turn(p, h0, h1, others):
    """Signed pivot from h0 to h1 that sweeps clear (short way first), or None."""
    d = canplay.wrap(h1 - h0)
    for delta in (d, d - 360 if d > 0 else d + 360):
        if abs(delta) < 3 or pivot_ok(p, h0, delta, others):
            return delta
    return None


def plan(robot, goal, hd, others):
    """(cost, [waypoints...goal], [pivots]) from the robot pose to `goal`, arriving facing `hd`, or None."""
    nodes = [[]] + [[(x, y)] for x in np.arange(FENCE[0], FENCE[1] + 0.1, GRID)
                    for y in np.arange(FENCE[2], FENCE[3] + 0.1, GRID)]
    best = None
    for via in nodes:
        pts = [robot[:2]] + via + [goal]
        h, cost, pivots = robot[2], 0.0, []
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1:
                continue
            bh = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            t = turn(a, h, bh, others)
            if t is None or not drive_ok(a, b, others):
                break
            pivots.append(t)
            cost += math.dist(a, b) + 0.08 * abs(t)
            h = bh
        else:
            t = turn(goal, h, hd, others)
            if t is None:
                continue
            pivots.append(t)
            cost += 0.08 * abs(t)
            if best is None or cost < best[0]:
                best = (cost, pts[1:], pivots)
        if best and not via:
            return best
    return best


def approach(robot, target, others, v_half=V_HALF):
    """Headings (best first) to bring the grip point onto `target`, as (cost, heading, stage, route)."""
    out = []
    for hd in range(0, 360, 15):
        c, s = math.cos(math.radians(hd)), math.sin(math.radians(hd))
        cx = target[0] - GRIP_FWD * c + GRIP_LEFT * s
        cy = target[1] - GRIP_FWD * s - GRIP_LEFT * c
        sx, sy = cx - STAGE * c, cy - STAGE * s
        if not (in_fence(cx, cy) and in_fence(sx, sy)):
            continue
        if not drive_ok((sx, sy), (cx, cy), others):
            continue
        if any(seg_dist(o, (cx + 6 * c, cy + 6 * s), (target[0] + 3 * c, target[1] + 3 * s)) < v_half for o in others):
            continue
        out.append((math.dist(robot[:2], (sx, sy)), hd, (sx, sy)))
    res = []
    for _, hd, st in sorted(out)[:6]:
        r = plan(robot, st, hd, others)
        if r:
            res.append((r[0], hd, st, r))
    return sorted(res)


def shift_for(points):
    """Offset (world - canbot) so every point sits 4 cm inside canbot's fence."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    mid_cb = ((CB_FENCE[0] + CB_FENCE[1]) / 2, (CB_FENCE[2] + CB_FENCE[3]) / 2)
    off = ((min(xs) + max(xs)) / 2 - mid_cb[0], (min(ys) + max(ys)) / 2 - mid_cb[1])
    for x, y in points:
        if not in_fence(x - off[0], y - off[1], (CB_FENCE[0] + 4, CB_FENCE[1] - 4, CB_FENCE[2] + 4, CB_FENCE[3] - 4)):
            raise SystemExit(f"leg spans too much for canbot's fence: {points}")
    return off


class Sorter:
    def __init__(self, robot, eye):
        self.r, self.e = robot, eye
        os.makedirs(os.path.join(SHOTS, "film"), exist_ok=True)
        self.n = max([int(os.path.basename(f)[:3]) for f in glob.glob(os.path.join(SHOTS, "[0-9][0-9][0-9]*.png"))] + [0])
        self.by_hand = False
        self.samples = json.load(open(CAL))["samples"] if os.path.exists(CAL) else []
        self.placed = [tuple(p) for p in json.load(open(STATE))["placed"]] if os.path.exists(STATE) else []
        self.calibrate()

    def calibrate(self):
        global GRIP_FWD, GRIP_LEFT
        if self.samples:
            GRIP_FWD = float(np.median([f for f, _ in self.samples]))
            GRIP_LEFT = float(np.median([l for _, l in self.samples]))
        self.r.run(f"gripcal {GRIP_FWD:.2f} {GRIP_LEFT:.2f} 0 0")
        print(f" grip point fwd {GRIP_FWD:.2f} left {GRIP_LEFT:.2f} ({len(self.samples)} samples)")

    def learn(self, aimed_pose, cube):
        """Where the dropped cube sits relative to the robot's pose at release, in the robot frame."""
        x, y, h = aimed_pose
        c, s = math.cos(math.radians(h)), math.sin(math.radians(h))
        dx, dy = cube[0] - x, cube[1] - y
        self.samples.append((dx * c + dy * s, -dx * s + dy * c))
        self.samples = self.samples[-12:]
        json.dump({"samples": self.samples}, open(CAL, "w"), indent=1)
        self.calibrate()

    def look(self, note):
        for k in range(5):
            try:
                return self._look(note)
            except Exception as e:
                if "no frame" not in str(e) or k == 4:
                    raise
                print("   camera dropout, retrying")
                time.sleep(3)

    def _look(self, note):
        robot = self.e.robot()
        if robot is None:
            canplay.lights_on()
            time.sleep(3)
            robot = self.e.robot()
        if robot is None:
            raise SystemExit("robot tag not seen")
        img = self.e.frame()
        cubes = self.e.cubes(img, robot)
        cubes += [p for p in self.placed if not any(math.dist(p[1:], c[1:]) < 3 for c in cubes)]
        self.n += 1
        self.e.snap(os.path.join(SHOTS, f"{self.n:03d}.png"), img, robot, cubes, note)
        return robot, cubes

    def send(self, cmd, robot, points):
        """One canbot RUN, the pose seeded from the camera in a frame shifted to fit canbot's fence."""
        off = shift_for([robot[:2]] + points)
        self.off = off
        self.r.run(f"setpose {robot[0] - off[0]:.2f} {robot[1] - off[1]:.2f} {robot[2]:.1f}")
        self.r.run("obsclear", until="CB obs")
        args = cmd[1:]
        for i in range(0, len(args) - 1, 2):
            args[i], args[i + 1] = args[i] - off[0], args[i + 1] - off[1]
        text = cmd[0] + " " + " ".join(f"{v:.2f}" for v in args)
        self.r.arrived = None
        stop = threading.Event()
        film = threading.Thread(target=self.film, args=(f"{self.n:03d}{cmd[0]}", stop), daemon=True)
        film.start()
        try:
            out = self.r.run(text)
        finally:
            stop.set()
            film.join()
        print(f"   {text}: {out}")
        return "fail" not in out and "abort" not in out

    def go(self, verb, target, holding):
        """Drive leg by leg to a stage point for `target`, then let canbot do the run-in."""
        chosen, blocked = None, 0
        for _ in range(16):
            robot, cubes = self.look(f"{verb} {target[0]:.0f},{target[1]:.0f}")
            others = [c[1:] for c in cubes if math.dist(c[1:], target) > (5.0 if self.by_hand and not holding else 2.5)
                      and not (holding and math.dist(c[1:], grip_point(robot)) < 8)]
            opts = approach(robot, target, others, 3.0 if holding else V_HALF)
            if not opts:
                near = min([math.dist(o, robot[:2]) for o in others] + [99])
                h = math.radians(robot[2])
                moves = [(d, (robot[0] + d * math.cos(h), robot[1] + d * math.sin(h))) for d in (-8, 8)]
                moves = [(min(math.dist(o, q) for o in others), d, q) for d, q in moves if in_fence(*q)
                         and drive_ok(robot[:2], q, [o for o in others if math.dist(o, robot[:2]) >= BODY_R] if d > 0 else [])]
                moves = [m for m in moves if m[0] > near + 2]
                if near >= BODY_R or not moves:
                    blocked += 1
                    if blocked < 4:
                        time.sleep(1)
                        continue
                    print(f"   no clear way to ({target[0]:.1f},{target[1]:.1f})")
                    return False
                _, d, q = max(moves)
                print(f"   boxed in ({near:.1f} cm from a cube): {'back' if d < 0 else 'ahead'} 8 cm")
                self.send(["leg", q[0], q[1], 1 if d > 0 else -1], robot, [q])
                continue
            same = [o for o in opts if o[1] == chosen]
            cost, hd, st, (_, pts, pivots) = same[0] if same else opts[0]
            chosen = hd
            if math.dist(robot[:2], st) < 3.5:
                err = canplay.wrap(hd - robot[2])
                if abs(err) > 6:
                    t = turn(robot[:2], robot[2], hd, others)
                    if t is None:
                        print("   final turn blocked")
                        return False
                    if abs(t) > 150:
                        self.send(["face", canplay.wrap(robot[2] + t / 2)], robot, [])
                        robot, _ = self.look("face")
                    self.send(["face", float(hd)], robot, [])
                    continue
                return self.push(verb, robot, target, hd, others)
            nxt = pts[0]
            if abs(pivots[0]) > 20:
                if abs(pivots[0]) > 150:
                    self.send(["face", canplay.wrap(robot[2] + pivots[0] / 2)], robot, [])
                    robot, _ = self.look("face")
                self.send(["face", math.degrees(math.atan2(nxt[1] - robot[1], nxt[0] - robot[0]))], robot, [])
                continue
            if abs(pivots[0]) > 150:
                self.send(["face", canplay.wrap(robot[2] + pivots[0] / 2)], robot, [])
                robot, _ = self.look("face")
            L = math.dist(robot[:2], nxt)
            if L > STEP_MAX:
                nxt = (robot[0] + (nxt[0] - robot[0]) * STEP_MAX / L, robot[1] + (nxt[1] - robot[1]) * STEP_MAX / L)
            print(f"   leg to ({nxt[0]:.1f},{nxt[1]:.1f}) [route {len(pts)} pts, stage ({st[0]:.1f},{st[1]:.1f}) hd {hd}]")
            self.send(["leg", nxt[0], nxt[1], 1], robot, [nxt])
        return False

    def push(self, verb, robot, target, hd, others):
        """Straight in from the stage, grip or release, straight back out."""
        c, s = math.cos(math.radians(hd)), math.sin(math.radians(hd))
        centre = (target[0] - GRIP_FWD * c + GRIP_LEFT * s, target[1] - GRIP_FWD * s - GRIP_LEFT * c)
        if verb == "pickat":
            self.r.run(f"grip {OPEN_W}", until="GRIP")
            time.sleep(0.5)
        self.send(["leg", centre[0], centre[1], 1], robot, [centre, target])
        at = self.r.run("where", until="CB pose")
        p = [float(v) for v in at.split()[2:5]]
        self.r.arrived = tuple(p)
        if verb == "pickat":
            self.r.run("grip 180", until="GRIP")
            time.sleep(1.0)
            self.r.run("holding 1")
        else:
            self.r.run(f"grip {OPEN_W}", until="GRIP")
            time.sleep(0.8)
            self.r.run("holding 0")
        back = (p[0] + self.off[0] - BACK * c, p[1] + self.off[1] - BACK * s)
        self.r.run(f"leg {back[0] - self.off[0]:.2f} {back[1] - self.off[1]:.2f} -1")
        if verb != "pickat":
            self.r.run(f"grip {STOW}", until="GRIP")
        return True

    def film(self, name, stop):
        eye, k = Eye(), 0
        while not stop.is_set():
            cv2.imwrite(os.path.join(SHOTS, "film", f"{name}_{k:02d}.jpg"), eye.frame())
            k += 1
            stop.wait(0.5)

    def drop_spots(self, col, cubes, near):
        """Free points on this colour's squares, nearest square first, each square's own centre outward."""
        out = []
        for sx, sy, wide in sorted(((sx, sy, w) for c, sx, sy, w in SQUARES if c == col), key=lambda q: math.dist(q[:2], near)):
            hx, hy = HALF if wide else HALF[::-1]
            pts = [(sx + dx, sy + dy) for dx in np.arange(-hx + 1.2, hx - 1.1, 1.0) for dy in np.arange(-hy + 1.2, hy - 1.1, 1.0)]
            out += sorted((p for p in pts if all(math.dist(p, c[1:]) > 3.2 for c in cubes)), key=lambda p: math.dist(p, (sx, sy)))
        return out

    def drop_spot(self, col, cubes, near):
        spots = self.drop_spots(col, cubes, near)
        return spots[0] if spots else None

    def move(self, col, cube):
        """Pick the cube at `cube` (named by eye) and place it on a `col` square."""
        print(f" pick {col} at ({cube[0]:.1f},{cube[1]:.1f}) (by hand)")
        self.by_hand = True
        self.r.run(f"grip {STOW}", until="GRIP")
        ok = self.go("pickat", cube, False)
        robot, cubes = self.look(f"picked {col}?")
        if not ok:
            raise SystemExit("pick failed")
        return self.place(col, cube, robot, cubes)

    def step(self, holding=None):
        if holding:
            robot, cubes = self.look("holding")
            self.r.run("holding 1")
            return self.place(holding, robot[:2], robot, cubes)
        robot, cubes = self.look("look")
        todo = [c for c in cubes if (on_square(c[1], c[2], 1.5) or ("-",))[0] != c[0]]
        print(f"robot ({robot[0]:.1f},{robot[1]:.1f},{robot[2]:.0f})  cubes {len(cubes)}  to sort {len(todo)}")
        if not todo:
            return False
        plans = []
        for col, x, y in todo:
            others = [c[1:] for c in cubes if math.dist(c[1:], (x, y)) > 0.5]
            opts = approach(robot, (x, y), others)
            if opts:
                dest = self.drop_spot(col, cubes, (x, y))
                if dest:
                    plans.append((opts[0][0] + math.dist((x, y), dest), col, (x, y)))
        if not plans:
            raise SystemExit("no cube can be reached")
        _, col, cube = min(plans)
        print(f" pick {col} at ({cube[0]:.1f},{cube[1]:.1f})")
        self.r.run(f"grip {STOW}", until="GRIP")
        ok = self.go("pickat", cube, False)
        robot, cubes = self.look(f"picked {col}?")
        missed = any(c[0] == col and math.dist(c[1:], cube) < 2.5 for c in cubes)
        print(f"   after pick: robot ({robot[0]:.1f},{robot[1]:.1f},{robot[2]:.0f}) cube left at pick spot: {missed}")
        if not ok or missed:
            self.r.run(f"grip {RELEASE}", until="GRIP")
            self.r.run("holding 0")
            self.r.run(f"grip {STOW}", until="GRIP")
            return True
        return self.place(col, cube, robot, cubes)

    def place(self, col, cube, robot, cubes):
        gp = grip_point(robot)
        free = [c for c in cubes if math.dist(c[1:], gp) > 8]
        others = [c[1:] for c in free]
        spots = self.drop_spots(col, free, cube)
        spot = next((p for p in spots if approach(robot, p, [o for o in others if math.dist(o, p) > 2.5], 3.0)), spots[0] if spots else None)
        if spot is None:
            raise SystemExit(f"no reachable free spot on a {col} square; still holding it (rerun with --holding {col})")
        print(f" place {col} at ({spot[0]:.1f},{spot[1]:.1f})")
        if not self.go("placeat", spot, True):
            raise SystemExit(f"could not place {col}; still holding it (rerun with --holding {col})")
        robot, cubes = self.look(f"placed {col}")
        here = [c for c in cubes if c[0] == col and math.dist(c[1:], spot) < 6 and c not in self.placed]
        gone = not any(c[0] == col and math.dist(c[1:], grip_point(robot)) < 5 for c in cubes)
        if not here and gone:
            print(f"   {col} not visible: taken as on its square at ({spot[0]:.1f},{spot[1]:.1f})")
        at = here[0][1:] if here else spot
        if (here or gone) and (on_square(*at, 1.5) or ("-",))[0] == col:
            self.placed = [p for p in self.placed if math.dist(p[1:], spot) > 3]
            self.placed.append((col, *at))
            json.dump({"placed": self.placed}, open(STATE, "w"), indent=1)
        for c in here:
            print(f"   {col} now at ({c[1]:.1f},{c[2]:.1f}), {math.dist(c[1:], spot):.1f} cm off, on square: {on_square(c[1], c[2])}")
        if len(here) == 1 and self.r.arrived:
            ax, ay, ah = self.r.arrived
            self.learn((ax + self.off[0], ay + self.off[1], ah), here[0][1:])
        return True


class Tigez(Robot):
    """canplay's link, also keeping the pose canbot reports when the gripper arrives."""
    arrived = None

    def reader(self, stream):
        for l in stream:
            if l.startswith("CB point err"):
                self.arrived = tuple(float(v) for v in l.split()[4:7])
            self.log.write(f"{time.time():.2f} < {l}")
            self.log.flush()
            self.q.put(l.rstrip())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["look", "play", "grip", "plan", "move"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--shot")
    ap.add_argument("--max", type=int, default=1)
    ap.add_argument("--holding", help="the robot already holds a cube of this colour: place it first")
    ap.add_argument("--host", default="naught")
    a = ap.parse_args()
    eye = Eye()
    if a.cmd == "look":
        robot = eye.robot()
        img = eye.frame()
        cubes = eye.cubes(img, robot)
        print("robot", robot and tuple(round(v, 1) for v in robot))
        for col, x, y in sorted(cubes):
            sq = on_square(x, y)
            print(f"{col:7s} ({x:6.1f},{y:6.1f})  {'on ' + sq[0] if sq else ''}")
        if a.shot:
            eye.snap(a.shot, img, robot, cubes, time.strftime("%H:%M:%S"))
        return
    if a.cmd == "plan":
        class Dry:
            def run(self, cmd, **kw):
                print("   would send:", cmd)
                return "CB end ok"
        s = Sorter(Dry(), eye)
        s.send = lambda cmd, robot, pts: print("   would send:", cmd) or False
        s.step()
        return
    robot = Tigez(a.host, "tigez")
    try:
        if a.cmd == "grip":
            print(robot.run(f"grip {a.arg}", until="GRIP"))
            return
        s = Sorter(robot, eye)
        if a.cmd == "move":
            x, y, col = a.arg.split(",")
            s.move(col, (float(x), float(y)))
            return
        for i in range(a.max):
            if not s.step(a.holding if i == 0 else None):
                print("all sorted")
                break
    finally:
        robot.close()


if __name__ == "__main__":
    main()
