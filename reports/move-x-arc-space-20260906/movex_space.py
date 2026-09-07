"""move_x(distance, rotation) parameter-space study.

Kinematics of the blended constant-ratio segment the engine already drives
(MotionEngine::beginSegment, service()), versus the pivot-then-straight
split moveX() substitutes at |rotation| >= 50 deg. Plus an emulation of
service()+VelocityShaper on an ideal plant, and the goToR arc-vs-chord
policy question.

All lengths mm, angles rad internally, plotted in cm / deg.
"""
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)

# tigez effective track width, MEASURED 2026-08-30 (captures/tigez-cal-20260830)
B = 114.4          # [mm]
CRUISE = 250.0     # [mm/s] MotionLimits::vMax default
VFLOOR = 70.0      # [mm/s] MotionLimits::vFloor default
ACCEL = 400.0      # [mm/s^2]
DECEL = 400.0
DT = 0.024         # [s] control cadence
TURN_FIRST = math.radians(50)

D2R = math.pi / 180
R2D = 180 / math.pi


# ----------------------------------------------------------------- kinematics
def arc_path(s, th, n=400):
    """Blended segment: heading rises linearly with path length, R = s/th."""
    t = np.linspace(0, 1, n)
    h = th * t
    if abs(th) < 1e-9:
        return s * t, np.zeros(n), h
    R = s / th
    return R * np.sin(h), R * (1 - np.cos(h)), h


def split_path(s, th, n=400):
    """Current moveX() at |th| >= 50 deg: pivot th in place, then straight s."""
    t = np.linspace(0, 1, n)
    return s * math.cos(th) * t, s * math.sin(th) * t, np.full(n, th)


def arc_end(s, th):
    x, y, _ = arc_path(s, th, 2)
    return x[-1], y[-1]


def split_end(s, th):
    return s * math.cos(th), s * math.sin(th)


def wheel_speeds(s, th):
    """Outer wheel at CRUISE; returns (vLeft, vRight) [mm/s] for the ratio."""
    dist = s
    yaw = th * B / 2
    left, right = dist - yaw, dist + yaw
    dom = max(abs(left), abs(right))
    if dom == 0:
        return 0.0, 0.0
    return CRUISE * left / dom, CRUISE * right / dom


def draw_robot(ax, x, y, h, scale=1.0, color="k", alpha=1.0):
    """Little diff-drive glyph: body rectangle + heading tick, in cm."""
    w = B / 10 * scale
    L = w * 1.2
    c, s_ = math.cos(h), math.sin(h)
    body = np.array([[-L / 2, -w / 2], [L / 2, -w / 2], [L / 2, w / 2],
                     [-L / 2, w / 2], [-L / 2, -w / 2]])
    rot = np.array([[c, -s_], [s_, c]])
    p = body @ rot.T + [x, y]
    ax.plot(p[:, 0], p[:, 1], color=color, lw=0.8, alpha=alpha)
    ax.plot([x, x + L / 2 * c], [y, y + L / 2 * s_], color=color, lw=1.5,
            alpha=alpha)


# ------------------------------------------------- fig 1: parameter gallery
def fig_gallery():
    dists = [50, 150, 300, -150]                      # mm
    rots = [30, 50, 90, 180, 360]                      # deg
    fig, axes = plt.subplots(len(dists), len(rots),
                             figsize=(3.1 * len(rots), 3.1 * len(dists)))
    for i, s in enumerate(dists):
        for j, rd in enumerate(rots):
            ax = axes[i, j]
            th = rd * D2R
            ax_, ay_, ah = arc_path(s, th)
            ax.plot(ax_ / 10, ay_ / 10, color="tab:blue", lw=2,
                    label="blended arc")
            draw_robot(ax, 0, 0, 0, color="0.5")
            draw_robot(ax, ax_[-1] / 10, ay_[-1] / 10, ah[-1],
                       color="tab:blue")
            if abs(th) >= TURN_FIRST:
                sx, sy, sh = split_path(s, th)
                ax.plot(sx / 10, sy / 10, color="tab:red", lw=1.5, ls="--",
                        label="current firmware\n(pivot, then straight)")
                draw_robot(ax, sx[-1] / 10, sy[-1] / 10, sh[-1],
                           color="tab:red", alpha=0.8)
                gap = math.hypot(ax_[-1] - sx[-1], ay_[-1] - sy[-1]) / 10
                ax.text(0.03, 0.97, f"endpoints differ\nby {gap:.1f} cm",
                        transform=ax.transAxes, va="top", fontsize=8,
                        color="tab:red")
            vl, vr = wheel_speeds(s, th)
            R = s / th if th else float("inf")
            ax.set_title(f"move_x({s/10:g} cm, {rd:g}°)   R = {R/10:.1f} cm\n"
                         f"wheels L {vl:+.0f} / R {vr:+.0f} mm/s",
                         fontsize=8.5)
            ax.set_aspect("equal")
            ax.grid(True, lw=0.3)
            ax.tick_params(labelsize=7)
            lim = max(abs(s), abs(R) * 2 if math.isfinite(R) else 0, 80) / 10
            ax.set_xlim(-lim * 0.6, lim * 1.1)
            ax.set_ylim(-lim * 0.9, lim * 0.9)
    h, l = axes[0, 2].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, fontsize=10,
               bbox_to_anchor=(0.5, -0.005))
    fig.suptitle("move_x(distance, rotation): every cell is a reachable "
                 "constant-radius arc.\nThe dashed red path is what "
                 "firmware drives today at |rotation| >= 50°: a different "
                 "endpoint and a different figure.", fontsize=12)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(f"{OUT}/fig1-gallery.png", dpi=130)
    plt.close(fig)


# -------------------------------------- fig 2: endpoint gap + wheel reversal
def fig_maps():
    s_axis = np.linspace(-400, 400, 321)
    th_axis = np.linspace(-360, 360, 289) * D2R
    S, TH = np.meshgrid(s_axis, th_axis)
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(np.abs(TH) > 1e-9, S / TH, np.inf)
        ax_ = np.where(np.isfinite(R), R * np.sin(TH), S)
        ay_ = np.where(np.isfinite(R), R * (1 - np.cos(TH)), 0.0)
    sx, sy = S * np.cos(TH), S * np.sin(TH)
    gap = np.hypot(ax_ - sx, ay_ - sy)
    gap = np.where(np.abs(TH) >= TURN_FIRST, gap, 0.0)

    # inner wheel speed with the outer at CRUISE
    yaw = TH * B / 2
    left, right = S - yaw, S + yaw
    dom = np.maximum(np.abs(left), np.abs(right))
    inner = np.where(np.abs(left) < np.abs(right), left, right)
    inner_v = CRUISE * inner / np.where(dom == 0, 1, dom)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 6))
    im = a1.pcolormesh(s_axis / 10, th_axis * R2D, gap / 10, shading="auto",
                       cmap="magma_r")
    fig.colorbar(im, ax=a1, label="|blended endpoint − split endpoint|  [cm]")
    a1.axhline(50, color="w", ls="--", lw=1)
    a1.axhline(-50, color="w", ls="--", lw=1)
    a1.text(-39, 55, "|rotation| = 50°: split fires above this line",
            color="w", fontsize=8)
    a1.set_xlabel("distance [cm]")
    a1.set_ylabel("rotation [deg]")
    a1.set_title("Where today's move_x lands somewhere other than the arc")

    im2 = a2.pcolormesh(s_axis / 10, th_axis * R2D, inner_v, shading="auto",
                        cmap="RdBu", vmin=-CRUISE, vmax=CRUISE)
    fig.colorbar(im2, ax=a2, label="inner wheel speed with outer at cruise "
                                    "[mm/s]  (blue = reversed)")
    # R = B/2 : one wheel stationary  ->  |th| * B/2 = |s|
    ss = np.linspace(-400, 400, 200)
    a2.plot(ss / 10, (ss / (B / 2)) * R2D, "k", lw=1.2)
    a2.plot(ss / 10, -(ss / (B / 2)) * R2D, "k", lw=1.2)
    a2.text(20, 120, "R = b/2\n(inner wheel stopped;\npivot about one wheel)",
            fontsize=8)
    # floor band: |inner| < VFLOOR
    band = np.abs(inner_v) < VFLOOR
    a2.contour(s_axis / 10, th_axis * R2D, band.astype(float), levels=[0.5],
               colors="k", linestyles=":", linewidths=1)
    a2.text(-38, -300, "dotted: inner wheel below the 70 mm/s floor\n"
            "for the whole segment", fontsize=8)
    a2.set_xlabel("distance [cm]")
    a2.set_ylabel("rotation [deg]")
    a2.set_title("Which wheel goes which way — the only physics in the plane")
    for a in (a1, a2):
        a.set_ylim(-360, 360)
    fig.suptitle("move_x parameter plane. Every point is a driveable arc; "
                 "the 50° line is not a physical boundary of anything.",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(f"{OUT}/fig2-maps.png", dpi=130)
    plt.close(fig)

    # A 1-D cut: inner wheel speed against radius
    fig, ax = plt.subplots(figsize=(8, 4))
    Rr = np.linspace(0, 400, 800)
    inner_r = CRUISE * (Rr - B / 2) / (Rr + B / 2)
    ax.plot(Rr / 10, inner_r, lw=2)
    ax.axhline(VFLOOR, color="tab:red", ls=":", label="vFloor 70 mm/s")
    ax.axhline(-VFLOOR, color="tab:red", ls=":")
    ax.axhline(0, color="k", lw=0.6)
    ax.axvline(B / 20, color="k", ls="--", lw=0.8)
    ax.text(B / 20 + 0.3, -200, "R = b/2 = %.1f cm" % (B / 20), fontsize=9)
    lo = B / 2 * (CRUISE - VFLOOR) / (CRUISE + VFLOOR)
    hi = B / 2 * (CRUISE + VFLOOR) / (CRUISE - VFLOOR)
    ax.axvspan(lo / 10, hi / 10, color="tab:red", alpha=0.12,
               label=f"inner wheel under the floor: R in {lo/10:.1f}–{hi/10:.1f} cm")
    ax.set_xlabel("arc radius R = distance / rotation  [cm]")
    ax.set_ylabel("inner wheel speed [mm/s]\n(outer wheel at 250)")
    ax.set_title("Inner wheel reverses below R = b/2 and is slow near it:\n"
                 "a radius question, not a rotation-angle question", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, lw=0.3)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig3-inner-wheel.png", dpi=130)
    plt.close(fig)
    return lo, hi


# -------------------------------------------------------- fig 4: showcases
def fig_showcase():
    fig, axes = plt.subplots(2, 3, figsize=(15, 9.5))
    axes = axes.ravel()

    def show(ax, segs, title, note=""):
        x = y = h = 0.0
        for k, (s, rd) in enumerate(segs):
            th = rd * D2R
            px, py, ph = arc_path(s, th)
            c, s_ = math.cos(h), math.sin(h)
            wx = x + px * c - py * s_
            wy = y + px * s_ + py * c
            ax.plot(wx / 10, wy / 10, lw=2,
                    color=plt.cm.viridis(k / max(1, len(segs) - 1)))
            x, y, h = wx[-1], wy[-1], h + th
            draw_robot(ax, x / 10, y / 10, h, color="0.3", alpha=0.6)
        draw_robot(ax, 0, 0, 0, color="k")
        ax.set_aspect("equal")
        ax.grid(True, lw=0.3)
        ax.set_title(title, fontsize=10)
        if note:
            ax.text(0.02, 0.02, note, transform=ax.transAxes, fontsize=8,
                    va="bottom")
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("y [cm]")

    vl, vr = wheel_speeds(50, 150 * D2R)
    show(axes[0], [(50, 150)],
         "Near target, big turn: move_x(5 cm, 150°)\n"
         f"R = {50/(150*D2R)/10:.1f} cm < b/2: wheels L {vl:+.0f} / R {vr:+.0f} mm/s",
         "one wheel forward, one back —\nthe blend does this by itself")
    vl, vr = wheel_speeds(-250, 180 * D2R)
    show(axes[1], [(-250, 180)],
         "Backwards wrap: move_x(−25 cm, 180°)\n"
         f"wheels L {vl:+.0f} / R {vr:+.0f} mm/s",
         "reverses along a half circle,\nends facing back the way it came")
    show(axes[2], [(2 * math.pi * 150, 360)],
         "Full circle: move_x(94.2 cm, 360°)  R = 15 cm",
         "returns to the start pose")
    show(axes[3], [(2 * math.pi * 100 * 2, 720)],
         "Two laps: move_x(125.7 cm, 720°)  R = 10 cm",
         "rotation beyond ±180° is a repeat count, not an error")
    spiral = [(s, 45) for s in np.linspace(20, 200, 16)]
    show(axes[4], spiral,
         "Spiral: 16 × move_x(s, 45°), s from 2 to 20 cm",
         "each segment is its own arc; R grows 2.5 → 25 cm\n"
         "(today every one of these would be a pivot + straight)")
    show(axes[5], [(300, 180), (300, -180)],
         "Figure-8 style: move_x(30, 180°) then move_x(30, −180°)",
         "two half circles, opposite hands")
    fig.suptitle("Things move_x can draw once it stops splitting: all "
                 "constant-ratio segments the engine already knows how to drive",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(f"{OUT}/fig4-showcase.png", dpi=130)
    plt.close(fig)


# ---------------------------- fig 5: service()+shaper emulation, ideal plant
def emulate(s, th, remain_axis="mean", lag=0.0, max_t=60.0):
    """Emulates MotionEngine::service() for one blended Segment on an ideal
    plant (wheels move exactly as commanded; counts == mm).

    remain_axis="mean": as built -- Segment::remaining() on the mean axis
    while the shaper's speed is the dominant WHEEL's.
    remain_axis="dominant": remaining measured on the dominant wheel.
    """
    dist_t = s
    yaw_t = th * B / 2
    left, right = dist_t - yaw_t, dist_t + yaw_t
    dom = max(abs(left), abs(right))
    v = 0.0
    posL = posR = 0.0
    t = 0.0
    log = []
    while t < max_t:
        dL, dR = posL, posR
        mean = 0.5 * (dL + dR)
        if remain_axis == "mean":
            remain = abs(dist_t) - abs(mean)
        else:
            # dominant WHEEL progress
            wheel = dR if abs(right) >= abs(left) else dL
            remain = dom - abs(wheel)
        remain = max(remain, 0.0)
        usable = max(remain - v * DT, 0.0)
        vBrake = math.sqrt(2 * DECEL * usable)
        vGoal = min(CRUISE, vBrake)
        vNext = min(max(vGoal, v - DECEL * DT), v + ACCEL * DT)
        if vNext < VFLOOR:
            vNext = VFLOOR
        arriving = remain <= vNext * DT
        if arriving:
            break
        velocity = (dist_t / dom) * vNext
        twist = (yaw_t / dom) * vNext
        posL += (velocity - twist) * DT
        posR += (velocity + twist) * DT
        v = vNext
        t += DT
        log.append((t, vNext, velocity, 0.5 * (posL + posR),
                    0.5 * (posR - posL)))
    log = np.array(log) if log else np.zeros((1, 5))
    mean_prog = 0.5 * (posL + posR)
    yaw_prog = 0.5 * (posR - posL)
    return dict(t=t, log=log, dist_err=mean_prog - dist_t,
                yaw_err_deg=(yaw_prog - yaw_t) / (B / 2) * R2D,
                dom=dom)


def fig_emulation():
    cases = [(300, 0, "straight 30 cm"),
             (300, 30, "30 cm, 30°  (R 57 cm)"),
             (150, 90, "15 cm, 90°  (R 9.5 cm)"),
             (50, 180, "5 cm, 180°  (R 1.6 cm, inner wheel reversed)"),
             (2 * math.pi * 150, 360, "94 cm, 360°  (R 15 cm)")]
    fig, axes = plt.subplots(2, len(cases), figsize=(4.2 * len(cases), 7.5))
    rows = []
    for j, (s, rd, name) in enumerate(cases):
        th = rd * D2R
        asb = emulate(s, th, "mean")
        fix = emulate(s, th, "dominant")
        ideal_t = asb["dom"] / CRUISE + CRUISE / ACCEL
        rows.append((name, asb["t"], fix["t"], asb["dist_err"],
                     asb["yaw_err_deg"], fix["dist_err"], fix["yaw_err_deg"]))
        a = axes[0, j]
        a.plot(asb["log"][:, 0], asb["log"][:, 1], color="tab:red",
               label="as built (remain on mean axis)")
        a.plot(fix["log"][:, 0], fix["log"][:, 1], color="tab:blue",
               label="remain on dominant wheel")
        a.axhline(VFLOOR, color="0.5", ls=":", lw=0.8)
        a.set_title(name, fontsize=9)
        a.set_xlabel("t [s]")
        if j == 0:
            a.set_ylabel("dominant wheel command [mm/s]")
        a.grid(True, lw=0.3)
        a.set_ylim(0, CRUISE * 1.1)
        b = axes[1, j]
        b.bar([0, 1], [asb["t"], fix["t"]], color=["tab:red", "tab:blue"])
        b.set_xticks([0, 1])
        b.set_xticklabels(["as built", "dominant"], fontsize=8)
        b.set_ylabel("segment time [s]" if j == 0 else "")
        for k, val in enumerate([asb["t"], fix["t"]]):
            b.text(k, val, f"{val:.2f} s", ha="center", va="bottom",
                   fontsize=8)
        b.text(0.5, 0.93,
               f"as built lands\n{asb['dist_err']:+.1f} mm, {asb['yaw_err_deg']:+.1f}°",
               transform=b.transAxes, ha="center", va="top", fontsize=8,
               color="tab:red")
        b.set_ylim(0, max(asb["t"], fix["t"]) * 1.45)
        b.grid(True, axis="y", lw=0.3)
    axes[0, 0].legend(fontsize=7, loc="lower right")
    fig.suptitle("service() + VelocityShaper emulated on an ideal plant "
                 "(lag 0, jerk 0). The blended branch brakes the dominant "
                 "WHEEL's speed against the MEAN axis's remaining distance:\n"
                 "harmless on a straight, wrong on a tight arc — the segment "
                 "crawls at the floor and the arrival test fires early.",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(f"{OUT}/fig5-shaper-emulation.png", dpi=130)
    plt.close(fig)
    return rows


# ---------------------------------------------------- fig 6: goTo policy
def fig_goto():
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
    a0, a1, a2 = axes
    chord = 300.0
    for k, bd in enumerate([15, 25, 45, 60, 90, 135]):
        beta = bd * D2R
        th = 2 * beta
        if th > math.pi:
            th -= 2 * math.pi
        R = chord / (2 * math.sin(beta))
        s = R * th
        px, py, _ = arc_path(s, th)
        col = plt.cm.viridis(k / 5)
        a0.plot(px / 10, py / 10, color=col, lw=1.8, label=f"bearing {bd}°")
        tx, ty = chord * math.cos(beta), chord * math.sin(beta)
        a0.plot([0, tx / 10], [0, ty / 10], color=col, lw=0.8, ls="--")
        a0.plot(tx / 10, ty / 10, "o", color=col, ms=5)
    draw_robot(a0, 0, 0, 0)
    a0.set_aspect("equal")
    a0.grid(True, lw=0.3)
    a0.legend(fontsize=8)
    a0.set_title("goTo(30 cm chord) as the tangent arc θ = 2·bearing\n"
                 "vs pivot-to-bearing then chord (dashed)", fontsize=10)
    a0.set_xlabel("x [cm]")
    a0.set_ylabel("y [cm]")

    beta = np.linspace(0.5, 179.5, 720) * D2R
    for chord, col in [(100, "tab:green"), (300, "tab:blue"),
                       (600, "tab:purple")]:
        th = 2 * beta
        th = np.where(th > math.pi, th - 2 * math.pi, th)
        R = chord / (2 * np.sin(beta))
        arclen = np.abs(R * th)
        vmean = CRUISE * np.abs(R) / (np.abs(R) + B / 2)
        t_arc = arclen / vmean + CRUISE / ACCEL
        t_split = (beta * B / 2) / CRUISE + CRUISE / ACCEL \
            + chord / CRUISE + CRUISE / ACCEL
        a1.plot(beta * R2D, t_arc - t_split, color=col, lw=1.8,
                label=f"chord {chord/10:g} cm")
        cross = beta[np.argmax(t_arc > t_split)] * R2D
        a1.axvline(cross, color=col, ls=":", lw=0.8)
    a1.axhline(0, color="k", lw=0.7)
    a1.axvline(25, color="tab:red", ls="--", lw=1)
    a1.text(26, a1.get_ylim()[1] * 0.85 if a1.get_ylim()[1] > 0 else 1,
            "current split:\nbearing ≥ 25°\n(θ ≥ 50°)", color="tab:red",
            fontsize=8)
    a1.set_ylim(-1.5, 6)
    a1.set_xlabel("target bearing [deg]")
    a1.set_ylabel("arc time − (pivot + chord) time  [s]")
    a1.set_title("Time cost of the arc vs pivot-then-chord\n"
                 "(dotted: break-even bearing per chord)", fontsize=10)
    a1.grid(True, lw=0.3)
    a1.legend(fontsize=8)

    sag = (chord / 2) * np.tan(beta / 2)
    a2.plot(beta * R2D, np.abs(sag) / 10, color="tab:blue", lw=1.8,
            label="lateral bulge of the arc (60 cm chord)")
    a2.set_ylim(0, 60)
    a2.set_ylabel("bulge [cm]", color="tab:blue")
    a2b = a2.twinx()
    th_end = np.where(2 * beta > math.pi, 2 * beta - 2 * math.pi, 2 * beta)
    a2b.plot(beta * R2D, np.abs(th_end) * R2D, color="tab:orange", lw=1.8,
             label="final heading, arc")
    a2b.plot(beta * R2D, beta * R2D, color="tab:orange", ls="--",
             label="final heading, pivot+chord")
    a2b.set_ylabel("final heading change [deg]", color="tab:orange")
    a2b.set_ylim(0, 190)
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = a2b.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
    a2.axvline(25, color="tab:red", ls="--", lw=1)
    a2.set_xlabel("target bearing [deg]")
    a2.set_title("What else the arc costs: it bulges sideways\n"
                 "and ends at twice the heading", fontsize=10)
    a2.grid(True, lw=0.3)
    fig.suptitle("goTo: the split IS a policy question here — the arc to a "
                 "point is only one of two ways to reach it, and they end in "
                 "different headings", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(f"{OUT}/fig6-goto-policy.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    fig_gallery()
    lo, hi = fig_maps()
    fig_showcase()
    rows = fig_emulation()
    fig_goto()
    print(f"inner wheel under floor for R in {lo:.1f}..{hi:.1f} mm "
          f"(b/2 = {B/2:.1f})")
    print("case | t as-built | t dominant | dist err | yaw err | "
          "dist err(fix) | yaw err(fix)")
    for r in rows:
        print(f"{r[0]} | {r[1]:.2f} s | {r[2]:.2f} s | {r[3]:+.1f} mm | "
              f"{r[4]:+.2f} deg | {r[5]:+.1f} mm | {r[6]:+.2f} deg")
    # a few endpoint gaps for the text
    for s, rd in [(50, 150), (150, 90), (300, 90), (300, 180), (300, 50)]:
        ax_, ay_ = arc_end(s, rd * D2R)
        sx, sy = split_end(s, rd * D2R)
        print(f"move_x({s} mm, {rd} deg): arc end ({ax_:.0f},{ay_:.0f}) "
              f"split end ({sx:.0f},{sy:.0f}) gap {math.hypot(ax_-sx, ay_-sy):.0f} mm")
