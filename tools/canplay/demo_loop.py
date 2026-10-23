"""Keep a robot busy for a demo: run setup.py round after round, cycling the cans
through a list of layouts, until stopped with Ctrl-C.

    uv run python tools/canplay/demo_loop.py --robot zetuv --relay magni
    uv run python tools/canplay/demo_loop.py --robot tigez --host jtl@192.168.4.52 \\
        --layout 13:4,64:2,63:6 --layout 13:2,64:6,63:4

A round that fails is reported and the next one re-plans from wherever the
camera sees the cans.
"""
import argparse, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUTS = ["13:6,64:2,63:4", "13:2,64:4,63:6", "13:4,64:6,63:2"]
NOISE = ("fork_posix", "ev_poll", "Traceback", "File ", "~~~", "^^^")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", default="zetuv")
    ap.add_argument("--relay", help="radio through the relay on this farm Pi")
    ap.add_argument("--host", help="USB on this Pi")
    ap.add_argument("--layout", action="append", help="tag:circle,... (repeatable); default cycles cans 13, 63, 64 over 2, 4, 6")
    a = ap.parse_args()
    link = ["--relay", a.relay] if a.relay else ["--host", a.host] if a.host else []
    base = [sys.executable, os.path.join(HERE, "setup.py"), "--robot", a.robot, "--no-home"] + link
    layouts = a.layout or LAYOUTS
    n = 0
    while True:
        goal = layouts[n % len(layouts)].split(",")
        print(f"=== round {n + 1}: {' '.join(goal)}", flush=True)
        r = subprocess.run(base + goal, capture_output=True, text=True)
        for line in (r.stdout + r.stderr).splitlines():
            if not any(k in line for k in NOISE):
                print("  " + line, flush=True)
        n += 1
        time.sleep(2)


if __name__ == "__main__":
    main()
