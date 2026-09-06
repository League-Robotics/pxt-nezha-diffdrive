"""Orange-dot-geometry square tour with a TIGHT harness.

The previous tour sat idle 57% of the time. That was the host, not the
robot: the old pump() always burned its whole timeout, so every STATUS
poll cost a fixed 2 s and every ack wait 3 s after the reply had already
landed. Here a reader thread drains the socket continuously and every
wait returns the instant its line appears.
"""
import json, re, socket, sys, threading, time

HOST, PORT = '192.168.1.147', 38493
# Orange-dot rectangle: corners (+-50, +-30) cm -> 100 cm and 60 cm legs
LEGS_MM = [1000, 600, 1000, 600]
PIVOT_MRAD = 1571


class Link:
    def __init__(s, host=HOST, port=PORT):
        s.sock = socket.create_connection((host, port), timeout=10)
        s.sock.settimeout(0.1)
        s.lines = []
        s.lock = threading.Lock()
        s.run = True
        s._seq = 0
        threading.Thread(target=s._rd, daemon=True).start()
        time.sleep(0.5)

    def _rd(s):
        buf = b''
        while s.run:
            try:
                d = s.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            buf += d
            while b'\n' in buf:
                r, buf = buf.split(b'\n', 1)
                t = r.decode('utf-8', 'replace').strip()
                if t:
                    with s.lock:
                        s.lines.append(t)

    def mark(s):
        with s.lock:
            return len(s.lines)

    def since(s, i):
        with s.lock:
            return s.lines[i:]

    def send(s, line):
        s.sock.sendall((line + '\r\n').encode())

    def wait(s, mark, pat, timeout):
        """Return the first matching line, as soon as it arrives."""
        rx = re.compile(pat)
        end = time.time() + timeout
        while time.time() < end:
            for l in s.since(mark):
                if rx.match(l):
                    return l
            time.sleep(0.005)          # 5 ms, not 2 s
        return None

    def unseq(s, cmd, pat, timeout=1.5, tries=3):
        for _ in range(tries):
            m = s.mark(); s.send(cmd)
            got = s.wait(m, pat, timeout)
            if got:
                return got
        return None

    def seqd(s, cmd, timeout=2.0, tries=4):
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        for _ in range(tries):
            m = s.mark(); s.send(wire)
            got = s.wait(m, r'^(ack|err)\s+%d\b' % s._seq, timeout)
            if got:
                return got
        raise RuntimeError(f'no ack for {wire!r}')

    def status(s):
        return s.unseq('STATUS', r'^status ')

    def done_count(s, tries=4):
        st = None
        for _ in range(tries):
            st = s.status()
            if st:
                break
        if not st:
            return None
        m = re.search(r'\bdone=(\d+)', st)
        return int(m.group(1)) if m else None

    def sync_seq(s):
        """Align our numbering with the robot's own `next`. HELLO resets
        expectedNext_ but NOT the cumulative `done` counter, so a
        baseline-relative wait compares against a stale-high value from
        an earlier session and never fires. Matching `next` makes the
        absolute test `done >= id` correct again."""
        st = s.status()
        if st:
            m = re.search(r'\bnext=(\d+)', st)
            if m:
                s._seq = int(m.group(1)) - 1
                return s._seq
        return None

    def await_motion(s, start_timeout=3.0, idle_frames=6, timeout=40.0):
        """Wait for the move by WATCHING THE TELEMETRY, not a counter.
        Both `done` and `next` proved unreliable across a session
        boundary -- `done` is cumulative and survives HELLO, so it reads
        stale-high and every counter test passes instantly, silently
        preempting each in-flight move with the next command. Wheel
        speed is a direct physical observation with no such history."""
        m = s.mark()
        t0 = time.time()
        moved = False
        quiet = 0
        while time.time() - t0 < timeout:
            fr = s.frames(m)
            if fr:
                m = s.mark()
                for f in fr:
                    speed = abs(f[9]) + abs(f[10])
                    if speed > 15:
                        moved = True
                        quiet = 0
                    elif moved:
                        quiet += 1
            if moved and quiet >= idle_frames:
                return True
            if not moved and time.time() - t0 > start_timeout:
                return False       # never started
            time.sleep(0.01)
        return False

    def await_id(s, want, timeout=40.0):
        """Wait until the robot reports this command id complete."""
        end = time.time() + timeout
        while time.time() < end:
            st = s.status()
            if st:
                m = re.search(r'\bdone=(\d+)', st)
                if m and int(m.group(1)) >= want:
                    return True
            time.sleep(0.02)
        return False

    def await_progress(s, baseline, timeout=40.0):
        """Wait for `done` to advance PAST a baseline captured before the
        command was issued. The counter is cumulative and survives HELLO,
        so an absolute `done >= seq` test returns instantly on a fresh
        session against a robot that has already run moves -- which
        silently preempts each in-flight move with the next one."""
        end = time.time() + timeout
        while time.time() < end:
            c = s.done_count()
            if c is not None and baseline is not None and c > baseline:
                return True
            time.sleep(0.02)
        return False

    def frames(s, i):
        out = []
        for l in s.since(i):
            p = l.split()
            if len(p) == 21 and p[0] == 't':
                try:
                    out.append([int(v) for v in p[1:]])
                except ValueError:
                    pass
        return out

    def close(s):
        try:
            s.seqd('TLM OFF')
        except Exception:
            pass
        s.run = False
        time.sleep(0.15)
        s.sock.close()


def main():
    l = Link()
    print('banner:', l.unseq('HELLO', r'^device '))
    print('seq synced to robot at', l.sync_seq())
    for c in ('SET accel 500', 'SET decel 300', 'SET jerk 4000',
              'SET plateau_min_s 0.15', 'SET max_yaw_rate 90'):
        l.seqd(c)
    print('shaping set', flush=True)

    l.seqd('TLM FULL')
    m = l.mark()
    t0 = time.time()
    for i, leg in enumerate(LEGS_MM):
        for dist, rot in ((leg, 0), (0, PIVOT_MRAD)):
            l.seqd(f'MOVE_X {dist} {rot} 300 40000')
            if not l.await_motion():
                print('  TIMEOUT waiting for completion', flush=True)
        print(f'  side {i+1} ({leg/10:.0f} cm) done  t={time.time()-t0:.1f}s',
              flush=True)
    frames = l.frames(m)
    l.seqd('TLM OFF')
    json.dump({'robot': 'gopiv', 'geometry': 'orange-dot 100x60 cm',
               'legs_mm': LEGS_MM, 'cruise': 300, 'accel': 500, 'decel': 300,
               'jerk': 4000, 'plateau': 0.15, 'yaw_cap': 90,
               'wall_s': time.time() - t0, 'frames': frames},
              open('/private/tmp/claude-501/-Volumes-Proj-proj-RobotProjects-pxt-nezha-diffdrive/101bc174-61d3-4a1f-9484-e6f0a191f653/scratchpad/tour_tight.json', 'w'))
    print(f'\nwall clock {time.time()-t0:.1f} s, {len(frames)} frames')
    l.close()


if __name__ == '__main__':
    main()
