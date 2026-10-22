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

    def can_at(self, s, n, tol=8.0):
        cx, cy = self.circles[n]
        best = None
        for k, (x, y, _) in s.items():
            if k == ROBOT_TAG:
                continue
            d = math.hypot(x - cx, y - cy)
            if d < tol and (best is None or d < best[1]):
                best = (k, d)
        return best[0] if best else None

    def held(self, s, can):
        if can not in s:
            return False
        x, y, h = s[ROBOT_TAG]
        cx, cy, _ = s[can]
        dx, dy = cx - x, cy - y
        fwd = dx * math.cos(math.radians(h)) + dy * math.sin(math.radians(h))
        return abs(fwd - GRIP_FWD) < 3 and math.hypot(dx, dy) < GRIP_FWD + 3

    def move(self, a, b):
        t0 = time.time()
        s = self.look()
        can = self.can_at(s, a)
        if can is None:
            print(f"  no can on circle {a}, skipping")
            return
        if self.can_at(s, b, tol=5) is not None and b != a:
            print(f"  circle {b} is occupied, skipping")
            return
        for attempt in range(2):
            self.seed(s, skip=can)
            x, y, _ = s[can]
            if "fail" in self.r.run(f"pickat {x:.2f} {y:.2f}"):
                print("  pick aborted")
            s = self.look()
            if self.held(s, can):
                break
            if not self.r.motors_ok():
                raise RuntimeError("motor battery went flat")
            print(f"  can {can} not in the gripper, retrying")
            self.r.run("grip 10", until="GRIP")
        else:
            raise RuntimeError(f"could not pick can {can}")
        tx, ty = self.circles[b]
        self.seed(s, skip=can)
        self.r.run("holding 1")
        self.r.point_err = 99.0
        end = self.r.run(f"placeat {tx:.2f} {ty:.2f}")
        if "fail" in end:
            print("  place aborted")
        hdg = float(end.split()[-1])
        s = self.look()
        if can in s:
            ex, ey = s[can][0] - tx, s[can][1] - ty
            err = math.hypot(ex, ey)
            self.scores.append(err)
            print(f"  can {can}: circle {a} -> {b}  error {err:.2f} cm (dx {ex:+.2f} dy {ey:+.2f})  {time.time() - t0:.0f} s")
            if self.r.point_err > 0.6:
                print(f"    robot stopped {self.r.point_err:.1f} cm short of the target; not learning from this one")
                return
            # error in the robot frame at release -> correct the gripper offset
            c, sn = math.cos(math.radians(hdg)), math.sin(math.radians(hdg))
            ef, el = ex * c + ey * sn, -ex * sn + ey * c
            k = 1 / (min(self.cal["n"], 12) + 4)
            self.cal = {"fwd": self.cal["fwd"] + k * ef, "left": self.cal["left"] + k * el, "n": self.cal["n"] + 1}
            save_cal(self.cal)
            self.r.run(f"gripcal {self.cal['fwd']:.2f} {self.cal['left']:.2f}")
            print(f"    robot frame fwd {ef:+.2f} left {el:+.2f} at heading {hdg:.0f}; grip now {self.cal['fwd']:.2f} {self.cal['left']:.2f}")
        else:
            print(f"  can {can} placed on {b} but not seen afterwards")

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
    try:
        for p, q in pairs:
            print(f"move {p} -> {q}")
            g.move(p, q)
        if not a.no_home:
            g.home()
    finally:
        robot.close()
    if g.scores:
        print(f"done in {time.time() - t0:.0f} s; mean error {sum(g.scores) / len(g.scores):.2f} cm over {len(g.scores)} cans")


if __name__ == "__main__":
    main()
