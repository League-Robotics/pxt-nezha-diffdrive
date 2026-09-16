#!/usr/bin/env python3
"""Fire one characterization CELL of sprint 039 ticket 003's sweep and
report the per-pulse encoder deltas.

One cell = N pulses at one (amplitude, width) on one wheel, fired from
rest with a settle between them, over a HELD-OPEN socket to the robot's
serial daemon. The held-open link is not optional: mbdeploy's own
`connect` returns once it has the ack and closes, so a `ret` line
arriving a moment later is lost by the harness and looks exactly like
the robot not answering (see captures/039-002-repro-20260915/).

The verdict this feeds: accept a cell if its per-pulse increment is a
repeatable 0.3-2 mm, sd/mean <= 0.4.

Usage:
  pulsesweep.py HOST PORT --amp 25 --width 2 --wheel left --count 20 --seq 28
"""
import argparse
import json
import re
import socket
import statistics
import sys
import time

# Integer-only fields: the target's printf has no float support, so the
# firmware reports hundredths of a millimetre as a scaled int (sprint 039
# ticket 001's hardware fix, 2026-09-16). Anything that parses a float
# here is reading a build that predates that fix.
RET = re.compile(
    r"left_counts=(-?\d+)\s+right_counts=(-?\d+)\s+"
    r"left_mm_x100=(-?\d+)\s+right_mm_x100=(-?\d+)"
)


class Link:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.setblocking(False)
        self.buf = b""

    def drain(self, seconds):
        """Read for `seconds`, returning every complete line seen."""
        lines = []
        until = time.time() + seconds
        while time.time() < until:
            try:
                chunk = self.sock.recv(4096)
            except BlockingIOError:
                time.sleep(0.01)
                continue
            if not chunk:
                break
            self.buf += chunk
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                text = line.decode("utf-8", "replace").rstrip("\r")
                if text:
                    lines.append(text)
        return lines

    def send(self, text):
        self.sock.sendall((text + "\n").encode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("port", type=int)
    ap.add_argument("--amp", type=float, required=True,
                    help="pulse amplitude [percent duty]")
    ap.add_argument("--width", type=int, required=True,
                    help="pulse width [control ticks]")
    ap.add_argument("--wheel", choices=["left", "right", "both"],
                    required=True)
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--seq", type=int, required=True,
                    help="first sequence id to use (STATUS's next=)")
    ap.add_argument("--settle", type=float, default=0.6,
                    help="seconds between pulses, wheels at rest")
    ap.add_argument("--sign", type=float, default=1.0,
                    help="-1 fires the cell in reverse")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    amplitudeLeft = args.amp * args.sign if args.wheel in ("left", "both") else 0.0
    amplitudeRight = args.amp * args.sign if args.wheel in ("right", "both") else 0.0

    link = Link(args.host, args.port)
    link.drain(0.6)

    samples = []
    seq = args.seq
    for index in range(args.count):
        link.send(f"RUN pulse {amplitudeLeft:g} {amplitudeRight:g} "
                  f"{args.width} #{seq}")
        seq += 1
        got = None
        deadline = time.time() + 6.0
        while time.time() < deadline:
            for line in link.drain(0.25):
                found = RET.search(line)
                if found:
                    got = found
                if "err" in line or "nack" in line:
                    print(f"  REFUSED: {line}", flush=True)
            if got:
                break
        if got is None:
            print(f"  pulse {index}: NO ret LINE (harness or robot)",
                  flush=True)
            continue
        left = int(got.group(3)) / 100.0   # [mm] from hundredths
        right = int(got.group(4)) / 100.0  # [mm]
        countsLeft, countsRight = float(got.group(1)), float(got.group(2))
        samples.append({"left": left, "right": right,
                        "countsLeft": countsLeft, "countsRight": countsRight})
        print(f"  pulse {index:2d}: left {left:+.2f} mm ({countsLeft:+.0f} c)  "
              f"right {right:+.2f} mm ({countsRight:+.0f} c)", flush=True)
        time.sleep(args.settle)

    driven = "left" if args.wheel == "left" else "right"
    values = [abs(s[driven]) for s in samples]
    result = {
        "amplitude": args.amp, "width": args.width, "wheel": args.wheel,
        "sign": args.sign, "requested": args.count, "returned": len(samples),
        "samples": samples,
    }
    if values:
        mean = statistics.fmean(values)
        sd = statistics.pstdev(values) if len(values) > 1 else 0.0
        result["mean_mm"] = mean
        result["sd_mm"] = sd
        result["ratio"] = (sd / mean) if mean else None
        zeros = sum(1 for v in values if v < 0.05)
        result["dead_pulses"] = zeros
        print(f"\ncell amp={args.amp} width={args.width} {args.wheel}: "
              f"mean {mean:.2f} mm, sd {sd:.2f}, sd/mean "
              f"{result['ratio']:.2f}, dead {zeros}/{len(values)}")
    else:
        print("\ncell produced NO samples")

    if args.out:
        with open(args.out, "w") as handle:
            json.dump(result, handle, indent=1)
    print(f"next sequence id: {seq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
