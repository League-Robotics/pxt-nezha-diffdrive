"""Radio link to a field robot through the torture relay pool.

The link is LOSSY -- 66-83% per-line delivery measured -- so every
request retries and the absence of a reply is never evidence of
absence. Sequenced verbs carry their #id and are resent with the SAME
id, because a resend that takes a fresh one presents as a numeric gap
and stalls the stream on purpose.
"""
import socket, time, re

class FieldLink:
    def __init__(s, channel, group, host='torture', port=8760):
        s.sock = socket.create_connection((host, port), timeout=15)
        s.buf = b''; s._seq = 0
        time.sleep(1.0); s.read(1.5)
        s.send_raw(f'!CG {channel} {group}'); time.sleep(0.4); s.read(0.8)
        s.send_raw('!GO'); time.sleep(0.4); s.read(0.8)

    def read(s, sec):
        end = time.time()+sec; got=[]
        s.sock.settimeout(0.25)
        while time.time() < end:
            try: c = s.sock.recv(4096)
            except socket.timeout: continue
            if not c: break
            s.buf += c
            while b'\n' in s.buf:
                r, s.buf = s.buf.split(b'\n',1)
                t = r.decode('ascii','replace').strip()
                if t.startswith('< '): t = t[2:]
                if t: got.append(t)
        return got

    def send_raw(s, line):
        s.sock.sendall(line.encode()+b'\n')

    def unseq(s, cmd, pat, tries=6, sec=1.5):
        rx = re.compile(pat)
        for _ in range(tries):
            s.send_raw(cmd)
            for t in s.read(sec):
                if rx.match(t): return t
        return None

    def seqd(s, cmd, tries=6, sec=2.0):
        """Sequenced verb. The id is fixed for all retries of THIS call."""
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        rx = re.compile(r'^(ack|err)\s+%d\b' % s._seq)
        for _ in range(tries):
            s.send_raw(wire)
            for t in s.read(sec):
                if rx.match(t): return t
        return None

    def hello(s):
        r = s.unseq('HELLO', r'^device ')
        s._seq = 0          # HELLO resets the robot's expectedNext_ to 1
        return r

    def close(s):
        try: s.sock.close()
        except Exception: pass
