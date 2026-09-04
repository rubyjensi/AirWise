import pytest
from fastapi.testclient import TestClient
from api.index import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_places_search():
    response = client.get("/api/places/search?q=delhi")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0
    assert any("Delhi" in r["name"] for r in data["results"])

def test_home_endpoint_structure():
    response = client.get("/api/home?lat=28.6139&lon=77.2090&profile=sensitive_respiratory&activity=run_cycle&duration=45")
    assert response.status_code == 200
    data = response.json()
    
    assert "location_name" in data
    assert "scene" in data
    assert data["scene"] in ["clear", "cloudy", "rain", "haze", "night"]
    assert "weather" in data
    assert "air_quality" in data
    assert "station" in data
    assert "contextual_sentence" in data
    assert "en" in data["contextual_sentence"]
    assert "hi" in data["contextual_sentence"]
    assert "personal_guidance" in data
    assert "dose_range_str" in data["personal_guidance"]
    assert "lower_exposure_window" in data
    assert "hourly" in data
    assert len(data["hourly"]) > 0
    assert "disclaimer" in data

def test_msn_map_proxy_endpoint():
    response = client.get("/api/msn-map?zoom=10")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert response.headers.get("x-frame-options") == "ALLOWALL"
    assert "weathermap" in response.text.lower() or "msn" in response.text.lower()

def test_msn_frame_endpoint():
    from unittest.mock import patch, AsyncMock
    with patch("api.index.msn_browser.get_screenshot", new_callable=AsyncMock) as mock_screenshot:
        mock_screenshot.return_value = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        response = client.get("/api/msn/frame")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == b"\xff\xd8\xff\xe0\x00\x10JFIF"

def test_msn_interact_endpoint():
    from unittest.mock import patch, AsyncMock
    with patch("api.index.msn_browser.interact", new_callable=AsyncMock) as mock_interact:
        mock_interact.return_value = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        response = client.post("/api/msn/interact", json={"action": "zoom_in"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "image" in data
        assert data["image"].startswith("data:image/jpeg;base64,")

