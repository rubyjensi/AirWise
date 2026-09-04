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
