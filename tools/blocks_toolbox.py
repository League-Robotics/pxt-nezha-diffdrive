"""Apply reports/blocks-toolbox.csv to the extension's block annotations.

`just blocks-apply` runs this; `just blocks-plan` shows what it would do
without writing. The CSV is the source of truth for toolbox layout --
edit it and re-run rather than hand-tuning weights in the source.

CSV columns that matter (others are ignored, so extra scratch columns
are fine):

    Cat Order   integer, orders the categories
    category    the toolbox category this block lives in
    Group Order integer, orders groups WITHIN a category; may be blank
                when the category has only one group
    group       the group header the block sits under
    new_order   integer, orders blocks WITHIN a group
    function    diffDrive.<name>, matched against the source

GROUP ORDER COMES FROM `Group Order`, NOT ROW ORDER. On 2026-08-29 the
CSV listed the GoTo rows above the Move rows while marking Move as
Group Order 1 -- deriving order from row position would have inverted
them. Row order is not consulted anywhere in this file.

Three pxt-core mechanics this encodes (read out of
node_modules/pxt-core/built/web/main.js, 2026-08-29):

WEIGHT SORTS DESCENDING, WITHIN A GROUP ONLY.
    Higher weight renders first. Weights here are assigned from the
    FINAL display position so they also read top-to-bottom in source;
    spaced by 10 so a block can be inserted later without renumbering.

A BLOCK WITH `subcategory` IS EXCLUDED FROM THE PARENT FLYOUT.
    The filter is `!sub && !advanced && !subcategory` for the top-level
    category. So exactly one category -- the lowest Cat Order -- must
    carry no subcategory attribute, or the parent category renders
    empty. `advanced=true` is the legacy "more" bucket and is mutually
    exclusive with subcategory (advanced wins); this script never
    emits it.

SUBCATEGORY ORDER COMES FROM THE NAMESPACE `subcategories` ARRAY.
    pxt falls back to `Object.keys(subcategoryMap)` (insertion order)
    when it is absent, which is not controllable. Subcategory rows
    inherit the namespace's `groups` list, so ONE global list serves
    every flyout -- each shows only the groups it actually has. That
    list can look oddly sorted; what matters is that filtering it per
    category yields that category's Group Order.
"""
import argparse
import collections
import csv
import json
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "reports" / "blocks-toolbox.csv"
SRC = REPO_ROOT / "src" / "blocks"
NS_FILE = SRC / "motion.ts"
WEIGHT_STEP = 10

# attributes this script owns; stripped then re-emitted
OWNED = re.compile(
    r'\s*(?:group="[^"]*"|subcategory="[^"]*"|advanced=\S+|weight=\S+)'
)


def load_rows(path):
    rows = []
    for i, r in enumerate(csv.DictReader(path.open()), start=2):
        try:
            fn = r["function"].strip()
            rows.append({
                "row": i,
                # float, not int: lets a block be inserted at 4.1 without
                # renumbering everything below it.
                "cat_order": float(r["Cat Order"]),
                "category": r["category"].strip(),
                "group_order": (r["Group Order"].strip() or None),
                "group": r["group"].strip(),
                "new_order": float(r["new_order"]),
                "func": fn.split(".", 1)[1] if "." in fn else fn,
                "block": r["block"].strip(),
            })
        except (KeyError, ValueError) as e:
            raise SystemExit(f"{path}:{i}: bad row ({e}): {r}") from e
    if not rows:
        raise SystemExit(f"{path}: no rows")
    return rows


def plan(rows):
    """Return (ordered_rows, groups, subcategories, top_category)."""
    # categories, by Cat Order
    cat_order = {}
    for r in rows:
        prev = cat_order.setdefault(r["category"], r["cat_order"])
        if prev != r["cat_order"]:
            raise SystemExit(
                f"category {r['category']!r} has conflicting Cat Order "
                f"{prev} and {r['cat_order']}"
            )
    cats = sorted(cat_order, key=lambda c: cat_order[c])
    top = cats[0]

    # groups within each category, by Group Order (blank sorts last)
    gkey, gfirst = {}, {}
    for r in rows:
        k = (r["category"], r["group"])
        gfirst.setdefault(k, r["row"])
        go = None if r["group_order"] is None else float(r["group_order"])
        if k in gkey and gkey[k] != go:
            raise SystemExit(
                f"group {r['group']!r} in {r['category']!r} has conflicting "
                f"Group Order {gkey[k]} and {go}"
            )
        gkey[k] = go
    # a group must not straddle categories -- the `groups` list is global
    homes = collections.defaultdict(set)
    for (cat, grp) in gkey:
        homes[grp].add(cat)
    for grp, cs in homes.items():
        if len(cs) > 1:
            raise SystemExit(
                f"group {grp!r} appears in more than one category ({sorted(cs)}); "
                "the namespace groups list is global, so that cannot be ordered"
            )

    ordered, groups = [], []
    for cat in cats:
        # Ties on Group Order break by FIRST ROW IN THE CSV, never
        # alphabetically: on 2026-08-29 Move/Drive/Wheels were all given
        # Group Order 1, and sorting those by name yields Drive, Move,
        # Wheels -- not the Move, Drive, Wheels the row order states.
        grps = sorted(
            (g for (c, g) in gkey if c == cat),
            key=lambda g: (gkey[(cat, g)] is None,
                           gkey[(cat, g)] or 0.0,
                           gfirst[(cat, g)]),
        )
        for g in grps:
            groups.append(g)
            members = sorted(
                (r for r in rows if r["category"] == cat and r["group"] == g),
                key=lambda r: r["new_order"],
            )
            ordered.extend(members)

    n = len(ordered)
    for pos, r in enumerate(ordered, start=1):
        r["position"] = pos
        # descending, so display order == weight order top to bottom
        r["weight"] = int((n - pos + 1) * WEIGHT_STEP)
    return ordered, groups, [c for c in cats if c != top], top


def source_functions():
    """Map function name -> (path, line index of its declaration)."""
    found = {}
    for path in sorted(SRC.glob("*.ts")):
        for i, line in enumerate(path.read_text().splitlines()):
            m = re.match(r"\s*(?:export\s+)?function\s+(\w+)", line)
            if m:
                found.setdefault(m.group(1), (path, i))
    return found


def validate(ordered, rows):
    seen = collections.Counter(r["func"] for r in rows)
    dupes = [f for f, c in seen.items() if c > 1]
    if dupes:
        raise SystemExit(f"duplicate function rows: {dupes}")
    per_group = collections.defaultdict(list)
    for r in rows:
        per_group[(r["category"], r["group"])].append(r["new_order"])
    for k, v in per_group.items():
        if len(set(v)) != len(v):
            raise SystemExit(f"duplicate new_order within {k}: {sorted(v)}")
    src = source_functions()
    missing = [r["func"] for r in rows if r["func"] not in src]
    if missing:
        raise SystemExit(f"CSV names functions absent from src/blocks: {missing}")
    return src


def apply(ordered, groups, subcats, top):
    by_func = {r["func"]: r for r in ordered}
    counts = collections.Counter()
    for path in sorted(SRC.glob("*.ts")):
        lines = path.read_text().splitlines(keepends=True)
        out, i = [], 0
        while i < len(lines):
            m = re.match(r"(\s*)(?:export\s+)?function\s+(\w+)", lines[i])
            if not m or m.group(2) not in by_func:
                out.append(lines[i]); i += 1
                continue
            indent, func = m.group(1), m.group(2)
            start = len(out)
            while start > 0 and out[start - 1].strip().startswith("//%"):
                start -= 1
            ann = out[start:]
            del out[start:]
            for a in ann:
                body = OWNED.sub("", a.rstrip("\n"))
                if body.strip() != "//%":
                    out.append(body + "\n")
            r = by_func[func]
            out.append(f'{indent}//% group="{r["group"]}" weight={r["weight"]}\n')
            if r["category"] != top:
                out.append(f'{indent}//% subcategory="{r["category"]}"\n')
            out.append(lines[i]); i += 1
            counts[path.name] += 1
        path.write_text("".join(out))

    txt = NS_FILE.read_text()
    m = re.search(
        r"(//% color=[^\n]*?)(?:\n//% (?:groups|subcategories)='[^\n]*')*"
        r"\n(namespace diffDrive \{)", txt)
    if not m:
        raise SystemExit(f"{NS_FILE}: namespace header not found")
    hdr = (m.group(1)
           + "\n//% groups='" + json.dumps(groups) + "'"
           + "\n//% subcategories='" + json.dumps(subcats) + "'"
           + "\n" + m.group(2))
    NS_FILE.write_text(txt[:m.start()] + hdr + txt[m.end():])
    return counts


def show(ordered, groups, subcats, top):
    print(f"top-level category : {top}")
    print(f"subcategories      : {subcats}")
    print(f"groups (global)    : {groups}\n")
    cat = grp = None
    for r in ordered:
        if r["category"] != cat:
            cat = r["category"]; grp = None
            print(f"[{cat}]")
        if r["group"] != grp:
            grp = r["group"]
            print(f"  == {grp}")
        print(f"     {r['position']:>2}. w={r['weight']:<4} "
              f"{'diffDrive.' + r['func']:<34} {r['block']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=pathlib.Path, default=CSV_PATH)
    ap.add_argument("--check", action="store_true",
                    help="print the plan; do not modify any source")
    args = ap.parse_args()

    rows = load_rows(args.csv)
    ordered, groups, subcats, top = plan(rows)
    validate(ordered, rows)
    show(ordered, groups, subcats, top)
    if args.check:
        print(f"\n--check: {len(ordered)} blocks planned, nothing written.")
        return 0
    counts = apply(ordered, groups, subcats, top)
    print(f"\nrewrote {sum(counts.values())} blocks: {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
