import pytest
from backend.telemetry_service import haversine_distance_km, find_nearest_known_station


def test_haversine_distance():
    # Distance between Mandir Marg and Connaught Place (~1.2 km)
    dist = haversine_distance_km(28.6289, 77.2065, 28.6364, 77.2010)
    assert 0.8 <= dist <= 1.8


def test_find_nearest_station_delhi():
    st = find_nearest_known_station(28.6139, 77.2090)
    assert "CPCB" in st["name"]
    assert st["distance_km"] < 10.0
