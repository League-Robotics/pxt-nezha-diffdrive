#!/usr/bin/env python3
"""RUN:arc capture -- the split-move phase-handoff confirmation.

Sprint 018 ticket 003: `RUN:arc:<deg>` (test/test.ts) issues a single
`tickedMove(20, deg)` -- 20 cm plus a rotation -- reproducing the shape
(`move(20, 180)`) that measured sprint 015 ticket 005's phase-handoff
defect (the kernel's `twistRef_` unwinding its own pivot at the phase
1 -> phase 2 handoff) and its fix. The endpoint heading alone cannot
distinguish the fix from the hypotheses it displaced, so this captures
the FULL h(t) trajectory -- not just before/after -- via the v6
POSE telemetry stream (`tools/tlm.py`), same shape as
`tools/tour_capture.py` but for one `RUN:arc` command instead of a
whole tour.

Firmware-identity check, in the SAME serial session as the capture
(re-opening the port resets the target program -- see
`.claude/rules/playfield-testing.md` -- so this deliberately does not
reopen the link between the check and the capture): a deliberately
bogus `RUN:` verb must draw NO reply (this project's RUN vocabulary is
string-keyed -- an unmatched verb is a silent no-op, never an echo),
then `RUN:arc:<deg>` itself must draw a `DBG:arc:` line -- a verb that
does not exist at all in any firmware built before this ticket, so
seeing it is itself the positive identity confirmation, not merely
"the board answered something."

Deliberately does NOT read the `oh` (OTOS world heading) column --
`RUN:arc`, like `RUN:pivot`, never calls worldReady()/readWorld(), so
`oh` reads flat/stale. `h` (encoder/gyro heading, wire cdeg) is the
only column with signal, which is exactly why this measurement is
valid run wheels-up on the bench stand: heading here is integrated
from the encoder differential, not the floor.

**KNOWN BLOCKER, found during ticket 003's own hardware session
(tovez, USB, this build)**: sending a cleartext `RUN:`/`DIAG` command
while v6 POSE telemetry is ACTIVELY SUBSCRIBED (i.e. exactly the
require_stream()-then-send order this script uses, matching
tour_capture.py's own shape) makes the link go completely silent --
no reply to the command, and telemetry itself stops -- for at least
15s, confirmed with both `RUN:gap` (pre-existing, zero-motion verb,
so this is NOT specific to ticket 003's new `arc` handler) and
`RUN:arc:180`. A fresh v6 command (`STATUS`) sent under the same
active-telemetry condition works fine and telemetry keeps flowing, so
the trigger is specifically a CLEARTEXT command arriving while v6
POSE streaming is on, not concurrency in general. Root cause, from
reading src/comms/protocol.cpp and wire_adapter.cpp: the v6 wire
stack's own `RUN <name> ... #<id>` verb is a permanent, deliberate
stub (`WireAdapter::onRun()` always returns `kUnknown` -- see its own
comment and `src/DESIGN.md`'s "onRun() is an honest kUnknown"); the
ONLY real by-name dispatch is protocol.cpp's literal `"RUN:"`-prefix
`handleRun()` bridge into CODAL's MessageBus, a completely separate
path from `wireHandler_.feed()` (which telemetry and every other v6
verb runs through) -- so there is no existing verb that can trigger a
test.ts RUN handler without going through the path that hangs.
Reopening the port (which resets the target -- see
`.claude/rules/playfield-testing.md`) recovers the link every time.
See `clasi/sprints/018-bench-truth-re-measure-accuracy-on-corrected-
motion/issues/confirm-the-handoff-fix-on-hardware.md` for the full
write-up. Until this is fixed, this script's subscribe-then-command
order will reliably raise SystemExit below -- it is kept as the
CORRECT tool for when the underlying hang is fixed, not a live,
working capture path today.

Usage:
  python3 tools/arc_capture.py [PORT] [--radio] [--deg 180]
      [--timeout 20] [--out-prefix .tmp/arc180]
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link
import tlm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default=None,
                    help='serial port; omit with --radio for zavaz')
    ap.add_argument('--radio', action='store_true',
                    help='capture over the zavaz relay. The bench stand '
                         'holds the wheels off the ground -- fine for this '
                         'heading-only measurement, meaningless for any '
                         'OTOS/translation column.')
    ap.add_argument('--deg', type=float, default=180.0,
                    help='RUN:arc:<deg> argument. |deg| >= 50 is required '
                         'to exercise the split-move (pivot-then-straight) '
                         'path at all -- moveX() blends anything smaller '
                         'into one move that never phase-hands-off.')
    ap.add_argument('--timeout', type=float, default=20.0)
    ap.add_argument('--out-prefix', default='.tmp/arc')
    a = ap.parse_args()

    link = open_link(a.port, radio=a.radio)

    # --- firmware-identity check (no motion) --------------------------
    # `ack `/`nack ` keepalive lines stream continuously regardless of
    # this command (tlm.py's own docstring: "streamed continuously at
    # 50 ms") -- they are not a reply to the bogus verb and must be
    # filtered out, or every check here would false-positive on them.
    bogus = 'RUN:notarealverb018003'
    seen = list(link.send_until(bogus, '\x00NEVER\x00', tries=1, wait=1.5,
                                 echo=False))
    reply = [s for s in seen if not s.startswith(('ack ', 'nack '))]
    if reply:
        print(f'  WARNING: bogus verb {bogus!r} drew a reply: {reply} -- '
              f'the RUN: dispatcher is not behaving as string-keyed/'
              f'silent-no-op as expected; identity check is inconclusive.')
    else:
        print(f'  OK: bogus verb {bogus!r} drew no reply (string-keyed '
              f'RUN: dispatch confirmed alive; {len(seen)} keepalive '
              f'line(s) filtered).')

    # --- subscribe telemetry BEFORE the move (fail loud if dead) ------
    try:
        stream = tlm.require_stream(link, timeout=3.0)
    except tlm.DeadTelemetryError as e:
        raise SystemExit(str(e)) from e

    # --- the real, single-shot measurement -----------------------------
    if abs(a.deg) < 50:
        print(f'  WARNING: |deg|={abs(a.deg)} < 50 -- this will NOT '
              f'exercise the split-move path (moveX() blends it into one '
              f'move instead).')
    cmd = f'RUN:arc:{a.deg:g}'
    t0 = time.time()
    h_trace = []   # (t_host, now_dev_ms, h_cdeg)
    end_line = None

    def _feed(s):
        """Feed one line to the telemetry stream; record an h(t) sample
        if it decoded to a real frame. Shared between the ack-wait
        window below and the main capture loop so no frame arriving in
        either window is silently dropped."""
        row = stream.feed(s)
        if row is not None:
            h_trace.append((round(time.time() - t0, 3), row['now'], row['h']))
        return row

    ack = link.send_until(cmd, 'DBG:arc:', tries=2, wait=5.0)
    for s in ack:
        _feed(s)
    if not any(s.startswith('DBG:arc:') for s in ack):
        raise SystemExit(
            f'no DBG:arc: receipt for {cmd}. Most likely cause (confirmed '
            f'during ticket 003, see this module\'s KNOWN BLOCKER note '
            f'above): the cleartext RUN: path goes silent once v6 POSE '
            f'telemetry is actively subscribed, which is exactly the '
            f'order this script just used. RUN:arc itself works fine '
            f'standalone (verified without telemetry active) -- this is '
            f'not evidence the flash failed. Aborting rather than '
            f'reporting a fake trajectory.')
    print(f'  OK: {cmd} acknowledged: {[s for s in ack if s.startswith("DBG:arc:")][0]!r} '
          f'-- firmware identity confirmed (this verb does not exist in '
          f'any pre-ticket-003 build).')

    deadline = time.time() + a.timeout
    while time.time() < deadline:
        line = link.p.readline()
        if not line:
            continue
        s = line.decode('ascii', errors='replace').strip()
        if s.startswith('< '):
            s = s[2:]
        if _feed(s) is not None:
            continue
        if s.startswith('ARC:end') or s.startswith('GAP:'):
            end_line = s
            if s.startswith('ARC:end'):
                break
            deadline = min(deadline, time.time() + 1.0)  # short tail
    link.close()

    if not h_trace:
        raise SystemExit('zero telemetry frames captured during the move '
                          '-- refusing to report an empty trajectory as a '
                          'result')

    meta = tlm.write_tlm_csv(stream, a.out_prefix + '_tlm.csv')
    with open(a.out_prefix + '_h.csv', 'w') as f:
        f.write('t_host,now_dev_ms,h_cdeg,h_deg\n')
        for t_host, now_ms, h_cdeg in h_trace:
            f.write(f'{t_host},{now_ms},{h_cdeg},{h_cdeg / 100.0}\n')

    # --- peak / leg-start / final, per the ticket's measurement table -
    h_deg = [h / 100.0 for _, _, h in h_trace]
    peak_i = max(range(len(h_deg)), key=lambda i: h_deg[i])
    peak = h_deg[peak_i]
    # leg-start: the first local minimum AFTER the peak -- where the
    # unwind (if any) bottoms out and the straight phase's own small
    # contribution takes over. If heading never comes back down after
    # the peak, leg-start IS the peak (no unwind observed).
    leg_start_i = peak_i
    for i in range(peak_i + 1, len(h_deg)):
        if h_deg[i] >= h_deg[leg_start_i]:
            break
        leg_start_i = i
    leg_start = h_deg[leg_start_i]
    final = h_deg[-1]

    print(f'\ncaptured {len(h_trace)} h(t) samples over '
          f'{h_trace[-1][0] - h_trace[0][0]:.2f}s; {end_line}; '
          f'telemetry {meta["frames"]} frames, {meta["dropped"]} dropped '
          f'({meta["loss_pct"]:.1f}% loss)')
    print(f'  peak heading during the move:  {peak:+.1f} deg '
          f'(sample {peak_i})')
    print(f'  peak -> leg-start (the unwind): {leg_start - peak:+.1f} deg '
          f'(sample {leg_start_i})')
    print(f'  final heading:                  {final:+.1f} deg')
    print(f'  wrote {a.out_prefix}_h.csv, {a.out_prefix}_tlm.csv/.meta.json')


if __name__ == '__main__':
    main()
