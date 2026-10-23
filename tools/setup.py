"""Put cans on chosen circles of the bb-obstacle mat with zetuv, in as few moves as it can.

    uv run python tools/setup.py 13:1 63:5 64:9    these cans (by tag) on these circles
    uv run python tools/setup.py 1 5 9             any cans on these circles
    uv run python tools/setup.py --plan 1 5 9      print the plan, do not move

Cans that block a goal, or that would be swept by the arms, are parked on a
free spot first. The camera is read before every move and the plan redone.
"""
import argparse, itertools, math, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canplay import (FENCE, FREE, Camera, Game, Robot, approach_heading, lights_on, use_robot)  # noqa: E402

GOAL_TOL = 1.5            # a can this close to its circle counts as placed
MAT = (-61.0, 59.0, -25.4, 34.2)


def on_mat(p):
    return MAT[0] <= p[0] <= MAT[1] and MAT[2] <= p[1] <= MAT[3]
PARK_CLEAR = 16.0         # parking spots keep this far from every goal circle


def parse(goals):
    out = []
    for g in goals:
        if ":" in g:
            t, c = g.split(":")
            out.append((int(t), int(c)))
        else:
            out.append((None, int(g)))
    return out


class Planner:
    def __init__(self, circles, grip):
        self.circles, self.grip = circles, grip
        xs = range(int(FENCE[0]) + 10, int(FENCE[1]) + 10, 6)
        ys = range(int(FENCE[2]) - 8, int(FENCE[3]) + 12, 6)
        self.spots = [(float(x), float(y)) for x in xs for y in ys]

    def free(self, pos, pt, skip):
        return all(math.dist(p, pt) >= FREE for k, p in pos.items() if k != skip)

    def feasible(self, pos, can, pt):
        others = [p for k, p in pos.items() if k != can]
        return (self.free(pos, pt, can)
                and approach_heading(*pos[can], others, self.grip) is not None
                and approach_heading(*pt, others, self.grip) is not None)

    def assign(self, pos, goals):
        """Fill anonymous goals with the cans that make the fewest, then shortest, moves."""
        fixed = {t: c for t, c in goals if t is not None}
        open_circles = [c for t, c in goals if t is None]
        spare = [k for k in pos if k not in fixed]
        if len(spare) < len(open_circles):
            raise SystemExit(f"need {len(open_circles)} spare cans, see {len(spare)}")
        best = None
        for combo in itertools.permutations(spare, len(open_circles)):
            moves = sum(math.dist(pos[k], self.circles[c]) > GOAL_TOL for k, c in zip(combo, open_circles))
            length = sum(math.dist(pos[k], self.circles[c]) for k, c in zip(combo, open_circles))
            if best is None or (moves, length) < best[0]:
                best = ((moves, length), dict(zip(combo, open_circles)))
        return {**fixed, **best[1]}

    def park_spot(self, pos, can, goal_pts):
        cands = [p for p in self.spots if all(math.dist(p, g) >= PARK_CLEAR for g in goal_pts)]
        cands.sort(key=lambda p: math.dist(p, pos[can]))
        for p in cands:
            if self.feasible(pos, can, p):
                return p
        return None

    def moves(self, pos, target):
        """Candidate next moves: straight home first, then parking a can that crowds a goal."""
        pending = [k for k in target if math.dist(pos[k], self.circles[target[k]]) > GOAL_TOL]
        out = []
        for k in sorted(pending, key=lambda k: math.dist(pos[k], self.circles[target[k]])):
            pt = self.circles[target[k]]
            if self.feasible(pos, k, pt):
                out.append((k, pt, f"to circle {target[k]}"))
        goal_pts = [self.circles[c] for c in target.values()]
        movable = [k for k in pos if k not in target or k in pending]
        movable.sort(key=lambda k: min(math.dist(pos[k], self.circles[target[p]]) for p in pending) if pending else 0)
        for k in movable[:3]:
            spot = self.park_spot(pos, k, goal_pts)
            if spot is not None and math.dist(spot, pos[k]) > FREE:
                out.append((k, spot, "parked"))
        return pending, out

    def plan(self, pos, target):
        """Fewest moves [(can, (x, y), why)] that bring every can in `target` home."""
        def dfs(pos, depth, parked):
            pending, cands = self.moves(pos, target)
            if not pending:
                return []
            if depth == 0:
                return None
            for k, pt, why in cands:
                if why == "parked" and k in parked:
                    continue
                nxt = dict(pos)
                nxt[k] = pt
                rest = dfs(nxt, depth - 1, parked | {k} if why == "parked" else parked)
                if rest is not None:
                    return [(k, pt, why)] + rest
            return None

        n = sum(math.dist(pos[k], self.circles[c]) > GOAL_TOL for k, c in target.items())
        for depth in range(n, n + 4):
            p = dfs(pos, depth, frozenset())
            if p is not None:
                return p
        return None

    def plan_or_clear(self, pos, target):
        p = self.plan(pos, target)
        if p is not None:
            return p
        # everything not already home goes to parking first, then home
        pos = dict(pos)
        steps = []
        goal_pts = [self.circles[c] for c in target.values()]
        for k in sorted(pos, key=lambda k: -min(math.dist(pos[k], g) for g in goal_pts)):
            if k in target and math.dist(pos[k], self.circles[target[k]]) <= GOAL_TOL:
                continue
            spot = self.park_spot(pos, k, goal_pts)
            if spot is None:
                return None
            steps.append((k, spot, "parked"))
            pos[k] = spot
        rest = self.plan(pos, target)
        return None if rest is None else steps + rest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("goals", nargs="+", help="circle, or tag:circle")
    ap.add_argument("--plan", action="store_true", help="print the plan and stop")
    ap.add_argument("--no-home", action="store_true")
    ap.add_argument("--host", default=os.environ.get("ZHOST"), help="talk over USB on this Pi instead of WiFi")
    ap.add_argument("--robot", default="zetuv")
    ap.add_argument("--fast", action="store_true", help="one fetch RUN per move; the robot carries the can blind")
    a = ap.parse_args()
    goals = parse(a.goals)
    use_robot(a.robot)
    lights_on()
    cam = Camera()
    robot = None if a.plan else Robot(a.host, a.robot)
    if robot and not robot.motors_ok():
        robot.close()
        sys.exit("motor battery is flat (STATUS connL/connR=0): charge or swap it, then run again")

    class NoRobot:
        def run(self, *args, **kw):
            return "CB end ok 0 0 0"

    g = Game(robot or NoRobot(), cam)
    g.fast = a.fast
    planner = Planner(g.circles, g.cal)
    s = g.look()
    pos = {k: p for k, p in g.cans(s).items() if on_mat(p)}
    gone = [t for t, _ in goals if t is not None and t not in pos]
    if gone:
        sys.exit(f"can(s) {gone} not on the field")
    target = planner.assign(pos, goals)
    steps = planner.plan_or_clear(pos, target)
    if steps is None:
        sys.exit("no plan: the cans cannot be moved without the arms touching a neighbour")
    print(f"plan: {len(steps)} move(s) for {', '.join(f'can {k} -> {c}' for k, c in target.items())}")
    for k, (x, y), why in steps:
        print(f"  can {k} -> ({x:.1f},{y:.1f}) {why}")
    if a.plan:
        return
    t0 = time.time()
    robot.run("tune 1")
    time.sleep(0.8)
    try:
        for _ in range(3 * len(steps) + 4):
            s = g.look()
            pos = {k: p for k, p in g.cans(s).items() if on_mat(p)}
            missing = [k for k in target if k not in pos]
            if missing:
                raise RuntimeError(f"can(s) {missing} not seen")
            steps = planner.plan_or_clear(pos, target)
            if steps is None:
                raise RuntimeError("no plan from here")
            if not steps:
                break
            k, (x, y), why = steps[0]
            g.move_can(k, x, y, why)
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
    s = g.look()
    for k, c in target.items():
        if k in s:
            cx, cy = g.circles[c]
            print(f"  can {k} on circle {c}: {math.dist(s[k][:2], (cx, cy)):.2f} cm from centre")
    print(f"done in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
