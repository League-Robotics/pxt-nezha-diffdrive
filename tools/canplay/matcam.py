"""Calibrate the overhead camera straight to the bb-obstacle mat, wherever the mat and table are.

    uv run python tools/canplay/matcam.py fit [out.json]     fit and save (default tools/canplay/matcam.json)
    uv run python tools/canplay/matcam.py robot vevov        the robot's mat pose from its tag

The daemon's deskewed frame removes the lens distortion; a homography from
that frame to mat cm is fitted through the mat's 12 red circles (each ring
found near a rough guess) and checked against the mat's ArUco fiducial.
Tags above the table are pulled toward the camera nadir by (H - h) / H.
"""
import json, math, os, sys
import numpy as np, cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from canplay import CAM, MAT_DIR, ROBOTS, Mat  # noqa: E402

SAVE = os.path.join(HERE, "matcam.json")
OLD_PPC, OLD_W, OLD_H = 5.95681310498883, 134.3, 89.3      # the daemon's deskew frame


def deskew_px(x, y):
    """Old playfield cm -> deskewed pixel (the frame is the old world extent, centred)."""
    return ((x + OLD_W / 2) * OLD_PPC, (OLD_H / 2 - y) * OLD_PPC)


def frame(d):
    f = d.get_frame(CAM, deskewed=True, encoding="png")
    return cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR)


def ring_centre(img, guess, r=18, win=34):
    """The printed ring nearest `guess` in the deskewed frame (a thin darker circle)."""
    x0, y0 = max(0, int(guess[0]) - win), max(0, int(guess[1]) - win)
    g = cv2.cvtColor(img[y0:y0 + 2 * win, x0:x0 + 2 * win], cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    found = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT, 1, 20, param1=40, param2=14,
                             minRadius=int(0.75 * r), maxRadius=int(1.3 * r))
    if found is None:
        return None
    gx, gy = guess[0] - x0, guess[1] - y0
    cx, cy, _ = min(found[0], key=lambda c: math.hypot(c[0] - gx, c[1] - gy))
    if math.hypot(cx - gx, cy - gy) > win * 0.7:
        return None
    return (float(cx) + x0, float(cy) + y0)


def fit(img, guesses):
    m = Mat("bb-obstacle")
    C = {c["n"]: tuple(float(v) for v in m.px_to_playfield(*c["px"])) for c in m.features["circles"]}
    src, dst, used = [], [], []
    for n, g in guesses.items():
        p = ring_centre(img, g)
        if p is None:
            print(f"circle {n}: ring not found near {g}")
            continue
        src.append(p)
        dst.append(C[n])
        used.append(n)
    H, _ = cv2.findHomography(np.array(src), np.array(dst), 0)
    res = [math.dist(apply(H, p), q) for p, q in zip(src, dst)]
    for n, r in zip(used, res):
        print(f"circle {n:2d}: residual {r:.2f} cm")
    return H, src


def apply(H, p):
    v = H @ [p[0], p[1], 1.0]
    return (v[0] / v[2], v[1] / v[2])


class MatCam:
    def __init__(self, path=SAVE):
        c = json.load(open(path))
        self.H = np.array(c["H"])
        self.Hinv = np.linalg.inv(self.H)
        self.cam_h = c["camera_height_cm"]
        self.nadir = tuple(c["nadir_mat"])

    def to_mat(self, px, py, h=0.0):
        x, y = apply(self.H, (px, py))
        k = (self.cam_h - h) / self.cam_h
        return (self.nadir[0] + (x - self.nadir[0]) * k, self.nadir[1] + (y - self.nadir[1]) * k)

    def to_px(self, x, y):
        return apply(self.Hinv, (x, y))

    def tags(self, img):
        """{id: corners (4x2 deskewed px)} for AprilTag 36h11."""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
                                      cv2.aruco.DetectorParameters())
        corners, ids, _ = det.detectMarkers(g)
        return {} if ids is None else {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}

    def robot_pose(self, corners, vision):
        """Robot centre (mat cm) and heading (deg) from its tag's corners and its config's vision block."""
        h = vision["tag_offset_z"] / 10
        pts = [self.to_mat(*c, h) for c in corners]
        cx = sum(p[0] for p in pts) / 4
        cy = sum(p[1] for p in pts) / 4
        # corner 0 -> 1 is the tag's top edge, left to right: the tag's +x
        yaw = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]))
        hd = yaw - vision["tag_offset_yaw"]
        r = math.radians(hd)
        ox, oy = vision["tag_offset_x"] / 10, vision["tag_offset_y"] / 10
        x = cx - (ox * math.cos(r) - oy * math.sin(r))
        y = cy - (ox * math.sin(r) + oy * math.cos(r))
        return x, y, (hd + 180) % 360 - 180


class MatSeer:
    """Stands in for canplay.Camera: robot poses from tags read in the deskewed frame and mapped
    with the mat calibration (the daemon's own world calibration may be stale)."""
    def __init__(self, robots):
        from aprilcam.client.discovery import Discovery
        self.d = Discovery().connect()
        self.mc = MatCam()
        self.vision = {}
        for name in robots:
            v = json.load(open(os.path.join(ROBOTS, f"{name}.json")))["vision"]
            self.vision[v["robot_tag_id"]] = v

    def seen(self, n=4):
        acc = {}
        for _ in range(n):
            tags = self.mc.tags(frame(self.d))
            for t, corners in tags.items():
                if t in self.vision:
                    acc.setdefault(t, []).append(self.mc.robot_pose(corners, self.vision[t]))
        out = {}
        for t, v in acc.items():
            if len(v) < max(1, n // 2):
                continue
            hd = math.degrees(math.atan2(sum(math.sin(math.radians(a[2])) for a in v), sum(math.cos(math.radians(a[2])) for a in v)))
            out[t] = (sum(a[0] for a in v) / len(v), sum(a[1] for a in v) / len(v), hd)
        return out


def main():
    from aprilcam.client.discovery import Discovery
    d = Discovery().connect()
    img = frame(d)
    if sys.argv[1] == "fit":
        guesses = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        guesses = {int(k): v for k, v in guesses.items()}
        H, _ = fit(img, guesses)
        cal = d.get_calibration(CAM)
        old_h = cal.camera_height_cm if hasattr(cal, "camera_height_cm") else cal["camera_height_cm"]
        drop = float(os.environ.get("TABLE_DROP_CM", "3.81"))
        nad = deskew_px(cal.camera_nadir_x_cm, cal.camera_nadir_y_cm)
        out = {"H": H.tolist(), "camera_height_cm": old_h + drop, "nadir_mat": list(apply(H, nad)),
               "note": f"homography deskewed px -> mat cm through the 12 circles; camera height = old {old_h:.1f} + table drop {drop}"}
        path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else SAVE
        json.dump(out, open(path, "w"), indent=1)
        print("saved", path, "camera height", round(old_h + drop, 1), "nadir", [round(v, 1) for v in out["nadir_mat"]])
    elif sys.argv[1] == "robot":
        mc = MatCam()
        v = json.load(open(os.path.join(ROBOTS, f"{sys.argv[2]}.json")))["vision"]
        tags = mc.tags(img)
        if v["robot_tag_id"] not in tags:
            sys.exit(f"tag {v['robot_tag_id']} not seen; saw {sorted(tags)}")
        print([round(a, 1) for a in mc.robot_pose(tags[v["robot_tag_id"]], v)])


if __name__ == "__main__":
    main()
