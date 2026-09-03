"""Confirm telemetry keeps flowing (via the nested service hook) while a
RUN job is dispatching, and that the link does not hang -- the
cleartext-RUN-hangs-the-link-under-active-telemetry class of defect
sprint 027 targeted, re-checked here under the executor inversion."""
import sys
import time
import pathlib

REPO = pathlib.Path("/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive")
sys.path.insert(0, str(REPO / "tools"))
import robotlink  # noqa: E402


def main():
    port = sys.argv[1]
    link = robotlink.open_link(port, radio=False)
    try:
        time.sleep(2.5)
        link.p.reset_input_buffer()
        link.send("HELLO")
        for s in link.lines(1.0):
            pass
        time.sleep(0.3)

        link.send("TLM POSE")
        for s in link.lines(1.0):
            print(f"tlm-sub< {s}")

        print(">>> RUN:pivot:90 while TLM POSE subscribed")
        t0 = time.monotonic()
        link.send("RUN:pivot:90")
        t_count = 0
        for s in link.lines(3.0):
            elapsed = time.monotonic() - t0
            if s.startswith("t "):
                t_count += 1
                if t_count <= 3 or s.startswith == "PIVOT:end":
                    print(f"  [{elapsed:5.2f}s] {s[:60]}")
            else:
                print(f"  [{elapsed:5.2f}s] {s}")
        print(f"telemetry frames seen during the job: {t_count}")

        link.send("TLM OFF")
        for s in link.lines(1.0):
            print(f"tlm-off< {s}")
    finally:
        link.close()


if __name__ == "__main__":
    main()
