"""tests/host/test_wifi_join_sequencer.py -- diffDrive::WifiJoinSequencer
(src/comms/wifi_join_sequencer.{h,cpp}) driving a real
diffDrive::WifiLink (src/comms/wifi_link.{h,cpp}, against a scripted
fake Ai-WB2-12F module, same FakeWifiUart shape test_wifi_link.py uses)
and a real diffDrive::WifiCredentialStore (src/comms/
wifi_credential_store.{h,cpp}, against a fake in-memory WifiFlashPort)
-- sprint 038 ticket 005 (SUC-004, R5: "on boot the link tries list
entries in order until one joins").

No hardware, no CODAL: this is the first host harness to exercise all
three host-portable sprint-038 pieces together, per the ticket's own
Testing Plan.

What this pins, each traced to the ticket's acceptance criteria:

* every Config WifiJoinSequencer builds sets forceExplicitJoin = true
  (the module-memory regression finding, sprint architecture's
  2026-09-10 Revision) -- the forceExplicitJoin MECHANICS themselves
  (AT+CWQAP then straight to the explicit join, no AT+CWJAP? poll, and
  the module-memory regression case) are pinned in test_wifi_link.py
  instead, per the ticket's own Files-to-modify list;
* one wrong entry (a scripted +CWJAP:2) followed by one correct entry
  reaches kReady within one boot;
* an all-wrong store cycles through its slots without wedging or
  crashing, for both a DEFINITIVE failure (advances immediately) and a
  retryable one (retries up to kMaxAttemptsPerSlot on the same slot,
  then advances anyway);
* a wire SET made mid-walk (simulated at the store level, per this
  ticket's own Testing Plan -- ticket 003's wire path is not
  necessarily integrated with this harness) is picked up on the walk's
  next pass, not only after a reboot;
* an empty store makes WifiJoinSequencer::service() a byte-for-byte
  pass-through to WifiLink::service() -- IDENTICAL observable behavior
  to driving that WifiLink directly with no sequencer at all (the
  sprint's own regression-guard success criterion).

No passphrase value in this file is anything that looks like it was
copied from a real config/wifi_secrets.json or a stakeholder's own
network, per `.claude/rules/measurement-citations.md`'s sibling rule.

Run with::

    uv run pytest tests/host/test_wifi_join_sequencer.py
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


@pytest.fixture(scope="session")
def lib(tmp_path_factory):
    path = compile_shared_lib(
        tmp_path_factory,
        sources=[_SRC_DIR / "comms" / "wifi_link.cpp",
                 _SRC_DIR / "comms" / "wifi_credential_store.cpp",
                 _SRC_DIR / "comms" / "wifi_join_sequencer.cpp",
                 _TEST_DIR / "wifi_join_sequencer_shim.cpp"],
        out_name="libwifi_join_sequencer_shim.so",
    )
    lib = ctypes.CDLL(str(path))
    lib.wjsCreate.restype = ctypes.c_void_p
    lib.wjsCreate.argtypes = []
    lib.wjsDestroy.argtypes = [ctypes.c_void_p]
    lib.wjsSetNow.argtypes = [ctypes.c_uint32]
    lib.wjsAdvance.argtypes = [ctypes.c_uint32]
    lib.wjsInject.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wjsTakeTx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.wjsTakeTx.restype = ctypes.c_int
    lib.wjsStoreSet.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p,
                                ctypes.c_char_p]
    lib.wjsStoreSet.restype = ctypes.c_int
    lib.wjsStoreClear.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wjsStoreClear.restype = ctypes.c_int
    lib.wjsBegin.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int]
    lib.wjsService.argtypes = [ctypes.c_void_p]
    for name in ("wjsLinkState", "wjsLastJoinError", "wjsCurrentSlot",
                 "wjsAttemptsOnSlot", "wjsWalking"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = ctypes.c_int
    lib.wjsLastCommand.argtypes = [ctypes.c_void_p]
    lib.wjsLastCommand.restype = ctypes.c_char_p
    lib.wjsCurrentSsid.argtypes = [ctypes.c_void_p]
    lib.wjsCurrentSsid.restype = ctypes.c_char_p
    lib.wjsCurrentHasPassword.argtypes = [ctypes.c_void_p]
    lib.wjsCurrentHasPassword.restype = ctypes.c_int
    lib.wjsMaxAttemptsPerSlot.argtypes = []
    lib.wjsMaxAttemptsPerSlot.restype = ctypes.c_int
    lib.wjsLinkBeginDirect.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                       ctypes.c_char_p, ctypes.c_char_p,
                                       ctypes.c_int, ctypes.c_int]
    return lib


class Seq:
    """A WifiJoinSequencer plus the WifiLink/WifiCredentialStore it
    drives, plus a scripted module. `step()` services once and returns
    every complete AT command line written since the last call."""

    def __init__(self, lib):
        self.lib = lib
        self.lib.wjsSetNow(1000)
        self.h = lib.wjsCreate()
        self._buf = ctypes.create_string_buffer(4096)

    def close(self):
        self.lib.wjsDestroy(self.h)

    # -- store, simulating a wire SET/CLEAR at the store level --------
    def store_set(self, slot, ssid, password):
        return self.lib.wjsStoreSet(self.h, slot, ssid.encode(), password.encode()) == 1

    def store_clear(self, slot):
        return self.lib.wjsStoreClear(self.h, slot) == 1

    # -- arm the sequencer (mirrors Protocol::serviceWifi()'s own
    # lazy-begin construction of the non-credential Config template) --
    def begin(self, hostname="tovez", port=7654, host_port=7655):
        self.lib.wjsBegin(self.h, hostname.encode(), port, host_port, 1)

    # -- module side ----------------------------------------------------
    def reply(self, text):
        data = text.encode() if isinstance(text, str) else text
        self.lib.wjsInject(self.h, data, len(data))

    def written(self):
        n = self.lib.wjsTakeTx(self.h, self._buf, 4096)
        return self._buf.raw[:n]

    def step(self, advance_ms=5):
        self.lib.wjsAdvance(advance_ms)
        self.lib.wjsService(self.h)
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
        """Drive through the CONFIGURE sequence once for whatever slot
        WifiLink was just begin()'d on."""
        for cmd in CONFIGURE_SEQUENCE:
            self.expect_command(cmd)
            self.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")

    def expect_cwqap_then_join(self, ssid, password, cwqap_reply="\r\nERROR\r\n"):
        """forceExplicitJoin's step 0/1: AT+CWQAP (tolerant), then the
        explicit AT+CWJAP= for THIS slot's own credentials -- never the
        AT+CWJAP? poll (ticket 005's whole point)."""
        self.expect_command("AT+CWQAP")
        self.reply(cwqap_reply)
        self.expect_command(f'AT+CWJAP="{ssid}","{password}"')

    def finish_bring_up(self, own_ip="192.168.1.196", mdns_ok=True, tcp_ok=True):
        """From a successful join reply already sent, drive the rest of
        bring-up (address/socket) to READY -- same sequence
        test_wifi_link.py's Link.bring_up() tail uses."""
        self.expect_command("AT+CWDHCP=1,1")
        self.reply("\r\nOK\r\n")
        self.expect_command("AT+CIPSTA?")
        self.reply(f'+CIPSTA:ip:"{own_ip}"\r\n+CIPSTA:gateway:"192.168.1.1"\r\n'
                   '+CIPSTA:netmask:"255.255.248.0"\r\n\r\nOK\r\n')
        self.expect_command('AT+CIPSTART=4,"UDP","255.255.255.255",7655,7654,2')
        self.reply("4,CONNECT\r\n\r\nOK\r\n")
        self.expect_command('AT+CIPSTART=3,"UDP","224.0.0.251",5353,5353,0')
        self.reply("3,CONNECT\r\n\r\nOK\r\n" if mdns_ok else "\r\nERROR\r\n")
        self.expect_command("AT+CIPSERVER=1,7654")
        self.reply("\r\nOK\r\n" if tcp_ok else "\r\nERROR\r\n")
        self.expect_command("AT+CIPSTO=0")
        self.reply("\r\nOK\r\n")
        self.step()
        assert self.state() == READY

    # -- introspection --------------------------------------------------
    def state(self):
        return self.lib.wjsLinkState(self.h)

    def last_join_error(self):
        return self.lib.wjsLastJoinError(self.h)

    def current_slot(self):
        return self.lib.wjsCurrentSlot(self.h)

    def attempts_on_slot(self):
        return self.lib.wjsAttemptsOnSlot(self.h)

    def walking(self):
        return self.lib.wjsWalking(self.h) == 1

    def last_command(self):
        return self.lib.wjsLastCommand(self.h).decode()

    def current_ssid(self):
        return self.lib.wjsCurrentSsid(self.h).decode()

    def current_has_password(self):
        return self.lib.wjsCurrentHasPassword(self.h) == 1


@pytest.fixture
def seq(lib):
    s = Seq(lib)
    yield s
    s.close()


# ------------------------------------------------------- module memory
# (forceExplicitJoin's own mechanics -- AT+CWQAP, no AT+CWJAP? poll,
# the badpw-boot.log regression case -- are pinned in test_wifi_link.py
# per this ticket's own Files-to-modify list; this file only pins that
# WifiJoinSequencer actually SETS the flag on every Config it builds,
# via the observable AT+CWQAP-first command sequence below.)

def test_sequencer_forces_explicit_join_on_every_slot(seq):
    assert seq.store_set(0, "Busboom Mesh", "hunter2")
    seq.begin(hostname="tovez")
    seq.configure()
    seq.expect_cwqap_then_join("Busboom Mesh", "hunter2")
    assert "AT+CWJAP?" not in seq.last_command()


# ------------------------------------------------ one wrong, one right

def test_one_wrong_entry_then_one_correct_reaches_ready_within_one_boot(seq):
    """The ticket's own headline acceptance criterion: scripted
    +CWJAP:2 on slot 0, OK on slot 1."""
    assert seq.store_set(0, "Busboom Mesh", "wrongpw000")
    assert seq.store_set(1, "Busboom Mesh", "hunter2")
    seq.begin(hostname="tovez")

    seq.configure()
    seq.expect_cwqap_then_join("Busboom Mesh", "wrongpw000")
    assert seq.current_slot() == 0
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()
    # Code 2 (wrong password) is a DEFINITIVE failure -- the advance to
    # slot 1 (and WifiLink::begin() on its Config, which resets the
    # state machine synchronously) happens within this same step(), no
    # extra poll needed.
    assert seq.current_slot() == 1
    assert seq.state() == CONFIGURE

    seq.configure()
    seq.expect_cwqap_then_join("Busboom Mesh", "hunter2")
    seq.reply("WIFI CONNECTED\r\nWIFI GOT IP\r\n\r\nOK\r\n")
    seq.step()
    assert seq.state() == ADDRESS
    seq.finish_bring_up()
    assert seq.current_slot() == 1


# --------------------------------------------------- all-wrong cycling

def test_all_wrong_store_cycles_slots_without_wedging_definitive(seq):
    """Every entry fails DEFINITIVELY (+CWJAP:2) -- the sequencer must
    keep advancing lap after lap, never stall."""
    creds = {0: ("NetA", "wrongA"), 1: ("NetB", "wrongB")}
    assert seq.store_set(0, *creds[0])
    assert seq.store_set(1, *creds[1])
    seq.begin(hostname="tovez")

    seen_slots = []
    for _ in range(6):  # three full laps over two entries
        slot = seq.current_slot()
        seen_slots.append(slot)
        seq.configure()
        seq.expect_cwqap_then_join(*creds[slot])
        seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
        seq.step()

    assert seen_slots == [0, 1, 0, 1, 0, 1]


def test_all_wrong_store_cycles_slots_without_wedging_retryable(seq, lib):
    """Every entry TIMES OUT (no +CWJAP: reply at all -- a retryable
    outcome per the policy table in wifi_join_sequencer.cpp) --
    kMaxAttemptsPerSlot retries on the SAME slot before advancing, not
    an immediate advance, and still never wedges."""
    max_attempts = lib.wjsMaxAttemptsPerSlot()
    assert max_attempts >= 1

    creds = {0: ("NetA", "timeoutA"), 1: ("NetB", "timeoutB")}
    assert seq.store_set(0, *creds[0])
    assert seq.store_set(1, *creds[1])
    seq.begin(hostname="tovez")

    seen_slots = []
    for _ in range(2 * max_attempts * 2):  # two full laps over two entries
        slot = seq.current_slot()
        seen_slots.append(slot)
        attempts_before = seq.attempts_on_slot()
        seq.configure()
        seq.expect_cwqap_then_join(*creds[slot])
        # No reply at all -- let the explicit join genuinely time out
        # (kJoinTimeout, wifi_link.h).
        seq.step(15100)
        assert seq.state() in (BACKOFF, CONFIGURE)  # CONFIGURE if this
                                                     # backoff was the
                                                     # slot's last and
                                                     # advance() already
                                                     # begin()'d the next
        # attemptsOnSlot_ resets to 0 the instant a NEW slot begins, so
        # it only keeps climbing on repeats of the SAME slot.
        if seq.current_slot() == seen_slots[-1]:
            assert seq.attempts_on_slot() == attempts_before + 1
            # Still on the SAME slot: WifiLink itself owns the retry --
            # it only restarts from AT+RST kBackoffDelay after
            # enterBackoff() (wifi_link.h), which the sequencer never
            # short-circuits. Let that much time pass before the next
            # lap's configure() expects AT+RST.
            seq.step(5100)
            assert seq.state() == CONFIGURE

    # Each slot gets exactly max_attempts tries before the sequencer
    # advances -- e.g. max_attempts=2: [0, 0, 1, 1, 0, 0, 1, 1].
    expected = []
    for lap in range(2):
        for slot in (0, 1):
            expected += [slot] * max_attempts
    assert seen_slots == expected[:len(seen_slots)]


# --------------------------------------------- wire SET picked up live

def test_wire_set_made_mid_walk_is_picked_up_without_a_reboot(seq):
    """A single wrong entry cycles on itself (definitive failure, wraps
    back to the same slot) until a SECOND, correct entry is written
    mid-walk (simulating a wire SET -- ticket 003 -- at the store
    level, per this ticket's own Testing Plan) -- picked up on the
    walk's very next pass, no reboot."""
    assert seq.store_set(0, "OnlyNet", "wrongpw000")
    seq.begin(hostname="tovez")

    seq.configure()
    seq.expect_cwqap_then_join("OnlyNet", "wrongpw000")
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()
    # Only slot 0 is occupied -- the scan wraps all the way around and
    # re-begins slot 0.
    assert seq.current_slot() == 0
    assert seq.state() == CONFIGURE

    # A wire SET lands mid-walk, providing a correct second entry.
    assert seq.store_set(1, "OnlyNet", "hunter2")

    seq.configure()
    seq.expect_cwqap_then_join("OnlyNet", "wrongpw000")
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()
    # Picked up on this very pass -- no reboot occurred.
    assert seq.current_slot() == 1

    seq.configure()
    seq.expect_cwqap_then_join("OnlyNet", "hunter2")
    seq.reply("WIFI CONNECTED\r\nWIFI GOT IP\r\n\r\nOK\r\n")
    seq.step()
    assert seq.state() == ADDRESS


# --------------------------------------------------------- empty store

def test_empty_store_is_a_pure_pass_through_to_wifilink(seq):
    """The sprint's own regression-guard success criterion: an empty
    store must produce IDENTICAL observable behavior to using WifiLink
    directly, with no WifiJoinSequencer involved at all.
    WifiJoinSequencer::begin() is deliberately NEVER called here (the
    store has zero occupied slots -- nothing was store_set()), exactly
    mirroring how Protocol::serviceWifi() begins WifiLink directly and
    never arms this class for its setupWifi()/baked precedence
    branches. What's asserted: the resulting configure -> join
    sequence is byte-for-byte the CONFIGURE_SEQUENCE
    test_wifi_link.py's own test_configure_sequence_is_verbatim_and_in_
    order pins for a bare WifiLink, and walking() -- proof this class
    ever touched the link's Config -- stays false throughout."""
    seq.lib.wjsLinkBeginDirect(seq.h, b"Busboom Mesh", b"hunter2", b"tovez",
                               7654, 7655)
    assert not seq.walking()

    for cmd in CONFIGURE_SEQUENCE:
        seq.expect_command(cmd)
        assert not seq.walking()  # never touched by the (unarmed) sequencer
        seq.reply("\r\nready\r\n" if cmd == "AT+RST" else "\r\nOK\r\n")
    seq.step()
    assert seq.state() == JOIN
    assert not seq.walking()


# --------------------------------------------- R1 introspection (038-006)
# currentSsid()/currentHasPassword() are what
# Protocol::emitWifiDebug() reads for DBG:wifi's `ssid=`/`haspw=`
# fields (sprint 038 ticket 006, sprint architecture R1). Exercised
# here directly, against the real WifiJoinSequencer -- unlike
# Protocol's own wiring, this class compiles under tests/host/, so
# this is a real test, not a source pin.

def test_current_ssid_empty_before_the_first_slot_is_begun(seq):
    """Before begin() -- or before service() has picked a slot --
    currentSsid() is "" and currentHasPassword() is false, mirroring
    currentSlot()'s own "meaningless (0) before begin" caveat. Nothing
    has called store_set()/begin() here at all."""
    assert seq.current_ssid() == ""
    assert not seq.current_has_password()


def test_current_ssid_and_has_password_reflect_the_walking_slot(seq):
    """Once the sequencer is walking, currentSsid() names the slot
    under test and currentHasPassword() reports whether ITS entry has
    a password -- never the password string itself (current_has_
    password() is a bool ctypes binding; there is no ctypes accessor
    anywhere in this harness that could return the real passphrase)."""
    assert seq.store_set(0, "Busboom Mesh", "hunter2")
    seq.begin(hostname="tovez")
    seq.step()  # arms the walk (service()'s first-pass advanceTo(0))
    assert seq.current_slot() == 0
    assert seq.current_ssid() == "Busboom Mesh"
    assert seq.current_has_password()


def test_current_has_password_false_for_open_network_slot(seq):
    """An empty stored password (a deliberate open-network entry, per
    WifiCredentialStore::set()'s own contract) must report
    haspw=false -- currentHasPassword() answers "is a password SET",
    not "is this slot occupied"."""
    assert seq.store_set(0, "Busboom Mesh", "")
    seq.begin(hostname="tovez")
    seq.step()
    assert seq.current_slot() == 0
    assert seq.current_ssid() == "Busboom Mesh"
    assert not seq.current_has_password()


def test_current_ssid_advances_with_the_walk(seq):
    """currentSsid() tracks whichever slot the walk has moved to, not
    a value frozen at the first begin() -- reusing the ticket 005
    one-wrong-then-one-correct scenario and checking the ssid/haspw
    pair at each slot along the way."""
    assert seq.store_set(0, "Busboom Mesh", "wrongpw000")
    assert seq.store_set(1, "GuestNet", "")
    seq.begin(hostname="tovez")

    seq.configure()
    seq.expect_cwqap_then_join("Busboom Mesh", "wrongpw000")
    assert seq.current_ssid() == "Busboom Mesh"
    assert seq.current_has_password()
    seq.reply("+CWJAP:2\r\n\r\nFAIL\r\n")
    seq.step()

    assert seq.current_slot() == 1
    assert seq.current_ssid() == "GuestNet"
    assert not seq.current_has_password()
