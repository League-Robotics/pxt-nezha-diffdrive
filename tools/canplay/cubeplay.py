"""Sort the coloured cubes into their garages on the bb-obstacle mat with a paddle-gripper robot.

    uv run python tools/canplay/cubeplay.py --relay magni [--shots DIR]
    uv run python tools/canplay/cubeplay.py --plan            show the next move and stop

Garages are filled far side first (blue, orange, green), each through its
open (dashed) side, deepest slot first. A cube whose pick or drop lane is
blocked by another cube waits; if nothing can move, the blocking cube is
parked on the north or south edge first. The camera is read before every
leg; an annotated frame is saved after every move.
"""
import argparse, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canplay  # noqa: E402
from canplay import Game, Robot, Camera, stage_pose, wrap  # noqa: E402
import cubes  # noqa: E402

ORDER = ["blue", "orange", "green"]
# (along, lateral) cm from the garage centre, along = the inward heading; deepest first
SLOTS = {"blue": [(4, 0), (-2, 5), (-2, -5), (-6, 0)],
         "orange": [(5, 1.5), (5, -5), (-2, 1.5), (-2, -5)],
         "green": [(6, 0), (0, 0), (-6, 0), (0, 6)]}
STAGE = 12.0
LONG_LEG = 45.0           # straight legs between any two free grid points: fewer pivots among the cubes
BODY = 10.0               # robot centre path keeps this far from any cube
V_OPEN = 8.5              # open paddles: lane half-width round the picked cube's path
V_NARROW = 5.0            # paddles opened only to NARROW_GRIP: a tighter lane
NARROW_GRIP = 50
HELD = 4.5                # held cube's path
RELEASE = 30              # wide enough to free a cube wedged deep in the V, not the full 14 cm swing
STOW = 75
TIP = 18.5                # closed paddle tips ahead of the robot centre
PUSH = 8.0                # how far to push a cube off its neighbour
# Eric's table: anti-start (circle 11, +x) is the top, start (circle 2) the bottom; the long
# sides are the circle-5 side (+y) and the circle-8 side (-y). Cubes are parked on those
# sides; the robot itself keeps to the middle, well away from every mat edge.
PARK_N = [(x, 27.0) for x in range(-40, 12, 8)]      # circle-5 side
PARK_S = [(x, -19.0) for x in range(-40, 22, 8)]     # circle-8 side
MIDDLE = 8.0              # a loose cube this close to the centre line (y 4) is in the way
DROP_HEADING = {"orange": 90}         # orange from the middle, toward the circle-5 edge
ORANGE_SLOTS = [(22.5, 27.5), (31.5, 27.5), (22.5, 20.5), (31.5, 20.5)]
canplay.FENCE = (-50.0, 42.0, -13.0, 18.0)           # robot centre: the middle of the field
HELD_ZONE = (11.0, 21.0, 5.0)   # a cube this far ahead (min, max) and this close sideways is in the paddles
# routes keep cube-sized clearances, not can-sized ones
canplay.BODY_CLEAR = 9.0 + 1.3 + 2.5
canplay.TIP_CLEAR = 6.0           # paddles and cube sized; canbot gets no obstacle list, so its can-sized check never refuses


class CubeRouter(canplay.Router):
    """The robot may start with a cube just ahead of its paddles: the start node itself is always allowed."""
    def pose_ok(self, x, y, h):
        if self.start is not None and math.dist((x, y), self.start) < 0.5:
            return True
        return super().pose_ok(x, y, h)


    def route(self, start, h0, goal, hg):
        """canplay's route with one extra node 10 cm behind the goal on the final heading,
        so the robot can arrive already facing it instead of pivoting among cubes."""
        import heapq
        self.start = start
        pre = ahead(goal, hg, -10)
        nodes = [start, goal, pre] + [(x, y) for x in canplay.frange(canplay.FENCE[0], canplay.FENCE[1], canplay.GRID)
                                      for y in canplay.frange(canplay.FENCE[2], canplay.FENCE[3], canplay.GRID)]
        nodes = nodes[:3] + [n for n in nodes[3:] if any(self.pose_ok(*n, h) for h in range(0, 360, 45))]
        best, prev = {}, {}
        pq = [(0.0, 0, round(h0) % 360, None)]
        while pq:
            cost, i, h, back = heapq.heappop(pq)
            if (i, h) in best:
                continue
            best[(i, h)] = cost
            prev[(i, h)] = back
            if i == 1:
                if self.turn_ok(*goal, h, hg):
                    legs, k = [], (i, h)
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
                if L > LONG_LEG and j not in (1, 2) or L > 60:
                    continue
                b = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
                for d, hh in ((1, b), (-1, b + 180)):
                    hq = round(hh) % 360
                    if (j, hq) in best or not self.turn_ok(*p, h, hh) or not self.leg_ok(p, q, hh):
                        continue
                    c = cost + L * (1.0 if d > 0 else 1.2) + canplay.TURN_COST * abs(wrap(hh - h))
                    heapq.heappush(pq, (c, j, hq, ((i, h), d)))
        return None


canplay.Router = CubeRouter


def spot_key(c):
    return (c[0], round(c[1] / 4), round(c[2] / 4))


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def ahead(p, h, d):
    return (p[0] + d * math.cos(math.radians(h)), p[1] + d * math.sin(math.radians(h)))


class Board:
    """Garage slots and drop headings."""
    def __init__(self):
        self.g = cubes.garages()
        self.slots = {}
        for col, (poly, (i, j)) in self.g.items():
            cx = sum(p[0] for p in poly) / 4
            cy = sum(p[1] for p in poly) / 4
            mx, my = (poly[i][0] + poly[j][0]) / 2, (poly[i][1] + poly[j][1]) / 2
            h = math.degrees(math.atan2(cy - my, cx - mx))
            u = (math.cos(math.radians(h)), math.sin(math.radians(h)))
            n = (-u[1], u[0])
            self.slots[col] = [((cx + a * u[0] + l * n[0], cy + a * u[1] + l * n[1]), h) for a, l in SLOTS[col]]
        self.slots["orange"] = [(p, DROP_HEADING["orange"]) for p in ORANGE_SLOTS]

    def home(self, col, x, y):
        return cubes.inside(self.g[col][0], x, y, 1.0)

    def in_any(self, x, y):
        return any(cubes.inside(poly, x, y, -2.0) for poly, _ in self.g.values())


class CubeGame(Game):
    def __init__(self, robot, cam, shots):
        super().__init__(robot, cam)
        self.v = cubes.Vision(cam.d)
        self.board = Board()
        self.mem = []              # last seen [(colour, x, y)]
        self.shots = shots
        self.n = 0
        self.stuck = {}
        self.holding = False
        self.v_open = V_OPEN
        # pivot corrections, camera-tuned per robot (live values reset on reboot)
        if "turn" in self.cal:
            robot.run(f"gripcal {self.cal['fwd']:.2f} {self.cal['left']:.2f} {self.cal['turn'][0]} {self.cal['turn'][1]}")

    def grip_point(self, pose):
        return ahead(pose[:2], pose[2], self.cal["fwd"])

    def observe(self):
        """(tag dict with cubes as obstacles, [(colour, x, y)] on the mat, the cube in the gripper or None)."""
        s = self.look()
        pose = s[canplay.ROBOT_TAG]
        seen = self.v.cubes(self.v.frame(), [pose[:2]])
        h = math.radians(pose[2])

        def in_paddles(c):
            dx, dy = c[1] - pose[0], c[2] - pose[1]
            f, l = dx * math.cos(h) + dy * math.sin(h), -dx * math.sin(h) + dy * math.cos(h)
            return HELD_ZONE[0] <= f <= HELD_ZONE[1] and abs(l) <= HELD_ZONE[2]
        held = next((c for c in seen if in_paddles(c)), None)
        if self.holding and held is not None:
            seen.remove(held)
        # cubes under the robot body are masked out: keep their last known place
        for c in self.mem:
            if math.dist(c[1:], pose[:2]) < cubes.BODY_CLEAR and not any(math.dist(c[1:], o[1:]) < 4 for o in seen):
                seen.append(c)
        self.mem = seen
        self.held = held
        for k in [k for k in s if isinstance(k, str)]:
            del s[k]
        for i, (_, x, y) in enumerate(seen):
            s[f"c{i}"] = (x, y, 0.0)
        return s, seen

    def shot(self, note):
        if not self.shots:
            return
        self.n += 1
        s = self.look()
        rx, ry, _ = s[canplay.ROBOT_TAG]
        path = os.path.join(self.shots, f"{self.n:02d}-{note.replace(' ', '-')}.png")
        self.v.snap(path, robots=[(rx, ry)], note=f"{time.strftime('%H:%M:%S')}  {note}")
        print(f"    image {path}")

    # ---- lanes

    def pick_ok(self, c, h, others):
        f = self.cal["fwd"]
        stand = ahead(c, h, -f)
        stage = stage_pose(*c, h, self.cal)      # the run-in shortens to fit, as the robot's does
        if not canplay.inside(*stage, 0) or not canplay.inside(*stand, 0):
            return False
        u = (math.cos(math.radians(h)), math.sin(math.radians(h)))

        def v_clear(o):
            # a cube just beyond the target (further along the approach) is past the paddles' reach
            along = (o[0] - c[0]) * u[0] + (o[1] - c[1]) * u[1]
            return along >= 2.5 or seg_dist(o, ahead(c, h, -STAGE), c) >= self.v_open
        return all(seg_dist(o, stage, stand) >= BODY and v_clear(o) for o in others)

    def pick_heading(self, c, others, prefer):
        hs = sorted(range(0, 360, 15), key=lambda h: abs(wrap(h - prefer)))
        return next((h for h in hs if self.pick_ok(c, h, others)), None)

    def place_ok(self, p, h, others):
        f = self.cal["fwd"]
        stand = ahead(p, h, -f)
        stage = stage_pose(*p, h, self.cal)
        if not canplay.inside(*stand, 0):
            return False
        return all(seg_dist(o, stage, stand) >= BODY and seg_dist(o, ahead(p, h, -STAGE), p) >= HELD for o in others)

    def free_slot(self, col, cubes_now, skip):
        """The deepest empty slot whose drop lane is clear."""
        others = [c[1:] for i, c in enumerate(cubes_now) if i != skip]
        for p, h in self.board.slots[col]:
            if any(math.dist(p, o) < 4 for o in others):
                continue
            # through the open side if there is room; the tape is only paint, so any side will do
            for dh in (0, 45, -45, 90, -90, 135, -135, 180):
                if self.place_ok(p, h + dh, others):
                    return p, wrap(h + dh)
        return None

    def candidates(self, robot, cubes_now):
        """Direct moves [(cube index, pick heading, (drop point, heading), why)], far garage first."""
        out = []
        for col in ORDER:
            for i, (cc, x, y) in enumerate(cubes_now):
                if cc != col or self.board.home(col, x, y) or self.stuck.get(spot_key(cubes_now[i]), 0) >= 2:
                    continue
                others = [c[1:] for j, c in enumerate(cubes_now) if j != i]
                slot = self.free_slot(col, cubes_now, i)
                if slot is None:
                    continue
                hp = self.pick_heading((x, y), others, math.degrees(math.atan2(y - robot[1], x - robot[0])))
                if hp is None or not self.place_ok(*slot, others):
                    continue
                out.append((math.dist(robot[:2], (x, y)), i, hp, slot, f"{col} to garage"))
            if out:
                return [min(out)[1:]]
        return []

    def clear_middle(self, robot, cubes_now):
        """Park the loose cube nearest start that sits in the middle lane."""
        mids = [i for i, c in enumerate(cubes_now)
                if abs(c[2] - 4) < MIDDLE and c[1] < 40 and not self.board.home(*c) and not self.board.in_any(*c[1:])]
        for i in sorted(mids, key=lambda i: cubes_now[i][1]):
            mv = self.parking(robot, cubes_now, only=i)
            if mv:
                return mv
        return []

    def parking(self, robot, cubes_now, only=None):
        """Move one cube that sits in a lane or garage of another colour to an edge."""
        best = None
        for i, (cc, x, y) in enumerate(cubes_now):
            if only is not None and i != only:
                continue
            if self.board.home(cc, x, y) or self.stuck.get(spot_key(cubes_now[i]), 0) >= 2:
                continue
            if any(abs(y - py) < 3 for _, py in PARK_N + PARK_S) and not self.board.in_any(x, y):
                continue               # already parked on an edge
            others = [c[1:] for j, c in enumerate(cubes_now) if j != i]
            hp = self.pick_heading((x, y), others, math.degrees(math.atan2(y - robot[1], x - robot[0])))
            if hp is None:
                continue
            for p in sorted(PARK_N + PARK_S, key=lambda q: math.dist(q, (x, y))):
                if any(math.dist(p, o) < 7 for o in others) or self.board.in_any(*p):
                    continue
                h = 90 if p[1] > 0 else -90
                if self.place_ok(p, h, others):
                    d = math.dist(robot[:2], (x, y)) + math.dist((x, y), p)
                    if best is None or d < best[0]:
                        best = (d, i, hp, (p, h), f"{cc} parked on the edge")
                    break
        return [best[1:]] if best else []

    def separation(self, robot, cubes_now):
        """Two touching cubes of different colours: push one sideways off its neighbour with the closed paddles."""
        best = None
        for i, a in enumerate(cubes_now):
            for j, b in enumerate(cubes_now):
                if i == j or a[0] == b[0] or math.dist(a[1:], b[1:]) > 5 or self.board.home(*a):
                    continue
                vx, vy = a[1] - b[1], a[2] - b[2]
                n = math.hypot(vx, vy) or 1
                vx, vy = vx / n, vy / n
                for wx, wy in ((-vy, vx), (vy, -vx)):
                    h = math.degrees(math.atan2(wy, wx))
                    # the paddle tip meets `a` 2 cm off its centre, on the side away from `b`
                    hit = (a[1] + 2 * vx, a[2] + 2 * vy)
                    start = ahead(hit, h, -(TIP + STAGE))
                    end = ahead(hit, h, PUSH - TIP)
                    if not (canplay.inside(*start, 0) and canplay.inside(*end, 0)):
                        continue
                    others = [c[1:] for k, c in enumerate(cubes_now) if k not in (i, j)]
                    if any(seg_dist(o, start, end) < BODY or seg_dist(o, ahead(start, h, TIP), ahead(hit, h, PUSH)) < 6 for o in others):
                        continue
                    d = math.dist(robot[:2], start)
                    if best is None or d < best[0]:
                        best = (d, i, start, end, h)
        return best

    def separate(self, sep, cubes_now):
        _, i, start, end, h = sep
        print(f"  pushing the {cubes_now[i][0]} cube at ({cubes_now[i][1]:.1f},{cubes_now[i][2]:.1f}) {PUSH:.0f} cm off its neighbour")
        s, now = self.observe()
        if not self.drive_route(s, start, h, [c[1:] for c in now], False):
            self.stuck[spot_key(cubes_now[i])] = self.stuck.get(spot_key(cubes_now[i]), 0) + 1
            print("    no clear route to the push")
            return
        s, _ = self.observe()
        self.seed(s)
        self.r.run(f"grip {STOW}", until="GRIP")
        self.r.run(f"leg {end[0]:.2f} {end[1]:.2f} 1")
        self.r.run(f"leg {start[0]:.2f} {start[1]:.2f} -1")

    # ---- moves

    def do_move(self, i, hp, slot, why, cubes_now):
        col, x, y = cubes_now[i]
        (px, py), hd = slot
        t0 = time.time()
        print(f"  {col} cube at ({x:.1f},{y:.1f}) -> ({px:.1f},{py:.1f}) [{why}], pick heading {hp}, drop heading {hd:.0f}")
        others = [c[1:] for j, c in enumerate(cubes_now) if j != i]
        s, _ = self.observe()
        r0 = s[canplay.ROBOT_TAG]
        prefer = math.degrees(math.atan2(y - r0[1], x - r0[0]))
        tries = [hp] + [h for h in sorted(range(0, 360, 15), key=lambda h: abs(wrap(h - prefer)))
                        if h != hp and self.pick_ok((x, y), h, others)]
        for hp in tries[:6]:
            if self.drive_route(s, stage_pose(x, y, hp, self.cal), hp, others + [(x, y)], False):
                break
        else:
            self.stuck[spot_key((col, x, y))] = self.stuck.get(spot_key((col, x, y)), 0) + 1
            print("    no clear route to the pick; trying another move")
            return False
        s, now = self.observe()
        c = min(now, key=lambda c: math.dist(c[1:], (x, y)))
        if c[0] != col or math.dist(c[1:], (x, y)) > 4:
            print("    the cube has moved; replanning")
            return False
        x, y = c[1:]
        skip = next((k for k, v in s.items() if isinstance(k, str) and math.dist(v[:2], (x, y)) < 3), None)
        self.seed(s, skip=skip)
        self.r.run(f"pickat {x:.2f} {y:.2f} {hp}")
        self.holding = True
        s, now = self.observe()
        if self.held is None or self.held[0] != col:
            self.holding = False
            self.stuck[spot_key((col, x, y))] = self.stuck.get(spot_key((col, x, y)), 0) + 1
            print("    pick missed: no " + col + " cube in the gripper")
            self.r.run(f"grip {STOW}", until="GRIP")
            return False
        self.mem = [c for c in self.mem if math.dist(c[1:], (x, y)) > 3]
        return self.deliver(col, slot if why.endswith("edge") else None, t0)

    def deliver(self, col, slot=None, t0=None):
        """Carry the cube in the paddles to a free slot in its garage (or to `slot`) and let it go there."""
        t0 = t0 or time.time()
        s, now = self.observe()
        others = [c[1:] for c in now]
        if slot is None:
            slot = self.free_slot(col, now, -1)
            if slot is not None and not self.place_ok(*slot, others):
                slot = None
        if slot is None:
            spots = [p for p in sorted(PARK_N + PARK_S, key=lambda q: math.dist(q, s[canplay.ROBOT_TAG][:2]))
                     if not self.board.in_any(*p) and all(math.dist(p, o) >= 7 for o in others)]
            slot = next(((p, 90 if p[1] > 0 else -90) for p in spots if self.place_ok(p, 90 if p[1] > 0 else -90, others)), None)
            print(f"    no clear lane into the {col} garage; parking the cube" if slot else "    nowhere to put it")
        if slot is None:
            self.release_here()
            return False
        (px, py), hd = slot
        stage = stage_pose(px, py, hd, self.cal)
        if not self.drive_route(s, stage, hd, others, True):
            print("    no clear route to the drop; putting the cube down here")
            self.release_here()
            return False
        s, _ = self.observe()
        self.seed(s, holding=True)
        # the held cube sits anywhere from the hinge to the tips: aim with where it is now
        pose = s[canplay.ROBOT_TAG]
        if self.held is not None:
            dx, dy = self.held[1] - pose[0], self.held[2] - pose[1]
            hr = math.radians(pose[2])
            pf, pl = dx * math.cos(hr) + dy * math.sin(hr), -dx * math.sin(hr) + dy * math.cos(hr)
        else:
            pf, pl = 16.0, 0.0
        pf += self.cal.get("overshoot", 0.0)
        stand = ahead((px, py), hd, -pf)
        stand = (stand[0] + pl * math.sin(math.radians(hd)), stand[1] - pl * math.cos(math.radians(hd)))
        self.r.run(f"goto {stand[0]:.2f} {stand[1]:.2f} {hd:.1f}")
        # the cube shifts in the V on the way and turns end a few degrees off: put the
        # cube itself on the target, measured by the camera, before letting go
        for _ in range(4):
            s, _ = self.observe()
            rpose = s[canplay.ROBOT_TAG]
            if self.held is None:
                break
            h = math.radians(rpose[2])
            dx, dy = self.held[1] - rpose[0], self.held[2] - rpose[1]
            cf, cl = dx * math.cos(h) + dy * math.sin(h), -dx * math.sin(h) + dy * math.cos(h)
            tx, ty = px - rpose[0], py - rpose[1]
            tf, tl = tx * math.cos(h) + ty * math.sin(h), -tx * math.sin(h) + ty * math.cos(h)
            print(f"    held cube {tf - cf:+.1f} cm short, {tl - cl:+.1f} cm left of the target")
            self.seed(s, holding=True)
            if abs(tl - cl) > 1.2:
                # swing the cube sideways onto the target line by a small turn about the robot centre
                turn = math.degrees(math.atan2(tl, tf) - math.atan2(cl, cf))
                self.r.run(f"face {wrap(rpose[2] + turn):.1f}")
            elif abs(tf - cf) > 1.2:
                d = tf - cf
                to = ahead(rpose[:2], rpose[2], d)
                self.r.run(f"leg {to[0]:.2f} {to[1]:.2f} {1 if d > 0 else -1}")
            else:
                break
        rpose = self.look()[canplay.ROBOT_TAG]
        self.release_here(rpose)
        s, now = self.observe()
        near = [c for c in now if c[0] == col and math.dist(c[1:], (px, py)) < 12]
        for c in near:
            ex, ey = c[1] - px, c[2] - py
            print(f"    DIAG cube landed {ex * math.cos(hr) + ey * math.sin(hr):+.1f} along, {-ex * math.sin(hr) + ey * math.cos(hr):+.1f} left of the slot")
        if not near:
            print(f"    {col} cube not found near the drop point")
            return True
        c = min(near, key=lambda c: math.dist(c[1:], (px, py)))
        ex, ey = c[1] - px, c[2] - py
        print(f"    placed {math.hypot(ex, ey):.1f} cm off the slot, {time.time() - t0:.0f} s"
              + ("  (in its garage)" if self.board.home(col, *c[1:]) else ""))
        # robot-frame error at release -> gripper offset, as canplay learns it
        h = math.radians(rpose[2])
        ef = ex * math.cos(h) + ey * math.sin(h)
        if abs(ef) < 6:
            self.cal = dict(self.cal, overshoot=self.cal.get("overshoot", 0.0) + 0.5 * ef, n=self.cal.get("n", 0) + 1)
            canplay.save_cal(self.cal)
            print(f"    drop overshoot correction now {self.cal['overshoot']:+.1f} cm")
        return True

    def release_here(self, rpose=None):
        rpose = rpose or self.look()[canplay.ROBOT_TAG]
        self.r.run(f"grip {RELEASE}", until="GRIP")
        time.sleep(0.6)
        self.r.run("holding 0")
        self.holding = False
        d = next((d for d in (STAGE, 9, 6, 3) if canplay.inside(*ahead(rpose[:2], rpose[2], -d), 0)), 0)
        back = ahead(rpose[:2], rpose[2], -d)
        s = self.look()
        self.seed(s)
        if d:
            self.r.run(f"leg {back[0]:.1f} {back[1]:.1f} -1")
        self.r.run(f"grip {STOW}", until="GRIP")

    def status(self, cubes_now):
        done = sum(1 for c in cubes_now if self.board.home(*c))
        return f"{done}/{len(cubes_now)} cubes home"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", default="zetuv")
    ap.add_argument("--relay")
    ap.add_argument("--host")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--shots", help="directory for an annotated frame after every move")
    ap.add_argument("--moves", type=int, default=30)
    a = ap.parse_args()
    canplay.use_robot(a.robot)
    canplay.CAL = os.path.join(HERE, f"cubeplay_cal_{a.robot}.json")
    if not os.path.exists(canplay.CAL):
        canplay.save_cal({"fwd": 15.2, "left": -1.7, "n": 0})
    canplay.lights_on()
    cam = Camera()

    class NoRobot:
        def run(self, *args, **kw):
            return "CB end ok 0 0 0"

    robot = NoRobot() if a.plan else Robot(a.host, a.robot, a.relay)
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    g = CubeGame(robot, cam, a.shots)
    t0 = time.time()
    try:
        g.shot("start")
        for _ in range(a.moves):
            s, now = g.observe()
            if g.held is not None and not a.plan:
                col = g.held[0]
                print(f"  a {col} cube is in the paddles: gripping it and taking it home")
                robot.run("grip 180", until="GRIP")
                g.holding = True
                g.deliver(col)
                g.shot(f"{col}-home")
                continue
            r = s[canplay.ROBOT_TAG]
            print(f"{time.strftime('%H:%M:%S')} {g.status(now)}")
            mv = g.candidates(r, now) or g.parking(r, now)
            if not mv and not a.plan:
                sep = g.separation(r, now)
                if sep is not None:
                    g.separate(sep, now)
                    g.shot("separate")
                    continue
            if not mv:
                print("  no move left" if all(g.board.home(*c) for c in now) else "  stuck: no clear lane for any cube")
                break
            if a.plan:
                i, hp, slot, why = mv[0]
                print(f"  next: {now[i][0]} ({now[i][1]:.1f},{now[i][2]:.1f}) -> ({slot[0][0]:.1f},{slot[0][1]:.1f}) {why}, pick heading {hp}")
                break
            i, hp, slot, why = mv[0]
            g.do_move(i, hp, slot, why, now)
            g.shot(f"{now[i][0]}-{why.split()[1]}")
    finally:
        if not a.plan:
            try:
                robot.run(f"grip {STOW}", until="GRIP", timeout=5)
            except Exception:
                pass
            robot.close()
    _, now = g.observe()
    g.shot("end")
    print(f"done: {g.status(now)} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
