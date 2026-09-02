"""Shared TCP link for gopiv hardware-acceptance capture scripts (sprint 028).

Adapted from captures/gopiv-profile-sweep-20260901/tight_tour.py's own
Link class (threaded reader, sub-second waits) -- copied rather than
imported per the dispatch brief ("copy into the capture dir and point
at meili's current port; do not edit the originals"). HOST/PORT are
gopiv's CURRENT farm address, resolved via zeroconf on 2026-09-02
(dns-sd -L gopiv _mbserial._tcp local. gave no output under this
harness -- resolved instead with a short python zeroconf ServiceBrowser
script using the mbdeploy pipx venv's zeroconf install; see notes.md).
"""
import re
import socket
import threading
import time

HOST, PORT = '192.168.1.150', 43181


class Link:
    def __init__(s, host=HOST, port=PORT):
        s.sock = socket.create_connection((host, port), timeout=10)
        s.sock.settimeout(0.1)
        s.lines = []
        s.lock = threading.Lock()
        s.run = True
        s._seq = 0
        s._t = threading.Thread(target=s._rd, daemon=True)
        s._t.start()
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
                        s.lines.append((time.time(), t))

    def close(s):
        s.run = False
        try:
            s.sock.close()
        except OSError:
            pass

    def mark(s):
        with s.lock:
            return len(s.lines)

    def since(s, i):
        with s.lock:
            return list(s.lines[i:])

    def send(s, line):
        s.sock.sendall((line + '\r\n').encode())

    def wait(s, mark, pat, timeout):
        rx = re.compile(pat)
        end = time.time() + timeout
        while time.time() < end:
            for ts, l in s.since(mark):
                if rx.match(l):
                    return l
            time.sleep(0.005)
        return None

    def unseq(s, cmd, pat, timeout=1.5, tries=3):
        for _ in range(tries):
            m = s.mark()
            s.send(cmd)
            got = s.wait(m, pat, timeout)
            if got:
                return got
        return None

    def seqd(s, cmd, timeout=2.0, tries=4):
        s._seq += 1
        wire = f'{cmd} #{s._seq}'
        for _ in range(tries):
            m = s.mark()
            s.send(wire)
            got = s.wait(m, rf'ack {s._seq}\b|err \d+ #{s._seq}\b|nack', timeout)
            if got:
                return got
        return None
