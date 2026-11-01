import io
import json

import pytest

from blindnav import scene_ai


def test_stairs_are_cautious_and_do_not_authorize_movement():
    result = scene_ai.format_scene({"visibility": "clear", "observations": [
        {"kind": "stairs_down", "position": "ahead"},
        {"kind": "road_edge", "position": "left"},
    ]})
    assert result["hazard"] is True
    assert "possible stairs going down ahead" in result["description"]
    assert "possible road edge on the left" in result["description"]
    assert "does not confirm the way is safe" in result["description"]


def test_unclear_scene_does_not_repeat_speculative_hazards():
    result = scene_ai.format_scene({"visibility": "unclear", "observations": [
        {"kind": "stairs_up", "position": "ahead"},
    ]})
    assert result["hazard"] is False
    assert "stairs" not in result["description"]
    assert "unclear" in result["description"]


@pytest.mark.parametrize("payload", [
    {}, {"visibility": "clear", "observations": "safe to cross"},
    {"visibility": "clear", "observations": [{"kind": "safe_to_cross", "position": "ahead"}]},
    {"visibility": "clear", "observations": [{"kind": "stairs_up", "position": "100 meters"}]},
    {"visibility": "clear", "observations": [None]},
])
def test_unrecognized_or_unbounded_output_is_rejected(payload):
    with pytest.raises(ValueError):
        scene_ai.format_scene(payload)


def test_missing_key_never_makes_cloud_request(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(scene_ai, "urlopen", lambda *args, **kwargs: pytest.fail("Unexpected cloud call"))
    with pytest.raises(ValueError, match="not configured"):
        scene_ai.analyze_scene(b"image")


def test_provider_request_uses_backend_header_and_safety_schema(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    def fake_open(request, timeout):
        assert timeout == 12
        assert "test-key" not in request.full_url
        assert request.get_header("X-goog-api-key") == "test-key"
        payload = json.loads(request.data)
        assert "blind pedestrian" in payload["systemInstruction"]["parts"][0]["text"]
        assert "Never infer" in payload["systemInstruction"]["parts"][0]["text"]
        assert payload["generationConfig"]["responseSchema"]["properties"]["observations"]["maxItems"] == 4
        text = json.dumps({"visibility": "clear", "observations": [{"kind": "entrance", "position": "right"}]})
        return io.BytesIO(json.dumps({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]}).encode())
    monkeypatch.setattr(scene_ai, "urlopen", fake_open)
    result = scene_ai.analyze_scene(b"image")
    assert "entrance on the right" in result["description"]
    assert result["hazard"] is False


def test_blocked_provider_response_does_not_become_a_description(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(scene_ai, "urlopen", lambda *args, **kwargs: io.BytesIO(b'{"candidates": []}'))
    with pytest.raises(ValueError, match="reliably"):
        scene_ai.analyze_scene(b"image")