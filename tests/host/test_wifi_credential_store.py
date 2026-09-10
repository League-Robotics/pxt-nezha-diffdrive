"""tests/host/test_wifi_credential_store.py -- diffDrive::WifiCredentialStore
(src/comms/wifi_credential_store.{h,cpp}) driven against a fake
WifiFlashPort (tests/host/wifi_flash_port_shim.cpp) backed by a plain
in-memory byte array -- no real flash, no CODAL, per sprint 038 ticket
002's own Test Strategy ("host tests drive a fake port rather than real
flash").

What this pins, each traced to the ticket's acceptance criteria:

* round-trip: a written (slot, ssid, password) reads back identically;
* list semantics: slots are independent -- writing/clearing one does
  not disturb another;
* page-boundary / record-size edges: an SSID/password at exactly the
  max length is accepted; one byte over is REJECTED, not silently
  truncated (the store deliberately does not inherit setupWifi()'s
  truncate-on-overflow behavior); an all-0xFF (erased) page reads back
  as every slot EMPTY, never as corrupted data;
* no passphrase value in this file -- every fixture string below is
  obviously fake (see .claude/rules/measurement-citations.md's sibling
  rule on secrets never being real-looking).

Run with::

    uv run pytest tests/host/test_wifi_credential_store.py
"""
import ctypes
import pathlib

import pytest

from test_kernel_harness import compile_shared_lib

_TEST_DIR = pathlib.Path(__file__).resolve().parent
_SRC_DIR = _TEST_DIR.parent.parent / "src"

# An obviously-fake fixture password -- never anything that looks like
# it was copied from a real config/wifi_secrets.json or a stakeholder's
# own network, per this ticket's own acceptance criteria.
FAKE_PASSWORD = "testpw123"


@pytest.fixture(scope="session")
def lib(tmp_path_factory):
    path = compile_shared_lib(
        tmp_path_factory,
        sources=[_SRC_DIR / "comms" / "wifi_credential_store.cpp",
                 _TEST_DIR / "wifi_flash_port_shim.cpp"],
        out_name="libwifi_credential_store_shim.so",
    )
    lib = ctypes.CDLL(str(path))
    lib.wcsCreate.restype = ctypes.c_void_p
    lib.wcsCreate.argtypes = []
    lib.wcsDestroy.argtypes = [ctypes.c_void_p]
    lib.wcsBegin.argtypes = [ctypes.c_void_p]
    lib.wcsOccupied.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wcsOccupied.restype = ctypes.c_int
    lib.wcsAnyOccupied.argtypes = [ctypes.c_void_p]
    lib.wcsAnyOccupied.restype = ctypes.c_int
    lib.wcsGet.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
    lib.wcsGet.restype = ctypes.c_int
    lib.wcsHasPassword.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wcsHasPassword.restype = ctypes.c_int
    lib.wcsSet.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p]
    lib.wcsSet.restype = ctypes.c_int
    lib.wcsClear.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wcsClear.restype = ctypes.c_int
    lib.wcsSlots.argtypes = []
    lib.wcsSlots.restype = ctypes.c_int
    lib.wcsSsidBytes.argtypes = []
    lib.wcsSsidBytes.restype = ctypes.c_int
    lib.wcsPasswordBytes.argtypes = []
    lib.wcsPasswordBytes.restype = ctypes.c_int
    lib.wcsRecordBytes.argtypes = []
    lib.wcsRecordBytes.restype = ctypes.c_int
    lib.wcsPortEraseFill.argtypes = [ctypes.c_void_p]
    lib.wcsPortByteAt.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wcsPortByteAt.restype = ctypes.c_int
    lib.wcsPortPokeByte.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.wcsPortSetRefuseWrites.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.wcsPortWriteCalls.argtypes = [ctypes.c_void_p]
    lib.wcsPortWriteCalls.restype = ctypes.c_int
    lib.wcsPortReadCalls.argtypes = [ctypes.c_void_p]
    lib.wcsPortReadCalls.restype = ctypes.c_int
    return lib


@pytest.fixture
def store(lib):
    handle = lib.wcsCreate()
    yield lib, handle
    lib.wcsDestroy(handle)


def _get(lib, handle, slot):
    ssid_buf = ctypes.create_string_buffer(lib.wcsSsidBytes())
    pw_buf = ctypes.create_string_buffer(lib.wcsPasswordBytes())
    ok = lib.wcsGet(handle, slot, ssid_buf, pw_buf)
    if not ok:
        return None
    return ssid_buf.value.decode(), pw_buf.value.decode()


def test_sizing_matches_protocol_buffers(lib):
    # 33/64 incl NUL -- matches Protocol::wifiSsid_/wifiPassword_
    # sizing, per this ticket's own record-layout requirement.
    assert lib.wcsSsidBytes() == 33
    assert lib.wcsPasswordBytes() == 64
    assert lib.wcsSlots() == 8


def test_fresh_store_is_all_empty(store):
    lib, handle = store
    lib.wcsBegin(handle)
    for slot in range(lib.wcsSlots()):
        assert lib.wcsOccupied(handle, slot) == 0
        assert _get(lib, handle, slot) is None
    assert lib.wcsAnyOccupied(handle) == 0


def test_any_occupied_true_iff_some_slot_is(store):
    # Sprint 038 ticket 005: Protocol::serviceWifi()'s lazy-begin uses
    # this to decide whether WifiJoinSequencer owns the join (a
    # non-empty store) or the setupWifi()/baked path does (an empty
    # one) -- it must not require scanning every slot at each call
    # site.
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsAnyOccupied(handle) == 0
    assert lib.wcsSet(handle, 5, b"some-net", FAKE_PASSWORD.encode()) == 1
    assert lib.wcsAnyOccupied(handle) == 1
    assert lib.wcsClear(handle, 5) == 1
    assert lib.wcsAnyOccupied(handle) == 0


def test_round_trip(store):
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsSet(handle, 0, b"classroom-net", FAKE_PASSWORD.encode()) == 1
    lib.wcsBegin(handle)  # force a re-read from the (fake) flash, not just cache reuse
    assert lib.wcsOccupied(handle, 0) == 1
    assert _get(lib, handle, 0) == ("classroom-net", FAKE_PASSWORD)


def test_round_trip_without_re_reading_begin(store):
    # set() must update the in-RAM cache itself too -- a caller should
    # not have to call begin() again just to see its own write.
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsSet(handle, 3, b"another-net", b"") == 1
    assert lib.wcsOccupied(handle, 3) == 1
    assert _get(lib, handle, 3) == ("another-net", "")


def test_open_network_has_no_password(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 1, b"open-net", b"")
    assert lib.wcsOccupied(handle, 1) == 1
    assert lib.wcsHasPassword(handle, 1) == 0


def test_has_password_true_when_set(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 1, b"secured-net", FAKE_PASSWORD.encode())
    assert lib.wcsHasPassword(handle, 1) == 1


def test_has_password_false_for_unoccupied_slot(store):
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsHasPassword(handle, 2) == 0


def test_slots_are_independent(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 0, b"net-zero", b"pw-zero-x")
    lib.wcsSet(handle, 1, b"net-one", b"pw-one-xx")
    lib.wcsSet(handle, 5, b"net-five", b"pw-five-x")

    assert _get(lib, handle, 0) == ("net-zero", "pw-zero-x")
    assert _get(lib, handle, 1) == ("net-one", "pw-one-xx")
    assert _get(lib, handle, 5) == ("net-five", "pw-five-x")
    # never written -- still empty
    for slot in (2, 3, 4, 6, 7):
        assert lib.wcsOccupied(handle, slot) == 0


def test_clearing_one_slot_does_not_disturb_others(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 0, b"net-zero", b"pw-zero-x")
    lib.wcsSet(handle, 1, b"net-one", b"pw-one-xx")

    assert lib.wcsClear(handle, 0) == 1
    lib.wcsBegin(handle)  # re-read from the fake page, not just the cache

    assert lib.wcsOccupied(handle, 0) == 0
    assert _get(lib, handle, 0) is None
    assert lib.wcsOccupied(handle, 1) == 1
    assert _get(lib, handle, 1) == ("net-one", "pw-one-xx")


def test_clear_wipes_the_password_bytes_in_flash(store):
    # Privacy requirement from this ticket's own critical context: a
    # cleared slot must not leave the old passphrase sitting in flash
    # in cleartext, readable by anything that later pokes the raw page.
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 0, b"net-zero", FAKE_PASSWORD.encode())
    lib.wcsClear(handle, 0)

    record_bytes = lib.wcsRecordBytes()
    raw = bytes(lib.wcsPortByteAt(handle, i) for i in range(record_bytes))
    assert FAKE_PASSWORD.encode() not in raw


def test_clear_out_of_range_slot_fails(store):
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsClear(handle, -1) == 0
    assert lib.wcsClear(handle, lib.wcsSlots()) == 0


def test_set_out_of_range_slot_fails(store):
    lib, handle = store
    lib.wcsBegin(handle)
    assert lib.wcsSet(handle, -1, b"x", b"y") == 0
    assert lib.wcsSet(handle, lib.wcsSlots(), b"x", b"y") == 0


def test_ssid_at_exactly_max_length_is_accepted(store):
    lib, handle = store
    lib.wcsBegin(handle)
    max_ssid = b"s" * (lib.wcsSsidBytes() - 1)  # 32 chars + NUL == 33
    assert lib.wcsSet(handle, 0, max_ssid, b"pw") == 1
    assert _get(lib, handle, 0) == (max_ssid.decode(), "pw")


def test_ssid_one_byte_over_max_is_rejected_not_truncated(store):
    lib, handle = store
    lib.wcsBegin(handle)
    over_ssid = b"s" * lib.wcsSsidBytes()  # 33 chars -- one over the 32-char cap
    assert lib.wcsSet(handle, 0, over_ssid, b"pw") == 0
    # rejected outright -- slot stays unoccupied, nothing truncated in
    assert lib.wcsOccupied(handle, 0) == 0


def test_password_at_exactly_max_length_is_accepted(store):
    lib, handle = store
    lib.wcsBegin(handle)
    max_pw = b"p" * (lib.wcsPasswordBytes() - 1)  # 63 chars + NUL == 64
    assert lib.wcsSet(handle, 0, b"net", max_pw) == 1
    assert _get(lib, handle, 0) == ("net", max_pw.decode())


def test_password_one_byte_over_max_is_rejected_not_truncated(store):
    lib, handle = store
    lib.wcsBegin(handle)
    over_pw = b"p" * lib.wcsPasswordBytes()  # 64 chars -- one over the 63-char cap
    assert lib.wcsSet(handle, 0, b"net", over_pw) == 0
    assert lib.wcsOccupied(handle, 0) == 0


def test_erased_page_reads_as_empty_not_corrupted(store):
    lib, handle = store
    lib.wcsPortEraseFill(handle)  # every byte 0xFF -- a never-written page
    lib.wcsBegin(handle)
    for slot in range(lib.wcsSlots()):
        assert lib.wcsOccupied(handle, slot) == 0
        assert _get(lib, handle, slot) is None


def test_raw_garbage_valid_byte_reads_as_empty(store):
    # A validity byte that is neither the store's own marker (0xA5) nor
    # an erased 0xFF -- e.g. flash noise -- still decodes as empty
    # rather than being trusted as an occupied record.
    lib, handle = store
    record_bytes = lib.wcsRecordBytes()
    lib.wcsPortPokeByte(handle, record_bytes - 1, 0x42)
    lib.wcsBegin(handle)
    assert lib.wcsOccupied(handle, 0) == 0
    assert _get(lib, handle, 0) is None


def test_a_write_failure_leaves_the_slot_unwritten(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsPortSetRefuseWrites(handle, 1)
    assert lib.wcsSet(handle, 0, b"net", b"pw") == 0
    lib.wcsPortSetRefuseWrites(handle, 0)
    assert lib.wcsOccupied(handle, 0) == 0


def test_begin_is_idempotent_and_re_readable(store):
    lib, handle = store
    lib.wcsBegin(handle)
    lib.wcsSet(handle, 4, b"repeat-net", b"pw-repeat")
    lib.wcsBegin(handle)
    lib.wcsBegin(handle)
    assert _get(lib, handle, 4) == ("repeat-net", "pw-repeat")
