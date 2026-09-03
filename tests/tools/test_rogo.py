"""tests/tools/test_rogo.py -- pins tools/rogo.py, the mDNS-discovering
netcat for the WiFi transport's TCP server.

No network, no subprocess: the dns-sd parsers are fed verbatim output
captured on 2026-09-02 (macOS, tovez announcing from 192.168.1.213 --
the same session's `dns-sd -G v4 tovez.local` gave that address), the
discovery order is exercised with `_dns_sd` and `resolve_host`
monkeypatched, and the pipe runs over a `socket.socketpair()`.

Run with::

    uv run pytest tests/tools/test_rogo.py
"""
import io
import pathlib
import socket
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
import rogo  # noqa: E402

# `dns-sd -L "tovez robot link" _robotlink._tcp local.`, 2026-09-02.
# Two interfaces heard the record, so the reach line repeats; the TXT
# record follows each one, indented by a space.
LOOKUP_OUT = (
    "Lookup tovez robot link._robotlink._tcp.local.\n"
    "DATE: ---Wed 02 Sep 2026---\n"
    "21:02:10.829  ...STARTING...\n"
    "21:02:10.829  tovez\\032robot\\032link._robotlink._tcp.local. can be reached at "
    "tovez.local.:7654 (interface 12) Flags: 1\n"
    " name=tovez role=robot link=v6 port=7654\n"
    "21:02:10.829  tovez\\032robot\\032link._robotlink._tcp.local. can be reached at "
    "tovez.local.:7654 (interface 12)\n"
    " name=tovez role=robot link=v6 port=7654\n"
)

# `dns-sd -B _robotlink._tcp local.`, same session.
BROWSE_OUT = (
    "Browsing for _robotlink._tcp.local.\n"
    "DATE: ---Wed 02 Sep 2026---\n"
    "21:01:54.567  ...STARTING...\n"
    "Timestamp     A/R    Flags  if Domain               Service Type         Instance Name\n"
    "21:01:54.568  Add        3   6 local.               _robotlink._tcp.     tovez robot link\n"
    "21:01:54.568  Add        2  12 local.               _robotlink._tcp.     tovez robot link\n"
)

# What dns-sd prints when nothing answers before the timeout.
LOOKUP_SILENT = (
    "Lookup zeguz robot link._robotlink._tcp.local.\n"
    "DATE: ---Wed 02 Sep 2026---\n"
    "21:02:10.829  ...STARTING...\n"
)


def test_parse_lookup_takes_host_port_and_txt():
    assert rogo.parse_lookup(LOOKUP_OUT) == (
        "tovez.local.", 7654,
        {"name": "tovez", "role": "robot", "link": "v6", "port": "7654"})


def test_parse_lookup_without_txt_line():
    text = LOOKUP_OUT.splitlines()[3] + "\n"
    assert rogo.parse_lookup(text) == ("tovez.local.", 7654, {})


def test_parse_lookup_silent_is_none():
    assert rogo.parse_lookup(LOOKUP_SILENT) is None
    assert rogo.parse_lookup("") is None


def test_parse_browse_dedupes_interfaces_and_keeps_order():
    assert rogo.parse_browse(BROWSE_OUT) == ["tovez robot link"]
    two = BROWSE_OUT + (
        "21:01:55.000  Add        2  12 local.               _robotlink._tcp.     gopiv robot link\n"
        "21:01:56.000  Rmv        0  12 local.               _robotlink._tcp.     tovez robot link\n")
    assert rogo.parse_browse(two) == ["tovez robot link", "gopiv robot link"]


def test_parse_browse_ignores_other_services():
    other = BROWSE_OUT.replace("_robotlink._tcp.", "_mbserial._tcp.")
    assert rogo.parse_browse(other) == []


def test_instance_name_matches_the_firmware_announcement():
    assert rogo.instance_name("tovez") == "tovez robot link"


def test_discover_prefers_the_srv_record(monkeypatch):
    calls = []

    def fake_dns_sd(args, timeout):
        calls.append(args)
        assert args[:2] == ["-L", "tovez robot link"]
        return LOOKUP_OUT

    monkeypatch.setattr(rogo, "_dns_sd", fake_dns_sd)
    monkeypatch.setattr(rogo, "resolve_host",
                        lambda h: {"tovez.local": "192.168.1.213"}.get(h.rstrip(".")))
    notes = []
    assert rogo.discover("tovez", log=notes.append) == ("192.168.1.213", 7654)
    assert calls == [["-L", "tovez robot link", "_robotlink._tcp", "local."]]
    assert notes and "7654" in notes[0] and "192.168.1.213" in notes[0]


def test_discover_uses_the_announced_port_not_the_default(monkeypatch):
    monkeypatch.setattr(rogo, "_dns_sd",
                        lambda args, timeout: LOOKUP_OUT.replace(":7654", ":9000"))
    monkeypatch.setattr(rogo, "resolve_host", lambda h: "10.0.0.5")
    assert rogo.discover("tovez") == ("10.0.0.5", 9000)


def test_discover_falls_back_to_name_dot_local(monkeypatch):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: LOOKUP_SILENT)
    monkeypatch.setattr(rogo, "resolve_host",
                        lambda h: "192.168.1.213" if h == "tovez.local" else None)
    notes = []
    assert rogo.discover("tovez", log=notes.append) == ("192.168.1.213", 7654)
    assert "assuming port 7654" in notes[-1]


def test_discover_returns_none_when_nothing_answers(monkeypatch):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: "")
    monkeypatch.setattr(rogo, "resolve_host", lambda h: None)
    assert rogo.discover("zeguz") is None


def test_target_skips_discovery_for_addresses(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("discovery must not run for a literal address")

    monkeypatch.setattr(rogo, "_dns_sd", boom)
    assert rogo.target("192.168.1.213") == ("192.168.1.213", 7654)
    assert rogo.target("192.168.1.213", port=7000) == ("192.168.1.213", 7000)
    monkeypatch.setattr(rogo, "resolve_host", lambda h: "192.168.1.213")
    assert rogo.target("tovez.local") == ("192.168.1.213", 7654)


def test_target_port_override_beats_the_srv_port(monkeypatch):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: LOOKUP_OUT)
    monkeypatch.setattr(rogo, "resolve_host", lambda h: "192.168.1.213")
    assert rogo.target("tovez", port=7000) == ("192.168.1.213", 7000)


def _robot():
    """A fake robot on a socketpair: banner on connect, `pong` to PING,
    echoes anything else back prefixed with `ack`."""
    host, robot = socket.socketpair()

    def serve():
        robot.sendall(b"device NEZHA2 robot tovez 3527777815\n")
        buf = b""
        try:
            while True:
                chunk = robot.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line == b"PING":
                        robot.sendall(b"pong 1\n")
                    elif line == b"BYE":
                        robot.close()
                        return
                    elif line:
                        robot.sendall(b"ack " + line + b"\n")
        except OSError:
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return host, t


def test_pipe_sends_argument_lines_and_collects_replies():
    sock, t = _robot()
    out = io.BytesIO()
    rc = rogo.pipe(sock, io.BytesIO(b""), out, lines=["PING", "STATUS"], wait=0.3)
    t.join(1.0)
    assert rc == 0
    assert out.getvalue() == (b"device NEZHA2 robot tovez 3527777815\n"
                              b"pong 1\n"
                              b"ack STATUS\n")


def test_pipe_copies_stdin_lines_until_eof():
    sock, t = _robot()
    out = io.BytesIO()
    rc = rogo.pipe(sock, io.BytesIO(b"PING\nTLM POSE #1\n"), out, wait=0.3)
    t.join(1.0)
    assert rc == 0
    assert out.getvalue().splitlines() == [
        b"device NEZHA2 robot tovez 3527777815", b"pong 1", b"ack TLM POSE #1"]


def test_pipe_reports_a_peer_close():
    sock, t = _robot()
    out = io.BytesIO()
    rc = rogo.pipe(sock, io.BytesIO(b"BYE\n"), out, wait=2.0)
    t.join(1.0)
    assert rc == 1
    assert out.getvalue() == b"device NEZHA2 robot tovez 3527777815\n"


def test_main_discover_prints_ip_and_port(monkeypatch, capsys):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: LOOKUP_OUT)
    monkeypatch.setattr(rogo, "resolve_host", lambda h: "192.168.1.213")
    assert rogo.main(["--discover", "-q", "tovez"]) == 0
    assert capsys.readouterr().out == "192.168.1.213 7654\n"


def test_main_browse_lists_instances(monkeypatch, capsys):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: BROWSE_OUT)
    assert rogo.main(["--browse"]) == 0
    assert capsys.readouterr().out == "tovez robot link\n"


def test_main_not_found_is_exit_1(monkeypatch, capsys):
    monkeypatch.setattr(rogo, "_dns_sd", lambda args, timeout: "")
    monkeypatch.setattr(rogo, "resolve_host", lambda h: None)
    assert rogo.main(["zeguz"]) == 1
    assert "not found" in capsys.readouterr().err


def test_main_requires_a_robot_or_browse():
    with pytest.raises(SystemExit) as e:
        rogo.main([])
    assert e.value.code == 2
