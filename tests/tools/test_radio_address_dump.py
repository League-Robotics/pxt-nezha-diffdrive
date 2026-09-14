"""tests/tools/test_radio_address_dump.py -- this repo's radio address map
against radio-robot-lib docs/design/radio-addressing.md (adopted
2026-09-13): tools/radio-address-dump must hash to the spec's D2 (the
cross-repo gate microbit-radio-relay's `just conformance` checks), and the
reverse map must match the spec's vectors and rejections."""
import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import make_deploy  # noqa: E402

D1 = "c22691f1c47bed3ac5317119487a30ea8fd0224d61c50bba551b1e624b548a84"
D2 = "305d6ee08cfae978fe13e1179c6047a56e1b0b1abe23c2cb757f01461cf2d35f"
DUMP = ROOT / "tools" / "radio-address-dump"


def _dump(*args):
    return subprocess.run([sys.executable, str(DUMP), *args],
                          capture_output=True, check=True).stdout


def test_dump_lists_the_python_implementation():
    assert _dump("--list").decode().split() == ["python"]


@pytest.mark.parametrize("version,digest", [("2", D2), ("1", D1)])
def test_dump_matches_the_spec_digests(version, digest):
    out = _dump("python", version)
    assert out.count(b"\n") == 3125
    assert hashlib.sha256(out).hexdigest() == digest


def test_vectors_file_matches_the_implementation():
    data = json.loads((ROOT / "docs" / "radio-address-vectors.json").read_text())
    rows = data["vectors"]
    assert rows
    for row in rows:
        name = row["name"]
        pair = (row["channel"], row["group"])
        assert make_deploy.derive_radio_from_name(name) == pair
        assert make_deploy.radio_address_to_name(*pair) == name


@pytest.mark.parametrize("channel,group", [(11, 16), (10, 15), (84, 20), (20, 14), (20, 256)])
def test_reverse_rejects_pairs_that_belong_to_no_name(channel, group):
    assert make_deploy.radio_address_to_name(channel, group) is None


@pytest.mark.parametrize("raw", ["VEVOV", " vevov "])
def test_names_normalize_before_derivation(raw):
    assert make_deploy.derive_radio_from_name(raw) == (20, 82)
