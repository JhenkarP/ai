import json
import math
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

import web_app
from blindnav.detector import Detection

class StubDetector:
    def detect(self, frame):
        return []

    def reset_tracking(self):
        pass


class CountingDepth:
    def __init__(self):
        self.calls = 0

    def estimate(self, frame):
        self.calls += 1
        return np.full(frame.shape[:2], 5.0, dtype=np.float32)


class SilentAudio:
    def say(self, alert, text):
        pass


def make_engine(depth_every: int):
    engine = object.__new__(web_app.InferenceEngine)
    engine.detector = StubDetector()
    engine.hazard_detector = None
    engine.door_detector = None
    engine.depth = CountingDepth()
    engine.depth_every = depth_every
    engine.audio = SilentAudio()
    engine.reset()
    return engine


def test_depth_is_recomputed_every_frame_when_depth_every_is_one():
    engine = make_engine(depth_every=1)
    image = np.zeros((120, 160, 3), dtype=np.uint8)

    for _ in range(4):
        engine.frame(image)

    assert engine.depth.calls == 4


def test_depth_is_reused_between_refreshes():
    engine = make_engine(depth_every=3)
    image = np.zeros((120, 160, 3), dtype=np.uint8)

    for _ in range(6):
        engine.frame(image)

    assert engine.depth.calls == 2


def test_depth_is_recomputed_when_the_frame_size_changes():
    engine = make_engine(depth_every=10)

    engine.frame(np.zeros((120, 160, 3), dtype=np.uint8))
    engine.frame(np.zeros((240, 320, 3), dtype=np.uint8))

    assert engine.depth.calls == 2


@pytest.mark.parametrize("value, expected", [
    (3, 3.0), (2.5, 2.5), (None, None), (True, None), ("5", None),
    (math.nan, None), (math.inf, None),
])
def test_finite_number(value, expected):
    assert web_app._finite_number(value) == expected


@pytest.fixture()
def server():
    web_app.state["location"] = None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web_app.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post_json(base, path, payload):
    request = Request(base + path, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    return urlopen(request, timeout=5)


def test_location_with_null_accuracy_is_accepted_and_not_exposed(server):
    response = post_json(server, "/location", {
        "latitude": 13.0, "longitude": 77.5, "accuracy": None, "heading": None,
        "heading_timestamp": None, "speed": None, "timestamp": 1,
    })
    assert response.status == 200
    assert web_app.state["location"]["accuracy"] is None

    state = json.loads(urlopen(server + "/state", timeout=5).read())
    assert "location" not in state
    health = json.loads(urlopen(server + "/health", timeout=5).read())
    assert "location" not in health


@pytest.mark.parametrize("payload", [
    {"latitude": 95, "longitude": 0},
    {"latitude": 0, "longitude": 200},
    {"latitude": "north", "longitude": 0},
    {"longitude": 0},
])
def test_invalid_location_is_rejected(server, payload):
    with pytest.raises(HTTPError) as error:
        post_json(server, "/location", payload)
    assert error.value.code == 400


def test_garbage_heading_timestamp_does_not_crash_navigation(server):
    response = post_json(server, "/location", {
        "latitude": 13.0, "longitude": 77.5, "accuracy": 5,
        "heading": 90, "heading_timestamp": "yesterday",
    })
    assert response.status == 200


@pytest.mark.parametrize("previous, reported, expected", [
    (None, 5.0, 5.0), (5.0, 5.2, 5.2), (5.0, 5.0, 5.001), (5.0, 4.0, 5.001),
])
def test_next_capture_time_never_goes_backwards(previous, reported, expected):
    assert web_app._next_capture_time(previous, reported) == pytest.approx(expected)


class ApproachingDetector:
    """One person whose box grows as if it will reach the user at t = 3 s."""

    def __init__(self):
        self.frame_number = 0
        self.seen = []

    def detect(self, frame):
        t = 0.1 * self.frame_number
        self.frame_number += 1
        height = int(100 * 3 / (3 - t))
        detection = Detection(box=(300, 50, 340, 50 + height), class_name="person",
                              confidence=0.9, track_id=1)
        self.seen.append(detection)
        return [detection]

    def reset_tracking(self):
        self.frame_number = 0


def send_frames(base, session, with_capture_time):
    import base64
    import cv2

    ok, jpeg = cv2.imencode(".jpg", np.full((480, 640, 3), 90, dtype=np.uint8))
    image = base64.b64encode(jpeg.tobytes()).decode()
    for number in range(12):
        payload = {"image": image}
        if with_capture_time:
            payload.update({"captured_at": 1000 + 0.1 * number, "session": session})
        post_json(base, "/frame", payload).read()


def test_time_to_collision_uses_the_capture_time_of_phone_frames(server, monkeypatch):
    engine = make_engine(depth_every=1)
    engine.detector = ApproachingDetector()
    monkeypatch.setattr(web_app.Handler, "engine", engine)
    monkeypatch.setattr(web_app.Handler, "capture_session", None)

    # The frames arrive within milliseconds of each other, so arrival time cannot show the approach.
    send_frames(server, "a", with_capture_time=False)
    assert engine.detector.seen[-1].ttc is None

    engine.reset()
    send_frames(server, "b", with_capture_time=True)
    # The estimate comes from a 1 s window, so it describes its middle (t = 0.6 s), not the last frame.
    assert engine.detector.seen[-1].ttc == pytest.approx(3 - 0.6, abs=0.15)
