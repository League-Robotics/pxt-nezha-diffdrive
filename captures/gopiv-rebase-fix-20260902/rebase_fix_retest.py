"""Sprint 028 ticket 002 reopen -- hardware proof of the rebase-race fix
on gopiv (fw built from commit HEAD at time of this capture, containing
motion_engine.{h,cpp}'s MoveState::epochLeft0/epochRight0 re-anchor).

Reproduces and re-tests Step E from
captures/gopiv-acceptance-028-20260902/step_e_rebase.py, extended to 5+
reps (per the reopen dispatch's own proof requirement) plus a fresh
busy-refusal recheck and a small rebase-at-leg-1 tour.

R.1..R.5: pivot, SET rebase 1 -> pose reads 0, MOVE_X 0 <+-900> 60 3000
          issued immediately after -> must deliver close to the full
          ~5157 commanded centidegrees (E.4's own reference completion,
          undisturbed by rebase, reached h=5008), not the 11 centideg
          E.2 measured pre-fix.
R.busy:   SET rebase 1 sent immediately after an in-flight MOVE_X is
          still refused (err 10) and the in-flight MOVE_X still
          completes normally -- re-confirms E.4 still holds post-fix.
R.tour:   SET rebase 1, then a short 4-leg tour (alternating pivot/
          straight) -- the first leg right after the rebase must not be
          the corrupted near-zero shortfall E.2 showed.
"""
import sys
import time

from gopiv_link import Link


def log(f, msg):
    print(msg)
    f.write(msg + '\n')
    f.flush()


def pose_lines_since(link, mark):
    return [l for ts, l in link.since(mark) if l.startswith('t ')]


def last_h(lines):
    """pose frame columns: t seq now flags x y h ox oy oh vl vr i2cf."""
    if not lines:
        return None
    parts = lines[-1].split()
    return int(parts[6])


def all_zero_xyh(lines):
    ok = True
    for l in lines:
        parts = l.split()
        if len(parts) < 7 or parts[4] != '0' or parts[5] != '0' or parts[6] != '0':
            ok = False
    return ok


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'rebase_fix_transcript.txt'
    with open(out_path, 'w') as f:
        link = Link()
        log(f, f'=== rebase-fix retest, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
        log(f, f'VER -> {link.unseq("VER", r"ver ")}')
        log(f, f'HELLO -> {link.unseq("HELLO", r"device ")}')

        tlm = link.seqd('TLM POSE')
        log(f, f'TLM POSE -> {tlm}')

        # Leading pivot to give the first rep a genuine nonzero prior
        # position to rebase away from (matches Step E.1's own setup).
        m = link.mark()
        log(f, f'leading MOVE_X 0 900 40 4000 -> {link.seqd("MOVE_X 0 900 40 4000")}')
        time.sleep(2.0)
        log(f, f'  h after leading pivot: {last_h(pose_lines_since(link, m))}')

        all_pass = True
        rotations = [-900, 900, -900, 900, -900]
        for i, rot in enumerate(rotations, start=1):
            log(f, f'\n--- R.{i}: pivot already at nonzero h, SET rebase 1, MOVE_X 0 {rot} 60 3000 ---')
            m1 = link.mark()
            rebase_reply = link.seqd('SET rebase 1')
            log(f, f'SET rebase 1 -> {rebase_reply}')
            time.sleep(0.4)
            zero_lines = pose_lines_since(link, m1)
            zeroed = all_zero_xyh(zero_lines)
            log(f, f'  {len(zero_lines)} post-rebase frames, all x=y=h=0: {zeroed}')
            if not zeroed:
                all_pass = False

            m2 = link.mark()
            move_reply = link.seqd(f'MOVE_X 0 {rot} 60 3000')
            log(f, f'MOVE_X 0 {rot} 60 3000 -> {move_reply}')
            time.sleep(2.2)
            move_lines = pose_lines_since(link, m2)
            h = last_h(move_lines)
            commanded = abs(rot) * 5.729578  # mrad -> centideg via 1 rad = 5729.578 cdeg, 900 mrad = 0.9 rad
            delivered_frac = (abs(h) / commanded) if h is not None else 0.0
            log(f, f'  {len(move_lines)} pose frames; final h={h} (commanded ~{commanded:.0f} cdeg, '
                    f'delivered {delivered_frac*100:.1f}%)')
            rep_ok = h is not None and delivered_frac > 0.80
            log(f, f'  R.{i} delivered > 80% of commanded rotation: {rep_ok}')
            if not rep_ok:
                all_pass = False

        log(f, f'\n=== R.1-R.5 summary: all reps passed = {all_pass} ===')

        # ---- busy-refusal recheck (E.4 equivalent) ----
        log(f, '\n--- R.busy: SET rebase 1 during in-flight MOVE_X (busy refusal recheck) ---')
        m4 = link.mark()
        t0 = time.time()
        link._seq += 1
        seq_move = link._seq
        link.send(f'MOVE_X 0 900 40 4000 #{seq_move}')
        link._seq += 1
        seq_rebase = link._seq
        link.send(f'SET rebase 1 #{seq_rebase}')
        end = time.time() + 6.0
        printed = 0
        while time.time() < end:
            lines = link.since(m4)
            for ts, l in lines[printed:]:
                log(f, f'  RX t={ts - t0:.3f}s  {l}')
            printed = len(lines)
            time.sleep(0.05)
        busy_lines = [l for ts, l in link.since(m4) if l.startswith('t ')]
        busy_h = last_h(busy_lines)
        log(f, f'  in-flight MOVE_X final h={busy_h} (E.4 reference: 5008)')

        # ---- small rebase-at-leg-1 tour ----
        log(f, '\n--- R.tour: SET rebase 1, then a 4-leg tour ---')
        m5 = link.mark()
        log(f, f'SET rebase 1 -> {link.seqd("SET rebase 1")}')
        time.sleep(0.4)
        tour_zero = pose_lines_since(link, m5)
        log(f, f'  post-rebase zero check ({len(tour_zero)} frames): {all_zero_xyh(tour_zero)}')

        legs = [
            ('MOVE_X 0 900 60 3000', 900, True),     # leg 1: pivot right after rebase -- the exact race
            ('MOVE_X 300 0 150 4000', 0, False),     # leg 2: straight
            ('MOVE_X 0 -1800 60 3500', -1800, True), # leg 3: pivot
            ('MOVE_X 300 0 150 4000', 0, False),     # leg 4: straight
        ]
        tour_ok = True
        for idx, (cmd, rot, is_pivot) in enumerate(legs, start=1):
            ml = link.mark()
            reply = link.seqd(cmd)
            log(f, f'leg {idx}: {cmd} -> {reply}')
            time.sleep(2.5 if is_pivot else 3.0)
            leg_lines = pose_lines_since(link, ml)
            if is_pivot:
                h = last_h(leg_lines)
                commanded = abs(rot) * 5.729578
                frac = (abs(h) / commanded) if h is not None else 0.0
                log(f, f'  leg {idx} (pivot) final h={h} (commanded ~{commanded:.0f} cdeg, '
                        f'delivered {frac*100:.1f}%)')
                if frac <= 0.80:
                    tour_ok = False
            else:
                log(f, f'  leg {idx} (straight): {len(leg_lines)} pose frames observed')
        log(f, f'\n=== R.tour first-leg-after-rebase sane: {tour_ok} ===')

        link.close()
        log(f, '\n=== rebase-fix retest complete ===')


if __name__ == '__main__':
    main()
