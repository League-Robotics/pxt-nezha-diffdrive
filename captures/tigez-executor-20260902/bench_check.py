"""Bench acceptance checks for sprint 028 ticket 003 (executor inversion),
run against tigez over USB. In-place motion ONLY (pivots), per the
dispatcher's explicit bench-safety instruction -- tigez is tethered on a
desk, off the playfield.

Usage:
    uv run --with pyserial python bench_check.py <port> <mode> <label>

mode: 'baseline' or 'fixed'
label: free text tag for the transcript filename
"""
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[0]))
# tools/robotlink.py lives in the repo; import it directly by path.
REPO = pathlib.Path("/Volumes/Proj/proj/RobotProjects/pxt-nezha-diffdrive")
sys.path.insert(0, str(REPO / "tools"))
import robotlink  # noqa: E402

CAP_DIR = REPO / "captures" / "tigez-executor-20260902"
CAP_DIR.mkdir(parents=True, exist_ok=True)


def parse_kv(line):
    out = {}
    for tok in line.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


class Transcript:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "w")

    def note(self, text):
        stamp = time.strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        print(line)
        self.f.write(line + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def drain(link, t, seconds, note_prefix=""):
    lines = []
    for s in link.lines(seconds):
        t.note(f"{note_prefix}{s}")
        lines.append(s)
    return lines


def get_status(link, t):
    time.sleep(0.15)
    link.send("STATUS")
    lines = drain(link, t, 1.0, "  status< ")
    time.sleep(0.15)
    for s in lines:
        if "status" in s and "ready" in s:
            return parse_kv(s)
    return None


def get_pong_ms(link, t):
    """PING's `pong <ms>` reply -- MEASURED clean and reliable over this
    link across 6+ consecutive reads, unlike STATUS's much longer line
    (see notes.md) -- so this is the primary reset detector: `ms` is the
    robot's own uptime clock and drops back near 0 on a reboot."""
    time.sleep(0.15)
    link.send("PING")
    lines = drain(link, t, 1.0, "  ping< ")
    time.sleep(0.15)
    for s in lines:
        if s.startswith("pong"):
            digits = "".join(c for c in s if c.isdigit())
            if digits:
                return int(digits)
    return None


def step_a_pivot_alone(link, t):
    t.note("=== STEP A: RUN:pivot:90 alone -- does the board reset? ===")
    before_ms = get_pong_ms(link, t)
    before = get_status(link, t)
    t.note(f"before: pong_ms={before_ms} status={before}")
    link.send("RUN:pivot:90")
    lines = drain(link, t, 3.0, "  a< ")
    reset_banner = [s for s in lines if ("NEZHA2" in s and "robot" in s)]
    after_ms = get_pong_ms(link, t)
    after = get_status(link, t)
    t.note(f"after: pong_ms={after_ms} status={after}")
    reset = bool(reset_banner)
    if before_ms is not None and after_ms is not None and after_ms < before_ms:
        reset = True
    t.note(f"STEP A RESULT: reset_observed={reset} banner_lines={reset_banner} "
           f"pong_ms {before_ms}->{after_ms}")
    return reset


def step_b_wire_move_mid_job(link, t):
    t.note("=== STEP B: RUN:pivot:90 then wire MOVE_X pivot mid-job ===")
    before_ms = get_pong_ms(link, t)
    t.note(f"before: pong_ms={before_ms}")
    link.send("RUN:pivot:-90")  # opposite sign vs step A, net toward zero
    time.sleep(0.35)
    link.send("MOVE_X 0 1571 100 3000 #1")
    lines = drain(link, t, 3.0, "  b< ")
    reset_banner = [s for s in lines if ("NEZHA2" in s and "robot" in s)]
    reply_lines = [s for s in lines if "ack" in s or "err" in s or "#1" in s]
    after_ms = get_pong_ms(link, t)
    reset = bool(reset_banner) or (
        before_ms is not None and after_ms is not None and after_ms < before_ms)
    t.note(f"after: pong_ms={after_ms}")
    t.note(f"STEP B RESULT: reset={reset} banner={reset_banner} "
           f"move_x_replies={reply_lines}")
    return reset, reply_lines


def step_c_abort_mid_job(link, t):
    t.note("=== STEP C: RUN:pivot:90 then RUN:abort mid-job ===")
    before_ms = get_pong_ms(link, t)
    t.note(f"before: pong_ms={before_ms}")
    link.send("RUN:pivot:90")
    time.sleep(0.3)
    link.send("RUN:abort")
    lines = drain(link, t, 2.0, "  c< ")
    reset_banner = [s for s in lines if ("NEZHA2" in s and "robot" in s)]
    after_ms = get_pong_ms(link, t)
    reset = bool(reset_banner) or (
        before_ms is not None and after_ms is not None and after_ms < before_ms)
    t.note(f"after: pong_ms={after_ms}")
    t.note(f"STEP C RESULT: reset={reset} banner={reset_banner}")
    return reset


def step_d_soak(link, t, n=12):
    t.note(f"=== STEP D (fixed only): {n} back-to-back RUN pivot jobs ===")
    before_ms = get_pong_ms(link, t)
    t.note(f"before: pong_ms={before_ms}")
    faults = []
    for i in range(n):
        deg = 30 if i % 2 == 0 else -30
        link.send(f"RUN:pivot:{deg}")
        lines = drain(link, t, 1.6, f"  d{i}< ")
        if any(("NEZHA2" in s and "robot" in s) for s in lines):
            faults.append(i)
        ms = get_pong_ms(link, t)
        t.note(f"  after job {i} (deg={deg}): pong_ms={ms}")
        if ms is None:
            faults.append(i)
    after_ms = get_pong_ms(link, t)
    after_status = get_status(link, t)
    t.note(f"after: pong_ms={after_ms} status={after_status}")
    t.note(f"STEP D RESULT: faults_at={faults}")
    return faults


def step_e_wire_refused_while_job_running(link, t):
    t.note("=== STEP E (fixed only): wire MOVE_X refused while job runs ===")
    link.send("RUN:pivot:-30")
    time.sleep(0.25)
    link.send("MOVE_X 0 1571 100 3000 #2")
    lines = drain(link, t, 2.5, "  e< ")
    t.note(f"STEP E RESULT lines: {lines}")
    return lines


def main():
    port, mode, label = sys.argv[1], sys.argv[2], sys.argv[3]
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = CAP_DIR / f"{mode}-{label}-{ts}.txt"
    t = Transcript(out)
    t.note(f"connecting to {port} mode={mode}")
    link = robotlink.open_link(port, radio=False)
    try:
        # MEASURED: the CDC-ACM link is corruption-prone for the first
        # ~2 s after the DTR-triggered reset open_link() performs
        # (garbled STATUS/HELLO text observed within that window; clean
        # once settled -- see notes.md). Extra settle time before any
        # real traffic.
        time.sleep(2.5)
        link.p.reset_input_buffer()
        link.send("HELLO")
        drain(link, t, 1.0, "  hello< ")
        time.sleep(0.3)

        if mode == "baseline":
            step_a_pivot_alone(link, t)
            # re-sync in case step A reset the board
            link.hello()
            drain(link, t, 0.5, "  resync< ")
            step_b_wire_move_mid_job(link, t)
            link.hello()
            drain(link, t, 0.5, "  resync< ")
            step_c_abort_mid_job(link, t)
        else:
            step_a_pivot_alone(link, t)
            step_b_wire_move_mid_job(link, t)
            step_c_abort_mid_job(link, t)
            step_d_soak(link, t, n=12)
            step_e_wire_refused_while_job_running(link, t)
    finally:
        # ALWAYS release the port -- a process that dies with it still
        # open has, empirically this session, left the CDC-ACM node
        # wedged for the next open (corrupted reads, then ENXIO) until
        # it settles on its own a few seconds later. Never skip this.
        link.close()

    t.note("done")
    t.close()
    print(f"transcript: {out}")


if __name__ == "__main__":
    main()
