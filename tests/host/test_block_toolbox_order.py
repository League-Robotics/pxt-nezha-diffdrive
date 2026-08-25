"""tests/host/test_block_toolbox_order.py -- sprint 012 ticket 007: a
recurrence guard for a toolbox-order regression, pinning each block
group's WITHIN-GROUP order against the pre-split `main.ts` baseline
(ticket 001's archived 71-entry block-surface listing).

**What happened.** Splitting `main.ts` into six cohesion-sized modules
(sprint 012) physically re-interleaved which file each `//%`-annotated
block lives in. Block-surface CONTENT parity survived the split
perfectly (57/57 visible blocks, same caption/group=/params/advanced/
hidden), but WITHIN-GROUP ORDER did not: PXT's block sort
(`pxtcompiler.js`'s `fnweight()`, `fn.attributes.weight || 50`) ties on
declaration/compile order when no function declares an explicit
`weight=`, and the split changed that order in 2 of 6 groups (Drive,
Move) purely as a side effect of which file each function now lives
in. Ticket 007's own exception block has the full before/after finding.

**The fix.** `motion.ts`, `stop.ts`, and `run.ts` now carry explicit
`weight=` on every member of the Drive and Move groups (not just the
moved ones -- mixing explicit weights with `|| 50` defaults inside one
group produces a worse, harder-to-reason-about order than either
extreme), descending in exactly the order that reproduces the
pre-split baseline. Pose/World/Setup/ENUM were unaffected by the split
and deliberately carry no explicit weight.

**Why a test, not just the weight= annotations.** The weights repair
today's instance; nothing stops a future refactor (a new file, a
reordered `pxt.json`, a moved function) from silently reintroducing
the same class of drift -- in a weighted group or an unweighted one.
This test pins the *rendered* order (weight-sorted, ties broken by
declaration/encounter order -- the same stable-sort model
`pxtcompiler.js`'s `fnweight()` implies) for all six groups against
the baseline, so any future drift fails a test instead of reaching a
student.

**Extraction method.** Static scan of `//%`-annotated `export
function`/`enum` declarations, concatenating `pxt.json`'s `.ts` files
in their declared order -- the same proxy method ticket 001
established and ticket 007 validated by reproducing ticket 001's own
archived baseline byte-for-byte (whitespace-normalized) before trusting
it on the split tree. No PXT/Blockly toolchain invocation; this reads
source text only, so it is cheap and needs no `pxt run` (which is
blocked on this codebase today by the pre-existing, unrelated TS9256
defect -- see ticket 007's completion notes).

Run with::

    uv run pytest tests/host/test_block_toolbox_order.py
"""

import json
import pathlib
import re
from collections import defaultdict

# tests/host/test_block_toolbox_order.py -> host -> tests -> repo root
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PXT_JSON = _REPO_ROOT / "pxt.json"

_DEFAULT_WEIGHT = 50  # pxtcompiler.js's fnweight(): fn.attributes.weight || 50

# The within-group toolbox order ticket 001 archived from the pre-split
# main.ts (its own "Block-surface listing", 71-entry baseline), filtered
# to visible (captioned) blocks/enum members only. Drive and Move are
# the two groups the sprint 012 split actually disturbed (see this
# module's docstring); Pose/World/Setup/ENUM are included too so any
# *future* drift in a group that happens to be fine today still fails
# here instead of reaching a student.
_BASELINE_GROUP_ORDER = {
    "Drive": [
        "setWheelSpeeds", "driveTwist", "stop", "emergencyStop",
        "clearEmergencyStop", "isStalled", "clearStallLatch",
    ],
    "Move": [
        "driveTick", "onRun", "onRunCommand", "move", "goTo",
        "startMove", "startGoTo", "isMoving", "moveProgress", "stopMove",
        "whileMoving", "whileGoingTo",
    ],
    "Pose": ["poseX", "poseY", "heading", "resetPose"],
    "World": [
        "startWorldTracking", "worldTrackingReady", "seedPose",
        "readWorld", "worldX", "worldY", "worldHeading",
        "calibrateWorldSensor", "setWorldSensorOffset",
        "setArrivalTolerance", "goToWorld",
    ],
    "Setup": [
        "setDefaultSpeed", "setDefaultYawRate", "setTrackWidth",
        "setWheelCalibration", "setConfigValue",
    ],
    "ENUM": [
        "ConfigField.MaxDuty", "ConfigField.FullDutyVelocity",
        "ConfigField.Kp", "ConfigField.Ki", "ConfigField.IMax",
        "ConfigField.Kaff", "ConfigField.PidMax",
        "ConfigField.TwistHoldGain", "ConfigField.SpeedFloor",
        "ConfigField.PosErrMax", "ConfigField.StallSpeed",
        "ConfigField.StallDemand", "ConfigField.StallWindow",
        "ConfigField.LambdaEnabled", "ConfigField.CrawlPulse",
        "ConfigField.DefaultCruise", "ConfigField.RotationalSlip",
        "ConfigField.StallClear",
    ],
}

_SIG_RE = re.compile(r"^\s*export function (\w+)\s*\(")
_ENUM_RE = re.compile(r"^\s*(?:export\s+)?enum\s+(\w+)\s*\{")
_MEMBER_RE = re.compile(r"^\s*(\w+)\s*=\s*-?\d+")
_ATTR_LINE_RE = re.compile(r"^\s*//%")
_BLOCK_RE = re.compile(r'block="([^"]*)"')
_GROUP_RE = re.compile(r'group="([^"]*)"')
_WEIGHT_RE = re.compile(r"\bweight=(\d+)")


def _ts_file_order():
    manifest = json.loads(_PXT_JSON.read_text())
    return [f for f in manifest["files"] if f.endswith(".ts")]


def _extract_entries():
    """Walk pxt.json's .ts files in declared order; yield (kind, name,
    group, caption, weight) for every enum member and export function
    that carries a //% block= caption (the only ones that ever reach
    the toolbox)."""
    entries = []
    for relpath in _ts_file_order():
        lines = (_REPO_ROOT / relpath).read_text(
            encoding="utf-8"
        ).splitlines(keepends=True)
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]

            m_enum = _ENUM_RE.match(line)
            if m_enum:
                enum_name = m_enum.group(1)
                i += 1
                pending_caption = None
                while i < n and "}" not in lines[i].split("//")[0]:
                    m_block = _BLOCK_RE.search(lines[i])
                    if m_block:
                        pending_caption = m_block.group(1)
                    m_member = _MEMBER_RE.match(lines[i])
                    if m_member and pending_caption is not None:
                        entries.append((
                            "ENUM",
                            f"{enum_name}.{m_member.group(1)}",
                            "ENUM",
                            pending_caption,
                            _DEFAULT_WEIGHT,
                        ))
                        pending_caption = None
                    i += 1
                i += 1
                continue

            m_fn = _SIG_RE.match(line)
            if m_fn:
                fn_name = m_fn.group(1)
                j = i - 1
                attr_lines = []
                while j >= 0 and _ATTR_LINE_RE.match(lines[j]):
                    attr_lines.insert(0, lines[j])
                    j -= 1
                attrs_text = "".join(attr_lines)
                m_cap = _BLOCK_RE.search(attrs_text)
                if m_cap:
                    m_grp = _GROUP_RE.search(attrs_text)
                    group = m_grp.group(1) if m_grp else "None"
                    m_w = _WEIGHT_RE.search(attrs_text)
                    weight = int(m_w.group(1)) if m_w else _DEFAULT_WEIGHT
                    entries.append((
                        "FUNC", fn_name, group, m_cap.group(1), weight,
                    ))
            i += 1
    return entries


def _rendered_group_order(entries):
    """Mirror pxtcompiler.js's fnweight()-driven sort: within each
    group, a stable sort on descending weight (default 50), ties
    broken by encounter order -- this IS the within-group toolbox
    order once every block has gone through a real PXT compile."""
    groups = defaultdict(list)
    for _kind, name, group, _caption, weight in entries:
        groups[group].append((name, weight))
    return {
        group: [name for name, _w in sorted(items, key=lambda t: -t[1])]
        for group, items in groups.items()
    }


def test_toolbox_group_order_matches_pre_split_baseline():
    """Every group's rendered (weight-sorted) order must match the
    pre-split main.ts baseline exactly. A mismatch means either a new
    file-layout change re-broke an unweighted group's tie-break order,
    or an explicit weight= was added/changed/removed without updating
    this guard -- either way, a student-visible toolbox reorder that
    must not land silently."""
    entries = _extract_entries()
    rendered = _rendered_group_order(entries)

    mismatches = {}
    for group, expected in _BASELINE_GROUP_ORDER.items():
        actual = rendered.get(group, [])
        if actual != expected:
            mismatches[group] = {"expected": expected, "actual": actual}

    assert not mismatches, (
        "toolbox within-group order drifted from the pre-split "
        f"baseline (sprint 012 ticket 001): {mismatches}"
    )


def test_baseline_covers_every_visible_group():
    """Guard the guard: every group the current tree actually produces
    a visible block/enum for must have a baseline entry above -- an
    empty diff on an unlisted group would silently prove nothing."""
    entries = _extract_entries()
    rendered = _rendered_group_order(entries)
    missing = set(rendered) - set(_BASELINE_GROUP_ORDER)
    assert not missing, (
        f"group(s) with visible blocks have no baseline to check "
        f"against: {missing}"
    )
