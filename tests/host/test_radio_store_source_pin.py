"""Text-level pins for the stored radio address (src/blocks/radiostore.ts
and program.ts), plus a Python restatement of its validation table.

tests/host/ cannot compile PXT TypeScript, so this pins the source shapes
and checks the restated rule against the bounds read from the source.

    uv run pytest tests/host/test_radio_store_source_pin.py
"""
import json
import math
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_STORE = (_ROOT / "src" / "blocks" / "radiostore.ts").read_text(encoding="utf-8")
_PROGRAM = (_ROOT / "src" / "blocks" / "program.ts").read_text(encoding="utf-8")


def _const(name: str) -> str:
    m = re.search(rf'const {name} = ("[^"]*"|\d+)', _STORE)
    assert m, name
    return m.group(1).strip('"')


CHANNEL_MAX = int(_const("radioChannelMax"))
GROUP_MAX = int(_const("radioGroupMax"))


def _error(channel, group) -> str:
    def ok(v, mx):
        return (not isinstance(v, float) or not math.isnan(v)) and 0 <= v <= mx and v == math.floor(v)

    if not ok(channel, CHANNEL_MAX):
        return "channel"
    if not ok(group, GROUP_MAX):
        return "group"
    return ""


def test_keys_are_system_settings_keys():
    assert _const("radioChannelKey") == "#radio.ch"
    assert _const("radioGroupKey") == "#radio.grp"


def test_bounds():
    assert (CHANNEL_MAX, GROUP_MAX) == (83, 255)


def test_store_is_registered_before_program_in_pxt_json():
    files = json.loads((_ROOT / "pxt.json").read_text())["files"]
    assert files.index("src/blocks/radiostore.ts") < files.index("src/blocks/program.ts")


@pytest.mark.parametrize("channel,group,expected", [
    (0, 0, ""), (83, 255, ""), (70, 12, ""), (7, 10, ""),
    (84, 10, "channel"), (-1, 10, "channel"), (1.5, 10, "channel"),
    (float("nan"), 10, "channel"),
    (10, 256, "group"), (10, -1, "group"), (10, 2.5, "group"),
])
def test_validation_table(channel, group, expected):
    assert _error(channel, group) == expected


def test_validation_source_matches_table():
    assert re.search(r'value >= 0 && value <= max && value == Math\.floor\(value\)', _STORE)
    assert re.search(r'isWholeNumberInRange\(channel, radioChannelMax\)', _STORE)
    assert re.search(r'isWholeNumberInRange\(group, radioGroupMax\)', _STORE)


def test_source_choice_order():
    m = re.search(r'function radioSourceFor\(.*?\n    }', _STORE, re.S)
    body = m.group(0)
    assert body.index('"program"') < body.index('"stored"') < body.index('"name"')


def test_set_validates_before_writing():
    m = re.search(r'function saveRadioAddress\(.*?\n    }', _PROGRAM, re.S)
    body = m.group(0)
    assert body.index("radioPairError(") < body.index("writeRadioAddress(")
    assert "radiostore.fail" in body


def test_boot_order_and_boot_line():
    m = re.search(r'export function setupRobot\(\).*', _PROGRAM, re.S)
    body = m.group(0)
    assert body.index("storedRadioAddress()") < body.index("radioSourceFor(")
    assert 'radioSource == "stored"' in body and 'radioSource == "name"' in body
    assert re.search(r'"boot radio " \+ name \+ " ch " \+ address\[0\] \+ " grp " \+ address\[1\]\s*\+ " " \+ radioSource', body)


def test_three_commands_registered_with_signatures():
    for name, sig in [
        ("_radioshow", '"()"'),
        ("_radioset", '"(channel:number=0, group:number=0)"'),
        ("_radioclear", '"()"'),
    ]:
        assert re.search(rf'onRun\("{name}"', _PROGRAM), name
        assert re.search(rf'runSignature\("{name}", {re.escape(sig)}\)', _PROGRAM), name


def test_report_names_and_keys():
    for key in ["ch", "grp", "stored", "source", "default_ch", "default_grp"]:
        assert re.search(rf'\.(num|str)\("{key}"', _PROGRAM), key
    assert "radiostore.values" in _PROGRAM and "radiostore.fail" in _PROGRAM


def test_setuprobot_jsdoc_lists_new_commands():
    doc = _PROGRAM[:_PROGRAM.index("export function setupRobot")]
    for c in ("_radioshow", "_radioset", "_radioclear"):
        assert c in doc
