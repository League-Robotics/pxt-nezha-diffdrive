"""Fast overhead-camera access: one persistent gRPC connection.

The obvious approach -- shelling out to `aprilcam tool get_tags` per
sample -- spawns a process and builds a fresh gRPC channel every time.
At the few-Hz rate needed to follow a moving robot that fell over:
the calls started timing out at 20 s under their own contention.
DaemonControl holds ONE channel open, so a sample is a single RPC.

Runs under the AprilTags venv, which has the aprilcam package:
  /Volumes/Proj/proj/RobotProjects/AprilTags/.venv/bin/python3
"""
import math
import sys

sys.path.insert(0, '/Volumes/Proj/proj/RobotProjects/AprilTags/src')

from aprilcam.client.control import DaemonControl

# The playfield daemon listens on TCP here. mDNS discovery does not find
# it and the local unix socket belongs to a different instance, so the
# host/port are explicit.
HOST, PORT = '127.0.0.1', 5280
CAM = 'arducam-ov9782-usb-camera'


class Cam:
    """Tag reader. `read` returns (yaw_deg, x_cm, y_cm) or None."""

    def __init__(self, cam=CAM, host=HOST, port=PORT):
        self.cam = cam
        self.dc = DaemonControl(host=host, port=port).connect()

    def read(self, tag_id=53):
        try:
            rec = self.dc.get_tags(self.cam).by_id(tag_id)
        except Exception:
            return None
        if rec is None:
            return None
        w = getattr(rec, 'world_xy', None)
        # The gRPC model calls it `yaw`; the MCP/JSON shape calls the
        # same quantity `orientation_yaw`. Accept either.
        raw = getattr(rec, 'yaw', None)
        if raw is None:
            raw = getattr(rec, 'orientation_yaw', 0.0)
        yaw = math.degrees(raw or 0.0)
        if not w or w[0] is None:
            return yaw, float('nan'), float('nan')
        return yaw, float(w[0]), float(w[1])

    def close(self):
        try:
            self.dc.close()
        except Exception:
            pass


def _stream(tag_id, hz):
    """Print `yaw_deg x_cm y_cm` lines forever, for another process.

    The camera library and pyserial live in DIFFERENT interpreters here
    (the AprilTags venv has aprilcam but no pip, so pyserial cannot be
    added to it). Rather than fight that, the camera runs as its own
    process and streams lines; the robot-driving process reads them.
    """
    import time
    cam = Cam()
    period = 1.0 / hz
    while True:
        r = cam.read(tag_id)
        if r is not None:
            print(f'{r[0]:.3f} {r[1]:.3f} {r[2]:.3f}', flush=True)
        time.sleep(period)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', type=int, default=53)
    ap.add_argument('--hz', type=float, default=20.0)
    args = ap.parse_args()
    _stream(args.tag, args.hz)
