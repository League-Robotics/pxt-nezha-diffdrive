#!/usr/bin/env python3
"""Generate ``src/blocks/motion.ts``'s ``ConfigField`` enum from
``src/comms/config_fields.h``.

The C++ table in that header is the single source of the wire's config
surface: one row per name a host can ``SET``/``GET``, each carrying its
ordinal and its unit. ``wire_adapter.cpp`` includes the header directly
and ``shims.cpp`` binds behaviour to the same ordinals. The block layer
cannot: PXT compiles a fixed TypeScript file set and has no way to read
a C++ table at build time, so the ``ConfigField`` enum has to be
*generated* from it and committed.

Each row in the header carries a comment line directly above it::

    // ConfigField.MaxDuty: "max duty %"
    {"max_duty", 0, "%"},

giving that row's TypeScript member name and its ``//% block=`` dropdown
label. A row without one is an error, not a skipped field -- that is
what keeps the enum from silently falling behind the table.

**When to re-run.** Whenever a row in ``src/comms/config_fields.h`` is
added, removed, renamed, renumbered, or has its ``ConfigField`` comment
edited::

    uv run python tools/gen_config_field_enum.py

Then commit the resulting ``src/blocks/motion.ts`` alongside the header
change. ``tests/tools/test_gen_config_field_enum.py`` regenerates and
compares, so a forgotten run fails the suite rather than shipping a
block layer that addresses the wrong ordinal.

``--check`` reports drift without writing (exit 1 on drift); ``--stdout``
prints the generated enum block instead of editing the file.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HEADER = _REPO_ROOT / "src" / "comms" / "config_fields.h"
MOTION_TS = _REPO_ROOT / "src" / "blocks" / "motion.ts"

_TABLE_RE = re.compile(r"kConfigFields\[\]\s*=\s*\{(.*?)\n\};", re.DOTALL)
_ROW_RE = re.compile(r'^\s*\{"([A-Za-z0-9_]+)",\s*(\d+),\s*"([^"]*)"\},\s*$')
_ANNOTATION_RE = re.compile(r'^\s*//\s*ConfigField\.(\w+):\s*"(.*)"\s*$')
_ENUM_RE = re.compile(r"enum ConfigField \{.*?\n\}", re.DOTALL)

_PREAMBLE = """\
    // GENERATED from src/comms/config_fields.h by
    // tools/gen_config_field_enum.py -- do not hand-edit. Add or rename
    // a field in that header and re-run the generator; the block layer
    // and the wire then cannot disagree about what an ordinal means.
    // The gaps below (22-27, 29, 31) are retired field numbers: an
    // ordinal is a wire contract and is never reused."""


class GeneratorError(RuntimeError):
    """The header could not be read as a field table."""


def parse_fields(header_text: str):
    """Return [(wire_name, ordinal, unit, ts_name, ts_label)] in table
    declaration order -- the order a bare wire ``GET`` dumps, and the
    order the enum's dropdown renders."""
    table = _TABLE_RE.search(header_text)
    if table is None:
        raise GeneratorError(
            f"{HEADER.name}: kConfigFields[] table not found -- the "
            f"generator reads that array and nothing else."
        )
    rows = []
    pending = None
    for line in table.group(1).splitlines():
        annotation = _ANNOTATION_RE.match(line)
        if annotation is not None:
            pending = annotation.groups()
            continue
        row = _ROW_RE.match(line)
        if row is None:
            continue
        wire_name, ordinal, unit = row.group(1), int(row.group(2)), row.group(3)
        if pending is None:
            raise GeneratorError(
                f'{HEADER.name}: row {{"{wire_name}", {ordinal}, ...}} has no '
                f'`// ConfigField.<Name>: "<label>"` comment above it. Every '
                f"row needs one -- it is where this generator gets the "
                f"TypeScript member name and the //% block= label."
            )
        rows.append((wire_name, ordinal, unit, pending[0], pending[1]))
        pending = None
    if not rows:
        raise GeneratorError(f"{HEADER.name}: kConfigFields[] table is empty.")
    _reject_duplicates(rows)
    return rows


def _reject_duplicates(rows) -> None:
    for index, label in ((0, "wire name"), (1, "ordinal"), (3, "ConfigField name")):
        seen = {}
        for row in rows:
            key = row[index]
            if key in seen:
                raise GeneratorError(
                    f"{HEADER.name}: duplicate {label} {key!r} "
                    f"({seen[key]} and {row[0]})"
                )
            seen[key] = row[0]


def render_enum(rows) -> str:
    """The complete ``enum ConfigField { ... }`` block, matching the
    surrounding file's 4-space indent and no-trailing-comma style."""
    lines = ["enum ConfigField {", _PREAMBLE]
    for position, (_, ordinal, _, ts_name, ts_label) in enumerate(rows):
        separator = "" if position == len(rows) - 1 else ","
        lines.append(f'    //% block="{ts_label}"')
        lines.append(f"    {ts_name} = {ordinal}{separator}")
    lines.append("}")
    return "\n".join(lines)


def render_motion_ts(motion_text: str, enum_block: str) -> str:
    if _ENUM_RE.search(motion_text) is None:
        raise GeneratorError(
            f"{MOTION_TS.name}: `enum ConfigField {{ ... }}` block not found."
        )
    return _ENUM_RE.sub(lambda _: enum_block, motion_text, count=1)


def generate() -> str:
    """The full desired text of ``src/blocks/motion.ts``."""
    rows = parse_fields(HEADER.read_text())
    return render_motion_ts(MOTION_TS.read_text(), render_enum(rows))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing; exit 1 if the checked-in "
        "enum differs from a fresh generation",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="print the generated enum block instead of editing the file",
    )
    args = parser.parse_args(argv)

    if args.stdout:
        print(render_enum(parse_fields(HEADER.read_text())))
        return 0

    wanted = generate()
    current = MOTION_TS.read_text()
    if wanted == current:
        print(f"{MOTION_TS.relative_to(_REPO_ROOT)} is up to date.")
        return 0
    if args.check:
        print(
            f"{MOTION_TS.relative_to(_REPO_ROOT)}'s ConfigField enum has "
            f"drifted from {HEADER.relative_to(_REPO_ROOT)} -- re-run "
            f"`uv run python tools/gen_config_field_enum.py`.",
            file=sys.stderr,
        )
        return 1
    MOTION_TS.write_text(wanted)
    print(f"Wrote {MOTION_TS.relative_to(_REPO_ROOT)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
