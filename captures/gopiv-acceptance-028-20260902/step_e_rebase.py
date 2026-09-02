"""Step E -- ticket 002 (SET rebase / SET estop_clear) hardware acceptance
on gopiv. Fixed firmware (0.20260902.2).

E.1: TLM POSE, a pivot, SET rebase 1 #n -> ack, x=y=h=0 on next frames,
     stays zero across the kernel's deferred re-anchor tick.
E.2: A second move afterward resumes cleanly from the new zero.
E.3: SET estop_clear 1 #n acks on an idle robot (no prior ESTOP).
E.4: SET rebase 1 during an in-flight MOVE_X is refused (err 10).
"""
import sys
import time

from gopiv_link import Link


def log(f, msg):
    print(msg)
    f.write(msg + '\n')
    f.flush()


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'step_e_transcript.txt'
    with open(out_path, 'w') as f:
        link = Link()
        log(f, f'=== Step E rebase/estop_clear, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
        log(f, f'VER -> {link.unseq("VER", r"ver ")}')
        log(f, f'HELLO -> {link.unseq("HELLO", r"device ")}')

        # subscribe telemetry
        tlm = link.seqd('TLM POSE')
        log(f, f'TLM POSE -> {tlm}')

        # ---- E.1: pivot, then SET rebase 1 ----
        log(f, '\n--- E.1: pivot then SET rebase 1 ---')
        m = link.mark()
        pivot_reply = link.seqd('MOVE_X 0 250 60 3000')
        log(f, f'MOVE_X (pivot, 250 mrad) -> {pivot_reply}')
        time.sleep(0.6)
        pre_lines = [l for ts, l in link.since(m) if l.startswith('t ')]
        if pre_lines:
            log(f, f'pose frame right after pivot -> {pre_lines[-1]}')

        m2 = link.mark()
        rebase_reply = link.seqd('SET rebase 1')
        log(f, f'SET rebase 1 -> {rebase_reply}')
        time.sleep(0.6)
        post_lines = [l for ts, l in link.since(m2) if l.startswith('t ')]
        log(f, f'{len(post_lines)} pose frames after rebase; ALL:')
        for l in post_lines:
            log(f, f'  {l}')
        all_zero = all(
            (lambda parts: len(parts) >= 6 and parts[3] == '0' and parts[4] == '0' and parts[5] == '0')(l.split())
            for l in post_lines
        )
        log(f, f'E.1 all post-rebase frames read x=y=h=0: {all_zero}')

        # ---- E.2: a second move resumes cleanly from the new zero ----
        log(f, '\n--- E.2: second pivot after rebase ---')
        m3 = link.mark()
        pivot2_reply = link.seqd('MOVE_X 0 -900 60 3000')
        log(f, f'MOVE_X (pivot, -900 mrad) -> {pivot2_reply}')
        time.sleep(1.5)
        lines2 = [l for ts, l in link.since(m3) if l.startswith('t ')]
        log(f, f'{len(lines2)} pose frames after second pivot; ALL:')
        for l in lines2:
            log(f, f'  {l}')

        # ---- E.3: SET estop_clear 1 on idle robot ----
        log(f, '\n--- E.3: SET estop_clear 1 (idle, no prior ESTOP) ---')
        est_reply = link.seqd('SET estop_clear 1')
        log(f, f'SET estop_clear 1 -> {est_reply}')

        # ---- E.4: SET rebase 1 refused during in-flight MOVE_X ----
        log(f, '\n--- E.4: SET rebase 1 during in-flight MOVE_X (busy refusal) ---')
        m4 = link.mark()
        t0 = time.time()
        link._seq += 1
        seq_move = link._seq
        link.send(f'MOVE_X 0 900 40 4000 #{seq_move}')
        link._seq += 1
        seq_rebase = link._seq
        link.send(f'SET rebase 1 #{seq_rebase}')
        end = time.time() + 8.0
        printed = 0
        while time.time() < end:
            lines = link.since(m4)
            for ts, l in lines[printed:]:
                log(f, f'  RX t={ts - t0:.3f}s  {l}')
            printed = len(lines)
            time.sleep(0.05)
        link.close()
        log(f, '\n=== Step E complete ===')


if __name__ == '__main__':
    main()
