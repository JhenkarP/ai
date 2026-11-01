import base64
import json
import math
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import cv2
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


def make_sharp_image(shape: tuple[int, int, int]) -> np.ndarray:
    return np.random.default_rng(0).integers(0, 256, shape, dtype=np.uint8)


def test_depth_is_recomputed_every_frame_when_depth_every_is_one():
    engine = make_engine(depth_every=1)
    image = make_sharp_image((120, 160, 3))

    for _ in range(4):
        engine.frame(image)

    assert engine.depth.calls == 4


def test_depth_is_reused_between_refreshes():
    engine = make_engine(depth_every=3)
    image = make_sharp_image((120, 160, 3))

    for _ in range(6):
        engine.frame(image)

    assert engine.depth.calls == 2


def test_depth_is_recomputed_when_the_frame_size_changes():
    engine = make_engine(depth_every=10)

    engine.frame(make_sharp_image((120, 160, 3)))
    engine.frame(make_sharp_image((240, 320, 3)))

    assert engine.depth.calls == 2


def test_blurry_frames_skip_depth_and_show_camera_quality_status():
    engine = make_engine(depth_every=1)

    engine.frame(np.full((120, 160, 3), 90, dtype=np.uint8))

    assert engine.depth.calls == 0
    assert web_app.state["status"] == "Image too blurry, hold the phone steadier"


def test_scene_description_uses_observed_objects_without_claiming_safety():
    detections = [
        Detection((0, 0, 30, 80), "person", 0.9),
        Detection((70, 0, 100, 80), "car", 0.8),
        Detection((40, 0, 60, 80), "stairs", 0.2),
    ]
    description = web_app.describe_scene(detections, 100, blurry=False, dark=False, blocked=True)
    assert "person on the left" in description
    assert "car on the right" in description
    assert "stairs" not in description
    assert "obstruction" in description
    assert "does not confirm the way is safe" in description


@pytest.mark.parametrize("blurry,dark,expected", [
    (True, False, "blurry"), (False, True, "too dark"),
    (False, False, "cannot confidently identify"),
])
def test_scene_description_handles_unreliable_or_empty_views(blurry, dark, expected):
    description = web_app.describe_scene([], 100, blurry=blurry, dark=dark, blocked=False)
    assert expected in description
    assert "Path clear" not in description


def test_frame_publishes_fresh_scene_description():
    engine = make_engine(depth_every=1)
    engine.frame(np.zeros((120, 160, 3), dtype=np.uint8))
    assert "too dark" in web_app.public_state()["scene_description"]


@pytest.mark.parametrize("value, expected", [
    (3, 3.0), (2.5, 2.5), (None, None), (True, None), ("5", None),
    (math.nan, None), (math.inf, None),
])
def test_finite_number(value, expected):
    assert web_app._finite_number(value) == expected


def test_google_walking_route_normalizes_geometry_steps_and_instructions(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"routes": [{
                "distanceMeters": 30,
                "duration": "45s",
                "polyline": {"geoJsonLinestring": {"coordinates": [
                    [77.4971, 13.0272], [77.4975, 13.0276], [77.4980, 13.0280],
                ]}},
                "legs": [{"steps": [
                    {
                        "distanceMeters": 12,
                        "startLocation": {"latLng": {"latitude": 13.0272, "longitude": 77.4971}},
                        "endLocation": {"latLng": {"latitude": 13.0276, "longitude": 77.4975}},
                        "navigationInstruction": {"maneuver": "DEPART", "instructions": "Head northeast"},
                    },
                    {
                        "distanceMeters": 18,
                        "startLocation": {"latLng": {"latitude": 13.0276, "longitude": 77.4975}},
                        "endLocation": {"latLng": {"latitude": 13.0280, "longitude": 77.4980}},
                        "navigationInstruction": {"maneuver": "TURN_RIGHT", "instructions": "Turn right onto 3rd Main Road"},
                    },
                ]}],
            }]}).encode("utf-8")

    monkeypatch.setenv("GOOGLE_ROUTES_API_KEY", "test-key")
    monkeypatch.setattr(web_app, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    route = web_app._google_walking_route((13.0272, 77.4971), (13.0280, 77.4980))

    assert route["distance"] == 30
    assert route["geometry"]["coordinates"][0] == [77.4971, 13.0272]
    assert route["legs"][0]["steps"][0]["maneuver"]["type"] == "depart"
    assert route["legs"][0]["steps"][1]["maneuver"]["type"] == "turn"
    assert route["legs"][0]["steps"][1]["maneuver"]["instruction"] == "Turn right onto 3rd Main Road"


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


def scene_payload(image=None):
    if image is None:
        image = make_sharp_image((120, 160, 3))
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return {"image": base64.b64encode(encoded).decode(), "captured_at": time.time()}


def test_cloud_scene_missing_key_is_explicit(server, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    config = json.load(urlopen(server + "/scene/config"))
    assert config["configured"] is False
    with pytest.raises(HTTPError) as error:
        post_json(server, "/scene/analyze", scene_payload())
    assert error.value.code == 503


def test_cloud_scene_rejects_stale_frames(server, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    payload = scene_payload()
    payload["captured_at"] -= 30
    with pytest.raises(HTTPError) as error:
        post_json(server, "/scene/analyze", payload)
    assert error.value.code == 400


def test_cloud_scene_checks_quality_before_upload(server, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(web_app, "analyze_scene", lambda *args: pytest.fail("Dark frame uploaded"))
    result = json.load(post_json(server, "/scene/analyze", scene_payload(np.zeros((120, 160, 3), dtype=np.uint8))))
    assert result["provider"] == "image-quality"
    assert "dark or blurry" in result["description"]


def test_cloud_scene_does_not_hold_obstacle_lock_and_rate_limits(server, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(web_app, "last_scene_request", -float("inf"))
    def fake_analysis(raw):
        assert not web_app.inference_lock.locked()
        return {"description": "Possible stairs ahead.", "hazard": True}
    monkeypatch.setattr(web_app, "analyze_scene", fake_analysis)
    assert json.load(post_json(server, "/scene/analyze", scene_payload()))["hazard"] is True
    with pytest.raises(HTTPError) as error:
        post_json(server, "/scene/analyze", scene_payload())
    assert error.value.code == 429


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


def test_google_provider_route_request_uses_google_walking_router(server, monkeypatch):
    web_app.state["location"] = {
        "latitude": 13.0272, "longitude": 77.4971, "accuracy": 5,
        "heading": None, "heading_timestamp": None,
    }
    route = {
        "distance": 30,
        "geometry": {"coordinates": [[77.4971, 13.0272], [77.498, 13.028]]},
        "legs": [{"steps": [{"distance": 30, "maneuver": {
            "type": "depart", "modifier": "straight", "bearing_after": 40,
            "location": [77.4971, 13.0272], "instruction": "Head northeast",
        }}]},],
    }
    called = []

    def fake_google_route(start, destination):
        called.append((start, destination))
        return route

    monkeypatch.setattr(web_app, "_google_walking_route", fake_google_route)
    monkeypatch.setattr(web_app, "_walking_route", lambda *_args: pytest.fail("OSM router must not be used"))

    response = post_json(server, "/route", {
        "destination": "Test destination",
        "destination_coordinates": [13.028, 77.498],
        "map_provider": "google",
    })
    result = json.loads(response.read())

    assert called == [((13.0272, 77.4971), (13.028, 77.498))]
    assert result["navigation"]["active"] is True
    assert result["navigation"]["route_geometry"] == [[13.0272, 77.4971], [13.028, 77.498]]


def test_google_provider_text_destination_uses_google_places_geocoding(server, monkeypatch):
    web_app.state["location"] = {
        "latitude": 13.0272, "longitude": 77.4971, "accuracy": 5,
        "heading": None, "heading_timestamp": None,
    }
    places_calls = []
    route_calls = []
    candidates = [
        {"latitude": 13.10, "longitude": 77.60, "display_name": "Far matching place"},
        {"latitude": 13.028, "longitude": 77.498, "display_name": "Nearby matching place"},
    ]
    route = {
        "distance": 30,
        "geometry": {"coordinates": [[77.4971, 13.0272], [77.498, 13.028]]},
        "legs": [{"steps": []}],
    }

    def fake_places(query, near, api_key):
        places_calls.append((query, near, bool(api_key)))
        return candidates

    def fake_google_route(start, destination):
        route_calls.append((start, destination))
        return route

    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.setattr(web_app, "_google_place_suggestions", fake_places)
    monkeypatch.setattr(web_app, "_google_walking_route", fake_google_route)
    monkeypatch.setattr(web_app, "_geocode", lambda *_args: pytest.fail("OSM geocoder must not be used"))
    monkeypatch.setattr(web_app, "_walking_route", lambda *_args: pytest.fail("OSM router must not be used"))

    response = post_json(server, "/route", {
        "destination": "Nearby matching place", "map_provider": "google",
    })
    result = json.loads(response.read())

    assert places_calls == [("Nearby matching place", (13.0272, 77.4971), True)]
    assert route_calls == [((13.0272, 77.4971), (13.028, 77.498))]
    assert result["navigation"]["active"] is True


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

    ok, jpeg = cv2.imencode(".jpg", make_sharp_image((240, 320, 3)))
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
