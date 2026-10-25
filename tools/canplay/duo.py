"""Two gripper robots share the bb-obstacle mat and move cans to a layout together.

    uv run python tools/canplay/duo.py 63:2 13:4 64:9 60:11
    uv run python tools/canplay/duo.py --plan 63:2 13:4 64:9 60:11

Each robot runs in its own worker process. The coordinator hands out can
moves, reserves the strip of field a move needs (robot -> can -> circle ->
park spot) and lets both robots drive at once only when their strips are well
apart; otherwise one waits on its park spot. Each robot plans its routes with
the other one as an obstacle.
"""
import argparse, json, math, os, queue, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canplay  # noqa: E402

ROBOTS = {
    "zetuv": {"link": ["--relay", "magni"], "park": (-46.0, 12.0, 0.0)},
    "tigez": {"link": [], "park": (22.0, 14.0, 180.0)},
}
APART = 26.0              # two moving robots' strips (robot centres and cans) stay this far apart
PARKED = 24.0             # a strip keeps this far from a parked robot's centre
GOAL_TOL = 2.0
MISSES = 2                # after this many off-target placements of a can, the other robot takes it
MAT = (-61.0, 59.0, -25.4, 34.2)


def robot_tags():
    return {n: json.load(open(os.path.join(canplay.ROBOTS, f"{n}.json")))["vision"]["robot_tag_id"] for n in ROBOTS}


def seg_dist(p, q, a, b):
    def pt_seg(c, u, v):
        dx, dy = v[0] - u[0], v[1] - u[1]
        L = dx * dx + dy * dy
        t = 0 if L == 0 else max(0, min(1, ((c[0] - u[0]) * dx + (c[1] - u[1]) * dy) / L))
        return math.dist(c, (u[0] + t * dx, u[1] + t * dy))
    return min(pt_seg(p, a, b), pt_seg(q, a, b), pt_seg(a, p, q), pt_seg(b, p, q))


def strip_dist(s1, s2):
    pairs1 = list(zip(s1, s1[1:])) or [(s1[0], s1[0])]
    pairs2 = list(zip(s2, s2[1:])) or [(s2[0], s2[0])]
    return min(seg_dist(p, q, a, b) for p, q in pairs1 for a, b in pairs2)


# ---------------------------------------------------------------- worker side

def worker(name):
    out = sys.stdout
    sys.stdout = sys.stderr
    canplay.use_robot(name)
    others = {t for n, t in robot_tags().items() if n != name}
    canplay.lights_on()
    cam = canplay.Camera()
    link = ROBOTS[name]["link"]
    relay = link[1] if link else None
    robot = canplay.Robot(None, name, relay)
    if not robot.motors_ok():
        print(json.dumps({"ok": False, "err": "motor battery flat"}), file=out, flush=True)
        return

    class DuoGame(canplay.Game):
        def look(self):
            s = super().look()
            # the other robot is a cloud of obstacle points: body and gripper
            for t in others & set(s):
                x, y, h = s.pop(t)
                c, sn = math.cos(math.radians(h)), math.sin(math.radians(h))
                pts = [(0, 0), (8, 0), (-8, 0), (0, 8), (0, -8), (16, 0)]
                for i, (f, l) in enumerate(pts):
                    s[f"r{t}.{i}"] = (x + f * c - l * sn, y + f * sn + l * c, 0.0)
            return s

    g = DuoGame(robot, cam)
    print(json.dumps({"ok": True, "ready": name}), file=out, flush=True)
    for line in sys.stdin:
        cmd = json.loads(line)
        try:
            if cmd["op"] == "move":
                ok = g.move_can(cmd["can"], cmd["x"], cmd["y"], cmd.get("label", "move"))
                res = {"ok": bool(ok)}
            elif cmd["op"] == "goto":
                s = g.look()
                obstacles = [p for k, p in g.cans(s).items()]
                res = {"ok": g.drive_route(s, (cmd["x"], cmd["y"]), cmd["h"], obstacles, False)}
            elif cmd["op"] == "quit":
                break
            else:
                res = {"ok": False, "err": f"unknown op {cmd['op']}"}
            x, y, h = g.look()[canplay.ROBOT_TAG]
            res["pose"] = [round(x, 1), round(y, 1), round(h, 1)]
        except Exception as e:
            res = {"ok": False, "err": f"{type(e).__name__}: {e}"}
            try:
                robot.run("where")
            except Exception:
                pass
        print(json.dumps(res), file=out, flush=True)
    try:
        robot.run("tune 2", timeout=5)
    except Exception:
        pass
    robot.close()


# ----------------------------------------------------------- coordinator side

class Worker:
    def __init__(self, name):
        self.name = name
        self.park = ROBOTS[name]["park"]
        self.p = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--worker", name],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.replies = queue.Queue()
        threading.Thread(target=self.read, daemon=True).start()
        self.job = None           # (strip, description) while busy
        self.parked = False
        self.failed = False

    def read(self):
        for line in self.p.stdout:
            self.replies.put(json.loads(line))
        self.replies.put({"ok": False, "err": "worker exited"})

    def send(self, cmd):
        self.p.stdin.write(json.dumps(cmd) + "\n")
        self.p.stdin.flush()


def say(name, msg):
    print(f"{time.strftime('%H:%M:%S')} [{name}] {msg}", flush=True)


class Coordinator:
    def __init__(self, goals, plan_only):
        self.tags = robot_tags()
        canplay.use_robot("zetuv")
        self.cam = canplay.Camera()
        for n in ROBOTS:
            canplay.use_robot(n)
            self.cam.d.register_tag(canplay.TagId(canplay.TagFamily.APRILTAG, canplay.ROBOT_TAG), canplay.ROBOT_MOUNT)
        mat = canplay.Mat("bb-obstacle")
        self.circles = {c["n"]: tuple(mat.px_to_playfield(*c["px"])) for c in mat.features["circles"]}
        self.target = {int(t): int(c) for t, c in (g.split(":") for g in goals)}
        self.plan_only = plan_only
        self.claimed = {}         # circle -> robot placing there
        self.moving = {}          # can -> robot carrying it
        self.failures = {}        # can -> failed attempts
        self.misses = {}          # (can, robot) -> placements that missed the circle
        self.grip = {}
        for n in ROBOTS:
            canplay.use_robot(n)
            self.grip[n] = canplay.load_cal()

    def look(self):
        s = self.cam.seen(10)
        robots = {n: s[t] for n, t in self.tags.items() if t in s}
        cans = {k: v[:2] for k, v in s.items() if k not in self.tags.values()
                and MAT[0] <= v[0] <= MAT[1] and MAT[2] <= v[1] <= MAT[3]}
        return robots, cans

    def pending(self, cans):
        return [k for k, c in self.target.items()
                if k in cans and math.dist(cans[k], self.circles[c]) > GOAL_TOL]

    def free(self, cans, circle, can):
        pt = self.circles[circle]
        if circle in self.claimed:
            return False
        return all(math.dist(p, pt) >= canplay.FREE for k, p in cans.items() if k != can)

    def strip(self, w, pos, can_pt, hp, goal_pt, hd):
        """Where the robot will be: its run-in, its body at the can, the can, for the pick then the place."""
        g = self.grip[w.name]
        out = [pos[:2]]
        for (x, y), h in ((can_pt, hp), (goal_pt, hd)):
            stage = canplay.stage_pose(x, y, h, g)
            body = (x - g["fwd"] * math.cos(math.radians(h)), y - g["fwd"] * math.sin(math.radians(h)))
            out += [stage, body, (x, y), body]
        return out + [w.park[:2]]

    def choose(self, w, workers, robots, cans):
        """The cheapest ready move for idle worker `w` that keeps clear of the other robot."""
        other = next(o for o in workers if o is not w)
        best = None
        for k in self.pending(cans):
            if k in self.moving or self.failures.get(k, 0) >= 2 or not self.free(cans, self.target[k], k):
                continue
            if self.misses.get((k, w.name), 0) >= MISSES and self.misses.get((k, other.name), 0) < MISSES:
                continue
            if sum(n for (c, _), n in self.misses.items() if c == k) >= 3 * MISSES:
                continue
            goal = self.circles[self.target[k]]
            others = [p for c, p in cans.items() if c != k] + [r[:2] for n, r in robots.items() if n != w.name]
            rx, ry = robots.get(w.name, w.park)[:2]
            cx, cy = cans[k]
            hp = canplay.approach_heading(cx, cy, others, self.grip[w.name], math.degrees(math.atan2(cy - ry, cx - rx)))
            hd = canplay.approach_heading(*goal, others, self.grip[w.name], math.degrees(math.atan2(goal[1] - cy, goal[0] - cx)))
            if hp is None or hd is None:
                continue
            st = self.strip(w, robots.get(w.name, w.park), cans[k], hp, goal, hd)
            if other.job is not None:
                if strip_dist(st, other.job[0]) < APART:
                    continue
            elif other.name in robots and strip_dist(st, [robots[other.name][:2]]) < PARKED:
                continue
            cost = sum(math.dist(a, b) for a, b in zip(st, st[1:]))
            if best is None or cost < best[0]:
                best = (cost, k, goal, st)
        return best

    def plan(self):
        robots, cans = self.look()
        for n, p in robots.items():
            print(f"  {n} at ({p[0]:.1f},{p[1]:.1f}) heading {p[2]:.0f}")
        for k, p in sorted(cans.items()):
            goal = self.target.get(k)
            print(f"  can {k} at ({p[0]:.1f},{p[1]:.1f})" + (f" -> circle {goal}" if goal else ""))
        missing = [k for k in self.target if k not in cans]
        if missing:
            sys.exit(f"can(s) {missing} not on the mat")
        return robots, cans

    def run(self):
        robots, cans = self.plan()
        if self.plan_only:
            return
        workers = [Worker(n) for n in ROBOTS]
        for w in workers:
            r = w.replies.get(timeout=120)
            if not r.get("ok"):
                sys.exit(f"{w.name}: {r.get('err')}")
            say(w.name, "ready")
        t0 = time.time()
        # Send each robot to its park spot, one at a time, nearest first so it clears the start square.
        for w in sorted(workers, key=lambda w: math.dist(robots[w.name][:2], w.park[:2])):
            say(w.name, f"to park spot ({w.park[0]:.0f},{w.park[1]:.0f})")
            w.send({"op": "goto", "x": w.park[0], "y": w.park[1], "h": w.park[2]})
            r = w.replies.get(timeout=600)
            say(w.name, f"parked at {r.get('pose')}" if r.get("ok") else f"park failed: {r.get('err')}")
            w.parked = True
        idle_since = None
        while True:
            # collect finished jobs
            for w in workers:
                if w.job is None:
                    continue
                try:
                    r = w.replies.get_nowait()
                except queue.Empty:
                    continue
                kind, k = w.job[1], w.job[2]
                if kind == "move":
                    self.moving.pop(k, None)
                    if not r.get("ok"):
                        self.failures[k] = self.failures.get(k, 0) + 1
                    _, now = self.look()
                    if k in now and math.dist(now[k], self.circles[self.target[k]]) > GOAL_TOL:
                        self.misses[(k, w.name)] = self.misses.get((k, w.name), 0) + 1
                        if self.misses[(k, w.name)] == MISSES:
                            say(w.name, f"missed circle {self.target[k]} twice with can {k}; handing it over")
                    self.claimed = {c: n for c, n in self.claimed.items() if n != w.name}
                    say(w.name, f"can {k} done" if r.get("ok") else f"can {k} failed: {r.get('err')}")
                    if not r.get("ok") and "Error" in str(r.get("err")):
                        w.failed = True
                    # back to the park spot as its own reserved job
                    robots, _ = self.look()
                    pos = robots.get(w.name, w.park)
                    w.job = ([pos[:2], w.park[:2]], "park", None)
                    w.send({"op": "goto", "x": w.park[0], "y": w.park[1], "h": w.park[2]})
                else:
                    say(w.name, f"parked at {r.get('pose')}")
                    w.job = None
            robots, cans = self.look()
            todo = self.pending(cans)
            if not todo and all(w.job is None for w in workers):
                break
            started = False
            for w in workers:
                if w.job is not None or w.failed:
                    continue
                pick = self.choose(w, workers, robots, cans)
                if pick is None:
                    continue
                _, k, goal, st = pick
                self.moving[k] = w.name
                self.claimed[self.target[k]] = w.name
                w.job = (st, "move", k)
                say(w.name, f"can {k} -> circle {self.target[k]}")
                w.send({"op": "move", "can": k, "x": goal[0], "y": goal[1],
                        "label": f"can {k} -> circle {self.target[k]}"})
                started = True
            if all(w.job is None for w in workers) and not started:
                idle_since = idle_since or time.time()
                if time.time() - idle_since > 20 or all(w.failed for w in workers):
                    say("duo", f"stuck: cans {todo} have no move that fits")
                    break
            else:
                idle_since = None
            time.sleep(0.5)
        for w in workers:
            w.send({"op": "quit"})
        robots, cans = self.look()
        for k, c in self.target.items():
            if k in cans:
                say("duo", f"can {k} on circle {c}: {math.dist(cans[k], self.circles[c]):.2f} cm off")
        say("duo", f"done in {time.time() - t0:.0f} s")
        for w in workers:
            w.p.wait(timeout=30)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        return worker(sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("goals", nargs="+", help="tag:circle")
    ap.add_argument("--plan", action="store_true", help="show the field and stop")
    a = ap.parse_args()
    canplay.lights_on()
    Coordinator(a.goals, a.plan).run()


if __name__ == "__main__":
    main()
