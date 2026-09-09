"""One TCP session to tigez via hodr's mbdeploy serial daemon. Every rx
line is timestamped so ordering (ack vs funcs lines) is evidence."""
import socket, sys, time, threading
HOST, PORT = '192.168.1.148', 33661
s = socket.create_connection((HOST, PORT), timeout=10)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1); s.settimeout(0.2)
t0 = time.time(); lines = []; lock = threading.Lock(); run = True
def rd():
    buf = b''
    while run:
        try: d = s.recv(4096)
        except socket.timeout: continue
        except OSError: break
        if not d: break
        buf += d
        while b'\n' in buf:
            raw, buf = buf.split(b'\n', 1)
            t = raw.decode('utf-8', 'replace').strip('\r ')
            if t:
                with lock: lines.append((time.time() - t0, t))
                print(f'{time.time()-t0:8.3f} < {t}', flush=True)
threading.Thread(target=rd, daemon=True).start()
def send(txt, wait):
    print(f'{time.time()-t0:8.3f} > {txt}', flush=True)
    s.sendall((txt + '\n').encode()); time.sleep(wait)
for cmd, wait in [(a, float(w)) for a, w in (x.split('|') for x in sys.argv[1:])]:
    send(cmd, wait)
run = False; s.close()
