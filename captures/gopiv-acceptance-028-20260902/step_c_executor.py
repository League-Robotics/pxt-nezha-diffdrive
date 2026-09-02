"""Step C -- ticket 003 (executor inversion) hardware acceptance on gopiv.

Fixed firmware (0.20260902.2, this sprint's HEAD). gopiv is a bare-motor
bench rig (no wheels on the ground, no OTOS) -- full tours are safe here.

C.1: RUN:square:20 completes; a wire MOVE_X sent mid-tour is refused
     (expected `err 10`) and the tour is undisturbed.
C.2: RUN:abort mid-tour stops it immediately (timed).
C.3: 10+ back-to-back RUN pivot jobs, no fault/reset, STATUS sane.
C.4: TLM POSE keeps flowing through a dispatched job.
"""
import sys
import time

from gopiv_link import Link


def log(f, msg):
    print(msg)
    f.write(msg + '\n')
    f.flush()


def status_dict(line):
    d = {}
    if not line:
        return d
    for tok in line.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            d[k] = v
    return d


def wait_idle(f, link, label, timeout=20.0):
    end = time.time() + timeout
    streak = 0
    st = None
    while time.time() < end:
        st = link.unseq('STATUS', r'status ', timeout=1.0, tries=2)
        if st and 'active=0' in st:
            streak += 1
        else:
            streak = 0
        if streak >= 2:
            log(f, f'{label}: confirmed idle -> {st}')
            return st
        time.sleep(0.4)
    log(f, f'{label}: TIMED OUT waiting for idle, last -> {st}')
    return st


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'step_c_transcript.txt'
    with open(out_path, 'w') as f:
        link = Link()
        log(f, f'=== Step C executor inversion, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
        log(f, f'VER -> {link.unseq("VER", r"ver ")}')
        log(f, f'HELLO -> {link.unseq("HELLO", r"device ")}')

        # ---- C.1: RUN:square:20, MOVE_X mid-tour refused ----
        log(f, '\n--- C.1: RUN:square:20, wire MOVE_X mid-tour ---')
        wait_idle(f, link, 'C.1 pre')
        m = link.mark()
        t0 = time.time()
        link.send('RUN:square:20')
        time.sleep(1.0)
        mid_reply = link.seqd('MOVE_X 0 500 60 3000')
        log(f, f'MOVE_X mid-tour reply -> {mid_reply}  (t={time.time() - t0:.3f}s)')
        printed = 0
        end = time.time() + 15.0
        banner = None
        while time.time() < end:
            lines = link.since(m)
            for ts, l in lines[printed:]:
                log(f, f'  RX t={ts - t0:.3f}s  {l}')
                if l.startswith('device NEZHA2') and banner is None:
                    banner = l
            printed = len(lines)
            time.sleep(0.05)
        st1 = wait_idle(f, link, 'C.1 post', timeout=15.0)
        log(f, f'C.1 unsolicited boot banner: {banner}')
        has_err = mid_reply is not None and 'err' in mid_reply
        log(f, f'C.1 mid-tour MOVE_X refused with err: {has_err}  (reply={mid_reply})')

        time.sleep(1.0)

        # ---- C.2: RUN:abort mid-tour, timed ----
        log(f, '\n--- C.2: RUN:abort timing ---')
        wait_idle(f, link, 'C.2 pre')
        # Un-aborted reference: time a bare RUN:pivot:90
        m = link.mark(); t0 = time.time()
        link.send('RUN:pivot:90')
        pivot_end = link.wait(m, r'PIVOT:end', 5.0)
        t_pivot_end = time.time() - t0
        log(f, f'reference RUN:pivot:90 (no abort): PIVOT:end at t={t_pivot_end:.3f}s')
        wait_idle(f, link, 'C.2 mid pre')

        m = link.mark(); t0 = time.time()
        link.send('RUN:pivot:90')
        time.sleep(0.3)
        t_abort = time.time()
        link.send('RUN:abort')
        pivot_end2 = link.wait(m, r'PIVOT:end', 5.0)
        t_pivot_end2 = time.time() - t0
        log(f, f'RUN:pivot:90 + RUN:abort at t={t_abort - t0:.3f}s: PIVOT:end at t={t_pivot_end2:.3f}s')
        log(f, f'abort cut the pivot short by {t_pivot_end - t_pivot_end2:.3f}s '
               f'(reference {t_pivot_end:.3f}s vs aborted {t_pivot_end2:.3f}s)')
        wait_idle(f, link, 'C.2 post')

        # ---- C.3: 10+ back-to-back RUN pivot jobs ----
        log(f, '\n--- C.3: back-to-back RUN pivot jobs ---')
        n_jobs = 12
        faults = []
        for i in range(n_jobs):
            deg = 30 if i % 2 == 0 else -30
            m = link.mark(); t0 = time.time()
            link.send(f'RUN:pivot:{deg}')
            got = link.wait(m, r'PIVOT:end', 4.0)
            ok = got is not None
            if not ok:
                faults.append(i)
            log(f, f'  job {i}: RUN:pivot:{deg} -> {"PIVOT:end seen" if ok else "NO REPLY / FAULT"}')
        st_final = link.unseq('STATUS', r'status ')
        log(f, f'C.3 STATUS after 12 jobs -> {st_final}')
        d = status_dict(st_final)
        log(f, f'C.3 faults={faults}  i2cf={d.get("i2cf")}  cyc={d.get("cyc")}  '
               f'ready={d.get("ready")}  connL={d.get("connL")}  connR={d.get("connR")}')

        time.sleep(1.0)

        # ---- C.4: TLM POSE during a dispatched job ----
        log(f, '\n--- C.4: TLM POSE during a dispatched RUN job ---')
        wait_idle(f, link, 'C.4 pre')
        tlm_reply = link.seqd('TLM POSE')
        log(f, f'TLM POSE subscribe -> {tlm_reply}')
        m = link.mark(); t0 = time.time()
        link.send('RUN:pivot:90')
        end = time.time() + 3.0
        tframes = 0
        printed = 0
        while time.time() < end:
            lines = link.since(m)
            for ts, l in lines[printed:]:
                if l.startswith('t ') or l.startswith('t\t'):
                    tframes += 1
                if 'PIVOT:end' in l:
                    log(f, f'  RX t={ts - t0:.3f}s  {l}')
            printed = len(lines)
            time.sleep(0.02)
        log(f, f'C.4 telemetry frames observed during job: {tframes}')
        # unsubscribe
        link.seqd('TLM OFF')
        wait_idle(f, link, 'C.4 post')

        link.close()
        log(f, '\n=== Step C complete ===')


if __name__ == '__main__':
    main()
