"""Serve the SafeStride live inference stream to a browser."""

import argparse
import cgi
import json
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import cv2
import numpy as np

from blindnav.announcer import Alert, Announcer, WARNING, message, rank_alerts
from blindnav.depth import DepthEstimator, object_distance
from blindnav.detector import HAZARD_CLASS_CONF, Detector
from blindnav.risk import MotionTracker
from blindnav.spatial import SpatialAnalyzer
from blindnav.speech import LiveSpeaker
from blindnav.visualize import TrailDrawer, draw_detections, draw_fps, draw_path

ROOT = Path(__file__).parent
WEB = ROOT / "web"
UPLOADS = ROOT / "data" / "uploads"
state_lock = threading.Lock()
inference_lock = threading.Lock()
state = {"connected": False, "status": "Waiting for camera", "alert": None,
         "alert_id": 0, "detections": 0, "fps": 0.0, "depth": False}


class InferenceEngine:
    def __init__(self, no_depth: bool, no_hazards: bool, depth_every: int = 2):
        self.detector = Detector()
        self.hazard_detector = None
        if not no_hazards and Path("models/hazards.pt").exists():
            self.hazard_detector = Detector("models/hazards.pt", class_conf=HAZARD_CLASS_CONF,
                                            all_classes=True, id_offset=100_000)
        self.depth = None if no_depth else self._load_depth()
        self.depth_every = max(1, depth_every)
        self.depth_frame = None
        self.frame_index = 0
        self.spatial = SpatialAnalyzer()
        self.motion = MotionTracker()
        self.announcer = Announcer()
        self.audio = LiveSpeaker("en")
        self.trails = TrailDrawer()
        self.started = time.perf_counter()
        self.last_guidance = None
        self.last_guidance_time = -float("inf")

    @staticmethod
    def _load_depth():
        try:
            return DepthEstimator(input_size=392)
        except Exception as exc:
            with state_lock:
                state["status"] = f"Depth unavailable: {type(exc).__name__}"
            return None

    def frame(self, image: np.ndarray):
        self.frame_index += 1
        started = time.perf_counter()
        detections = self.detector.detect(image)
        if self.hazard_detector:
            detections += self.hazard_detector.detect(image)
        path = None
        alert_text = None
        if self.depth:
            if self.depth_frame is None or self.frame_index % self.depth_every == 1:
                self.depth_frame = self.depth.estimate(image)
            depth = self.depth_frame
            for detection in detections:
                detection.distance = object_distance(depth, detection.box)
            path = self.spatial.analyze(depth, detections)
            elapsed = time.perf_counter() - self.started
            self.motion.update(elapsed, detections, path, image.shape[0])
            alert = self.announcer.decide(elapsed, rank_alerts(detections, path))
            if alert:
                if path.guidance and alert.guidance is None:
                    alert.guidance = path.guidance
                alert_text = message(alert)
                self.audio.say(alert, alert_text)
            elif path.guidance and (path.guidance != self.last_guidance or
                                    elapsed - self.last_guidance_time > 5.0):
                alert = Alert("guidance", "obstacle", path.distance, path.clock or 12,
                              0.0, WARNING, guidance=path.guidance)
                alert_text = message(alert)
                self.audio.say(alert, alert_text)
                self.last_guidance = path.guidance
                self.last_guidance_time = elapsed
        self.trails.draw(image, detections)
        if path is not None:
            draw_path(image, path)
        draw_detections(image, detections)
        draw_fps(image, 1 / max(time.perf_counter() - started, 0.001))
        with state_lock:
            if alert_text:
                state["alert_id"] += 1
            state.update({"connected": True, "status": "Monitoring",
                          "detections": len(detections),
                          "fps": round(1 / max(time.perf_counter() - started, 0.001), 1),
                          "depth": self.depth is not None})
            if alert_text:
                state["alert"] = alert_text
        return image


class Handler(BaseHTTPRequestHandler):
    engine = None
    source = 0

    def log_message(self, *_args):
        return

    def do_GET(self):
        route = urlparse(self.path)
        if route.path == "/health":
            with state_lock:
                self._json({"ok": True, **state})
        elif route.path == "/state":
            with state_lock:
                self._json(dict(state))
        elif route.path == "/stream":
            self._stream()
        else:
            self._static(route.path)

    def do_POST(self):
        if urlparse(self.path).path == "/frame":
            self._frame()
            return
        if urlparse(self.path).path != "/upload":
            self.send_error(404)
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 2 * 1024 * 1024 * 1024:
            self.send_error(413, "Video is larger than 2 GB")
            return
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(400, "Expected multipart video upload")
            return
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                environ={"REQUEST_METHOD": "POST",
                                         "CONTENT_TYPE": content_type,
                                         "CONTENT_LENGTH": str(content_length)})
        uploaded = form["video"] if "video" in form else None
        if uploaded is None or not uploaded.filename:
            self.send_error(400, "No video file was provided")
            return
        original_name = Path(uploaded.filename).name
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
            self.send_error(415, "Use an MP4, MOV, AVI, MKV, WEBM, or M4V video")
            return
        UPLOADS.mkdir(parents=True, exist_ok=True)
        saved = UPLOADS / f"{Path(original_name).stem[:50]}-{uuid.uuid4().hex[:8]}{suffix}"
        with saved.open("wb") as destination:
            shutil.copyfileobj(uploaded.file, destination)
        Handler.source = str(saved)
        self._json({"ok": True, "name": original_name, "source": str(saved),
                    "message": f"{original_name} uploaded and ready"})

    def _json(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, route):
        relative = "index.html" if route in ("/", "") else route.lstrip("/")
        file_path = (WEB / relative).resolve()
        if WEB.resolve() not in file_path.parents or not file_path.is_file():
            self.send_error(404)
            return
        content_type = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}.get(
            file_path.suffix, "application/octet-stream")
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self.send_error(503, "Camera could not be opened")
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with state_lock:
            state["connected"] = True
            state["status"] = "Starting inference"
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] > 1280:
                    frame = cv2.resize(frame, (1280, int(frame.shape[0] * 1280 / frame.shape[1])))
                frame = self.engine.frame(frame)
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if not ok:
                    continue
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                self.wfile.write(encoded.tobytes())
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            cap.release()
            with state_lock:
                state["connected"] = False
                state["status"] = "Camera stopped"

    def _frame(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 8 * 1024 * 1024:
            self.send_error(413, "Camera frame is missing or too large")
            return
        raw = self.rfile.read(content_length)
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            self.send_error(400, "Invalid camera frame")
            return
        if image.shape[1] > 1280:
            image = cv2.resize(image, (1280, int(image.shape[0] * 1280 / image.shape[1])))
        with inference_lock:
            annotated = self.engine.frame(image)
        ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            self.send_error(500, "Could not encode annotated frame")
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source", default="0", help="webcam index or video path")
    parser.add_argument("--no-depth", action="store_true")
    parser.add_argument("--no-hazards", action="store_true")
    parser.add_argument("--depth-every", type=int, default=2)
    args = parser.parse_args()
    Handler.source = int(args.source) if args.source.isdigit() else args.source
    Handler.engine = InferenceEngine(args.no_depth, args.no_hazards, args.depth_every)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"SafeStride web console: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()