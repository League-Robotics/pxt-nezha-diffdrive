#!/usr/bin/env python3
"""RUN:arc capture -- the split-move phase-handoff confirmation.

`RUN:arc:<deg>` (test/test.ts) issues a single `tickArcSampled(20, deg)`
-- 20 cm plus a rotation -- reproducing the shape (`move(20, 180)`) that
measured the split-move phase-handoff defect (the kernel's `twistRef_`
unwinding its own pivot at the phase 1 -> phase 2 handoff) and its fix.
The endpoint heading alone cannot distinguish the fix from the
hypotheses it displaced, so this needs the FULL h(t) trajectory, not
just before/after.

**The v6-telemetry capture path is a dead end -- do not use it.**
Subscribing v6 POSE telemetry and then sending a cleartext `RUN:` line
hangs the link completely (no reply, telemetry itself stops) for at
least 15s with no recovery short of reopening the port -- confirmed
over six reproductions, independent of this verb (a pre-existing,
zero-motion verb reproduces it identically) and independent of general
concurrency (a v6 command under the same active-telemetry condition
works fine). Root cause: the v6 wire stack's own by-name RUN dispatch
(`WireAdapter::onRun()`) is a permanent stub that always returns
`kUnknown`; the only real by-name dispatch is the cleartext `RUN:`-
prefix path, which is exactly the path that hangs under active
telemetry. See
`clasi/issues/cleartext-run-hangs-the-link-under-active-telemetry.md`
for the full isolation. Fixing that is a `src/comms/` change out of
scope for a bench-measurement tool.

**The path this script actually uses instead**: the same "sample into
arrays and dump afterwards" pattern `src/shims.cpp`'s `probe()` doc
comment already prescribes for anything that needs per-tick state out
of a move (a request/reply round trip DURING a move is independently
dangerous -- a 197.5 mm leg once collapsed to 0.3 mm under one). `RUN:arc`
now samples `diffDrive.heading()` on-device, once per tick, entirely on
its own fiber while the move runs, and dumps the trajectory as `ARCT:`
lines (`ARCT:meta:<n>:<capped>`, then `ARCT:<chunk>:<csv of centidegree
ints>` lines, then `ARCT:done`) after `ARC:end`. No telemetry is ever
subscribed, so the link-hang trigger above cannot fire -- this script
opens the link, sends ONE `RUN:arc:<deg>` command, and reads the
trajectory back off the same cleartext stream the `DBG:`/`GAP:`/
`ARC:end` lines already use.

Deliberately carries no OTOS/`oh` column at all -- `RUN:arc`, like
`RUN:pivot`, never calls `worldReady()`/`readWorld()`, so there is no
world-frame signal to read here in the first place. `h` (encoder/gyro
heading, wire cdeg convention) is the only quantity this capture
carries, which is exactly why it is valid wheels-up on the bench stand:
heading here is integrated from the encoder differential, not the
floor.

Usage:
  python3 tools/arc_capture.py [PORT] [--radio] [--deg 180]
      [--timeout 15] [--out-prefix .tmp/arc]
"""
import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from robotlink import open_link

# Must match test/test.ts's own ARCT_CHUNK -- only used here to size the
# expected-chunk-count sanity check below, not to parse individual
# lines (those are self-delimiting: `ARCT:<chunk>:<csv>`).
_ARCT_CHUNK = 20


def _parse_trajectory(link, timeout):
    """Read GAP:/ARC:end/ARCT:* lines after a RUN:arc command has
    already been acknowledged. Returns (gap_line, arc_end_line,
    h_cdeg list, capped bool). Raises SystemExit on an incomplete or
    malformed dump rather than returning a partial trajectory silently.
    """
    gap_line = None
    arc_end_line = None
    meta = None            # (total, capped)
    chunks = {}             # chunk index -> [cdeg, ...]
    done = False
    deadline = time.time() + timeout
    while time.time() < deadline and not done:
        line = link.p.readline()
        if not line:
            continue
        s = line.decode('ascii', errors='replace').strip()
        if s.startswith('< '):
            s = s[2:]           # relay control-plane prefix
        if not s:
            continue
        if s.startswith('GAP:'):
            gap_line = s
        elif s.startswith('ARC:end'):
            arc_end_line = s
        elif s.startswith('ARCT:meta:'):
            parts = s.split(':')
            if len(parts) != 4:
                raise SystemExit(f'malformed ARCT:meta: line: {s!r}')
            meta = (int(parts[2]), parts[3] == '1')
        elif s == 'ARCT:done':
            done = True
        elif s.startswith('ARCT:'):
            rest = s[len('ARCT:'):]
            idx_str, _, csv = rest.partition(':')
            chunks[int(idx_str)] = [int(v) for v in csv.split(',') if v]
        # everything else (ack/nack lines, DBG:, unrelated lines) is
        # silently ignored -- same filtering tour_capture.py/tlm.py
        # already apply to the same reliability line (no longer an
        # unsolicited stream since sprint 024 ticket 001 removed
        # protocol.cpp's free-running emitReliability() call; see the
        # firmware-identity check below for why the filter still runs
        # at all).

    if meta is None:
        raise SystemExit(
            'no ARCT:meta: line received -- either the dump never '
            'started or the read timed out before it arrived. '
            f'gap={gap_line!r} arc_end={arc_end_line!r}')
    if not done:
        raise SystemExit(
            'ARCT:done never arrived -- trajectory dump incomplete '
            f'({len(chunks)} chunk line(s) received). Not reporting a '
            'partial trajectory as a result.')

    total, capped = meta
    combined = []
    for idx in sorted(chunks):
        combined.extend(chunks[idx])
    if len(combined) != total:
        raise SystemExit(
            f'trajectory dump incomplete: ARCT:meta: promised {total} '
            f'samples, assembled {len(combined)} from chunk indices '
            f'{sorted(chunks)} -- a chunk line was likely dropped.')
    return gap_line, arc_end_line, combined, capped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('port', nargs='?', default=None,
                    help='serial port; omit with --radio for zavaz')
    ap.add_argument('--wifi', metavar='NAME|IP', default=None,
        help='drive the robot over its WiFi TCP server (default carrier since 2026-09-02)')
    ap.add_argument('--radio', action='store_true',
                    help='capture over the zavaz relay. The bench stand '
                         'holds the wheels off the ground -- fine for this '
                         'heading-only measurement, meaningless for any '
                         'OTOS/translation column (RUN:arc reads neither).')
    ap.add_argument('--robot', default='vevov',
                    help="board name -- resolves the zavaz relay's "
                         "channel/group for --radio; ignored otherwise")
    ap.add_argument('--deg', type=float, default=180.0,
                    help='RUN:arc:<deg> argument. |deg| >= 50 is required '
                         'to exercise the split-move (pivot-then-straight) '
                         'path at all -- moveX() blends anything smaller '
                         'into one move that never phase-hands-off.')
    ap.add_argument('--timeout', type=float, default=15.0,
                    help='seconds to wait for the GAP:/ARC:end/ARCT: '
                         'dump after the move is acknowledged -- a 180 '
                         'deg arc itself takes about 2.8s.')
    ap.add_argument('--out-prefix', default='.tmp/arc')
    a = ap.parse_args()

    link = open_link(a.port, radio=a.radio, wifi=a.wifi, robot=a.robot)

    # --- firmware-identity check (no motion) --------------------------
    # `ack `/`nack ` lines are filtered out of this check even though
    # they can no longer arrive as an unsolicited stream -- sprint 024
    # ticket 001 deleted protocol.cpp's free-running emitReliability()
    # call, so a reply can now only ever follow a request (see
    # clasi/issues/reliability-line-free-runs-at-20-hz-on-the-radio-
    # with-no-host.md). The filter is defensive/vestigial rather than
    # load-bearing: it stays because some OTHER reply sharing this same
    # link (STATUS, GET, etc.) could still land inside this read
    # window, not because a beacon is expected -- keeping it costs
    # nothing even against firmware that never sends one.
    bogus = 'RUN:notarealverb'
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

    # --- the real, single-shot measurement -----------------------------
    # Deliberately NO telemetry subscription anywhere in this script --
    # see the module docstring's "dead end" section. RUN:arc is sent
    # cleartext exactly as verified standalone-safe.
    if abs(a.deg) < 50:
        print(f'  WARNING: |deg|={abs(a.deg)} < 50 -- this will NOT '
              f'exercise the split-move path (moveX() blends it into one '
              f'move instead).')
    cmd = f'RUN:arc:{a.deg:g}'
    ack = link.send_until(cmd, 'DBG:arc:', tries=2, wait=5.0)
    if not any(s.startswith('DBG:arc:') for s in ack):
        raise SystemExit(
            f'no DBG:arc: receipt for {cmd} -- either the flash does not '
            f'carry this verb, or the command was lost in transit.')
    print(f'  OK: {cmd} acknowledged: '
          f'{[s for s in ack if s.startswith("DBG:arc:")][0]!r}')

    gap_line, arc_end_line, h_cdeg, capped = _parse_trajectory(
        link, a.timeout)
    link.close()

    if capped:
        print(f'  WARNING: on-device sample cap was hit -- the '
              f'trajectory below is TRUNCATED, not the whole move '
              f'({len(h_cdeg)} samples captured).')

    with open(a.out_prefix + '_h.csv', 'w') as f:
        f.write('sample_i,h_cdeg,h_deg\n')
        for i, cdeg in enumerate(h_cdeg):
            f.write(f'{i},{cdeg},{cdeg / 100.0}\n')

    # --- peak / leg-start / final, per the ticket's measurement table -
    h_deg = [c / 100.0 for c in h_cdeg]
    peak_i = max(range(len(h_deg)), key=lambda i: h_deg[i])
    peak = h_deg[peak_i]
    # leg-start: the first local minimum AFTER the peak -- where the
    # unwind (if any) bottoms out and the straight phase's own small
    # contribution takes over. If heading never comes back down after
    # the peak, leg-start IS the peak (no unwind observed). Honest about
    # its own limits: this is a trajectory-shape heuristic, not a
    # ground-truth phase-boundary marker -- the sample stream carries no
    # explicit phase-transition flag.
    leg_start_i = peak_i
    for i in range(peak_i + 1, len(h_deg)):
        if h_deg[i] >= h_deg[leg_start_i]:
            break
        leg_start_i = i
    leg_start = h_deg[leg_start_i]
    final = h_deg[-1]

    print(f'\ncaptured {len(h_deg)} h(t) samples (on-device, per-tick); '
          f'{gap_line}; {arc_end_line}')
    print(f'  peak heading during the move:   {peak:+.2f} deg '
          f'(sample {peak_i})')
    if leg_start_i == peak_i:
        print(f'  peak -> leg-start (the unwind): no post-peak local '
              f'minimum found -- reporting peak -> final instead: '
              f'{final - peak:+.2f} deg')
    else:
        print(f'  peak -> leg-start (the unwind): {leg_start - peak:+.2f} '
              f'deg (sample {leg_start_i})')
    print(f'  final heading:                  {final:+.2f} deg')
    print(f'  wrote {a.out_prefix}_h.csv')


if __name__ == '__main__':
    main()
