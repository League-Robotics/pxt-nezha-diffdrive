"""tests/host/test_wifi_link.py -- diffDrive::WifiLink (src/comms/
wifi_link.{h,cpp}) driven against a scripted fake Ai-WB2-12F module.

What this pins, each traced to radio-robot-lib/docs/design/wifi-link.md
(the porting authority) or to the measured record it cites:

* the configure sequence, verbatim and in order (wifi-link.md S5.2);
* the CWJAP? poll-before-command landmine (S5.3);
* CIPMUX socket shape: link 4 UDP mode 2 on :7654, remote :7655 (S5.5);
* +IPD demux in BOTH header forms, one datagram == one line, peer
  learned off the header alone (S6, S6.1);
* ONE AT+CIPSEND per outbound line, prompt-then-payload, with the
  learned peer's address on every send (S7);
* drop-don't-stall: nothing queued before ready / before a peer, a
  bounded queue that drops NEWEST, a rejected prompt that drops the
  datagram (S7, S7.1 -- the measured heap wedge);
* peer-silence forget at 60 s (S6.1);
* the >= 50 ms telemetry gate (S7.1, mandatory for every port);
* a strict step's ERROR -> backoff -> restart from AT+RST;
* the DNS-SD announcement's exact wire bytes, decoded here with a small
  RFC 1035 name parser (pointer compression included) -- the packet the
  robot multicasts is checked field-by-field, not just for substrings.

No hardware, no network: the "module" is the test replying to what the
link wrote. Run with::

    uv run pytest tests/host/test_wifi_link.py
"""
import ctypes
import pathlib
import struct

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

# WifiLink::State
DISABLED, CONFIGURE, JOIN, ADDRESS, SOCKET, READY, BACKOFF = range(7)

CONFIGURE_SEQUENCE = [
    "AT+RST", "AT", "ATE0", "AT+CIPMODE=0", "AT+CIPSERVER=0",
    "AT+CIPCLOSE=5", "AT+CIPCLOSE", "AT+CWMODE=1", "AT+CIPMUX=1",
    "AT+CIPDINFO=1",
]


@pytest.fixture(scope="session")
def lib(tmp_path_factory):
    path = compile_shared_lib(
        tmp_path_factory,
        sources=[_SRC_DIR / "comms" / "wifi_link.cpp",
                 _TEST_DIR / "wifi_link_shim.cpp"],
        out_name="libwifi_link_shim.so",
    )
    lib = ctypes.CDLL(str(path))
    lib.wlCreate.restype = ctypes.c_void_p
    lib.wlCreate.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.wlDestroy.argtypes = [ctypes.c_void_p]
    lib.wlSetNow.argtypes = [ctypes.c_uint32]
    lib.wlAdvance.argtypes = [ctypes.c_uint32]
    lib.wlInject.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wlTakeTx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wlTakeTx.restype = ctypes.c_int
    lib.wlSetRefuseWrites.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wlService.argtypes = [ctypes.c_void_p]
    lib.wlSendLine.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.wlSendLine.restype = ctypes.c_int
    lib.wlTryReceive.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wlTryReceive.restype = ctypes.c_int
    for name in ("wlState", "wlPeerKnown", "wlPeerPort", "wlRestarts", "wlDrops",
                 "wlSent", "wlReceived", "wlNewPeerEdge", "wlStateChanged",
                 "wlTelemetryAllowed", "wlMdnsOpen", "wlMdnsCount",
                 "wlClearRxCalls", "wlBaud"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = ctypes.c_int
    for name in ("wlPeerIp", "wlOwnIp", "wlLastCommand", "wlLastReply"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = ctypes.c_char_p
    lib.wlBuildMdns.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                                ctypes.c_char_p, ctypes.c_int]
    lib.wlBuildMdns.restype = ctypes.c_int
    return lib


class Link:
    """The link plus a scripted module. `step()` services the link once
    and returns every complete AT command line it wrote since the last
    call (payload bytes written after a `>` prompt are returned raw)."""

    def __init__(self, lib, ssid="Busboom Mesh", password="hunter2", hostname="tovez"):
        self.lib = lib
        self.lib.wlSetNow(1000)
        self.h = lib.wlCreate(ssid.encode(), password.encode(), hostname.encode())
        self._buf = ctypes.create_string_buffer(4096)

    def close(self):
        self.lib.wlDestroy(self.h)

    # -- module side --------------------------------------------------
    def reply(self, text):
        data = text.encode() if isinstance(text, str) else text
        self.lib.wlInject(self.h, data, len(data))

    def written(self):
        n = self.lib.wlTakeTx(self.h, self._buf, 4096)
        return self._buf.raw[:n]

    def step(self, advance_ms=5):
        self.lib.wlAdvance(advance_ms)
        self.lib.wlService(self.h)
        return self.written()

    def commands(self, advance_ms=5):
        raw = self.step(advance_ms)
        return [c for c in raw.decode("latin-1").split("\r\n") if c]

    # -- drive the scripted bring-up ----------------------------------
    def expect_command(self, text):
        """Service until the link writes exactly `text`; fail loudly if
        it writes anything else first."""
        for _ in range(50):
            cmds = self.commands()
            if cmds:
                assert cmds == [text], f"expected {text!r}, link wrote {cmds!r}"
                return
        raise AssertionError(f"link never wrote {text!r} (state {self.state()})")

    def bring_up(self, own_ip="192.168.1.196", mdns_ok=True, join_query_hits=True,
                 drain_mdns=True):
        for cmd in CONFIGURE_SEQUENCE:
            self.expect_command(cmd)
            self.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")
        self.expect_command("AT+CWJAP?")
        if join_query_hits:
            self.reply('+CWJAP:"Busboom Mesh","aa:bb",6,-50\r\n\r\nOK\r\n')
        else:
            self.reply("No AP\r\n\r\nOK\r\n")
            for _ in range(5):
                self.step(1600)  # each query times out at 1500 ms
                self.expect_command("AT+CWJAP?")
                self.reply("No AP\r\n\r\nOK\r\n")
            self.step(1600)
            self.expect_command('AT+CWJAP="Busboom Mesh","hunter2"')
            self.reply("WIFI CONNECTED\r\nWIFI GOT IP\r\n\r\nOK\r\n")
        self.expect_command("AT+CWDHCP=1,1")
        self.reply("\r\nOK\r\n")
        self.expect_command("AT+CIPSTA?")
        self.reply(f'+CIPSTA:ip:"{own_ip}"\r\n+CIPSTA:gateway:"192.168.1.1"\r\n'
                   '+CIPSTA:netmask:"255.255.248.0"\r\n\r\nOK\r\n')
        self.expect_command('AT+CIPSTART=4,"UDP","255.255.255.255",7655,7654,2')
        self.reply("4,CONNECT\r\n\r\nOK\r\n")
        self.expect_command('AT+CIPSTART=3,"UDP","224.0.0.251",5353,5353,0')
        self.reply("3,CONNECT\r\n\r\nOK\r\n" if mdns_ok else "\r\nERROR\r\n")
        self.step()
        assert self.state() == READY
        # A ready link with a socket and an address announces itself on
        # its first idle pass; most tests want that out of the way.
        if drain_mdns and mdns_ok and own_ip:
            self.drain_announcement()

    def drain_announcement(self):
        """Service through one mDNS announcement (CIPSEND on link 3,
        prompt, payload, SEND OK) and return the packet bytes."""
        cmds = self.commands()
        assert len(cmds) == 1 and cmds[0].startswith("AT+CIPSEND=3,"), cmds
        n = int(cmds[0].split(",")[1])
        self.reply(">")
        raw = self.step()
        assert len(raw) == n, (len(raw), n)
        self.reply("SEND OK\r\n")
        self.step()
        return raw

    def datagram(self, payload, ip="192.168.1.40", port=7655, link=4, extended=True):
        data = payload.encode() if isinstance(payload, str) else payload
        if extended:
            head = f'+IPD,{link},{len(data)},"{ip}",{port}:'.encode()
        else:
            head = f'+IPD,{link},{len(data)}:'.encode()
        self.reply(head + data)

    # -- link side ----------------------------------------------------
    def state(self):
        return self.lib.wlState(self.h)

    def send(self, line):
        return self.lib.wlSendLine(self.h, line.encode()) == 1

    def receive(self):
        n = self.lib.wlTryReceive(self.h, self._buf, 4096)
        return None if n < 0 else self._buf.raw[:n]


@pytest.fixture
def link(lib):
    l = Link(lib)
    yield l
    l.close()


# ------------------------------------------------------------- bring-up

def test_empty_ssid_leaves_the_link_disabled_and_silent(lib):
    l = Link(lib, ssid="")
    try:
        for _ in range(20):
            assert l.commands() == []
        assert l.state() == DISABLED
        assert not l.send("PING")
    finally:
        l.close()


def test_begin_opens_the_uart_at_115200(link):
    assert link.lib.wlBaud(link.h) == 115200


def test_configure_sequence_is_verbatim_and_in_order(link):
    """wifi-link.md S5.2: AT+RST FIRST (the RJ11-powered module keeps
    state across an nRF reset), then the exact teardown/setup list."""
    seen = []
    for cmd in CONFIGURE_SEQUENCE:
        link.expect_command(cmd)
        seen.append(cmd)
        link.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")
    assert seen == CONFIGURE_SEQUENCE
    link.step()
    assert link.state() == JOIN


def test_tolerant_configure_steps_advance_on_error(link):
    """CIPSERVER=0 / CIPCLOSE answer ERROR on a fresh module ("nothing
    to close") -- expected, not a fault."""
    for cmd in CONFIGURE_SEQUENCE:
        link.expect_command(cmd)
        if cmd in ("AT+CIPSERVER=0", "AT+CIPCLOSE=5", "AT+CIPCLOSE", "AT+CIPMODE=0"):
            link.reply("\r\nERROR\r\n")
        else:
            link.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")
    link.step()
    assert link.state() == JOIN
    assert link.lib.wlRestarts(link.h) == 0


def test_strict_configure_step_error_backs_off_and_restarts_from_rst(link):
    for cmd in CONFIGURE_SEQUENCE:
        link.expect_command(cmd)
        if cmd == "AT+CIPMUX=1":
            link.reply("\r\nERROR\r\n")
            break
        link.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")
    link.step()
    assert link.state() == BACKOFF
    assert link.lib.wlRestarts(link.h) == 1
    assert link.commands(4000) == []          # still backing off
    link.step(1100)                           # past kBackoffDelayMs
    assert link.state() == CONFIGURE
    link.expect_command("AT+RST")


def test_join_polls_cwjap_query_before_commanding_a_join(link):
    """S5.3 landmine: an explicit CWJAP fired into the module's own
    post-RST auto-rejoin answers busy/ERROR. Query first; only join
    explicitly after the polls come up empty."""
    link.bring_up(join_query_hits=False)
    assert link.state() == READY


def test_join_query_hit_skips_the_explicit_join(link):
    link.bring_up(join_query_hits=True)
    assert link.state() == READY
    assert 'AT+CWJAP="' not in link.lib.wlLastCommand(link.h).decode()


def test_ready_state_learns_own_ip_from_cipsta(link):
    link.bring_up(own_ip="192.168.4.11")
    assert link.lib.wlOwnIp(link.h) == b"192.168.4.11"


def test_mdns_socket_refusal_is_tolerated(link):
    link.bring_up(mdns_ok=False)
    assert link.state() == READY
    assert link.lib.wlMdnsOpen(link.h) == 0


def test_state_change_edge_fires_once_per_transition(link):
    assert link.lib.wlStateChanged(link.h) == 1   # DISABLED -> CONFIGURE at begin()
    assert link.lib.wlStateChanged(link.h) == 0
    link.bring_up()
    assert link.lib.wlStateChanged(link.h) == 1
    assert link.lib.wlStateChanged(link.h) == 0


# ------------------------------------------------------- inbound demux

def test_datagram_on_link_4_becomes_one_line_and_teaches_the_peer(link):
    link.bring_up()
    assert link.lib.wlPeerKnown(link.h) == 0
    link.datagram("HELLO\n", ip="192.168.1.40", port=7655)
    link.step()
    assert link.receive() == b"HELLO"        # trailing '\n' stripped
    assert link.receive() is None
    assert link.lib.wlPeerKnown(link.h) == 1
    assert link.lib.wlPeerIp(link.h) == b"192.168.1.40"
    assert link.lib.wlPeerPort(link.h) == 7655
    assert link.lib.wlReceived(link.h) == 1


def test_plain_ipd_header_form_still_delivers_payload(link):
    """CIPDINFO=0 form `+IPD,<link>,<len>:` -- payload delivered, no
    peer learned (nothing to learn from)."""
    link.bring_up()
    link.datagram("PING", extended=False)
    link.step()
    assert link.receive() == b"PING"
    assert link.lib.wlPeerKnown(link.h) == 0


def test_empty_datagram_counts_as_heard_from(link):
    """S6.1: the HEADER is the evidence -- a keepalive with no payload
    still teaches/refreshes the peer."""
    link.bring_up()
    link.datagram("", ip="192.168.1.7", port=7655)
    link.step()
    assert link.lib.wlPeerKnown(link.h) == 1
    assert link.lib.wlPeerIp(link.h) == b"192.168.1.7"
    assert link.receive() == b""


def test_payload_is_binary_safe_and_split_across_reads(link):
    link.bring_up()
    payload = b"ST\x00OP #1 OK ERROR\n"   # contains matcher tokens and a NUL
    head = f'+IPD,4,{len(payload)},"192.168.1.40",7655:'.encode()
    whole = head + payload
    link.reply(whole[:9]); link.step()
    link.reply(whole[9:30]); link.step()
    link.reply(whole[30:]); link.step()
    assert link.receive() == payload[:-1]
    assert link.state() == READY           # the "ERROR" inside payload never reached the matchers


def test_datagram_on_another_link_is_dropped(link):
    link.bring_up()
    link.datagram("noise", link=3)
    link.step()
    assert link.receive() is None
    assert link.lib.wlPeerKnown(link.h) == 0


def test_new_peer_edge_fires_once_per_new_address(link):
    link.bring_up()
    assert link.lib.wlNewPeerEdge(link.h) == 0
    link.datagram("HELLO", ip="192.168.1.40"); link.step()
    assert link.lib.wlNewPeerEdge(link.h) == 1
    link.datagram("PING", ip="192.168.1.40"); link.step()
    assert link.lib.wlNewPeerEdge(link.h) == 0     # same peer re-heard: no edge
    link.datagram("HELLO", ip="192.168.1.41"); link.step()
    assert link.lib.wlNewPeerEdge(link.h) == 1     # a genuinely different host


def test_inbound_ring_is_bounded_and_counts_drops(link):
    link.bring_up()
    for i in range(6):
        link.datagram(f"L{i}")
    link.step()
    got = []
    while (line := link.receive()) is not None:
        got.append(line)
    assert got == [b"L0", b"L1", b"L2", b"L3"]      # kRxSlots == 4, drop newest
    assert link.lib.wlDrops(link.h) == 2


# ------------------------------------------------------- outbound sends

def test_send_before_ready_or_before_a_peer_is_dropped_not_queued(link):
    assert not link.send("device x")
    link.bring_up()
    assert not link.send("device x")               # ready, but no peer yet
    assert link.commands() == []


def test_one_cipsend_per_line_prompt_then_payload_to_the_learned_peer(link):
    """S7: exactly one AT+CIPSEND per outbound line, carrying the
    learned peer's ip/port, then the payload after the '>' prompt, then
    SEND OK counts it sent."""
    link.bring_up()
    link.datagram("HELLO", ip="192.168.1.40", port=7655); link.step()
    sent0 = link.lib.wlSent(link.h)
    assert link.send("device NEZHA2 robot tovez 1")
    link.expect_command('AT+CIPSEND=4,28,"192.168.1.40",7655')
    link.reply("\r\nOK\r\n>")
    raw = link.step()
    assert raw == b"device NEZHA2 robot tovez 1\n"    # payload only, '\n' framed
    link.reply("\r\nRecv 28 bytes\r\n\r\nSEND OK\r\n")
    link.step()
    assert link.lib.wlSent(link.h) == sent0 + 1
    assert link.commands() == []                        # nothing else sent


def test_sends_are_serialized_one_in_flight_at_a_time(link):
    link.bring_up()
    link.datagram("HELLO"); link.step()
    assert link.send("a") and link.send("b")
    link.expect_command('AT+CIPSEND=4,2,"192.168.1.40",7655')
    assert link.commands(50) == []                  # 'b' waits for 'a's SEND OK
    link.reply(">"); link.step()
    link.reply("SEND OK\r\n"); link.step()
    link.expect_command('AT+CIPSEND=4,2,"192.168.1.40",7655')


def test_rejected_prompt_drops_the_datagram_and_moves_on(link):
    link.bring_up()
    link.datagram("HELLO"); link.step()
    sent0 = link.lib.wlSent(link.h)
    assert link.send("x")
    link.expect_command('AT+CIPSEND=4,2,"192.168.1.40",7655')
    link.reply("\r\nERROR\r\n"); link.step()
    assert link.lib.wlDrops(link.h) == 1
    assert link.lib.wlSent(link.h) == sent0
    assert link.state() == READY                    # a dropped frame is not a link failure


def test_prompt_timeout_drops_the_datagram(link):
    link.bring_up()
    link.datagram("HELLO"); link.step()
    assert link.send("x")
    link.expect_command('AT+CIPSEND=4,2,"192.168.1.40",7655')
    link.step(4100)
    assert link.lib.wlDrops(link.h) == 1


def test_send_queue_is_bounded_drop_newest(link):
    """S7.1 -- the measured heap wedge: the queue MUST be bounded."""
    link.bring_up()
    link.datagram("HELLO"); link.step()
    accepted = [link.send(f"line{i}") for i in range(12)]
    assert accepted == [True] * 8 + [False] * 4    # kTxSlots == 8
    assert link.lib.wlDrops(link.h) == 4


def test_peer_is_forgotten_after_60s_of_silence(link):
    link.bring_up()
    link.datagram("HELLO"); link.step()
    assert link.lib.wlPeerKnown(link.h) == 1
    link.step(59000)
    assert link.lib.wlPeerKnown(link.h) == 1
    link.step(1500)
    assert link.lib.wlPeerKnown(link.h) == 0
    assert not link.send("x")


def test_telemetry_gate_enforces_50ms_floor_and_queue_room(link):
    link.bring_up()
    assert link.lib.wlTelemetryAllowed(link.h) == 0   # no peer yet
    link.datagram("TLM POSE #1"); link.step()
    assert link.lib.wlTelemetryAllowed(link.h) == 1
    assert link.lib.wlTelemetryAllowed(link.h) == 0   # same instant: floor
    link.step(49)
    assert link.lib.wlTelemetryAllowed(link.h) == 0
    link.step(2)
    assert link.lib.wlTelemetryAllowed(link.h) == 1
    for i in range(7):
        assert link.send(f"t {i}")                     # fill to 7 of 8 slots
    link.lib.wlAdvance(100)                            # floor satisfied, queue still full
    assert link.lib.wlTelemetryAllowed(link.h) == 0   # no room for thdr + t


def test_line_over_the_wire_cap_is_clipped_not_overflowed(link):
    link.bring_up()
    link.datagram("HELLO"); link.step()
    assert link.send("x" * 300)
    link.expect_command('AT+CIPSEND=4,241,"192.168.1.40",7655')


# --------------------------------------------------------------- mDNS

def _parse_name(pkt, off):
    labels = []
    jumped = False
    end = None
    for _ in range(64):
        n = pkt[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | pkt[off + 1]
            if not jumped:
                end = off + 2
            jumped = True
            off = ptr
            continue
        labels.append(pkt[off + 1:off + 1 + n].decode())
        off += 1 + n
    return ".".join(labels), (end if end is not None else off)


def _parse_packet(pkt):
    ident, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", pkt[:12])
    assert (ident, qd, ns, ar) == (0, 0, 0, 0)
    assert flags == 0x8400, hex(flags)
    off = 12
    records = []
    for _ in range(an):
        name, off = _parse_name(pkt, off)
        rtype, rclass, ttl, rdlen = struct.unpack("!HHIH", pkt[off:off + 10])
        off += 10
        rdata = pkt[off:off + rdlen]
        rdstart = off
        off += rdlen
        records.append((name, rtype, rclass, ttl, rdata, rdstart))
    assert off == len(pkt), "trailing bytes"
    return records


def test_mdns_announcement_decodes_to_the_five_dns_sd_records(lib):
    out = ctypes.create_string_buffer(512)
    n = lib.wlBuildMdns(out, 512, b"tovez", b"192.168.1.196", 7654)
    assert 0 < n <= 256, n                          # fits one send slot
    pkt = out.raw[:n]
    recs = _parse_packet(pkt)
    assert len(recs) == 5
    by_type = {}
    for name, rtype, rclass, ttl, rdata, rdstart in recs:
        assert ttl == 120
        by_type.setdefault(rtype, []).append((name, rclass, rdata, rdstart))

    ptrs = by_type[12]
    assert [(n, c) for n, c, _, _ in ptrs] == [
        ("_services._dns-sd._udp.local", 1), ("_robotlink._udp.local", 1)]
    assert _parse_name(pkt, ptrs[0][3])[0] == "_robotlink._udp.local"
    assert _parse_name(pkt, ptrs[1][3])[0] == "tovez robot link._robotlink._udp.local"

    (srv_name, srv_class, srv_rdata, srv_start), = by_type[33]
    assert srv_name == "tovez robot link._robotlink._udp.local"
    assert srv_class == 0x8001                       # cache-flush
    prio, weight, port = struct.unpack("!HHH", srv_rdata[:6])
    assert (prio, weight, port) == (0, 0, 7654)
    assert _parse_name(pkt, srv_start + 6)[0] == "tovez.local"

    (txt_name, txt_class, txt_rdata, _), = by_type[16]
    assert txt_name == "tovez robot link._robotlink._udp.local"
    strings, i = [], 0
    while i < len(txt_rdata):
        ln = txt_rdata[i]
        strings.append(txt_rdata[i + 1:i + 1 + ln].decode())
        i += 1 + ln
    assert strings == ["name=tovez", "role=robot", "link=v6-udp", "port=7654"]

    (a_name, a_class, a_rdata, _), = by_type[1]
    assert a_name == "tovez.local"
    assert a_class == 0x8001
    assert a_rdata == bytes([192, 168, 1, 196])


def test_mdns_announcement_refuses_a_bad_ip_or_empty_host(lib):
    out = ctypes.create_string_buffer(512)
    assert lib.wlBuildMdns(out, 512, b"tovez", b"", 7654) == 0
    assert lib.wlBuildMdns(out, 512, b"tovez", b"192.168.1", 7654) == 0
    assert lib.wlBuildMdns(out, 512, b"", b"192.168.1.5", 7654) == 0
    assert lib.wlBuildMdns(out, 64, b"tovez", b"192.168.1.5", 7654) == 0   # does not fit


def test_ready_link_multicasts_the_announcement_on_link_3_and_repeats_each_minute(link):
    link.bring_up(own_ip="192.168.1.196", drain_mdns=False)
    raw = link.drain_announcement()
    recs = _parse_packet(raw)
    assert recs[4][0] == "tovez.local" and recs[4][4] == bytes([192, 168, 1, 196])
    assert link.lib.wlMdnsCount(link.h) == 1
    assert link.commands(30000) == []              # 30 s: nothing yet
    cmds = link.commands(30500)                    # 60.5 s: re-announced
    assert cmds and cmds[0].startswith("AT+CIPSEND=3,"), cmds
    assert link.lib.wlMdnsCount(link.h) == 2


def test_no_announcement_without_a_known_own_ip(link):
    link.bring_up(own_ip="")
    for _ in range(5):
        assert link.commands(20000) == []
    assert link.lib.wlMdnsCount(link.h) == 0


def test_protocol_traffic_preempts_the_announcement(link):
    """The announcer only runs when the send queue is empty -- a reply
    never waits behind a 200-byte multicast."""
    link.bring_up()
    link.datagram("HELLO"); link.step()
    link.step(30000)
    link.datagram("PING"); link.step()            # keepalive: peer stays known
    link.lib.wlAdvance(30500)                     # the next announcement is now due...
    assert link.send("ack 1 0 none")              # ...but a reply is queued first
    cmds = link.commands()
    assert cmds == ['AT+CIPSEND=4,13,"192.168.1.40",7655'], cmds
    link.reply(">"); link.step(); link.reply("SEND OK\r\n"); link.step()
    cmds = link.commands()                        # only THEN the announcement
    assert cmds and cmds[0].startswith("AT+CIPSEND=3,"), cmds
