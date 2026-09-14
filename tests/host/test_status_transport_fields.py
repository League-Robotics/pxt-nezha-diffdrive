"""tests/host/test_status_transport_fields.py -- STATUS reports the WiFi
link and the radio link (with its channel and group) through the REAL
WireAdapter.

test_wire_grammar.py pins the formatting against a fake adapter; this file
proves WireAdapter::status() actually fills the four fields from
Protocol's hooks (protocolWifiConnected(), protocolRadioEnabled(),
protocolRadioChannel(), protocolRadioGroup()). Those hooks live in the
pxt.h-bound protocol.cpp, so wire_motion_verb_shim.cpp stubs them with
values waSetTransportStatus() sets.

Run with::

    uv run pytest tests/host/test_status_transport_fields.py
"""
import ctypes

import pytest

from test_config_surface_single_source import (
    WireAdapterHandle,
    _SHIM_SOURCES,
    _bind,
)
from test_kernel_harness import compile_shared_lib


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    path = compile_shared_lib(tmp_path_factory, sources=_SHIM_SOURCES,
                              out_name="libstatus_transport_shim.so")
    lib = _bind(ctypes.CDLL(str(path)))
    lib.waSetTransportStatus.argtypes = [ctypes.c_int] * 4
    lib.waSetTransportStatus.restype = None
    yield lib
    lib.waSetTransportStatus(0, 0, 0, 0)


def _status(lib, wifi, radio, channel, group):
    lib.waSetTransportStatus(wifi, radio, channel, group)
    with WireAdapterHandle(lib) as wa:
        wa.feed(b"STATUS\n")
        return wa.take_sink().decode()


def _fields(line):
    return dict(tok.split("=", 1) for tok in line.split()[1:] if "=" in tok)


def test_status_reports_wifi_connected_and_radio_channel_group(lib):
    line = _status(lib, wifi=1, radio=0, channel=55, group=114)
    fields = _fields(line)
    assert (fields["wifi"], fields["radio"]) == ("1", "0")
    assert (fields["channel"], fields["group"]) == ("55", "114")


def test_status_reports_radio_enabled_and_wifi_down(lib):
    fields = _fields(_status(lib, wifi=0, radio=1, channel=37, group=43))
    assert (fields["wifi"], fields["radio"]) == ("0", "1")
    assert (fields["channel"], fields["group"]) == ("37", "43")


def test_existing_status_keys_are_unchanged(lib):
    """The new keys are appended; every key a parser already reads is
    still present and `reason=` still precedes them."""
    line = _status(lib, wifi=1, radio=1, channel=25, group=19)
    keys = [tok.split("=", 1)[0] for tok in line.split()[1:]]
    for key in ("ready", "active", "connL", "connR", "otos", "wedge", "flags",
                "i2cf", "cyc", "tlm", "next", "done", "reason"):
        assert key in keys
    assert keys[-4:] == ["wifi", "radio", "channel", "group"]
