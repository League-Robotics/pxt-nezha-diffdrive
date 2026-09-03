"""Step A -- baseline on gopiv's OLD firmware (0.20260901.1), before flashing.

A.1: RUN:pivot:90 alone -- does the board reset at completion?
A.2: RUN:square:20 with a sequenced MOVE_X sent mid-tour.
A.3: RUN:square:20 then RUN:abort mid-tour.

gopiv is a bare-motor bench rig (no wheels on the ground, no OTOS) --
every motion verb is safe here per the dispatch brief's board rule.

Simple, generous-timeout design: earlier probing this session
(debug_a3.py / debug_timing.py / debug_duration.py, same directory)
showed RUN:square:20's real duration on this old firmware is not
consistent request to request -- sometimes cyc/i2cf advance visibly
over several seconds, sometimes a STATUS poll immediately after shows
active=0 with cyc/i2cf frozen. Rather than trying to precisely catch
an "active" transition (which itself races against the old firmware's
3-fiber dispatch -- arguably the exact class of nondeterminism this
sprint exists to remove), this script just drains everything received
during a generous fixed window and reports it verbatim, tagged with
elapsed time, plus before/after STATUS and a reset check (unsolicited
boot banner, or `cyc` going backwards).
"""
import sys
import time

from gopiv_link import Link


def status_dict(line):
    d = {}
    if not line:
        return d
    for tok in line.split():
        if '=' in tok:
            k, v = tok.split('=', 1)
            d[k] = v
    return d


def log(f, msg):
    print(msg)
    f.write(msg + '\n')
    f.flush()


def drain_for(f, link, m, t0, seconds):
    """Print/log every line received since mark `m`, live, for `seconds`."""
    printed = 0
    banner = None
    end = time.time() + seconds
    while time.time() < end:
        lines = link.since(m)
        for ts, l in lines[printed:]:
            log(f, f'  RX t={ts - t0:.3f}s  {l}')
            if l.startswith('device NEZHA2') and banner is None:
                banner = l
        printed = len(lines)
        time.sleep(0.05)
    return banner


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'step_a_transcript.txt'
    with open(out_path, 'w') as f:
        link = Link()
        log(f, f'=== Step A baseline, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')

        ver = link.unseq('VER', r'ver ')
        hello = link.unseq('HELLO', r'device ')
        log(f, f'VER -> {ver}')
        log(f, f'HELLO -> {hello}')

        # ---- A.1: RUN:pivot:90 alone ----
        log(f, '\n--- A.1: RUN:pivot:90 alone ---')
        st0 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS before -> {st0}')
        d0 = status_dict(st0)
        m = link.mark()
        t0 = time.time()
        link.send('RUN:pivot:90')
        banner_a1 = drain_for(f, link, m, t0, 5.0)
        st1 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS after -> {st1}')
        d1 = status_dict(st1)
        reset_a1 = (banner_a1 is not None) or (
            'cyc' in d0 and 'cyc' in d1 and int(d1['cyc']) < int(d0['cyc'])
        )
        log(f, f'A.1 unsolicited boot banner: {banner_a1}')
        log(f, f'A.1 cyc before={d0.get("cyc")} after={d1.get("cyc")}')
        log(f, f'A.1 RESET OBSERVED: {reset_a1}')

        time.sleep(1.0)

        # ---- A.2: RUN:square:20 with a sequenced MOVE_X mid-tour ----
        log(f, '\n--- A.2: RUN:square:20, MOVE_X mid-tour ---')
        st0 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS before -> {st0}')
        d0 = status_dict(st0)
        m = link.mark()
        t0 = time.time()
        link.send('RUN:square:20')
        time.sleep(1.0)  # give the tour a beat to actually get moving
        mid_reply = link.seqd('MOVE_X 0 500 60 3000')
        log(f, f'MOVE_X mid-tour reply -> {mid_reply}  (t={time.time() - t0:.3f}s)')
        banner_a2 = drain_for(f, link, m, t0, 10.0)
        st1 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS after -> {st1}')
        d1 = status_dict(st1)
        reset_a2 = (banner_a2 is not None) or (
            'cyc' in d0 and 'cyc' in d1 and int(d1['cyc']) < int(d0['cyc'])
        )
        log(f, f'A.2 unsolicited boot banner: {banner_a2}')
        log(f, f'A.2 RESET OBSERVED: {reset_a2}')
        log(f, f'A.2 mid-tour wire reply had explicit err: {"err" in (mid_reply or "")}')

        time.sleep(1.0)

        # ---- A.3: RUN:square:20 then RUN:abort mid-tour ----
        log(f, '\n--- A.3: RUN:square:20 then RUN:abort mid-tour ---')
        st0 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS before -> {st0}')
        d0 = status_dict(st0)
        m = link.mark()
        t0 = time.time()
        link.send('RUN:square:20')
        time.sleep(1.0)
        t_abort = time.time()
        link.send('RUN:abort')
        log(f, f'RUN:abort sent at t={t_abort - t0:.3f}s')
        banner_a3 = drain_for(f, link, m, t0, 10.0)
        st1 = link.unseq('STATUS', r'status ')
        log(f, f'STATUS after -> {st1}')
        d1 = status_dict(st1)
        reset_a3 = (banner_a3 is not None) or (
            'cyc' in d0 and 'cyc' in d1 and int(d1['cyc']) < int(d0['cyc'])
        )
        log(f, f'A.3 unsolicited boot banner: {banner_a3}')
        log(f, f'A.3 RESET OBSERVED: {reset_a3}')

        link.close()
        log(f, '\n=== Step A complete ===')


if __name__ == '__main__':
    main()
