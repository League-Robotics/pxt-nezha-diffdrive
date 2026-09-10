"""tests/host/test_wifi_protocol_seam.py -- sprint 038 ticket 006's own
acceptance criterion: "WireAdapter's wifiCred* seam reads/writes the
SAME store instance WifiJoinSequencer walks -- verified by a test that
sets a credential over the (simulated) wire and observes the sequencer
pick it up on its next wrap."

Ticket 005's own `test_wire_set_made_mid_walk_is_picked_up_without_a_
reboot` (test_wifi_join_sequencer.py) proved the WRAP-PICKUP mechanic,
but deliberately at the STORE level (`store.set(...)` directly, against
a `WifiCredentialStore` local to that one shim) -- its own header
comment says so explicitly: "ticket 003's wire path is not necessarily
integrated with this harness." This file closes exactly that gap: the
SET here goes through the REAL wire stack -- `WireHandler::
execWifiCred()` -> `WireAdapter::wifiCredSet()` -- and the
`WifiJoinSequencer` reading it back is constructed in a DIFFERENT
translation unit (`wifi_protocol_seam_shim.cpp`, vs. the WireAdapter's
own home in `wire_motion_verb_shim.cpp`), against the SAME
`diffDrive::wifiCredentialStore()` singleton both link against (one
instance per loaded shared library, not per translation unit -- see
`wifi_protocol_seam_shim.cpp`'s own header comment). If a future change
ever re-pointed WireAdapter at a second, independent store instance,
this is the test that would catch it: the SET would still ack, but the
sequencer would never see the new slot.

No hardware, no CODAL -- same host-only discipline every file in this
directory follows for src/comms/wire_adapter.cpp, wire_handler.cpp,
wifi_link.cpp, wifi_join_sequencer.cpp and wifi_credential_store.cpp
(none of them include pxt.h; only protocol.cpp does, which is why THAT
file's own tests must be source-pins instead of a run like this one).

No passphrase value in this file is anything that looks like it was
copied from a real config/wifi_secrets.json or a stakeholder's own
network, per `.claude/rules/measurement-citations.md`'s sibling rule.

Run with::

    uv run pytest tests/host/test_wifi_protocol_seam.py
"""
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

# diffDrive::WifiLink::State
DISABLED, CONFIGURE, JOIN, ADDRESS, SOCKET, READY, BACKOFF = range(7)

CONFIGURE_SEQUENCE = [
    "AT+RST", "AT", "ATE0", "AT+CIPMODE=0", "AT+CIPSERVER=0",
    "AT+CIPCLOSE=5", "AT+CIPCLOSE", "AT+CWMODE=1", "AT+CIPMUX=1",
    "AT+CIPDINFO=1",
]

_SHIM_SOURCES = [
    _SRC_DIR / "core" / "diffdrive.cpp",
    _SRC_DIR / "motion" / "motion_engine.cpp",
    _SRC_DIR / "motion" / "velocity_shaper.cpp",
    _SRC_DIR / "comms" / "wire_handler.cpp",
    _SRC_DIR / "comms" / "wire_adapter.cpp",
    _SRC_DIR / "comms" / "run_registry.cpp",
    _SRC_DIR / "comms" / "wifi_credential_store.cpp",
    # The ONE diffDrive::wifiCredentialStore() singleton definition
    # linked into this .so -- wire_motion_verb_shim.cpp's WaHandle
    # (WireAdapter) and wifi_protocol_seam_shim.cpp's WpsHandle
    # (WifiJoinSequencer) both call this same free function and so
    # share the identical store instance.
    _TEST_DIR / "wifi_credential_store_host_singleton.cpp",
    _SRC_DIR / "comms" / "wifi_link.cpp",
    _SRC_DIR / "comms" / "wifi_join_sequencer.cpp",
    _TEST_DIR / "wire_motion_verb_shim.cpp",
    _TEST_DIR / "wifi_protocol_seam_shim.cpp",
]


def _ack(n, last_done=0, reason="none"):
    return f"ack {n} {last_done} {reason}\n".encode()


@pytest.fixture(scope="session")
def lib(tmp_path_factory):
    path = compile_shared_lib(
        tmp_path_factory, sources=_SHIM_SOURCES,
        out_name="libwifi_protocol_seam_shim.so",
    )
    lib = ctypes.CDLL(str(path))

    # -- WaHandle (wire_motion_verb_shim.cpp): the real WireAdapter --
    lib.waCreate.argtypes = [
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.waCreate.restype = ctypes.c_void_p
    lib.waDestroy.argtypes = [ctypes.c_void_p]
    lib.waFeed.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waSinkLength.argtypes = [ctypes.c_void_p]
    lib.waSinkLength.restype = ctypes.c_int
    lib.waSinkRead.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.waSinkRead.restype = ctypes.c_int
    lib.waSinkClear.argtypes = [ctypes.c_void_p]

    # -- WpsHandle (wifi_protocol_seam_shim.cpp): the WifiJoinSequencer --
    lib.wpsCreate.restype = ctypes.c_void_p
    lib.wpsCreate.argtypes = []
    lib.wpsDestroy.argtypes = [ctypes.c_void_p]
    lib.wpsSetNow.argtypes = [ctypes.c_uint32]
    lib.wpsAdvance.argtypes = [ctypes.c_uint32]
    lib.wpsInject.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wpsTakeTx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wpsTakeTx.restype = ctypes.c_int
    lib.wpsBegin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int]
    lib.wpsService.argtypes = [ctypes.c_void_p]
    for name in ("wpsLinkState", "wpsCurrentSlot", "wpsCurrentHasPassword",
                 "wpsWalking"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = ctypes.c_int
    lib.wpsCurrentSsid.argtypes = [ctypes.c_void_p]
    lib.wpsCurrentSsid.restype = ctypes.c_char_p
    return lib


class Wire:
    """The real WireAdapter, driven over the v6 wire text protocol --
    only what this file needs (WIFICRED SET)."""

    def __init__(self, lib):
        self.lib = lib
        self.h = lib.waCreate(b"tovez", b"SN001", b"diffdrive", b"nezha2",
                              b"6.0.0")
        self._next_id = 1

    def close(self):
        self.lib.waDestroy(self.h)

    def wificred_set(self, slot, ssid, password):
        """Sends a real `WIFICRED SET <slot> <ssid> <password> #<id>`
        line and returns the ack/err bytes."""
        line = f"WIFICRED SET {slot} {ssid} {password} #{self._next_id}\n"
        self._next_id += 1
        self.lib.waFeed(self.h, line.encode(), len(line))
        length = self.lib.waSinkLength(self.h)
        if length == 0:
            return b""
        buf = ctypes.create_string_buffer(length)
        n = self.lib.waSinkRead(self.h, buf, length)
        assert n == length
        self.lib.waSinkClear(self.h)  # waSinkRead() does not drain the sink
        return buf.raw[:length]


class Seq:
    """The WifiJoinSequencer plus the WifiLink it drives, against the
    SAME wifiCredentialStore() singleton `Wire` above reaches through
    WireAdapter::wifiCredSet() -- same shape as
    test_wifi_join_sequencer.py's own Seq, minus the store_set()/
    store_clear() methods (this file writes the store ONLY through
    `Wire.wificred_set()`, never directly, since proving that path is
    the whole point)."""

    def __init__(self, lib):
        self.lib = lib
        self.lib.wpsSetNow(1000)
        self.h = lib.wpsCreate()
        self._buf = ctypes.create_string_buffer(4096)

    def close(self):
        self.lib.wpsDestroy(self.h)

    def begin(self, hostname="tovez", port=7654, host_port=7655):
        self.lib.wpsBegin(self.h, hostname.encode(), port, host_port, 1)

    def reply(self, text):
        data = text.encode() if isinstance(text, str) else text
        self.lib.wpsInject(self.h, data, len(data))

    def written(self):
        n = self.lib.wpsTakeTx(self.h, self._buf, 4096)
        return self._buf.raw[:n]

    def step(self, advance_ms=5):
        self.lib.wpsAdvance(advance_ms)
        self.lib.wpsService(self.h)
        return self.written()

    def commands(self, advance_ms=5):
        raw = self.step(advance_ms)
        return [c for c in raw.decode("latin-1").split("\r\n") if c]

    def expect_command(self, text):
        for _ in range(80):
            cmds = self.commands()
            if cmds:
                assert cmds == [text], f"expected {text!r}, sequencer wrote {cmds!r}"
                return
        raise AssertionError(
            f"sequencer never wrote {text!r} (state {self.state()}, "
            f"slot {self.current_slot()})")

    def configure(self):
        for cmd in CONFIGURE_SEQUENCE:
            self.expect_command(cmd)
            self.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")

    def expect_cwqap_then_join(self, ssid, password, cwqap_reply="\r\nERROR\r\n"):
        self.expect_command("AT+CWQAP")
        self.reply(cwqap_reply)
        self.expect_command(f'AT+CWJAP="{ssid}","{password}"')

    def state(self):
        return self.lib.wpsLinkState(self.h)

    def current_slot(self):
        return self.lib.wpsCurrentSlot(self.h)

    def current_ssid(self):
        return self.lib.wpsCurrentSsid(self.h).decode()

    def current_has_password(self):
        return self.lib.wpsCurrentHasPassword(self.h) == 1

    def walking(self):
        return self.lib.wpsWalking(self.h) == 1


@pytest.fixture
def wire(lib):
    w = Wire(lib)
    yield w
    w.close()


@pytest.fixture
def seq(lib):
    s = Seq(lib)
    yield s
    s.close()


def test_wifi_cred_set_over_the_wire_acks(wire):
    """Sanity: the real WireAdapter path acks a well-formed SET --
    proof the rest of this file's SETs are landing, not silently
    failing before ever reaching the store."""
    assert wire.wificred_set(0, "TestNetA", "wrongpwA0") == _ack(1)


def test_sequencer_picks_up_a_slot_set_over_the_real_wire(wire, seq):
    """The ticket's own headline case: WIFICRED SET over the real wire
    reaches the SAME store WifiJoinSequencer walks, with NOTHING set
    directly at the store level anywhere in this test."""
    assert wire.wificred_set(0, "TestNetA", "wrongpwA0") == _ack(1)
    seq.begin(hostname="tovez")
    seq.configure()
    assert seq.current_slot() == 0
    assert seq.current_ssid() == "TestNetA"
    assert seq.current_has_password()


def test_wire_set_made_mid_walk_is_picked_up_without_a_reboot(wire, seq):
    """Ticket 005's own mid-walk-pickup scenario
    (test_wifi_join_sequencer.py), replayed with BOTH SETs going
    through the real wire instead of a direct store_set() call: a
    single wrong entry cycles on itself (definitive failure, wraps back
    to the same slot) until a SECOND, correct entry is written mid-walk
    over the wire -- picked up on the walk's very next pass, no
    reboot."""
    assert wire.wificred_set(0, "OnlyNet", "wrongpw000") == _ack(1)
    seq.begin(hostname="tovez")

    seq.configure()
    seq.expect_cwqap_then_join("OnlyNet", "wrongpw000")
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()
    # Only slot 0 is occupied -- the scan wraps all the way around and
    # re-begins slot 0.
    assert seq.current_slot() == 0
    assert seq.state() == CONFIGURE

    # A WIFICRED SET over the real wire lands mid-walk, providing a
    # correct second entry -- this is the line this whole file exists
    # to prove reaches the sequencer's own store.
    assert wire.wificred_set(1, "OnlyNet", "hunter2") == _ack(2)

    seq.configure()
    seq.expect_cwqap_then_join("OnlyNet", "wrongpw000")
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()
    # Picked up on this very pass -- no reboot occurred, and the
    # credential arrived only through WireAdapter::wifiCredSet().
    assert seq.current_slot() == 1
    assert seq.current_ssid() == "OnlyNet"
    assert seq.current_has_password()
