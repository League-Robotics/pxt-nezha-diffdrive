#!/usr/bin/env python3
"""50 cm straight moves, scored per wheel from each wheel's own encoder.

Ported from nezha-esp32/tools/mb50.py (the one-wheel micro:bit bench rig):
the Wire class, run_line and the STATUS parsing keep their shape, but the
link is now `robotlink.open_link()`, so the same tool drives a robot on
local USB (`--port`) or through the loki serial-bridge tunnel
(`--wifi 127.0.0.1`).

  tools/mb50.py --wifi 127.0.0.1 --mode position --tag position
  tools/mb50.py --wifi 127.0.0.1 --mode kernel --tag kernel \
      --set "v_floor 40" --set "decel 1000" --set "stop_distance 0.3"

`--mode position` sets `position_mode 1` (the motor's own position loop
runs MOVE_X) and samples STATUS `posmove` once mid-move to confirm the
built-in path, then once after the move (it must read 0). `--mode kernel`
sets `position_mode 0` (the kernel's own profile) and records `posmove`
the same way, as the comparison set.

Per-wheel truth: the FULL telemetry frame carries `posl`/`posr`, the raw
wheel position counts (1 count = 0.1 degree of shaft, so
mm = count * pi * wheel_diameter / 3600, wheel_diameter read back with
GET). Each trial reads both counters at rest before and after the move.
The velocity columns are integrated over the move as a cross-check, and
x/y odometry as a third. All three are ENCODER truth, not floor truth.

Writes <out>/<tag>.csv (one row per trial) and <out>/<tag>_<cruise>_<n>.csv
(the telemetry frames: t_ms, posl, posr, vl, vr, x). "Percent" of the old
rig protocol is cruise mm/s here: 75 / 150 / 250 of v_max 250.
"""
import argparse
import csv
import math
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tlm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "captures", "zuvat-position-2026-10-27", "fiftycm")
MODES = {"position": 1, "kernel": 0}
REST_MMPS = 2          # |v| at or under this on both wheels counts as at rest
REST_FRAMES = 3        # consecutive rest frames that end a move


def parse_status(line):
    """`status k=v ...` -> {k: v} (strings), or None for any other line."""
    if not line.startswith("status "):
        return None
    return dict(kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)


def posmove_of(status):
    """STATUS posmove flag as 0/1, or None when the field is absent."""
    if status is None or "posmove" not in status:
        return None
    return int(status["posmove"])


def parse_get(line):
    """`get <name> <value>` -> (name, float), or None."""
    parts = line.split()
    if len(parts) == 3 and parts[0] == "get":
        try:
            return parts[1], float(parts[2])
        except ValueError:
            return None
    return None


def mm_per_count(wheel_diameter):
    """One count is 0.1 degree of shaft: pi * D / 3600 [mm]."""
    return wheel_diameter * math.pi / 3600.0


def wheel_errors(before, after, mm, per_count):
    """Signed per-wheel error [mm] along the commanded direction.

    `before`/`after` are (posl, posr) at rest. Travel is measured in the
    direction of `mm` so a reverse leg that goes 499.6 mm reads -0.4.
    Returns (travel_l, travel_r, err_l, err_r)."""
    sign = 1.0 if mm >= 0 else -1.0
    tl = (after[0] - before[0]) * per_count * sign
    tr = (after[1] - before[1]) * per_count * sign
    return tl, tr, tl - abs(mm), tr - abs(mm)


def integrate_wheels(frames):
    """Trapezoid integral of vl/vr [mm/s] over device `now` [ms] ->
    (left_mm, right_mm), signed. `frames` are dicts with now/vl/vr."""
    left = right = 0.0
    for a, b in zip(frames, frames[1:]):
        dt = (b["now"] - a["now"]) / 1000.0
        left += 0.5 * (a["vl"] + b["vl"]) * dt
        right += 0.5 * (a["vr"] + b["vr"]) * dt
    return left, right


def summarize(rows):
    """Per (cruise, direction, wheel): n, mean, sd, worst, mean time.

    `rows` are trial dicts with cruise, mm, err_l_mm, err_r_mm, ms_host.
    Returns a list of dicts in cruise, direction, wheel order."""
    out = []
    for cruise in sorted({r["cruise"] for r in rows}):
        for direction in ("fwd", "rev"):
            grp = [r for r in rows if r["cruise"] == cruise
                   and (r["mm"] >= 0) == (direction == "fwd")]
            if not grp:
                continue
            for wheel in ("l", "r"):
                e = [r[f"err_{wheel}_mm"] for r in grp]
                out.append({
                    "cruise": cruise, "dir": direction, "wheel": wheel,
                    "n": len(e), "mean": statistics.mean(e),
                    "sd": statistics.stdev(e) if len(e) > 1 else 0.0,
                    "worst": max(e, key=abs),
                    "ms_host": statistics.mean(r["ms_host"] for r in grp)})
    return out


class Wire:
    """A sequenced-verb session over `robotlink.Link`, plus the telemetry
    frame buffer. `Link` owns the `#id` counter; this class owns what the
    old rig's Wire did: say, poll, expect, cmd, status, set."""

    def __init__(self, link, verbose=False):
        self.link = link
        self.verbose = verbose
        self.stream = tlm.TlmStream()
        self.frames = []                    # (host_t, dict) in arrival order
        self.pending = []
        self.statuses = []                  # (host_t, dict)

    def say(self, line):
        if self.verbose:
            print("  >", line, file=sys.stderr)
        self.link.send(line)

    def poll(self, budget=0.08):
        """Read for at most `budget` s; frames go to self.frames, STATUS
        lines to self.statuses, everything else is returned."""
        out = []
        for line in self.link.lines(budget):
            if self.verbose:
                print("  <", line, file=sys.stderr)
            row = self.stream.feed(line)
            if row is not None:
                self.frames.append((time.time(), dict(row)))
                continue
            if line.startswith(("thdr ", "t ")) or line.startswith("DBG:"):
                continue
            st = parse_status(line)
            if st is not None:
                self.statuses.append((time.time(), st))
                continue
            out.append(line)
        return out

    def expect(self, pred, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pending.extend(self.poll())
            for index, line in enumerate(self.pending):
                if pred(line):
                    del self.pending[:index + 1]
                    return line
            if len(self.pending) > 200:
                del self.pending[:-50]
        raise TimeoutError("no matching reply")

    def cmd(self, verb_and_args, timeout=3.0):
        """Send a sequenced verb; return (ack line, host time of the ack)."""
        self.say(verb_and_args)
        line = self.expect(lambda s: s.startswith(("ack", "nack", "err")), timeout)
        t_ack = time.time()
        if not line.startswith("ack"):
            raise RuntimeError(f"{verb_and_args}: {line}")
        return line, t_ack

    def status(self, timeout=2.0):
        mark = len(self.statuses)
        self.say("STATUS")
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pending.extend(self.poll())
            if len(self.statuses) > mark:
                return self.statuses[-1][1]
        raise TimeoutError("no STATUS reply")

    def get(self, name):
        self.say(f"GET {name}")
        line = self.expect(lambda s: (parse_get(s) or ("",))[0] == name, 3.0)
        return parse_get(line)[1]

    def set(self, name, value):
        self.cmd(f"SET {name} {value}")

    def rest_counts(self, settle=0.5):
        """(posl, posr) from the freshest frame once the wheels sit still."""
        deadline = time.time() + 4.0
        while time.time() < deadline:
            self.frames.clear()
            end = time.time() + settle
            while time.time() < end:
                self.pending.extend(self.poll())
            got = [f for _, f in self.frames]
            if len(got) >= 2 and all(
                    abs(f["vl"]) <= REST_MMPS and abs(f["vr"]) <= REST_MMPS
                    and f["posl"] == got[-1]["posl"] and f["posr"] == got[-1]["posr"]
                    for f in got):
                return got[-1]["posl"], got[-1]["posr"], got[-1]
        raise TimeoutError("wheels did not come to rest")


def run_line(w, verb_and_args, prefix, timeout):
    """RUN <handler> and wait for the handler's emitted line (old rig shape)."""
    w.cmd(f"RUN {verb_and_args}", timeout=3.0)
    line = w.expect(lambda s: s.startswith(prefix), timeout)
    return dict(kv.split("=", 1) for kv in line.split(":")[1:] if "=" in kv)


def run_trial(w, mm, cruise, timeout_ms, per_count):
    """One MOVE_X leg. Returns (trial record, frame rows)."""
    pl0, pr0, f0 = w.rest_counts()
    st0 = w.status()
    w.frames.clear()
    w.statuses.clear()
    expect_s = abs(mm) / cruise
    _, t_ack = w.cmd(f"MOVE_X {int(round(mm))} 0 {int(cruise)} {int(timeout_ms)}")
    t_rest = None
    t_rest_dev = t_start_dev = None
    moved = False
    rest_run = 0
    posmove_mid = None
    sent_status = False
    seen = 0
    deadline = t_ack + timeout_ms / 1000.0 + 3.0
    while time.time() < deadline:
        w.pending.extend(w.poll(0.05))
        if not sent_status and time.time() - t_ack >= max(0.4, 0.4 * expect_s):
            w.say("STATUS")
            sent_status = True
        for t_host, f in w.frames[seen:]:
            if abs(f["vl"]) > REST_MMPS or abs(f["vr"]) > REST_MMPS:
                if not moved:
                    t_start_dev = f["now"]
                moved = True
                rest_run = 0
            elif moved:
                rest_run += 1
                if rest_run == 1:
                    t_rest, t_rest_dev = t_host, f["now"]
        seen = len(w.frames)
        if moved and rest_run >= REST_FRAMES:
            break
    else:
        raise TimeoutError("move did not finish")
    if sent_status:
        mark = time.time() + 1.0
        while not w.statuses and time.time() < mark:
            w.pending.extend(w.poll(0.05))
    if w.statuses:
        posmove_mid = posmove_of(w.statuses[0][1])
    move_frames = [f for _, f in w.frames]
    t_done = (t_rest - t_ack) if t_rest else float("nan")
    time.sleep(0.3)
    stf = w.status()
    pl1, pr1, f1 = w.rest_counts()
    tl, tr, el, er = wheel_errors((pl0, pr0), (pl1, pr1), mm, per_count)
    sign = 1.0 if mm >= 0 else -1.0
    il, ir = integrate_wheels([f0] + move_frames + [f1])
    odo = math.hypot(f1["x"] - f0["x"], f1["y"] - f0["y"])
    rec = {
        "mm": mm, "cruise": cruise,
        "travel_l_mm": round(tl, 2), "travel_r_mm": round(tr, 2),
        "err_l_mm": round(el, 2), "err_r_mm": round(er, 2),
        "int_l_mm": round(il * sign, 1), "int_r_mm": round(ir * sign, 1),
        "odo_mm": round(odo, 1),
        "ms_host": round(t_done * 1000),
        "ms_device": (t_rest_dev - t_start_dev) if t_start_dev is not None else "",
        "posmove_mid": "" if posmove_mid is None else posmove_mid,
        "posmove_after": "" if posmove_of(stf) is None else posmove_of(stf),
        "reason": stf.get("reason", ""),
        "i2cf_delta": int(stf.get("i2cf", 0)) - int(st0.get("i2cf", 0)),
        "posl0": pl0, "posr0": pr0, "posl1": pl1, "posr1": pr1,
    }
    t0 = move_frames[0]["now"] if move_frames else 0
    rows = [{"t_ms": f["now"] - t0, "posl": f["posl"] - pl0, "posr": f["posr"] - pr0,
             "vl": f["vl"], "vr": f["vr"], "x": f["x"]} for f in move_frames]
    return rec, rows


def write_csv(path, rows, fields=None):
    with open(path, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields or list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)


def print_table(table):
    print(f"{'cruise':>7} {'dir':>4} {'wh':>2} {'n':>2} {'mean mm':>8} {'sd':>6} "
          f"{'worst':>7} {'ms host':>8}")
    for r in table:
        print(f"{r['cruise']:>7} {r['dir']:>4} {r['wheel']:>2} {r['n']:>2} "
              f"{r['mean']:>8.2f} {r['sd']:>6.2f} {r['worst']:>7.2f} {r['ms_host']:>8.0f}")


def main():
    from robotlink import open_link
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None, help="local USB serial port")
    ap.add_argument("--wifi", metavar="NAME|IP", default=None,
                    help="WiFi/tunnel carrier, e.g. 127.0.0.1 for the loki bridge")
    ap.add_argument("--mode", choices=sorted(MODES), default="position")
    ap.add_argument("--mm", type=float, default=500.0)
    ap.add_argument("--cruise", default="75,150,250", help="mm/s list (30/60/100 %% of v_max 250)")
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--set", action="append", default=[], help='"name value" applied before the trials')
    ap.add_argument("--tag", default=None)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--timeout", type=int, default=8000)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    tag = args.tag or args.mode

    w = Wire(open_link(args.port, wifi=args.wifi), args.verbose)
    os.makedirs(args.out, exist_ok=True)
    try:
        w.set("position_mode", MODES[args.mode])
        for spec in args.set:
            name, value = spec.split()
            w.set(name, value)
        w.cmd("TLM FULL")
        per_count = mm_per_count(w.get("wheel_diameter"))
        rows = []
        for cruise in [int(c) for c in args.cruise.split(",")]:
            for trial in range(args.trials):
                mm = args.mm if trial % 2 == 0 else -args.mm
                rec, frames = run_trial(w, mm, cruise, args.timeout, per_count)
                rec = {"mode": args.mode, "trial": trial, **rec}
                rows.append(rec)
                write_csv(os.path.join(args.out, f"{tag}_{cruise}_{trial}.csv"), frames)
                print(rec)
                w.cmd("STOP")
                time.sleep(0.5)
    finally:
        try:
            w.cmd("STOP")
            w.cmd("TLM OFF")
        except Exception as exc:    # noqa: BLE001 - best effort on the way out
            print("cleanup failed:", exc, file=sys.stderr)
    write_csv(os.path.join(args.out, f"{tag}.csv"), rows)
    table = summarize(rows)
    write_csv(os.path.join(args.out, f"{tag}_summary.csv"), table)
    print()
    print_table(table)


if __name__ == "__main__":
    main()
