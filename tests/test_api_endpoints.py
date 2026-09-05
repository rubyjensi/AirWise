import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import httpx

from api.index import app
from api.models import HomeResponse, CigaretteEquivalents

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_home_endpoint_returns_cigarette_equivalents():
    res = client.get("/api/home?lat=28.6139&lon=77.2090&activity=walk&duration=30")
    assert res.status_code == 200
    data = res.json()
    
    # Validate against Pydantic schema
    home_obj = HomeResponse(**data)
    assert isinstance(home_obj.cigarette_equivalents, CigaretteEquivalents)
    
    ce = data["cigarette_equivalents"]
    assert "cigarette_count" in ce
    assert "with_n95" in ce
    assert "full_day_cigarettes" in ce
    assert "headline_en" in ce
    assert "headline_hi" in ce
    assert "subtext_en" in ce
    assert "subtext_hi" in ce
    assert ce["cigarette_count"] >= 0.05
    assert ce["with_n95"] <= ce["cigarette_count"]
    assert len(ce["headline_en"]) > 0
    assert len(ce["headline_hi"]) > 0


def test_aqi_map_reverse_proxy_success():
    mock_html = "<html><head><title>AQI Map</title></head><body><header>Nav</header><div id='root'>Map</div></body></html>"
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = httpx.Response(200, text=mock_html, request=httpx.Request("GET", "https://www.aqi.in/in/air-quality-map"))
        mock_get.return_value = mock_resp
        
        res = client.get("/api/aqi-map")
        assert res.status_code == 200
        assert res.headers.get("x-frame-options") == "ALLOWALL"
        assert res.headers.get("content-security-policy") == "frame-ancestors *"
        assert '<base href="https://www.aqi.in/">' in res.text
        assert 'airwise-aqi-cleaner' in res.text
        assert 'header, nav, footer' in res.text


def test_aqi_map_fallback_on_upstream_failure():
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Connection timed out")):
        res = client.get("/api/aqi-map")
        assert res.status_code == 200
        assert res.headers.get("x-frame-options") == "ALLOWALL"
        assert res.headers.get("content-security-policy") == "frame-ancestors *"
        assert "https://www.aqi.in/in/air-quality-map" in res.text
        assert "Open Live Map on AQI.in" in res.text


def test_reverse_geocode_endpoint():
    res = client.get("/api/reverse-geocode?lat=28.6139&lon=77.2090")
    assert res.status_code == 200
    data = res.json()
    assert "name" in data
    assert "Raisina Hill, New Delhi" in data["name"] or "New Delhi" in data["name"]
    assert data["latitude"] == 28.6139
    assert data["longitude"] == 77.2090


def test_reverse_geocode_fallback_on_timeout():
    from api.index import _GEOCODE_CACHE
    # Use unique coords not in cache
    test_lat, test_lon = 28.7123, 77.1234
    cache_key = f"{round(test_lat, 3)},{round(test_lon, 3)}"
    _GEOCODE_CACHE.pop(cache_key, None)

    with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Nominatim timed out")):
        res = client.get(f"/api/reverse-geocode?lat={test_lat}&lon={test_lon}")
        assert res.status_code == 200
        data = res.json()
        assert "name" in data
        assert "New Delhi, Delhi" in data["name"] or "Location (" in data["name"]


def test_home_station_warning_when_far():
    # Lat/Lon far from any CPCB reference station (>15km)
    res = client.get("/api/home?lat=27.5&lon=77.0")
    assert res.status_code == 200
    data = res.json()
    st = data["station"]
    assert st["is_far"] is True
    assert st["warning"] is not None
    assert "Nearest monitoring station is" in st["warning"]
    assert "km away. Local air quality may be inconsistent due to micro-climates." in st["warning"]


def test_home_station_no_warning_when_near():
    # Mandir Marg is ~2.7km from central Delhi coords
    res = client.get("/api/home?lat=28.6139&lon=77.2090")
    assert res.status_code == 200
    data = res.json()
    st = data["station"]
    assert st["is_far"] is False
    assert st["warning"] is None


def test_home_resolves_live_location_names():
    for loc in ["My Current Location", "Live Location", "Locating…", "Locating..."]:
        res = client.get(f"/api/home?lat=28.6139&lon=77.2090&location_name={loc}")
        assert res.status_code == 200
        data = res.json()
        assert data["location_name"] != loc
        assert "Raisina Hill, New Delhi" in data["location_name"] or "New Delhi" in data["location_name"]
