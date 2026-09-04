#!/usr/bin/env python3
"""One lossless session to a farm robot's serial daemon: send lines, log every
reply with a timestamp.  Resolves the dynamic _mbserial._tcp port via dns-sd.
usage: linerun.py ROBOT LOGFILE "CMD[|wait_s]" ["CMD|wait_s" ...]
A wait_s suffix (default 1.5) is how long to collect replies after that line."""
import sys, socket, subprocess, time, re
robot, logf, cmds = sys.argv[1], sys.argv[2], sys.argv[3:]
p = subprocess.Popen(['dns-sd', '-L', robot, '_mbserial._tcp', 'local.'], stdout=subprocess.PIPE, text=True)
time.sleep(3); p.kill(); out = p.stdout.read()
m = re.search(r'can be reached at (\S+?):(\d+)', out)
if not m: raise SystemExit('dns-sd could not resolve %s: %r' % (robot, out))
host, port = m.group(1).rstrip('.'), int(m.group(2))
print('serial daemon', host, port)
s = socket.create_connection((host, port), timeout=10); s.settimeout(0.2)
log = open(logf, 'a')
def collect(sec):
    end = time.time() + sec; buf = b''
    while time.time() < end:
        try: buf += s.recv(65536)
        except socket.timeout: pass
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            t = line.decode('utf-8', 'replace').strip()
            if t:
                print('  <', t); log.write('%.3f < %s\n' % (time.time(), t))
time.sleep(0.5); collect(0.5)
for c in cmds:
    cmd, _, w = c.partition('|'); w = float(w) if w else 1.5
    print('>', cmd); log.write('%.3f > %s\n' % (time.time(), cmd)); log.flush()
    s.sendall((cmd + '\r\n').encode()); collect(w)
log.close(); s.close()
