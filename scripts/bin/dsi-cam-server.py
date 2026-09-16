#!/usr/bin/env python3
"""Live Pi camera view for the DSI Camera kiosk: MJPEG over HTTP on
127.0.0.1 only (never exposed to the LAN or the PINET hotspot).

Uses picamera2's MJPEGEncoder (hardware JPEG on the Pi 3B) at 10 fps to keep
CPU and power draw low. Runs only while the Camera kiosk is open; SIGTERM
stops recording so the camera is released.

The served page is a bare <img> (the cog/WPE kiosk renders that reliably and
does NOT deliver taps to web content). Photo/record are driven by NATIVE
layer-shell buttons (dsi-cam-controls.py) that POST to the capture endpoints
here; captures are saved to /mnt/pinet-media/camera, upright.
"""
import datetime
import io
import json
import logging
import os
import queue
import signal
import socketserver
import subprocess
import sys
import threading
import time
from http import server
from threading import Condition

from PIL import Image
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder
from picamera2.outputs import FfmpegOutput, FileOutput

ADDRESS = ("127.0.0.1", 8081)
SIZE = (640, 480)
FRAME_US = 100000  # 10 fps
CONFIG = "/etc/default/dsi-camera"
MEDIA_DIR = "/mnt/pinet-media/camera"


def read_rotation():
    """CAMERA_ROTATION (0/90/180/270) from CONFIG; the camera is mounted in
    portrait, and libcamera can only flip, not rotate 90, so the page rotates."""
    try:
        with open(CONFIG) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "CAMERA_ROTATION" and value.strip() in ("0", "90", "180", "270"):
                    return int(value)
    except OSError:
        pass
    return 90


ROTATION = read_rotation()


def build_page(rotation):
    if rotation in (90, 270):
        img_css = ("position:absolute; top:50%; left:50%; width:100vh; height:auto; "
                   f"transform:translate(-50%,-50%) rotate({rotation}deg);")
    else:
        img_css = (f"width:100vw; height:100vh; object-fit:cover; display:block; "
                   f"transform:rotate({rotation}deg);")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Pi Camera</title>
<style>
html, body {{ margin: 0; height: 100%; background: #000; overflow: hidden; }}
img {{ {img_css} }}
</style></head>
<body><img src="/stream.mjpg" alt=""></body></html>
""".encode()


PAGE = build_page(ROTATION)


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


# --- camera worker ---
# All picamera2 encoder ops must run on ONE persistent thread. An encoder
# started from a transient HTTP worker thread produces no output once that
# thread exits (the MJPEG encoder works only because the main thread that
# starts it lives on in serve_forever). So funnel every camera op through a
# single long-lived worker, which also serialises access to the one camera.
rec_state = {"active": False, "encoder": None, "output": None, "tmp": None, "final": None}
_cam_q = queue.Queue()


def _camera_worker():
    while True:
        fn, resq = _cam_q.get()
        try:
            resq.put((True, fn()))
        except Exception as exc:  # noqa: BLE001
            resq.put((False, exc))


def _on_cam(fn):
    """Run fn() on the camera worker thread and return its result (or raise)."""
    resq = queue.Queue()
    _cam_q.put((fn, resq))
    ok, val = resq.get()
    if not ok:
        raise val
    return val


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir():
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
    except OSError:
        pass


def capture_photo():
    _ensure_dir()
    name = f"photo_{_stamp()}.jpg"
    final = os.path.join(MEDIA_DIR, name)
    tmp = final + ".raw.jpg"

    def _cap():
        request = picam2.capture_request()
        try:
            request.save("main", tmp)
        finally:
            request.release()

    _on_cam(_cap)
    angle = (360 - ROTATION) % 360
    if angle:
        with Image.open(tmp) as im:
            im.rotate(angle, expand=True).save(final, quality=90)
        os.remove(tmp)
    else:
        os.replace(tmp, final)
    return name


def record_start():
    _ensure_dir()
    name = f"video_{_stamp()}.mp4"
    final = os.path.join(MEDIA_DIR, name)
    tmp = final + ".raw.mp4"

    def _start():
        if rec_state["active"]:
            raise RuntimeError("already recording")
        encoder = H264Encoder()
        output = FfmpegOutput(tmp)
        picam2.start_encoder(encoder, output, name="main")
        rec_state.update(active=True, encoder=encoder, output=output, tmp=tmp, final=final)

    _on_cam(_start)
    return name


def record_stop():
    def _stop():
        if not rec_state["active"]:
            raise RuntimeError("not recording")
        paths = (rec_state["tmp"], rec_state["final"])
        picam2.stop_encoder([rec_state["encoder"]])
        rec_state.update(active=False, encoder=None, output=None, tmp=None, final=None)
        return paths

    tmp, final = _on_cam(_stop)
    time.sleep(0.4)
    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        raise RuntimeError("no video captured (encoder produced no file)")
    name = os.path.basename(final)
    rot_ccw = (360 - ROTATION) % 360
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-display_rotation", str(rot_ccw), "-i", tmp,
             "-c", "copy", final],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        os.remove(tmp)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        try:
            os.replace(tmp, final)
        except OSError:
            pass
    return name


class StreamingHandler(server.BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            if self.path == "/capture/photo":
                self._json(200, {"ok": True, "file": capture_photo()})
            elif self.path == "/record/start":
                self._json(200, {"ok": True, "file": record_start()})
            elif self.path == "/record/stop":
                self._json(200, {"ok": True, "file": record_stop()})
            else:
                self.send_error(404)
        except Exception as exc:  # noqa: BLE001
            logging.warning("capture error: %s", exc)
            try:
                self._json(200, {"ok": False, "error": str(exc)})
            except OSError:
                pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path == "/record/status":
            self._json(200, {"recording": rec_state["active"]})
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _shutdown(*_):
    try:
        if rec_state["active"] and rec_state["encoder"] is not None:
            picam2.stop_encoder([rec_state["encoder"]])
    except Exception:  # noqa: BLE001
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown)
logging.basicConfig(level=logging.WARNING)

picam2 = Picamera2()
# Two streams so the MJPEG preview and the on-demand H264 recorder each get
# their own encoder (two encoders can't share one stream). Both YUV420: the
# Pi's hardware H264 encoder rejects RGB/XBGR. lores drives the live preview;
# main is captured for stills and recorded to H264 video.
picam2.configure(picam2.create_video_configuration(
    main={"size": SIZE, "format": "YUV420"},
    lores={"size": SIZE, "format": "YUV420"},
    controls={"FrameDurationLimits": (FRAME_US, FRAME_US)},
))
output = StreamingOutput()
picam2.start_recording(MJPEGEncoder(), FileOutput(output), name="lores")
threading.Thread(target=_camera_worker, daemon=True).start()
try:
    StreamingServer(ADDRESS, StreamingHandler).serve_forever()
finally:
    picam2.stop_recording()
