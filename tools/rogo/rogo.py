#!/usr/bin/env python3
"""rogo -- `nc` for a robot: find it by mDNS, then pipe stdin/stdout to
its v6 wire over WiFi.

The Planet X Ai-WB2-12F transport (the firmware's `wifi_link` module,
on the wifi-transport branch) announces every robot over DNS-SD as the
instance "`<name> robot link`" on `_robotlink._tcp` (and `_udp`), with
an SRV record naming `<name>.local` and the TCP server's port, and a
TXT record `name=<name> role=robot link=v6 port=<port>`. The TCP
server is a plain line stream, like USB: connect, get the `device ...`
banner, type lines, read lines. That is everything rogo does:

    rogo tovez                      # interactive: type verbs, see replies
    rogo tovez PING STATUS          # send these lines, print replies, exit
    echo 'TLM POSE #1' | rogo tovez --wait 5
    rogo --browse                   # who is announcing on _robotlink._tcp
    rogo --discover tovez           # print "<ip> <port>" and exit
    rogo 192.168.1.213              # skip discovery (port 7654)
    rogo tovez.local --port 7654    # a hostname is fine too

Discovery, in order:

  1. `dns-sd -L "<name> robot link" _robotlink._tcp local.` -- the
     robot's own announcement, which carries the PORT. This is the
     authority; the port is whatever the robot says it is.
  2. `<name>.local` through the OS resolver on the default port 7654 --
     the robot also announces its A record, and macOS caches it. Used
     only when (1) turns up nothing in time.

Both are passive. The robot only ANNOUNCES (an unsolicited response
every 60 s, TTL 120) and answers no mDNS queries, so a host that has
not heard an announcement yet can wait up to a minute for either path;
a host that has (mDNSResponder caches the records) answers both
instantly. rogo never sends the UDP broadcast `HELLO` that
tools/wifilink.py's discover() falls back to, because `HELLO` is a
session reset on the robot and TCP and UDP share one sequence counter.

An argument that already looks like an address (an IPv4 literal or
anything with a dot in it) skips discovery.

What the TCP server does (per the wifi-transport branch's
wifi_link module and its tovez verification, captures/tovez-wifi-20260902/
in that worktree): on connect the robot sends the `device NEZHA2 robot
<name> <serial>` banner and one `DBG:wifi state=... ip=... tcp=...`
status line; lines are `\n`-terminated (`\r` is stripped), at most 240
bytes, and an overlong line is discarded whole; up to three clients
may be connected and replies go to whichever client spoke LAST, so a
second rogo steals the first one's replies until it speaks again.

Only the standard library; runs under `uv run python tools/rogo/rogo.py`
or bare `python3`. `dns-sd` is macOS's; on a host without it step (1)
is skipped and step (2) needs an mDNS-aware resolver (avahi).

Wire reminders, since this is a raw pipe with no help from the tool:
sequenced verbs (`GET SET TLM STOP RUN WHEELS_* MOVE_* GO_TO_*`) need a
trailing `#<id>` counting from 1 or the robot silently drops them;
`HELLO` resets that count (it is a session reset, not a liveness
probe -- use `PING`), and since the TCP and UDP planes share the
counter, start a session with `HELLO` and then count from 1. `ESTOP`
latches until the board reboots.

dns-sd output formats this parses were captured 2026-09-02 on the
author's Mac with tovez announcing (the verbatim samples are the
fixtures in tests/tools/test_rogo.py). MEASURED tovez 2026-09-03,
captures/rogo-tovez-20260903/: discovery, argument mode, stdin mode,
by-IP and the `just` recipe all answered (banner, pong, status, id).
"""
import argparse
import re
import socket
import subprocess
import sys
import threading

DEFAULT_PORT = 7654
SERVICE = "_robotlink._tcp"
LOOKUP_TIMEOUT_S = 3.0
BROWSE_TIMEOUT_S = 3.0
DEFAULT_WAIT_S = 1.0

# `dns-sd -L` prints one of these per interface the record was heard
# on; the instance name has spaces escaped as `\032`.
_REACH_RE = re.compile(r"can be reached at (\S+?):(\d+)\b")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def instance_name(robot):
    """The DNS-SD instance the firmware announces for `robot`."""
    return f"{robot} robot link"


def _dns_sd(args, timeout):
    """Run `dns-sd` for up to `timeout` seconds and return whatever it
    printed. dns-sd never exits on its own, so the timeout is the normal
    path, not an error; its partial output is the result. Returns '' if
    there is no dns-sd on this host."""
    try:
        p = subprocess.run(["dns-sd", *args], capture_output=True, text=True,
                           timeout=timeout)
        return p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return out or ""
    except OSError:
        return ""


def parse_lookup(text):
    """From `dns-sd -L` output, the (host, port, txt) the service can be
    reached at, or None. `txt` is the TXT record as a dict (empty if
    absent). The first `can be reached at` line wins; the TXT line, when
    present, is the line after it."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _REACH_RE.search(line)
        if not m:
            continue
        host, port = m.group(1), int(m.group(2))
        txt = {}
        if i + 1 < len(lines) and lines[i + 1].startswith(" "):
            for item in lines[i + 1].split():
                k, _, v = item.partition("=")
                txt[k] = v
        return host, port, txt
    return None


def parse_browse(text, service=SERVICE):
    """From `dns-sd -B` output, the instance names added, in first-seen
    order, once each (the same instance shows up once per interface)."""
    names = []
    marker = f"{service}."
    for line in text.splitlines():
        cols = line.split(None, 6)
        if len(cols) == 7 and cols[1] == "Add" and cols[5] == marker:
            name = cols[6].strip()
            if name not in names:
                names.append(name)
    return names


def browse(timeout=BROWSE_TIMEOUT_S):
    """Instance names currently announcing on `_robotlink._tcp`."""
    return parse_browse(_dns_sd(["-B", SERVICE, "local."], timeout))


def resolve_host(host):
    """`host` -> IPv4 address string, or None. Accepts a literal."""
    host = host.rstrip(".")
    if _IPV4_RE.match(host):
        return host
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        return None
    return infos[0][4][0] if infos else None


def discover(robot, timeout=LOOKUP_TIMEOUT_S, log=None):
    """(ip, port) for `robot`, or None. See the module docstring for
    the order. `log` gets a one-line note about which path answered."""
    log = log or (lambda _msg: None)
    found = parse_lookup(_dns_sd(["-L", instance_name(robot), SERVICE, "local."],
                                 timeout))
    if found:
        host, port, txt = found
        ip = resolve_host(host)
        if ip:
            log(f"rogo: {instance_name(robot)!r} -> {host}:{port} -> {ip}"
                + (f" (txt {' '.join(f'{k}={v}' for k, v in txt.items())})" if txt else ""))
            return ip, port
        log(f"rogo: {SERVICE} says {host}:{port} but {host} does not resolve")
    ip = resolve_host(f"{robot}.local")
    if ip:
        log(f"rogo: no {SERVICE} record for {robot!r} within {timeout:.0f}s; "
            f"{robot}.local -> {ip}, assuming port {DEFAULT_PORT}")
        return ip, DEFAULT_PORT
    return None


def target(arg, port=None, timeout=LOOKUP_TIMEOUT_S, log=None):
    """Turn the positional argument into (ip, port). A literal address
    or dotted hostname skips discovery; a bare name is a robot."""
    if "." in arg or _IPV4_RE.match(arg):
        ip = resolve_host(arg)
        if not ip:
            return None
        return ip, port or DEFAULT_PORT
    got = discover(arg, timeout=timeout, log=log)
    if not got:
        return None
    return got[0], (port or got[1])


def pipe(sock, inp, out, lines=None, wait=DEFAULT_WAIT_S):
    """The netcat part. `sock` is a connected stream socket; everything
    it sends goes to `out` (a binary writer) as it arrives. If `lines`
    is given they are sent (newline-terminated) instead of reading
    `inp`; otherwise `inp` (a binary reader, normally stdin) is copied
    to the socket line by line until EOF. After the input ends, keep
    reading for `wait` seconds so trailing replies are not cut off.
    Returns 0 if the socket was still open when we chose to leave, 1
    if the peer closed it first."""
    closed = threading.Event()

    def reader():
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                out.write(chunk)
                out.flush()
        except OSError:
            pass
        closed.set()

    def send(line):
        if isinstance(line, str):
            line = line.encode()
        if not line.endswith(b"\n"):
            line += b"\n"
        try:
            sock.sendall(line)
        except OSError:
            closed.set()

    rt = threading.Thread(target=reader, daemon=True)
    rt.start()
    peer_closed = False
    try:
        if lines is not None:
            for line in lines:
                if closed.is_set():
                    break
                send(line)
        else:
            input_done = threading.Event()

            def feeder():
                try:
                    for line in iter(inp.readline, b""):
                        if closed.is_set():
                            break
                        send(line)
                finally:
                    input_done.set()

            # a daemon so a process leaving on a closed socket is not
            # held hostage by a readline() blocked on the terminal
            threading.Thread(target=feeder, daemon=True).start()
            while not input_done.is_set() and not closed.is_set():
                input_done.wait(0.1)
        closed.wait(wait)
        # decide before our own shutdown makes the reader set `closed`
        peer_closed = closed.is_set()
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        rt.join(1.0)
    return 1 if peer_closed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rogo", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("robot", nargs="?",
                    help="robot name (tovez), or a host/IP to skip discovery")
    ap.add_argument("lines", nargs="*",
                    help="wire lines to send instead of reading stdin")
    ap.add_argument("--port", type=int,
                    help=f"override the announced port (default {DEFAULT_PORT} "
                         "when discovery is skipped)")
    ap.add_argument("--wait", type=float, default=DEFAULT_WAIT_S,
                    help="seconds to keep reading after input ends (default %(default)s)")
    ap.add_argument("--timeout", type=float, default=LOOKUP_TIMEOUT_S,
                    help="seconds to wait for the mDNS lookup (default %(default)s)")
    ap.add_argument("--browse", action="store_true",
                    help=f"list the instances announcing on {SERVICE} and exit")
    ap.add_argument("--discover", action="store_true",
                    help="print '<ip> <port>' and exit without connecting")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="no discovery notes on stderr")
    a = ap.parse_args(argv)

    def log(msg):
        if not a.quiet:
            print(msg, file=sys.stderr, flush=True)

    if a.browse:
        for name in browse():
            print(name)
        return 0
    if not a.robot:
        ap.error("a robot name or address is required (or --browse)")

    got = target(a.robot, port=a.port, timeout=a.timeout, log=log)
    if not got:
        print(f"rogo: {a.robot!r} not found -- no {SERVICE} announcement and "
              f"{a.robot}.local does not resolve. Is the module joined? "
              "(the board's USB prints `DBG:wifi state=5 ip=...` when it is; "
              f"`dns-sd -B {SERVICE}` shows who is announcing)", file=sys.stderr)
        return 1
    ip, port = got
    if a.discover:
        print(f"{ip} {port}")
        return 0

    try:
        sock = socket.create_connection((ip, port), timeout=5.0)
    except OSError as e:
        print(f"rogo: connect {ip}:{port}: {e}", file=sys.stderr)
        return 1
    sock.settimeout(None)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    log(f"rogo: connected to {ip}:{port}")
    try:
        rc = pipe(sock, sys.stdin.buffer, sys.stdout.buffer,
                  lines=a.lines or None, wait=a.wait)
    except KeyboardInterrupt:
        return 130
    if rc:
        log("rogo: peer closed the connection")
    return rc


if __name__ == "__main__":
    sys.exit(main())
