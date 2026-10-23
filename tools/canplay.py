"""Move cans between the numbered circles of the bb-obstacle mat with zetuv.

    uv run python tools/canplay.py 9 5 1 7     move the can on circle 9 to 5, then 1 to 7, then go home
    uv run python tools/canplay.py --swap 9 5  swap the cans on 9 and 5 (via the park spot)
    uv run python tools/canplay.py --home      just drive home

The camera finds the robot and every can; the robot (test/canbot.ts) drives
each leg itself and reports when it is done, so nothing waits on a timer.
"""
import argparse, json, math, os, queue, re, subprocess, sys, tempfile, threading, time, urllib.request

from aprilcam.client.discovery import Discovery
from aprilcam.types import MountParameters, TagFamily, TagId

MAT_DIR = "/Volumes/Proj/proj/robot-projects/radio-robot-lib/config/mat"
sys.path.insert(0, MAT_DIR)
from mattools import Mat  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field import wrap  # noqa: E402

CAM = "arducam-ov9782-usb-camera"
ROBOT_TAG = 58
BIAS = (1.4, -0.2)        # raised tags read this far off on this camera (cm)
GRIP_FWD = 18.7
PARK = (24.0, -10.0)
CAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canplay_cal.json")


class Robot:
    def __init__(self, host, name):
        self.p = subprocess.Popen(["ssh", host, f"/opt/mbtools/bin/mbserial {name}"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.q = queue.Queue()
        self.log = open(os.path.join(tempfile.gettempdir(), "canplay.log"), "a")
        threading.Thread(target=self.reader, daemon=True).start()
        self.seq = 0
        self.point_err = 0.0
        self.expect("connected", 40)
        self.line("STATUS")
        self.expect("status", 5)
        self.line("HELLO")
        self.expect("device", 5)

    def reader(self):
        for l in self.p.stdout:
            self.log.write(f"{time.time():.2f} < {l}")
            self.log.flush()
            self.q.put(l.rstrip())

    def line(self, text):
        self.log.write(f"{time.time():.2f} > {text}\n")
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()

    def expect(self, pattern, timeout, resend=None):
        end = time.time() + timeout
        while time.time() < end:
            try:
                l = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            if l.startswith("nack ") and resend:
                self.seq = int(l.split()[1])
                self.line(resend())
                continue
            if l.startswith("err 1 ") and resend:      # program still starting up
                time.sleep(1)
                self.seq += 1
                self.line(resend())
                continue
            if l.startswith("CB point err"):
                self.point_err = float(l.split()[3])
            if re.search(pattern, l):
                return l
        raise TimeoutError(f"no '{pattern}' within {timeout}s")

    def run(self, cmd, until=r"CB (end|pose|obs|holding|cans)", timeout=120):
        self.seq += 1
        self.line(f"RUN {cmd} #{self.seq}")
        return self.expect(until, timeout, resend=lambda: f"RUN {cmd} #{self.seq}")

    def motors_ok(self):
        """The Cutebot reports connL/connR=0 and I2C failures when its motor battery is flat."""
        self.seq += 1
        self.line(f"WHEELS_V 0 0 300 #{self.seq}")    # the drive only starts on a motion command
        self.expect(f"ack {self.seq} ", 5)
        time.sleep(0.6)
        self.line("STATUS")
        st = self.expect("status", 5)
        return "connL=1" in st and "connR=1" in st

    def close(self):
        self.p.stdin.close()
        self.p.terminate()


class Camera:
    def __init__(self):
        self.d = Discovery().connect()
        cans = json.load(open(os.path.join(MAT_DIR, "cans.json")))
        self.can_ids = [t["number"] for t in cans["tags"]]
        self.d.register_tag(TagId(TagFamily.APRILTAG, ROBOT_TAG),
                            MountParameters(mount_x=0.53, mount_y=0.0, mount_z=11.2, mount_yaw_rad=-1.556))
        for n in self.can_ids:
            self.d.register_tag(TagId(TagFamily.APRILTAG, n), MountParameters(mount_z=cans["tag_height_mm"] / 10))

    def frames(self, n=8):
        out = []
        for _ in range(n):
            out.append({t.tag.number: t for t in self.d.get_tags(CAM).tags
                        if t.tag.family.value == "apriltag" and t.world is not None})
            time.sleep(0.04)
        return out

    def seen(self, n=8):
        """{tag: (x, y, yaw_deg)} averaged, raised-tag bias removed."""
        acc = {}
        for f in self.frames(n):
            for k, t in f.items():
                acc.setdefault(k, []).append((t.world.x, t.world.y, t.yaw_rad))
        out = {}
        for k, v in acc.items():
            if len(v) < n // 2:
                continue
            x = sum(a[0] for a in v) / len(v) - BIAS[0]
            y = sum(a[1] for a in v) / len(v) - BIAS[1]
            h = math.degrees(math.atan2(sum(math.sin(a[2]) for a in v), sum(math.cos(a[2]) for a in v)))
            out[k] = (x, y, h)
        return out


def lights_on():
    try:
        urllib.request.urlopen("http://192.168.6.122/rpc/Switch.Set?id=0&on=true", timeout=3).read()
    except Exception:
        pass


def load_cal():
    try:
        c = json.load(open(CAL))
        if "fwd" in c:
            return c
    except Exception:
        pass
    if True:
        return {"fwd": GRIP_FWD, "left": -0.9, "n": 0}


def save_cal(c):
    json.dump(c, open(CAL, "w"), indent=1)


# Robot-centre fence and planning margin (match test/canbot.ts).
FENCE = (-53.5, 50.0, -16.0, 25.0)
INSET = 3.0
STAGE = 12.0
# Where the open arms, the run-in and the back-out sweep, relative to the
# gripper point (forward, left), grown by a can radius and a margin.
SWEEP_FWD = (-28.5, 6.5)       # back to the 15 cm back-out
SWEEP_LEFT = (-15.5, 14.0)
FREE = 8.0                # a spot is taken when a can is this close


def inside(x, y, m=INSET):
    return FENCE[0] + m <= x <= FENCE[1] - m and FENCE[2] + m <= y <= FENCE[3] - m


def sweep_hits(tx, ty, hdg, others):
    c, sn = math.cos(math.radians(hdg)), math.sin(math.radians(hdg))
    for ox, oy in others:
        f = (ox - tx) * c + (oy - ty) * sn
        l = -(ox - tx) * sn + (oy - ty) * c
        if SWEEP_FWD[0] < f < SWEEP_FWD[1] and SWEEP_LEFT[0] < l < SWEEP_LEFT[1]:
            return True
    return False


def approach_heading(tx, ty, others, grip, prefer=None):
    """A heading to grip or release a can at (tx, ty) without the arms touching
    any of `others`, closest to `prefer`; None when there is none."""
    hs = range(0, 360, 15)
    if prefer is not None:
        hs = sorted(hs, key=lambda h: abs(wrap(h - prefer)))
    for h in hs:
        c, sn = math.cos(math.radians(h)), math.sin(math.radians(h))
        rx = tx - grip["fwd"] * c + grip["left"] * sn
        ry = ty - grip["fwd"] * sn - grip["left"] * c
        # the robot shortens its run-in (12, 8, 5, 2 cm) when that is all that fits
        if not inside(rx, ry) or not any(inside(rx - st * c, ry - st * sn) for st in (STAGE, 8, 5, 2)):
            continue
        if not inside(rx - 15 * c, ry - 15 * sn, 0):      # the back-out must stay on the mat
            continue
        body = 9.0 + 3.3 + 1.0                             # robot body clear of every can
        if any(math.dist(p, o) < body for o in others
               for p in ((rx, ry), (rx - STAGE * c, ry - STAGE * sn), (rx - 15 * c, ry - 15 * sn))):
            continue
        if sweep_hits(tx, ty, h, others):
            continue
        return h
    return None


# Route planning: the robot is a body circle at its centre plus a gripper
# circle (stowed ring, or the held can) GRIP_FWD ahead.
BODY_CLEAR = 9.0 + 3.3 + 1.0
TIP_CLEAR = 4.5 + 3.3 + 1.0
CAN_FENCE = (-58.0, 56.0, -22.0, 31.0)
GRID = 6.0
TURN_COST = 0.15          # cm of travel a degree of pivot is worth


class Router:
    def __init__(self, obstacles, grip, holding):
        self.obs, self.grip, self.holding = obstacles, grip, holding

    def pose_ok(self, x, y, h):
        if not inside(x, y, 0):
            return False
        if any(math.dist((x, y), o) < BODY_CLEAR for o in self.obs):
            return False
        tx = x + self.grip["fwd"] * math.cos(math.radians(h))
        ty = y + self.grip["fwd"] * math.sin(math.radians(h))
        if self.holding and not (CAN_FENCE[0] <= tx <= CAN_FENCE[1] and CAN_FENCE[2] <= ty <= CAN_FENCE[3]):
            return False
        return all(math.dist((tx, ty), o) >= TIP_CLEAR for o in self.obs)

    def turn_ok(self, x, y, h1, h2):
        d = wrap(h2 - h1)
        n = max(1, int(abs(d) / 5))
        return all(self.pose_ok(x, y, h1 + d * k / n) for k in range(n + 1))

    def leg_ok(self, p, q, h):
        n = max(1, int(math.dist(p, q) / 1.5))
        return all(self.pose_ok(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n, h) for k in range(n + 1))

    def route(self, start, h0, goal, hg):
        """[(x, y, dir)] legs from start (heading h0) to goal, ending able to turn to hg; None if blocked."""
        import heapq
        nodes = [start, goal] + [(x, y) for x in frange(FENCE[0], FENCE[1], GRID) for y in frange(FENCE[2], FENCE[3], GRID)]
        nodes = [nodes[0], nodes[1]] + [n for n in nodes[2:] if any(self.pose_ok(*n, h) for h in range(0, 360, 45))]
        best = {}
        pq = [(0.0, 0, round(h0) % 360, None)]
        prev = {}
        while pq:
            cost, i, h, back = heapq.heappop(pq)
            key = (i, h)
            if key in best:
                continue
            best[key] = cost
            prev[key] = back
            if i == 1:
                if self.turn_ok(*goal, h, hg):
                    legs = []
                    k = key
                    while prev[k] is not None:
                        pk, d = prev[k]
                        legs.append((*nodes[k[0]], d))
                        k = pk
                    return list(reversed(legs))
                continue
            p = nodes[i]
            for j, q in enumerate(nodes):
                if j == i:
                    continue
                L = math.dist(p, q)
                if L > 2.2 * GRID and j != 1:
                    continue
                if L > 60:
                    continue
                b = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
                for d, hh in ((1, b), (-1, b + 180)):
                    hq = round(hh) % 360
                    if (j, hq) in best:
                        continue
                    if not self.turn_ok(*p, h, hh) or not self.leg_ok(p, q, hh):
                        continue
                    c = cost + L * (1.0 if d > 0 else 1.2) + TURN_COST * abs(wrap(hh - h))
                    heapq.heappush(pq, (c, j, hq, (key, d)))
        return None


def frange(a, b, step):
    v = a + step / 2
    while v < b:
        yield v
        v += step


def stage_pose(tx, ty, h, grip):
    """Where the robot starts its run-in for a fixed-heading grip/release (as test/canbot.ts picks it)."""
    c, sn = math.cos(math.radians(h)), math.sin(math.radians(h))
    rx = tx - grip["fwd"] * c + grip["left"] * sn
    ry = ty - grip["fwd"] * sn - grip["left"] * c
    for st in (STAGE, 8, 5, 2):
        if inside(rx - st * c, ry - st * sn, 0):
            return rx - st * c, ry - st * sn
    return rx, ry


class Game:
    def __init__(self, robot, cam):
        self.r, self.c = robot, cam
        mat = Mat("bb-obstacle")
        self.circles = {c["n"]: tuple(mat.px_to_playfield(*c["px"])) for c in mat.features["circles"]}
        self.circles[0] = PARK
        self.cal = load_cal()
        self.scores = []
        self.r.run(f"gripcal {self.cal['fwd']:.2f} {self.cal['left']:.2f}")

    def look(self):
        s = self.c.seen()
        if ROBOT_TAG not in s:
            lights_on()
            time.sleep(1)
            s = self.c.seen(12)
        if ROBOT_TAG not in s:
            raise RuntimeError("robot tag not seen")
        return s

    def seed(self, s, skip=None):
        x, y, h = s[ROBOT_TAG]
        self.r.run(f"setpose {x:.2f} {y:.2f} {h:.2f}")
        self.r.run("obsclear", until="CB obs")
        pts = [v for k, v in s.items() if k != ROBOT_TAG and k != skip]
        for i in range(0, len(pts), 4):
            self.r.run("obs " + " ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in pts[i:i + 4]), until="CB obs")

    def can_at(self, s, n, tol=FREE):
        cx, cy = self.circles[n]
        best = None
        for k, (x, y, _) in s.items():
            if k == ROBOT_TAG:
                continue
            d = math.hypot(x - cx, y - cy)
            if d < tol and (best is None or d < best[1]):
                best = (k, d)
        return best[0] if best else None

    def cans(self, s):
        return {k: (v[0], v[1]) for k, v in s.items() if k != ROBOT_TAG}

    def held(self, s, can):
        if can not in s:
            return False
        x, y, h = s[ROBOT_TAG]
        cx, cy, _ = s[can]
        dx, dy = cx - x, cy - y
        fwd = dx * math.cos(math.radians(h)) + dy * math.sin(math.radians(h))
        return abs(fwd - GRIP_FWD) < 4 and math.hypot(dx, dy) < GRIP_FWD + 4

    def drive_route(self, s, goal, hg, obstacles, holding, skip=None):
        """Drive the planned legs to `goal`; False when no clear route exists."""
        x, y, h = s[ROBOT_TAG]
        if math.dist((x, y), goal) < 3:
            return True
        legs = Router(obstacles, self.cal, holding).route((x, y), h, goal, hg)
        if legs is None:
            print("    no clear route; leaving the path to the robot")
            return False
        self.seed(s, skip=skip)
        for lx, ly, d in legs:
            if "fail" in self.r.run(f"leg {lx:.1f} {ly:.1f} {d}"):
                print("    leg aborted")
                return False
        return True

    def headings(self, s, can, tx, ty):
        """Safe headings to pick `can` and to put it down at (tx, ty), or None."""
        others = [p for k, p in self.cans(s).items() if k != can]
        rx, ry, _ = s[ROBOT_TAG]
        cx, cy = self.cans(s)[can]
        hp = approach_heading(cx, cy, others, self.cal, math.degrees(math.atan2(cy - ry, cx - rx)))
        hd = approach_heading(tx, ty, others, self.cal, math.degrees(math.atan2(ty - cy, tx - cx)))
        return (hp, hd) if hp is not None and hd is not None else None

    def move_can(self, can, tx, ty, label):
        """Pick `can` wherever the camera sees it and put it down at (tx, ty)."""
        t0 = time.time()
        s = self.look()
        hs = self.headings(s, can, tx, ty)
        if hs is None:
            print(f"  {label}: no safe way to pick or place can {can} without the arms touching a neighbour")
            return False
        for _attempt in range(2):
            x, y = self.cans(s)[can]
            others = [p for k, p in self.cans(s).items() if k != can]
            if self.drive_route(s, stage_pose(x, y, hs[0], self.cal), hs[0], others + [(x, y)], False):
                s = self.look()
            self.seed(s, skip=can)
            if "fail" in self.r.run(f"pickat {x:.2f} {y:.2f} {hs[0]}"):
                print("  pick aborted")
            for _ in range(3):
                time.sleep(0.3)
                s = self.look()
                if can in s:
                    break
            else:
                raise RuntimeError(f"can {can} not seen after the pick; leaving the gripper closed")
            if self.held(s, can):
                break
            if not self.r.motors_ok():
                raise RuntimeError("motor battery went flat")
            print(f"  can {can} not in the gripper, retrying")
            self.r.run("grip 10", until="GRIP")
            hs = self.headings(s, can, tx, ty) or hs
        else:
            raise RuntimeError(f"could not pick can {can}")
        for _attempt in range(3):
            others = [p for k, p in self.cans(s).items() if k != can]
            if self.drive_route(s, stage_pose(tx, ty, hs[1], self.cal), hs[1], others, True, skip=can):
                s = self.look()
            self.seed(s, skip=can)
            self.r.run("holding 1")
            self.r.point_err = 99.0
            end = self.r.run(f"placeat {tx:.2f} {ty:.2f} {hs[1]}")
            hdg = float(end.split()[-1])
            time.sleep(0.3)
            s = self.look()
            if "fail" not in end or not self.held(s, can):
                break
            print("  place aborted with the can still held; trying again")
            hs = self.headings(s, can, tx, ty) or hs
        if "fail" in end:
            print("  place aborted")
        if can not in s:
            print(f"  {label}: can {can} not seen after placing")
            return False
        ex, ey = s[can][0] - tx, s[can][1] - ty
        err = math.hypot(ex, ey)
        self.scores.append(err)
        print(f"  {label}: can {can} error {err:.2f} cm (dx {ex:+.2f} dy {ey:+.2f})  {time.time() - t0:.0f} s")
        if self.r.point_err > 0.6:
            print(f"    robot stopped {self.r.point_err:.1f} cm short of the target; not learning from this one")
            return True
        # error in the robot frame at release -> correct the gripper offset
        c, sn = math.cos(math.radians(hdg)), math.sin(math.radians(hdg))
        ef, el = ex * c + ey * sn, -ex * sn + ey * c
        k = 1 / (min(self.cal["n"], 12) + 4)
        self.cal = {"fwd": self.cal["fwd"] + k * ef, "left": self.cal["left"] + k * el, "n": self.cal["n"] + 1}
        save_cal(self.cal)
        self.r.run(f"gripcal {self.cal['fwd']:.2f} {self.cal['left']:.2f}")
        return True

    def move(self, a, b):
        s = self.look()
        can = self.can_at(s, a)
        if can is None:
            print(f"  no can on circle {a}, skipping")
            return
        if b != a and self.can_at(s, b) is not None:
            print(f"  circle {b} is occupied, skipping")
            return
        self.move_can(can, *self.circles[b], f"circle {a} -> {b}")

    def home(self):
        s = self.look()
        self.seed(s)
        self.r.run("home")
        x, y, h = self.look()[ROBOT_TAG]
        print(f"  home: robot at ({x:.1f},{y:.1f}) heading {h:.1f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("circles", nargs="*", type=int, help="from to [from to ...]")
    ap.add_argument("--swap", action="store_true", help="swap the cans on the two circles given")
    ap.add_argument("--home", action="store_true", help="only drive home")
    ap.add_argument("--no-home", action="store_true", help="stay put at the end")
    ap.add_argument("--host", default=os.environ.get("ZHOST", "jtl@192.168.4.52"))
    ap.add_argument("--robot", default="zetuv")
    a = ap.parse_args()
    pairs = list(zip(a.circles[0::2], a.circles[1::2]))
    if a.swap:
        if len(a.circles) != 2:
            ap.error("--swap takes two circles")
        p, q = a.circles
        pairs = [(p, 0), (q, p), (0, q)]
    lights_on()
    cam = Camera()
    robot = Robot(a.host, a.robot)
    if not robot.motors_ok():
        robot.close()
        sys.exit("motor battery is flat (STATUS connL/connR=0): charge or swap it, then run again")
    g = Game(robot, cam)
    if a.swap:
        s = g.look()
        missing = [c for c in a.circles if g.can_at(s, c) is None]
        if missing or g.can_at(s, 0, tol=8) is not None:
            robot.close()
            sys.exit(f"cannot swap: no can on circle(s) {missing}" if missing else "cannot swap: the park spot is taken")
    t0 = time.time()
    robot.run("tune 1")
    time.sleep(0.8)
    try:
        for p, q in pairs:
            print(f"move {p} -> {q}")
            g.move(p, q)
            robot.run("tune 0")
        if not a.no_home:
            g.home()
    finally:
        try:
            robot.run("tune 2", timeout=5)
            time.sleep(1)
        except Exception:
            pass
        robot.close()
    if g.scores:
        print(f"done in {time.time() - t0:.0f} s; mean error {sum(g.scores) / len(g.scores):.2f} cm over {len(g.scores)} cans")


if __name__ == "__main__":
    main()
