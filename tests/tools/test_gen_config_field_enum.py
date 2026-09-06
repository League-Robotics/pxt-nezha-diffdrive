"""tests/tools/test_gen_config_field_enum.py -- the drift backstop for
`tools/gen_config_field_enum.py`.

`src/blocks/motion.ts`'s `ConfigField` enum is GENERATED from
`src/comms/config_fields.h` and committed, because PXT compiles a fixed
TypeScript file set and cannot read a C++ table at build time. A
generated-and-committed file is only as good as the discipline of
re-running the generator, and that discipline is exactly what failed
before: the enum and the wire's own name table drifted until they were
not even the same length.

So this file regenerates and compares. A field added to the header
without re-running::

    uv run python tools/gen_config_field_enum.py

fails here, in seconds, rather than shipping a block layer that
addresses a different ordinal than the wire does. The generator's own
input contract (every row needs a `// ConfigField.<Name>: "<label>"`
annotation, no duplicate names or ordinals) is tested here too, against
synthetic headers -- those are the failures that would otherwise show up
as a silently short enum.

Run with::

    uv run pytest tests/tools/test_gen_config_field_enum.py
"""

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "tools"))

import gen_config_field_enum as gen  # noqa: E402


def test_checked_in_enum_matches_a_fresh_generation():
    """The committed src/blocks/motion.ts must be byte-for-byte what the
    generator produces from the committed src/comms/config_fields.h.

    If this fails, do not hand-edit the enum: change the header if the
    field list is wrong, then run
    `uv run python tools/gen_config_field_enum.py` and commit both."""
    current = gen.MOTION_TS.read_text()
    wanted = gen.generate()
    assert current == wanted, (
        "src/blocks/motion.ts's ConfigField enum has drifted from "
        "src/comms/config_fields.h -- re-run "
        "`uv run python tools/gen_config_field_enum.py` and commit the "
        "result."
    )


def test_check_mode_agrees_with_the_committed_files():
    """`--check` is the same comparison as a CI gate would run, and must
    pass on a clean tree."""
    assert gen.main(["--check"]) == 0


def test_every_row_yields_one_enum_member():
    """One row in, one member out -- no row silently skipped for want of
    an annotation, and no member invented."""
    rows = gen.parse_fields(gen.HEADER.read_text())
    enum_block = gen.render_enum(rows)
    for _, ordinal, _, ts_name, ts_label in rows:
        assert f"    {ts_name} = {ordinal}" in enum_block, ts_name
        assert f'//% block="{ts_label}"' in enum_block, ts_name
    members = [line for line in enum_block.splitlines() if " = " in line]
    assert len(members) == len(rows)


def test_generated_enum_ordinals_match_the_table():
    """The generated numeric values ARE the wire ordinals. This is the
    property everything else rests on: blocks/motion.ts's
    setConfigValue() passes the enum's number straight into the
    setKernelValue() shim with no name-based translation at the
    crossing, so a wrong number here writes the wrong field on a real
    robot and nothing reports an error."""
    rows = gen.parse_fields(gen.HEADER.read_text())
    generated = gen.render_enum(rows)
    for _, ordinal, _, ts_name, _ in rows:
        assert f"{ts_name} = {ordinal}" in generated


def _write_header(tmp_path, table_body):
    header = tmp_path / "config_fields.h"
    header.write_text(
        "namespace diffDrive {\n"
        "constexpr ConfigFieldDescriptor kConfigFields[] = {\n"
        + table_body
        + "\n};\n}\n"
    )
    return header


def test_a_row_without_an_annotation_is_an_error(tmp_path, monkeypatch):
    """A row with no `// ConfigField.<Name>: "<label>"` above it must
    stop the generator, not be quietly skipped -- a skipped row is a
    field the wire has and the block layer does not, which is the whole
    defect this generator exists to prevent."""
    header = _write_header(tmp_path, '    {"orphan", 7, "mm"},')
    monkeypatch.setattr(gen, "HEADER", header)
    with pytest.raises(gen.GeneratorError, match="no\n?.*ConfigField"):
        gen.parse_fields(header.read_text())


def test_a_duplicate_ordinal_is_an_error(tmp_path, monkeypatch):
    """Two rows on one ordinal is two definitions of one field -- the
    exact condition the single-table rewrite exists to make
    impossible."""
    header = _write_header(
        tmp_path,
        '    // ConfigField.First: "first"\n'
        '    {"first", 7, "mm"},\n'
        '    // ConfigField.Second: "second"\n'
        '    {"second", 7, "mm"},',
    )
    monkeypatch.setattr(gen, "HEADER", header)
    with pytest.raises(gen.GeneratorError, match="duplicate ordinal"):
        gen.parse_fields(header.read_text())


def test_a_duplicate_wire_name_is_an_error(tmp_path, monkeypatch):
    """findConfigField() is a linear search, so a repeated name means
    the second row is unreachable while looking authoritative."""
    header = _write_header(
        tmp_path,
        '    // ConfigField.First: "first"\n'
        '    {"same", 7, "mm"},\n'
        '    // ConfigField.Second: "second"\n'
        '    {"same", 8, "mm"},',
    )
    monkeypatch.setattr(gen, "HEADER", header)
    with pytest.raises(gen.GeneratorError, match="duplicate wire name"):
        gen.parse_fields(header.read_text())


def test_a_missing_table_is_an_error(tmp_path, monkeypatch):
    """A header the generator cannot parse must fail loudly rather than
    emit an empty enum over a file full of live block programs."""
    header = tmp_path / "config_fields.h"
    header.write_text("namespace diffDrive {}\n")
    monkeypatch.setattr(gen, "HEADER", header)
    with pytest.raises(gen.GeneratorError, match="not found"):
        gen.parse_fields(header.read_text())
