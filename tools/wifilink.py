#!/usr/bin/env python3
"""The robot over WiFi: a UDP link to the v6 wire on port 7654, plus
discovery.

The firmware's WiFi transport (src/comms/wifi_link.h) learns the host
from the FIRST datagram it receives, so this end binds a FIXED local
port (7655 -- radio-robot-lib/docs/design/wifi-link.md section 2) rather
than an ephemeral one: a host that restarts reclaims the same port and
the robot keeps talking to it. It forgets a host after 60 s of silence,
so a session that only watches telemetry sends a bare-newline keepalive
every 15 s (the firmware drops an empty line as framing, never as a
malformed command).

Three ways to find the robot, in the order a bench script should try:

  1. `--host <ip>`                  you already know it
  2. mDNS: `discover_mdns("tovez")` the robot announces `tovez.local`
                                    and "tovez robot link" on
                                    `_robotlink._udp` every 60 s; this
                                    asks the OS resolver (dns-sd /
                                    getaddrinfo), which caches it
  3. broadcast: `discover_broadcast()`
                                    HELLO to the subnet broadcast on
                                    :7654; the first `device ...` banner
                                    back names the robot and its address

    from wifilink import WifiLink, discover
    link = WifiLink(discover('tovez'))
    print(link.ask('HELLO'))
    link.close()

Also a CLI:

    uv run python tools/wifilink.py --robot tovez HELLO PING ID
    uv run python tools/wifilink.py --host 192.168.1.196 "STATUS"
    uv run python tools/wifilink.py --discover           # just find it
"""
import argparse
import socket
import subprocess
import sys
import threading
import time

ROBOT_PORT = 7654
LOCAL_PORT = 7655
KEEPALIVE_S = 15.0
DISCOVERY_S = 8.0


def _subnet_broadcasts():
    """Every IPv4 broadcast address this machine has, plus the limited
    broadcast. macOS/Linux: parse `ifconfig`; failing that, just the
    limited broadcast."""
    out = set(["255.255.255.255"])
    try:
        text = subprocess.run(["ifconfig"], capture_output=True, text=True,
                              timeout=5).stdout
        for line in text.splitlines():
            if "broadcast" in line:
                out.add(line.split("broadcast")[1].split()[0])
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(out)


def discover_broadcast(robot=None, timeout=DISCOVERY_S, local_port=LOCAL_PORT):
    """Broadcast HELLO until a `device NEZHA2 robot <name> <serial>`
    banner comes back (any robot, or only `robot`). Returns
    (ip, name) or None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("", local_port))
    s.settimeout(0.5)
    end = time.time() + timeout
    try:
        while time.time() < end:
            for addr in _subnet_broadcasts():
                try:
                    s.sendto(b"HELLO\n", (addr, ROBOT_PORT))
                except OSError:
                    pass
            deadline = time.time() + 1.0
            while time.time() < deadline:
                try:
                    data, (ip, _port) = s.recvfrom(4096)
                except socket.timeout:
                    continue
                for line in data.decode("ascii", "replace").splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and parts[0] == "device" and parts[2] == "robot":
                        if robot is None or parts[3] == robot:
                            return ip, parts[3]
    finally:
        s.close()
    return None


def discover_mdns(robot, timeout=DISCOVERY_S):
    """Resolve `<robot>.local` through the OS resolver, which caches the
    robot's own mDNS announcements. Returns the IP or None. Tries
    getaddrinfo first (works on macOS and on Linux with avahi), then
    `dns-sd -G` on macOS as a fallback that forces a fresh lookup."""
    host = f"{robot}.local"
    end = time.time() + timeout
    while time.time() < end:
        try:
            for _fam, _t, _p, _c, sa in socket.getaddrinfo(host, ROBOT_PORT,
                                                          socket.AF_INET,
                                                          socket.SOCK_DGRAM):
                return sa[0]
        except socket.gaierror:
            pass
        try:
            out = subprocess.run(["dns-sd", "-G", "v4", host], capture_output=True,
                                 text=True, timeout=2.0).stdout
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        except OSError:
            out = ""
        for line in out.splitlines():
            cols = line.split()
            if host in line and len(cols) >= 6 and cols[-2].count(".") == 3:
                return cols[-2]
            for c in cols:
                if c.count(".") == 3 and all(p.isdigit() for p in c.split(".")):
                    return c
        time.sleep(0.5)
    return None


def browse_mdns(timeout=4.0):
    """`dns-sd -B _robotlink._udp` for `timeout` seconds; returns the
    instance names seen (e.g. ['tovez robot link']). macOS only."""
    try:
        p = subprocess.run(["dns-sd", "-B", "_robotlink._udp"], capture_output=True,
                           text=True, timeout=timeout)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
    except OSError:
        return []
    names = []
    for line in out.splitlines():
        if "_robotlink._udp." in line and " Add " in line:
            names.append(line.split("_robotlink._udp.")[1].strip())
    return names


def discover(robot, timeout=DISCOVERY_S, quiet=False):
    """mDNS first, then broadcast. Returns the IP, or exits."""
    ip = discover_mdns(robot, timeout=min(timeout, 4.0))
    if ip:
        if not quiet:
            print(f"wifilink: {robot}.local -> {ip} (mDNS)", file=sys.stderr)
        return ip
    got = discover_broadcast(robot, timeout=timeout)
    if got:
        if not quiet:
            print(f"wifilink: {got[1]} answered HELLO from {got[0]} (broadcast)",
                  file=sys.stderr)
        return got[0]
    sys.exit(f"wifilink: {robot} not found by mDNS ({robot}.local) or by "
             f"broadcast HELLO on :{ROBOT_PORT} within {timeout:.0f}s -- is the "
             "module joined? (watch the robot's USB for `DBG:wifi state=5`)")


class WifiLink:
    """One UDP socket, the `ask()`/`read()` shape tools/wire_acceptance.py's
    other links share, with a background keepalive."""

    def __init__(self, host, port=ROBOT_PORT, local_port=LOCAL_PORT):
        self.host, self.port = host, port
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.s.bind(("", local_port))
        self.s.settimeout(0.1)
        self.buf = b""
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._last_tx = time.time()
        self._ka = threading.Thread(target=self._keepalive, daemon=True)
        self._ka.start()

    def _keepalive(self):
        while not self._stop.wait(1.0):
            if time.time() - self._last_tx >= KEEPALIVE_S:
                self.send(b"\n")

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        with self.lock:
            self.s.sendto(data, (self.host, self.port))
            self._last_tx = time.time()

    def read(self, sec):
        end = time.time() + sec
        got = []
        while time.time() < end:
            try:
                c, _ = self.s.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            self.buf += c
            # one datagram carries one or more complete lines
            while b"\n" in self.buf:
                r, self.buf = self.buf.split(b"\n", 1)
                t = r.decode("ascii", "replace").strip()
                if t:
                    got.append(t)
            if self.buf and not self.buf.endswith(b"\n"):
                # a datagram without a terminator is still one whole line
                t = self.buf.decode("ascii", "replace").strip()
                self.buf = b""
                if t:
                    got.append(t)
        return got

    def ask(self, line, sec=0.8):
        self.send(line.rstrip("\n") + "\n")
        return self.read(sec)

    def close(self):
        self._stop.set()
        self.s.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", help="robot IP (skip discovery)")
    ap.add_argument("--robot", default="tovez", help="robot name for discovery")
    ap.add_argument("--discover", action="store_true",
                    help="only discover and print the address")
    ap.add_argument("--browse", action="store_true",
                    help="list _robotlink._udp instances seen over mDNS")
    ap.add_argument("--wait", type=float, default=1.0, help="seconds to read after each line")
    ap.add_argument("lines", nargs="*", help="wire lines to send, in order")
    a = ap.parse_args()
    if a.browse:
        for name in browse_mdns():
            print(name)
        return 0
    host = a.host or discover(a.robot)
    if a.discover:
        print(host)
        return 0
    link = WifiLink(host)
    try:
        for line in a.lines or ["HELLO"]:
            print(f"> {line}")
            for t in link.ask(line, a.wait):
                print(f"< {t}")
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
