# tests — Python-run test root

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-24 · **Status:** stable

The repo's pytest-run test tree. Run everything with `uv run pytest`
from the repo root — that builds whatever native shims are needed and
runs every suite from a clean checkout.

Subsystems:

- [`host/`](host/DESIGN.md) — the native host test harness: this
  extension's portable firmware C++ (kernel, motion engine, v6 wire
  stack, wire adapter) compiled for the desktop with the system
  compiler and driven from pytest through `ctypes`, against fake
  ports. No micro:bit, PXT, or CODAL anywhere in the link.
- [`tools/`](tools/DESIGN.md) (sprint 008) — plain-Python unit tests
  over `tools/` scripts' own logic, no shim compilation and no
  hardware/network. One file so far: `test_make_deploy_triage.py`,
  pinning `tools/make_deploy.py`'s `classify_attempt()` (hard-failure
  vs. known-benign-retry vs. unknown build-output triage) against
  saved/synthetic build-log fixtures — see `tools/DESIGN.md`'s "Build
  checkpoint triage" section for what the logic itself decides.

Not to be confused with the sibling `test/` root (singular) — those
are PXT `testFiles`, on-robot MakeCode programs with no assertions,
documented in [`test/DESIGN.md`](../test/DESIGN.md).
