"""Precisely time RUN:pivot:90 to PIVOT:end, with and without a
mid-flight RUN:abort, to confirm abort actually shortens the job on the
FIXED (executor-inversion) firmware -- not just that PIVOT:end
eventually appears (which happens either way)."""
import sys
import time
import pathlib

REPO = pathlib.Path("/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive")
sys.path.insert(0, str(REPO / "tools"))
import robotlink  # noqa: E402

CAP_DIR = REPO / "captures" / "tigez-executor-20260902"


def run_once(link, note, send_abort_after=None):
    t0 = time.monotonic()
    link.send("RUN:pivot:90")
    if send_abort_after is not None:
        time.sleep(send_abort_after)
        link.send("RUN:abort")
    end_t = None
    for s in link.lines(3.0):
        elapsed = time.monotonic() - t0
        print(f"  [{elapsed:6.3f}s] {s}")
        if s.startswith("PIVOT:end"):
            end_t = elapsed
    print(f"{note}: PIVOT:end at {end_t}")
    return end_t


def main():
    port = sys.argv[1]
    link = robotlink.open_link(port, radio=False)
    try:
        time.sleep(2.5)
        link.p.reset_input_buffer()
        link.send("HELLO")
        for s in link.lines(1.0):
            pass
        time.sleep(0.5)

        print("=== no abort (baseline timing) ===")
        t_no_abort = run_once(link, "no-abort")
        time.sleep(0.5)

        print("=== with abort at 0.3s ===")
        t_abort = run_once(link, "abort@0.3s", send_abort_after=0.3)
    finally:
        link.close()
    print(f"\nSUMMARY: no-abort={t_no_abort}s abort@0.3s={t_abort}s")


if __name__ == "__main__":
    main()
