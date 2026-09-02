"""A.3 retest: wait for a genuinely idle robot first, then RUN:square:20 + RUN:abort."""
import sys, time
from gopiv_link import Link

def log(f, msg):
    print(msg); f.write(msg+'\n'); f.flush()

out_path = sys.argv[1] if len(sys.argv) > 1 else 'step_a3_retry_transcript.txt'
with open(out_path, 'w') as f:
    link = Link()
    log(f, f'=== A.3 retest, {time.strftime("%Y-%m-%d %H:%M:%S")} ===')
    # Wait for genuinely idle (active=0 for 2 consecutive polls, 1s apart)
    idle_streak = 0
    end = time.time() + 30
    st = None
    while time.time() < end:
        st = link.unseq('STATUS', r'status ', timeout=1.0, tries=2)
        log(f, f'poll -> {st}')
        if st and 'active=0' in st:
            idle_streak += 1
        else:
            idle_streak = 0
        if idle_streak >= 2:
            break
        time.sleep(1.0)
    log(f, f'Confirmed idle: {st}')

    m = link.mark(); t0 = time.time()
    link.send('RUN:square:20')
    time.sleep(1.0)
    t_abort = time.time()
    link.send('RUN:abort')
    log(f, f'RUN:abort sent at t={t_abort-t0:.3f}s')
    printed = 0
    end = time.time() + 10.0
    banner = None
    while time.time() < end:
        lines = link.since(m)
        for ts, l in lines[printed:]:
            log(f, f'  RX t={ts-t0:.3f}s  {l}')
            if l.startswith('device NEZHA2') and banner is None:
                banner = l
        printed = len(lines)
        time.sleep(0.05)
    st1 = link.unseq('STATUS', r'status ')
    log(f, f'STATUS after -> {st1}')
    log(f, f'unsolicited boot banner: {banner}')
    link.close()
    log(f, '=== A.3 retest complete ===')
