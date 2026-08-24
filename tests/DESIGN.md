# tests — Python-run test root

**Owner:** Eric Busboom · **Last reviewed:** 2026-08-23 · **Status:** stable

The repo's pytest-run test tree. Run everything with `uv run pytest`
from the repo root — that builds whatever native shims are needed and
runs every suite from a clean checkout.

One subsystem:

- [`host/`](host/DESIGN.md) — the native host test harness: this
  extension's portable firmware C++ (kernel, motion engine, v6 wire
  stack, wire adapter) compiled for the desktop with the system
  compiler and driven from pytest through `ctypes`, against fake
  ports. No micro:bit, PXT, or CODAL anywhere in the link.

Not to be confused with the sibling `test/` root (singular) — those
are PXT `testFiles`, on-robot MakeCode programs with no assertions,
documented in [`test/DESIGN.md`](../test/DESIGN.md).
