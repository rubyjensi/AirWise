import pytest
from api.clinical_engine import (
    calculate_inhalation_dose,
    calculate_heat_index,
    evaluate_multi_stressor,
    find_lower_exposure_window,
    VENTILATION_RATES,
    DEPOSITION_FRACTIONS
)

def test_ventilation_rates_ordering():
    """Verify that minute ventilation increases with physical exertion."""
    assert VENTILATION_RATES["rest"][1] < VENTILATION_RATES["walk"][1]
    assert VENTILATION_RATES["walk"][1] < VENTILATION_RATES["run_cycle"][1]

def test_deposition_fraction_respiratory_sensitivity():
    """Verify that asthmatic/respiratory sensitivity has higher deposition fraction than standard."""
    df_std = DEPOSITION_FRACTIONS["standard"][1]
    df_resp = DEPOSITION_FRACTIONS["sensitive_respiratory"][1]
    assert df_resp > df_std
    assert df_resp == 0.62

def test_inhalation_dose_range():
    """Verify dose calculation returns a realistic min-max range."""
    # 30 min walk with PM2.5 = 100 ug/m3
    res = calculate_inhalation_dose(pm25_ug_m3=100.0, activity="walk", sensitivity="standard", duration_minutes=30)
    assert res["dose_min_ug"] < res["dose_typical_ug"] < res["dose_max_ug"]
    assert res["dose_typical_ug"] > 0
    assert len(res["assumptions"]) == 4

def test_respiratory_profile_inhales_more():
    """For the exact same walk, an asthmatic patient absorbs more particulate mass than a healthy adult."""
    std_res = calculate_inhalation_dose(pm25_ug_m3=120.0, activity="walk", sensitivity="standard", duration_minutes=30)
    resp_res = calculate_inhalation_dose(pm25_ug_m3=120.0, activity="walk", sensitivity="sensitive_respiratory", duration_minutes=30)
    assert resp_res["dose_typical_ug"] > std_res["dose_typical_ug"]

def test_heat_index_calculation():
    """Verify apparent temperature is higher than dry-bulb temperature when warm and humid."""
    hi = calculate_heat_index(temp_c=35.0, humidity=65.0)
    assert hi > 35.0
    # Cold weather does not inflate heat index
    assert calculate_heat_index(temp_c=12.0, humidity=80.0) == 12.0

def test_multi_stressor_cardiovascular_alert():
    """Verify that compound heat and PM2.5 triggers the cardiovascular flag."""
    res = evaluate_multi_stressor(pm25=110.0, temp_c=38.0, humidity=60.0)
    codes = [f["code"] for f in res["compound_flags"]]
    assert "CARDIOVASCULAR_STRAIN" in codes

def test_find_lower_exposure_window_finds_drop():
    """Verify that the window optimizer discovers an evening particulate trough."""
    mock_hourly = [
        {"hour_display": "14:00", "aqi": 210, "pm25": 95, "temp_c": 34, "wind_speed_kmh": 6},
        {"hour_display": "15:00", "aqi": 200, "pm25": 90, "temp_c": 33, "wind_speed_kmh": 7},
        {"hour_display": "16:00", "aqi": 180, "pm25": 80, "temp_c": 32, "wind_speed_kmh": 8},
        {"hour_display": "17:00", "aqi": 150, "pm25": 65, "temp_c": 30, "wind_speed_kmh": 10},
        {"hour_display": "18:00", "aqi": 120, "pm25": 50, "temp_c": 28, "wind_speed_kmh": 14},
        {"hour_display": "19:00", "aqi": 115, "pm25": 48, "temp_c": 27, "wind_speed_kmh": 15},
        {"hour_display": "20:00", "aqi": 125, "pm25": 52, "temp_c": 26, "wind_speed_kmh": 13},
    ]
    window = find_lower_exposure_window(mock_hourly, current_aqi=210, activity="walk", sensitivity="standard")
    assert window["has_better_window"] is True
    assert window["delta_aqi"] >= 25
    assert "18:00" in window["window_label"] or "17:00" in window["window_label"]
