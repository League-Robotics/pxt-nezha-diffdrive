"""Find the coloured cubes on the bb-obstacle mat in the overhead camera's deskewed frame.

    uv run python tools/canplay/cubes.py [out.png]     list the cubes, optionally save an annotated frame

The deskewed frame maps to mat coordinates by an affine fitted to the
mat's 12 red circles (residuals under 0.4 cm). The mat has a green cast,
so a cube is found by its saturation lift over the local background.
"""
import math, os, sys, time
import numpy as np, cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canplay import CAM, Mat  # noqa: E402

PX2W = np.array([[0.1697, -0.0037, -69.9161], [-0.0046, -0.1689, 44.3513]])
W2PX = np.linalg.inv(np.vstack([PX2W, [0, 0, 1]]))[:2]
COLORS = {"orange": ((12, 48), (0, 140, 255)), "blue": ((92, 118), (255, 0, 0)), "green": ((50, 68), (0, 150, 0))}
LIFT = 14
CUBE_PX = 160                           # one cube's blob area in frame pixels
INTERIOR = (65, 770, 50, 400)           # the mat, in frame pixels
ROBOT_CLEAR = 14.0                      # cm round a robot centre: its chassis reads as blue
BODY_CLEAR = 11.0                       # cm round a robot centre for the other colours


MAP = None               # a matcam.MatCam: deskewed px <-> mat cm by homography, overriding PX2W


def to_world(px, py):
    if MAP is not None:
        return MAP.to_mat(px, py)
    return tuple(PX2W @ [px, py, 1])


def to_px(x, y):
    if MAP is not None:
        return tuple(int(round(v)) for v in MAP.to_px(x, y))
    return tuple(int(round(v)) for v in W2PX @ [x, y, 1])


def use_matcam(mc):
    """Map pixels with a fitted mat calibration; the search box becomes the mat's own outline."""
    global MAP, INTERIOR
    MAP = mc
    xs, ys = zip(*(mc.to_px(x, y) for x in (-60.5, 58.5) for y in (-24.9, 33.7)))
    INTERIOR = (int(min(xs)), int(max(xs)), int(min(ys)), int(max(ys)))


def garages():
    """{colour: (corners [(x, y)], open side (i, j))} in mat cm."""
    m = Mat("bb-obstacle")
    return {s["color"]: ([tuple(float(v) for v in m.px_to_playfield(*p)) for p in s["corners_px"]], tuple(s["opening"]))
            for s in m.features["squares"]}


def inside(poly, x, y, margin=0.0):
    """Point in convex polygon, at least `margin` cm in from every side."""
    n = len(poly)
    sgn = None
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        d = cross / math.hypot(bx - ax, by - ay)
        s = d > 0
        if sgn is None:
            sgn = s
        if s != sgn or abs(d) < margin:
            return False
    return True


class Vision:
    def __init__(self, daemon):
        self.d = daemon

    def frame(self):
        f = self.d.get_frame(CAM, deskewed=True, encoding="png")
        return cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)

    def cubes(self, img, robots=(), clear=ROBOT_CLEAR):
        """[(colour, x, y)] in mat cm; `robots` are (x, y) centres whose surroundings (`clear` cm) are ignored."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, _ = cv2.split(hsv)
        lift = cv2.subtract(s, cv2.medianBlur(s, 41))
        field = np.zeros_like(s)
        x0, x1, y0, y1 = INTERIOR
        field[y0:y1, x0:x1] = 255
        out = []
        for name, ((lo, hi), _) in COLORS.items():
            # the chassis reads blue: blue is ignored further out than the other colours
            mask = field.copy()
            r = clear if name == "blue" else min(clear, BODY_CLEAR)
            for rx, ry in robots:
                cv2.circle(mask, to_px(rx, ry), int(r / 0.169), 0, -1)
            m = (((h >= lo) & (h <= hi) & (lift > LIFT)).astype(np.uint8) * 255) & mask
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))   # drops the garage lines (<= 6 px)
            n, lab, st, cen = cv2.connectedComponentsWithStats(m)
            for i in range(1, n):
                _, _, w, hh, a = st[i]
                if a < 60 or w < 8 or hh < 8 or w > 60 or hh > 60 or a / (w * hh) < 0.4:
                    continue
                # cubes near the field edge show their sides and read large: split only
                # a blob that is long (two cubes side by side) or far too big for one
                if max(w, hh) / min(w, hh) >= 1.5 and a >= 1.4 * CUBE_PX:
                    k = max(2, round(a / (1.3 * CUBE_PX)))
                else:
                    k = 1 if a < 2.6 * CUBE_PX else round(a / (1.3 * CUBE_PX))
                if k == 1:
                    # a paddle (hue ~14, like a reddish cube) is long and thin; a cube is square
                    if w > 34 or hh > 34 or a / (w * hh) < 0.55 or max(w, hh) / min(w, hh) > 1.6:
                        continue
                    out.append((name, *to_world(*cen[i])))
                    continue
                # touching cubes merge into one blob: split it by area
                pts = np.argwhere(lab == i).astype(np.float32)[:, ::-1]
                _, _, centres = cv2.kmeans(pts, min(k, 4), None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5), 3,
                                           cv2.KMEANS_PP_CENTERS)
                out += [(name, *to_world(*c)) for c in centres]
        return out

    def snap(self, path, img=None, robots=(), note=""):
        """Save the frame with cubes boxed and garages outlined."""
        img = self.frame() if img is None else img
        out = img.copy()
        for name, (corners, _) in garages().items():
            cv2.polylines(out, [np.array([to_px(*c) for c in corners])], True, COLORS[name][1], 1)
        for name, x, y in self.cubes(img, robots):
            px, py = to_px(x, y)
            cv2.rectangle(out, (px - 11, py - 11), (px + 11, py + 11), COLORS[name][1], 2)
        if note:
            cv2.putText(out, note, (10, 525), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(out, note, (10, 525), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        cv2.imwrite(path, out)
        return path


def main():
    from aprilcam.client.discovery import Discovery
    v = Vision(Discovery().connect())
    img = v.frame()
    for name, x, y in sorted(v.cubes(img)):
        home = next((c for c, (poly, _) in garages().items() if inside(poly, x, y)), "-")
        print(f"{name:6s} ({x:6.1f},{y:6.1f})  in {home} garage")
    if len(sys.argv) > 1:
        print("saved", v.snap(sys.argv[1], img, note=time.strftime("%H:%M:%S")))


if __name__ == "__main__":
    main()
