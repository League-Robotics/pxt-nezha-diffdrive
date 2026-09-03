"""Isolated, careful re-test of "wire MOVE_X mid RUN job" on BASELINE
firmware, with a long post-send observation window and no HELLO-based
resync (which can silently swallow a corrupted banner line) -- to
confirm or refute whether this specific sequence triggers a delayed
reset, as first suggested by a pong_ms discontinuity between the
original Step B and Step C runs.
"""
import sys
import time
import pathlib

REPO = pathlib.Path("/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive")
sys.path.insert(0, str(REPO / "tools"))
import robotlink  # noqa: E402

CAP_DIR = REPO / "captures" / "tigez-executor-20260902"
CAP_DIR.mkdir(parents=True, exist_ok=True)


def main():
    port = sys.argv[1]
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = CAP_DIR / f"baseline-stepB-isolated-{ts}.txt"
    f = open(out, "w")

    def note(text):
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        print(line)
        f.write(line + "\n")
        f.flush()

    link = robotlink.open_link(port, radio=False)
    try:
        time.sleep(2.5)
        link.p.reset_input_buffer()
        link.send("HELLO")
        for s in link.lines(1.0):
            note(f"hello< {s}")
        time.sleep(0.5)

        link.send("PING")
        for s in link.lines(1.0):
            note(f"ping-before< {s}")
        time.sleep(0.3)

        note(">>> sending RUN:pivot:-90")
        link.send("RUN:pivot:-90")
        time.sleep(0.35)
        note(">>> sending MOVE_X 0 1571 100 3000 #1 (mid-job)")
        link.send("MOVE_X 0 1571 100 3000 #1")

        note(">>> observing for 8 s ...")
        end = time.time() + 8.0
        while time.time() < end:
            for s in link.lines(0.5):
                note(f"obs< {s}")

        link.send("PING")
        for s in link.lines(1.0):
            note(f"ping-after< {s}")
    finally:
        link.close()
    note("done")
    f.close()
    print(f"transcript: {out}")


if __name__ == "__main__":
    main()
