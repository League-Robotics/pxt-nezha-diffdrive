from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import make_deploy


def test_no_otos_changes_only_boot_initializer(tmp_path):
    source = tmp_path / 'test/test.ts'
    source.parent.mkdir()
    original = "const otosBootId = diffDrive.otosBegin()\nfunction probe() { diffDrive.otosBegin() }\n"
    source.write_text(original)
    make_deploy._disable_otos_boot(tmp_path)
    assert source.read_text() == original.replace(
        'const otosBootId = diffDrive.otosBegin()', 'const otosBootId = 0')


@pytest.mark.parametrize('text', ['', 'const otosBootId = diffDrive.otosBegin()\n' * 2])
def test_no_otos_rejects_missing_or_ambiguous_initializer(tmp_path, text):
    source = tmp_path / 'test/test.ts'
    source.parent.mkdir()
    source.write_text(text)
    with pytest.raises(ValueError, match='exactly one'):
        make_deploy._disable_otos_boot(tmp_path)
    assert source.read_text() == text