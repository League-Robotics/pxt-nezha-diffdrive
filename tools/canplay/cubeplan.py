"""Sort the cubes by planning ahead: look once, plan a run of moves, drive them blind, look again.

    uv run python tools/canplay/cubeplan.py --relay magni [--batch N] [--shots DIR]
    uv run python tools/canplay/cubeplan.py --plan              print the plan, do not drive

Each round: one camera look gives the robot pose and every cube; the planner
simulates up to N moves (route legs, pick, carry, drop), updating where each
cube and the robot will be; the robot is then told its pose once and drives
the whole batch on its own odometry. The next look shows how far reality
drifted from the plan, and the rest is replanned from there.
"""
import argparse, json, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import canplay  # noqa: E402
import cubeplay  # noqa: E402  (patches canplay's router and clearances for cubes)
from cubeplay import CubeGame, ahead, STAGE, RELEASE, STOW, V_OPEN, V_NARROW, NARROW_GRIP  # noqa: E402
from canplay import Camera, Robot, stage_pose, wrap  # noqa: E402

BACKOUT = 15.0            # canbot's pickAt backs straight out this far


class LayoutBoard:
    """Targets are numbered circles holding a given colour (a recorded layout), not the garages."""
    TOL = 3.5               # the drawn circles are 3.2 cm in radius

    def __init__(self, path):
        lay = json.load(open(path))
        m = canplay.Mat(lay.get("mat", "bb-obstacle"))
        centre = {c["n"]: tuple(float(v) for v in m.px_to_playfield(*c["px"])) for c in m.features["circles"]}
        self.slots = {}
        for n, col in sorted(lay["circles"].items(), key=lambda kv: -centre[int(kv[0])][0]):
            self.slots.setdefault(col, []).append((centre[int(n)], 0.0))

    def home(self, col, x, y):
        return any(math.dist(p, (x, y)) < self.TOL for p, _ in self.slots.get(col, []))

    def in_any(self, x, y):
        return False


def back_from(pose, d):
    """The pose `d` cm straight back, shortened to stay inside the fence (as the robot does)."""
    for dd in (d, 12, 9, 6, 3):
        p = ahead(pose[:2], pose[2], -dd)
        if canplay.inside(*p, 0):
            return (*p, pose[2])
    return pose


class Planner:
    def __init__(self, game, layout=False):
        self.g = game
        self.layout = layout

    def route(self, pose, goal, hg, obstacles, holding):
        return canplay.Router(obstacles, self.g.cal, holding).route(pose[:2], pose[2], goal, hg)

    def plan(self, pose, cubes_now, batch):
        """[(description, [RUN commands]), ...] and the predicted cubes after them."""
        g, cal = self.g, self.g.cal
        cubes_now = list(cubes_now)
        steps = []
        backed = False
        F = canplay.FENCE
        if not canplay.inside(*pose[:2], 0):
            # straight back into the middle lane first
            ex = min(max(pose[0], F[0] + 3), F[1] - 3)
            ey = min(max(pose[1], F[2] + 3), F[3] - 3)
            steps.append((f"into the middle lane at ({ex:.1f},{ey:.1f})", [f"leg {ex:.1f} {ey:.1f} 1"], None))
            pose = (ex, ey, math.degrees(math.atan2(ey - pose[1], ex - pose[0])))
        for _ in range(4 * batch + 12):
            if sum(1 for st in steps if st[2]) >= batch:
                break
            def options():
                middle = [] if self.layout else g.clear_middle(pose, cubes_now)
                return middle or g.candidates(pose, cubes_now) or g.parking(pose, cubes_now)
            g.v_open = V_OPEN
            mv = options()
            if not mv:
                # a cube with neighbours too close for the fully open V: open the paddles only partway
                g.v_open = V_NARROW
                mv = options()
            if not mv:
                sep = g.separation(pose, cubes_now)
                if sep is None:
                    print(f"      (no candidate move from ({pose[0]:.1f},{pose[1]:.1f}))")
                    break
                _, i, start, end, h = sep
                legs = self.route(pose, start, h, [c[1:] for c in cubes_now], False)
                if legs is None:
                    back = back_from(pose, 12)
                    crowded = any(math.dist(c[1:], pose[:2]) < 22 for c in cubes_now)
                    if crowded and not backed and math.dist(back[:2], pose[:2]) > 2:
                        # too close to see a way round: back off and plan again from there
                        steps.append(("back off the cubes", [f"leg {back[0]:.1f} {back[1]:.1f} -1"], None))
                        pose = back
                        backed = True
                        continue
                    print("      (no route to push two touching cubes apart)")
                    break
                col, x, y = cubes_now[i]
                cmds = [f"leg {lx:.1f} {ly:.1f} {d}" for lx, ly, d in legs]
                cmds += [f"face {h:.1f}", f"grip {STOW}", f"leg {end[0]:.1f} {end[1]:.1f} 1", f"leg {start[0]:.1f} {start[1]:.1f} -1"]
                moved = ahead((x, y), h, cubeplay.PUSH)
                steps.append((f"push {col} ({x:.1f},{y:.1f}) off its neighbour", cmds, None))
                cubes_now = cubes_now[:i] + [(col, *moved)] + cubes_now[i + 1:]
                pose = (*start, h)
                continue
            i, hp, slot, why = mv[0]
            col, x, y = cubes_now[i]
            others = [c[1:] for j, c in enumerate(cubes_now) if j != i]
            # pick: try headings until a route to the run-in exists
            prefer = math.degrees(math.atan2(y - pose[1], x - pose[0]))
            heads = [hp] + [h for h in sorted(range(0, 360, 15), key=lambda h: abs(wrap(h - prefer)))
                            if h != hp and g.pick_ok((x, y), h, others)]
            legs1 = None
            for hp in heads[:6]:
                stage1 = stage_pose(x, y, hp, cal)
                # a run-in shortened to fit the lane leaves the tips over the target itself
                target = [(x, y)] if math.dist(stage1, (x, y)) >= cal["fwd"] + 10 else []
                # cubes touching the target are the pick lane's business, not the route's
                apart = [o for o in others if math.dist(o, (x, y)) > 5]
                legs1 = self.route(pose, stage1, hp, apart + target, False)
                if legs1 is not None:
                    break
            if legs1 is None:
                print(f"      (no route to pick {col} at ({x:.1f},{y:.1f}); tried headings {heads[:6]} from ({pose[0]:.1f},{pose[1]:.1f}) {pose[2]:.0f})")
                g.stuck[cubeplay.spot_key(cubes_now[i])] = 99
                continue
            stand1 = ahead((x, y), hp, -cal["fwd"])
            stand1 = (stand1[0] + cal["left"] * math.sin(math.radians(hp)), stand1[1] - cal["left"] * math.cos(math.radians(hp)))
            after_pick = back_from((*stand1, hp), BACKOUT)
            # drop: the slot the move chose, re-checked without this cube
            rest = cubes_now[:i] + cubes_now[i + 1:]
            others2 = [c[1:] for c in rest]
            if why.endswith("edge"):
                options = [slot]
            else:
                # every free slot and entry angle with a clear lane, deepest first
                options = []
                for p, h in g.board.slots[col]:
                    if any(math.dist(p, o) < 4 for o in others2):
                        continue
                    options += [(p, wrap(h + dh)) for dh in (0, 45, -45, 90, -90, 135, -135, 180)
                                if g.place_ok(p, h + dh, others2)]
            legs2 = None
            for (px, py), hd in options:
                stage2 = stage_pose(px, py, hd, cal)
                legs2 = self.route(after_pick, stage2, hd, others2, True)
                if legs2 is not None:
                    break
            if legs2 is None:
                print(f"      (no route to any {col} drop from ({after_pick[0]:.1f},{after_pick[1]:.1f}))")
                g.stuck[cubeplay.spot_key(cubes_now[i])] = 99
                continue
            stand2 = ahead((px, py), hd, -cal["fwd"])
            stand2 = (stand2[0] + cal["left"] * math.sin(math.radians(hd)), stand2[1] - cal["left"] * math.cos(math.radians(hd)))
            after_drop = back_from((*stand2, hd), STAGE)
            cmds = [f"leg {lx:.1f} {ly:.1f} {d}" for lx, ly, d in legs1]
            g.v_open = V_OPEN
            if g.pick_ok((x, y), hp, others):
                cmds += [f"face {hp:.1f}", "holding 0", f"pickat {x:.2f} {y:.2f} {hp}", "holding 1"]
            else:
                # narrow pick: run in with the paddles only partway open, close, back straight out
                cmds += [f"face {hp:.1f}", "holding 0", f"grip {NARROW_GRIP}",
                         f"goto {stand1[0]:.2f} {stand1[1]:.2f} {hp}", "grip 180", "holding 1",
                         f"leg {after_pick[0]:.1f} {after_pick[1]:.1f} -1"]
            cmds += [f"leg {lx:.1f} {ly:.1f} {d}" for lx, ly, d in legs2]
            cmds += [f"face {hd:.1f}", f"goto {stand2[0]:.2f} {stand2[1]:.2f} {hd:.1f}", f"grip {RELEASE}", "holding 0"]
            if math.dist(after_drop[:2], stand2) > 1:
                cmds.append(f"leg {after_drop[0]:.1f} {after_drop[1]:.1f} -1")
            cmds += [f"grip {STOW}"]
            steps.append((f"{col} ({x:.1f},{y:.1f}) -> ({px:.1f},{py:.1f}) [{why}]", cmds, (col, px, py)))
            cubes_now = rest + [(col, px, py)]
            pose = after_drop
        return steps, cubes_now


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", default="zetuv")
    ap.add_argument("--relay")
    ap.add_argument("--host")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--batch", type=int, default=3, help="moves to drive blind between looks")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--shots")
    ap.add_argument("--quiet", action="store_true", help="no start and end tunes (for a game run a move at a time)")
    ap.add_argument("--matcam", action="store_true", help="map the camera with tools/canplay/matcam.json (the mat's own circles), not the daemon's playfield calibration")
    ap.add_argument("--layout", help="a recorded layout (tools/canplay/layouts/*.json): put the cubes back on those circles")
    a = ap.parse_args()
    canplay.use_robot(a.robot)
    canplay.CAL = os.path.join(HERE, f"cubeplay_cal_{a.robot}.json")
    canplay.lights_on()
    if a.matcam:
        import cubes, matcam
        cam = matcam.MatSeer([a.robot])
        cubes.use_matcam(cam.mc)
    else:
        cam = Camera()

    class NoRobot:
        def run(self, *args, **kw):
            return "CB end ok 0 0 0"

        def close(self):
            pass

    robot = NoRobot() if a.plan else Robot(a.host, a.robot, a.relay)
    if a.shots:
        os.makedirs(a.shots, exist_ok=True)
    g = CubeGame(robot, cam, a.shots)
    if a.layout:
        g.board = LayoutBoard(a.layout)
    p = Planner(g, bool(a.layout))
    t0 = time.time()
    looks = 0
    if not a.plan and not a.quiet:
        robot.run("tune 1")
    try:
        for rnd in range(a.rounds):
            s, now = g.observe()             # eyes open
            looks += 1
            if g.held is not None and not a.plan:
                print(f"  letting go of the {g.held[0]} cube in the paddles")
                g.holding = True
                g.release_here()
                s, now = g.observe()
            g.shot(f"look-{rnd + 1}")
            pose = s[canplay.ROBOT_TAG]
            print(f"{time.strftime('%H:%M:%S')} look {looks}: {g.status(now)}; robot ({pose[0]:.1f},{pose[1]:.1f}) {pose[2]:.0f}")
            if rnd and predicted:
                for col, px, py in predicted:
                    near = min((c for c in now if c[0] == col), key=lambda c: math.dist(c[1:], (px, py)), default=None)
                    if near is not None and math.dist(near[1:], (px, py)) < 12:
                        print(f"    planned {col} at ({px:.1f},{py:.1f}): found {math.dist(near[1:], (px, py)):.1f} cm away"
                              + ("  (home)" if g.board.home(*near) else ""))
                    else:
                        print(f"    planned {col} at ({px:.1f},{py:.1f}): not found there")
            g.stuck = {}
            steps, after = p.plan(pose, now, a.batch)
            if not steps:
                print("  nothing left to move" if all(g.board.home(*c) for c in now) else "  no plannable move")
                break
            print(f"  plan: {len(steps)} move(s), {sum(len(c) for _, c, _ in steps)} commands")
            for desc, cmds, _ in steps:
                print(f"    {desc}  ({len(cmds)} commands)")
            if a.plan:
                break
            # eyes closed: one pose fix, then the whole batch on odometry
            robot.run(f"setpose {pose[0]:.2f} {pose[1]:.2f} {pose[2]:.2f}")
            # the planner keeps clear of the cubes; canbot's own can-sized check would only fight it
            robot.run("obsclear", until="CB obs")
            predicted = []
            failed = False
            for desc, cmds, dest in steps:
                print(f"  {time.strftime('%H:%M:%S')} {desc}")
                for c in cmds:
                    if c.startswith("grip"):
                        robot.run(c, until="GRIP")
                    elif c.startswith("obs"):
                        robot.run(c, until="CB obs")
                    else:
                        out = robot.run(c)
                        if "fail" in out:
                            print(f"    {c} -> {out}: the world is not as planned; opening eyes")
                            failed = True
                            break
                if failed:
                    robot.run(f"grip {RELEASE}", until="GRIP")
                    robot.run("holding 0")
                    break
                if dest:
                    predicted.append(dest)
                    robot.run("tune 0")
    finally:
        try:
            robot.run(f"grip {STOW}", until="GRIP", timeout=5)
            if not a.quiet:
                robot.run("tune 2", timeout=5)
        except Exception:
            pass
        robot.close()
    _, now = g.observe()
    g.shot("end")
    print(f"done: {g.status(now)} in {time.time() - t0:.0f} s with {looks} looks")


if __name__ == "__main__":
    main()
