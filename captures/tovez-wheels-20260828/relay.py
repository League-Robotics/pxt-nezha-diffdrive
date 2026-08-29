"""Minimal mbrelay pool client (torture 192.168.1.12:8760)."""
import socket, time

HOST, PORT = '192.168.1.12', 8760


class Relay:
    def __init__(self, channel=3, group=10, power=7, timeout=2.0):
        self.s = socket.create_connection((HOST, PORT), timeout=10)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.s.settimeout(timeout)
        self.buf = b''
        time.sleep(0.4)
        self._drain(0.5)
        # connect banner is truncated ~68% of the time; HELLO is reliable
        self.name = self._banner()
        self.cmd(f'!P {power}')
        self.cmd(f'!CG {channel} {group}')
        self.channel = channel

    def _drain(self, secs):
        t = time.time()
        while time.time() - t < secs:
            try:
                d = self.s.recv(4096)
                if not d:
                    break
                self.buf += d
            except socket.timeout:
                break
        out, self.buf = self.buf, b''
        return out.decode('utf-8', 'replace')

    def _banner(self):
        self.s.sendall(b'HELLO\r\n')
        txt = self._drain(2.0)
        for ln in txt.splitlines():
            if ln.startswith('DEVICE:RADIOBRIDGE'):
                return ln.split(':')[3]
        return '?' + txt.strip()

    def cmd(self, line, wait=0.5):
        self.s.sendall((line + '\r\n').encode())
        return self._drain(wait)

    def radio(self, text, wait=2.0):
        """Send one line over the radio via the command plane."""
        return self.cmd('> ' + text, wait)

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass
