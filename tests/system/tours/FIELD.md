# Playfield budget — what every tour in this directory is sized against

**Usable area: 120 cm wide x 80 cm high.** From the centre that is

    x in +-600 mm      y in +-400 mm

Stakeholder correction, 2026-09-01. Earlier files in this directory
were sized against `+-671.5 x +-446.5 mm` (the full 134.3 x 89.3 cm
field carried in `.claude/rules/playfield-testing.md`). That is the
*field*; the **usable** area is smaller, and tours built to the old
number do not fit. `infinity.tour` at r = 300 mm spanned exactly
1200 mm — the entire usable width, with zero margin.

## The working budget

Keep **50 mm of margin**, so every tour must live inside

    x in +-550 mm      y in +-350 mm

## Orientation is part of the sizing

A tour is written in the frame it starts in: the robot begins at the
origin facing **+x**. That is not the same as the field's long axis,
and for the asymmetric figures it matters which way they are staged.

Two of them come out **perpendicular** to the initial heading, which is
easy to get backwards:

| tour | extent in the START frame | stage the robot facing |
|---|---|---|
| `square` | +x 0..600, +y 0..600 | either axis (symmetric) |
| `diamond` | +-450 x, 0..900 y | either axis (symmetric) |
| `circle` | +-300 x, 0..600 y | either axis (symmetric) |
| `infinity` | **+-250 x, +-500 y** | along the SHORT (N-S) axis |
| `snake` | **+-125 x, 0..1000 y** | along the SHORT (N-S) axis |
| `spline` | +-361 x, +-263 y | either axis |

`infinity` and `snake` advance *perpendicular* to where the robot
points at the start — the first half-circle turns the robot through
180°, so progress is sideways. Staged facing along the field's long
axis they would run off the short one.

## Sizes, and why each is the largest that fits

| tour | size | binding limit |
|---|---|---|
| `square` | 600 mm sides | 600 <= 700 (y: 2 x 350) |
| `diamond` | 450 mm sides | 450 x sqrt2 = 636 <= 700 |
| `circle` | r = 300 mm | 2r = 600 <= 700 |
| `infinity` | r = 250 mm | 4r = 1000 <= 1100 (x) |
| `snake` | r = 125 mm, 4 bends | 8r = 1000 <= 1100 (x) |
| `spline` | `complex.path.json`, unscaled | +-361 x +-263, fits with 189/87 mm spare |

Every tour also has to start from the right place to be centred — a
600 mm square driven from the field centre reaches +600 mm, which is
outside the budget. Each file states its own staging offset.

## Before commanding motion on the real field

`.claude/rules/playfield-testing.md`'s pre-flight check still applies
and this file does not replace it: compute the full projected path from
a **measured** start pose through every leg, and confirm every waypoint
clears the margin. These numbers say a tour *can* fit, not that it will
from wherever the robot happens to be sitting.
