"""Serve the SafeStride live inference stream to a browser."""

import argparse
import base64
import cgi
import json
import math
import os
import secrets
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np

from blindnav.announcer import Alert, Announcer, URGENT, WARNING, message, rank_alerts
from blindnav.depth import DepthEstimator, object_distance
from blindnav.detector import HAZARD_CLASS_CONF, Detector
from blindnav.navigation import NavigationManager
from blindnav.risk import MotionTracker
from blindnav.spatial import SpatialAnalyzer, keep_confirmed_stairs
from blindnav.speech import LiveSpeaker
from blindnav.visualize import TrailDrawer, draw_detections, draw_fps, draw_path

ROOT = Path(__file__).parent
WEB = ROOT / "web"
MODELS = ROOT / "models"
UPLOADS = ROOT / "data" / "uploads"
state_lock = threading.Lock()
inference_lock = threading.Lock()
state = {"connected": False, "status": "Waiting for camera", "alert": None,
         "alert_id": 0, "detections": 0, "fps": 0.0, "depth": False,
         "location": None, "alert_time": 0.0, "urgent": False,
         "active_alert": None, "safety_active": False, "safety_urgent": False,
         "alert_urgent": False,
         "navigation": {"active": False, "guidance": None, "event_id": 0}}
navigation_lock = threading.Lock()
navigation = NavigationManager()
screen_share_lock = threading.Lock()
screen_share = {"token": None, "offer": None, "answer": None, "frame": None}

SCREEN_VIEWER_HTML = r"""<!doctype html>
<html lang="en">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
    <title>SafeStride screen share</title>
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #10191d; color: #edf5f2; font: 16px system-ui, sans-serif; }
        main { width: min(100vw, 680px); padding: 16px; }
        img { display: block; width: 100%; max-height: 92vh; background: #050809; object-fit: contain; border-radius: 8px; }
        #status { padding: 12px 2px; color: #9ce5c8; }
    </style>
</head>
<body>
    <main><img id="screen" alt="Live SafeStride app preview"><div id="status">Waiting for phone frames…</div></main>
    <script>
        const token = __SESSION_TOKEN__;
        const preview = document.getElementById('screen');
        const status = document.getElementById('status');
        let previousUrl = null;
        async function pollFrame() {
            try {
                const response = await fetch(`/screen/frame?token=${encodeURIComponent(token)}&t=${Date.now()}`, { cache: 'no-store' });
                if (response.status === 404) {
                    status.textContent = 'Share session expired. Start sharing again on the phone.';
                    return;
                }
                if (response.status === 200) {
                    const nextUrl = URL.createObjectURL(await response.blob());
                    preview.src = nextUrl;
                    if (previousUrl) URL.revokeObjectURL(previousUrl);
                    previousUrl = nextUrl;
                    status.textContent = 'Live app preview';
                }
            } catch {
                status.textContent = 'Waiting for phone connection…';
            }
            setTimeout(pollFrame, 500);
        }
        pollFrame();
    </script>
</body>
</html>"""


def _finite_number(value) -> float | None:
    """A JSON number as float, or None for null, booleans, strings, NaN and infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _json_request(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "SafeStride-Assist/0.1"})
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _geocode(query: str) -> tuple[float, float, str]:
    url = "https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" + quote(query)
    results = _json_request(url)
    if not results:
        raise ValueError("Destination was not found")
    result = results[0]
    return float(result["lat"]), float(result["lon"]), result.get("display_name", query)


def _place_suggestions(query: str, near: tuple[float, float] | None = None) -> list[dict]:
    params = {"limit": 5, "lang": "en", "q": query}
    if near:
        latitude, longitude = near
        params.update({"lat": latitude, "lon": longitude})
    url = "https://photon.komoot.io/api/?" + urlencode(params)
    features = _json_request(url).get("features", [])
    suggestions = []
    seen_coordinates = set()
    for feature in features:
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) != 2:
            continue
        latitude, longitude = float(coordinates[1]), float(coordinates[0])
        coordinate_key = (round(latitude, 6), round(longitude, 6))
        if coordinate_key in seen_coordinates:
            continue
        seen_coordinates.add(coordinate_key)
        name = properties.get("name") or properties.get("street") or query
        locality = properties.get("city") or properties.get("town") or properties.get("village")
        address_parts = [name, properties.get("street"), properties.get("district"), locality,
                         properties.get("state"), properties.get("country")]
        display_name = ", ".join(dict.fromkeys(part for part in address_parts if part))
        suggestions.append({
            "name": name,
            "display_name": display_name,
            "latitude": latitude,
            "longitude": longitude,
        })
    return suggestions


def _google_place_suggestions(
    query: str,
    near: tuple[float, float] | None,
    api_key: str,
) -> list[dict]:
    payload = {"textQuery": query, "languageCode": "en", "regionCode": "IN", "pageSize": 5}
    if near:
        payload["locationBias"] = {
            "circle": {
                "center": {"latitude": near[0], "longitude": near[1]},
                "radius": 50000,
            }
        }
    request = Request(
        "https://places.googleapis.com/v1/places:searchText",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        results = json.loads(response.read().decode("utf-8")).get("places", [])
    return [
        {
            "name": place.get("displayName", {}).get("text", query),
            "display_name": place.get("formattedAddress") or place.get("displayName", {}).get("text", query),
            "latitude": float(place["location"]["latitude"]),
            "longitude": float(place["location"]["longitude"]),
        }
        for place in results
        if place.get("location")
    ]


def _walking_route(start: tuple[float, float], destination: tuple[float, float]) -> dict:
    base = os.environ.get(
        "SAFESTRIDE_ROUTING_URL",
        "https://routing.openstreetmap.de/routed-foot/route/v1/driving",
    )
    coordinates = f"{start[1]},{start[0]};{destination[1]},{destination[0]}"
    url = f"{base}/{coordinates}?overview=full&geometries=geojson&steps=true"
    payload = _json_request(url)
    routes = payload.get("routes", [])
    if not routes:
        raise ValueError("No walking route was found")
    return routes[0]


class InferenceEngine:
    def __init__(self, no_depth: bool, no_hazards: bool, depth_every: int = 2):
        self.detector = Detector(str(MODELS / "yolo11s.pt"))
        self.hazard_detector = None
        self.door_detector = None
        if not no_hazards and (MODELS / "hazards.pt").exists():
            self.hazard_detector = Detector(str(MODELS / "hazards.pt"), class_conf=HAZARD_CLASS_CONF,
                                            all_classes=True, id_offset=100_000)
        if (MODELS / "doors.pt").exists():
            self.door_detector = Detector(str(MODELS / "doors.pt"), all_classes=True, id_offset=200_000)
        self.depth = None if no_depth else self._load_depth()
        self.depth_every = max(1, depth_every)
        self.audio = LiveSpeaker("en")
        self.reset()

    def reset(self) -> None:
        """Forget everything about the previous video or camera session."""
        for detector in (self.detector, self.hazard_detector, self.door_detector):
            if detector:
                detector.reset_tracking()
        self.depth_frame = None
        self.frame_index = 0
        self.spatial = SpatialAnalyzer()
        self.motion = MotionTracker()
        self.announcer = Announcer()
        self.trails = TrailDrawer()
        self.started = time.perf_counter()
        self.last_guidance = None
        self.last_guidance_time = -float("inf")
        self.safety_clear_frames = 0
        self.safety_latched = False
        self.safety_latched_urgent = False

    @staticmethod
    def _load_depth():
        try:
            return DepthEstimator(input_size=392)
        except Exception as exc:
            with state_lock:
                state["status"] = f"Depth unavailable: {type(exc).__name__}"
            return None

    def frame(self, image: np.ndarray, speak_alert: bool = True, timestamp: float | None = None):
        """`timestamp`: video time in seconds. Without it, wall-clock time since start is used."""
        self.frame_index += 1
        started = time.perf_counter()
        detections = self.detector.detect(image)
        if self.hazard_detector:
            detections += self.hazard_detector.detect(image)
        if self.door_detector:
            detections += self.door_detector.detect(image)
        path = None
        alert_text = None
        active_alerts = []
        if self.depth:
            stale = self.depth_frame is None or self.depth_frame.shape != image.shape[:2]
            if stale or (self.frame_index - 1) % self.depth_every == 0:
                self.depth_frame = self.depth.estimate(image)
            depth = self.depth_frame
            for detection in detections:
                detection.distance = object_distance(depth, detection.box)
            path = self.spatial.analyze(depth, detections)
            detections = keep_confirmed_stairs(detections)
            elapsed = timestamp if timestamp is not None else time.perf_counter() - self.started
            self.motion.update(elapsed, detections, path, image.shape[0])
            active_alerts = rank_alerts(detections, path)
            if active_alerts:
                self.safety_latched = True
                self.safety_latched_urgent = active_alerts[0].level == URGENT
                self.safety_clear_frames = 0
            elif self.safety_latched:
                self.safety_clear_frames += 1
                if self.safety_clear_frames >= 3:
                    self.safety_latched = False
                    self.safety_latched_urgent = False
                    self.safety_clear_frames = 0
            alert = self.announcer.decide(elapsed, active_alerts)
            if alert:
                if path.guidance and alert.guidance is None:
                    alert.guidance = path.guidance
                alert_text = message(alert)
                if speak_alert:
                    self.audio.say(alert, alert_text)
            elif path.guidance and (path.guidance != self.last_guidance or
                                    elapsed - self.last_guidance_time > 5.0):
                alert = Alert("guidance", "obstacle", path.distance, path.clock or 12,
                              0.0, WARNING, guidance=path.guidance)
                alert_text = message(alert)
                if speak_alert:
                    self.audio.say(alert, alert_text)
                self.last_guidance = path.guidance
                self.last_guidance_time = elapsed
        else:
            detections = keep_confirmed_stairs(detections)
        self.trails.draw(image, detections)
        if path is not None:
            draw_path(image, path)
        draw_detections(image, detections)
        draw_fps(image, 1 / max(time.perf_counter() - started, 0.001))
        with state_lock:
            if alert_text:
                state["alert_id"] += 1
                state["alert_time"] = time.time()
                state["alert_urgent"] = alert.level == URGENT
            state.update({"connected": True, "status": "Monitoring",
                          "detections": len(detections),
                          "fps": round(1 / max(time.perf_counter() - started, 0.001), 1),
                          "depth": self.depth is not None,
                          "active_alert": (message(active_alerts[0]) if active_alerts else
                                           "Confirming the path is clear" if self.safety_latched else None),
                          "safety_active": self.safety_latched,
                          "safety_urgent": self.safety_latched_urgent,
                          "urgent": self.safety_latched_urgent})
            if alert_text:
                state["alert"] = alert_text
        return image


class Handler(BaseHTTPRequestHandler):
    engine = None
    source = 0

    def log_message(self, *_args):
        return

    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            pass  # the client went away (on Windows this is often ConnectionAbortedError)

    @staticmethod
    def _public_state() -> dict:
        """State for clients. The user's GPS position stays on the server."""
        with state_lock:
            return {key: value for key, value in state.items() if key != "location"}

    def _screen_token_is_valid(self, token: str) -> bool:
        with screen_share_lock:
            active_token = screen_share["token"]
            return bool(active_token and secrets.compare_digest(token, active_token))

    def _screen_page(self, token: str):
        if not self._screen_token_is_valid(token):
            self.send_error(404, "Screen-share session is unavailable")
            return
        body = SCREEN_VIEWER_HTML.replace("__SESSION_TOKEN__", json.dumps(token)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _screen_signal(self, signal: str):
        token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not self._screen_token_is_valid(token):
            self.send_error(404, "Screen-share session is unavailable")
            return
        with screen_share_lock:
            self._json({signal: screen_share[signal]})

    def _screen_start(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > 4096:
            self.send_error(413, "Screen-share session request is too large")
            return
        if content_length:
            self.rfile.read(content_length)
        token = secrets.token_urlsafe(24)
        with screen_share_lock:
            screen_share.update({"token": token, "offer": None, "answer": None, "frame": None})
        self._json({"token": token})

    def _screen_write_frame(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4_000_000:
            self.send_error(413, "Screen frame is missing or too large")
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            token = str(payload.get("token", ""))
            image = payload.get("image")
            if not isinstance(image, str):
                raise ValueError("Missing screen frame")
            frame = base64.b64decode(image, validate=True)
            if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
                raise ValueError("Invalid JPEG screen frame")
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_error(400, "Invalid screen frame")
            return
        with screen_share_lock:
            active_token = screen_share["token"]
            if not active_token or not secrets.compare_digest(token, active_token):
                self.send_error(404, "Screen-share session is unavailable")
                return
            screen_share["frame"] = frame
        self._json({"ok": True})

    def _screen_read_frame(self):
        token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not self._screen_token_is_valid(token):
            self.send_error(404, "Screen-share session is unavailable")
            return
        with screen_share_lock:
            frame = screen_share["frame"]
        if frame is None:
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(frame)))
        self.end_headers()
        self.wfile.write(frame)

    def _screen_write_signal(self, signal: str):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 256_000:
            self.send_error(413, "Screen-share signaling payload is missing or too large")
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            token = str(payload.get("token", ""))
            description = payload.get("description")
            if not isinstance(description, dict) or description.get("type") not in {"offer", "answer"}:
                raise ValueError("Invalid WebRTC session description")
            if not isinstance(description.get("sdp"), str) or len(description["sdp"]) > 240_000:
                raise ValueError("Invalid WebRTC session description")
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_error(400, "Invalid screen-share signaling payload")
            return
        with screen_share_lock:
            active_token = screen_share["token"]
            if not active_token or not secrets.compare_digest(token, active_token):
                self.send_error(404, "Screen-share session is unavailable")
                return
            screen_share[signal] = description
        self._json({"ok": True})

    def _screen_stop(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(content_length)) if content_length else {}
            token = str(payload.get("token", ""))
        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_error(400, "Invalid screen-share stop payload")
            return
        with screen_share_lock:
            active_token = screen_share["token"]
            if active_token and secrets.compare_digest(token, active_token):
                screen_share.update({"token": None, "offer": None, "answer": None, "frame": None})
        self._json({"ok": True})

    def do_GET(self):
        route = urlparse(self.path)
        if route.path == "/health":
            self._json({"ok": True, **self._public_state()})
        elif route.path == "/state":
            self._json(self._public_state())
        elif route.path == "/stream":
            self._stream()
        elif route.path == "/places":
            query = parse_qs(route.query).get("q", [""])[0].strip()
            if len(query) < 3:
                self._json({"suggestions": []})
                return
            with state_lock:
                current = state.get("location")
            near = (current["latitude"], current["longitude"]) if current else None
            try:
                google_api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
                suggestions = (
                    _google_place_suggestions(query, near, google_api_key)
                    if google_api_key
                    else _place_suggestions(query, near)
                )
                provider = "Google Places" if google_api_key else "Photon"
                self._json({"suggestions": suggestions, "provider": provider})
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self.send_error(502 if isinstance(exc, OSError) else 400, str(exc))
        elif route.path == "/screen":
            token = parse_qs(route.query).get("token", [""])[0]
            self._screen_page(token)
        elif route.path == "/screen/frame":
            self._screen_read_frame()
        elif route.path == "/screen/offer":
            self._screen_signal("offer")
        elif route.path == "/screen/answer":
            self._screen_signal("answer")
        else:
            self._static(route.path)

    def do_POST(self):
        route_path = urlparse(self.path).path
        if route_path == "/screen/session":
            self._screen_start()
            return
        if route_path == "/screen/frame":
            self._screen_write_frame()
            return
        if route_path == "/screen/offer":
            self._screen_write_signal("offer")
            return
        if route_path == "/screen/answer":
            self._screen_write_signal("answer")
            return
        if route_path == "/screen/stop":
            self._screen_stop()
            return
        if urlparse(self.path).path == "/frame":
            self._frame()
            return
        if urlparse(self.path).path == "/location":
            self._location()
            return
        if urlparse(self.path).path == "/route":
            self._route()
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

    def _location(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4096:
            self.send_error(413, "Location payload is missing or too large")
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            heading_age_ms = payload.get("heading_age_ms")
            heading_timestamp = _finite_number(payload.get("heading_timestamp"))
            if _finite_number(heading_age_ms) is not None and heading_age_ms >= 0:
                heading_timestamp = time.time() * 1000 - heading_age_ms
            latitude, longitude = float(payload["latitude"]), float(payload["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("Coordinates are outside the valid range")
            location = {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": _finite_number(payload.get("accuracy")),  # may be null on some phones
                "heading": _finite_number(payload.get("heading")),
                "heading_timestamp": heading_timestamp,
                "speed": _finite_number(payload.get("speed")),
                "timestamp": _finite_number(payload.get("timestamp")),
            }
        except (ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
            self.send_error(400, "Invalid location payload")
            return
        with state_lock:
            state["location"] = location
        with navigation_lock:
            update = navigation.update(location["latitude"], location["longitude"],
                                       location.get("heading"), location.get("accuracy"),
                                       location.get("heading_timestamp"))
            state["navigation"] = {
                **navigation.snapshot(),
                "message": update.message,
                "off_route": update.off_route,
                "arrived": update.arrived,
                "distance_remaining": update.distance_remaining,
            }
        self._json({"ok": True})

    def _route(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 4096:
            self.send_error(413, "Route payload is missing or too large")
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            destination_query = str(payload.get("destination", "")).strip()
            if not destination_query:
                raise ValueError("Destination is required")
            with state_lock:
                current = state.get("location")
            if not current:
                raise ValueError("Waiting for the browser GPS position")
            selected_coordinates = payload.get("destination_coordinates")
            if selected_coordinates is None:
                destination = _geocode(destination_query)
            else:
                if not isinstance(selected_coordinates, list) or len(selected_coordinates) != 2:
                    raise ValueError("Destination coordinates must contain latitude and longitude")
                latitude, longitude = map(float, selected_coordinates)
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError("Destination coordinates are outside the valid range")
                destination = (latitude, longitude, destination_query)
            route = _walking_route(
                (current["latitude"], current["longitude"]),
                (destination[0], destination[1]),
            )
            with navigation_lock:
                update = navigation.set_route(route, (destination[0], destination[1]))
                nav_state = {
                    **navigation.snapshot(),
                    "event_id": update.event_id,
                    "message": "Route ready. Hold still while I check the road direction.",
                    "guidance": "Route ready. Hold still while I check the road direction.",
                    "destination_name": destination[2],
                    "distance_remaining": route.get("distance"),
                }
                navigation.last_message = nav_state["message"]
                state["navigation"] = nav_state
            self._json({"ok": True, "navigation": nav_state})
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send_error(502 if isinstance(exc, OSError) else 400, str(exc))

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
        source = self.source
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            self.send_error(503, "Camera could not be opened")
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        # Video files are processed faster or slower than real time: speeds and
        # time-to-collision must use the video's own clock, not the wall clock.
        is_file = isinstance(source, str) and not source.lower().startswith(("http://", "https://", "rtsp://"))
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_number = 0
        with state_lock:
            state["connected"] = True
            state["status"] = "Starting inference"
        with inference_lock:
            self.engine.reset()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[1] > 1280:
                    frame = cv2.resize(frame, (1280, int(frame.shape[0] * 1280 / frame.shape[1])))
                timestamp = frame_number / video_fps if is_file else None
                frame_number += 1
                with inference_lock:
                    frame = self.engine.frame(frame, timestamp=timestamp)
                ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                if not ok:
                    continue
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                self.wfile.write(encoded.tobytes())
                self.wfile.write(b"\r\n")
                self.wfile.flush()
        except ConnectionError:
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
        mobile_json = self.headers.get("Content-Type", "").startswith("application/json")
        if mobile_json:
            try:
                payload = json.loads(raw)
                raw = base64.b64decode(payload["image"], validate=True)
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                self.send_error(400, "Invalid base64 camera frame")
                return
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            self.send_error(400, "Invalid camera frame")
            return
        if image.shape[1] > 1280:
            image = cv2.resize(image, (1280, int(image.shape[0] * 1280 / image.shape[1])))
        with inference_lock:
            annotated = self.engine.frame(image, speak_alert=not mobile_json)
        ok, encoded = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            self.send_error(500, "Could not encode annotated frame")
            return
        if mobile_json:
            body = json.dumps({
                "image": base64.b64encode(encoded.tobytes()).decode("ascii"),
                "state": self._public_state(),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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