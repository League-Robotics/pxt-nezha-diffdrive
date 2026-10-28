---
status: pending
---

# `close_sprint` bumps the version with major 0 and writes only `pyproject.toml`

Seen at the sprint 042 and 043 closes (2026-10-27): `close_sprint` wrote
0.20261027.1 and 0.20261027.2 into `pyproject.toml` and pushed the tags,
while this repo's version line was 1.20261006.1 and lives in five
places that `dotconfig version bump --major 1` keeps in sync
(`config/dotconfig.yaml`, `pyproject.toml`, `package.json`, `pxt.json`,
`kVersion` in `src/comms/protocol.cpp`). zuvat's firmware reported
`0.20261027.1` for a day. Restored by hand as 1.20261027.1 (commit
3503e8d, local tag `v1.20261027.1`); the pushed `v0.*` tags are still on
origin.

Cause: `clasi/close.py` line ~1044 calls
`compute_next_version(project_root=...)` with the `major` argument left
at its default of 0, and `.clasi/settings.yaml` has `version_format` and
`version_trigger` but no major. The clasi bump also knows only
`pyproject.toml`.

Fix options: (a) a `version_major` setting (or read the major from the
current version carrier) in clasi, and a `version_command` setting so a
project can point the close at `dotconfig version bump --major 1`;
(b) until then, run `dotconfig version bump --major 1` after every close
in this repo and delete the stray `v0.*` tags. Report (a) upstream with
the `report` skill.
