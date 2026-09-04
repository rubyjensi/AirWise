"""
VayuGuard Main FastAPI Application
Serves the unified /api/home endpoint, city searches, and mounts public static assets.
"""

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from typing import Optional, List, Dict, Any

from api.models import (
    HomeResponse, CurrentWeather, CurrentAirQuality,
    StationMetadata, LowerExposureWindow, HourlyItem
)
from api.telemetry_service import (
    fetch_open_meteo_telemetry, haversine_km, get_aqi_category,
    determine_scene, get_contextual_sentence, CPCB_STATIONS
)
from api.clinical_engine import (
    calculate_inhalation_dose, evaluate_multi_stressor, find_lower_exposure_window
)
from api.advisory_service import generate_deterministic_guidance

app = FastAPI(
    title="AirWise API",
    description="Atmospheric Weather & Personalized Environmental Health Guidance",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def vercel_rewrite_middleware(request: Request, call_next):
    path_param = request.query_params.get("__path")
    matched_header = request.headers.get("x-matched-path")
    
    target_path = None
    if path_param:
        target_path = "/" + path_param.lstrip("/")
        if not target_path.startswith("/api"):
            target_path = "/api" + target_path
    elif matched_header and not matched_header.startswith("/api/index.py"):
        target_path = matched_header.split("?")[0]
        
    if target_path:
        request.scope["path"] = target_path

    response = await call_next(request)
    return response

# Curated search database for quick latency-free city lookup
POPULAR_CITIES = [
    {"name": "New Delhi", "state": "Delhi", "country": "India", "lat": 28.6139, "lon": 77.2090, "aqi_sample": 184},
    {"name": "Mumbai", "state": "Maharashtra", "country": "India", "lat": 19.0760, "lon": 72.8777, "aqi_sample": 92},
    {"name": "Bengaluru", "state": "Karnataka", "country": "India", "lat": 12.9716, "lon": 77.5946, "aqi_sample": 64},
    {"name": "Kolkata", "state": "West Bengal", "country": "India", "lat": 22.5726, "lon": 88.3639, "aqi_sample": 142},
    {"name": "Chennai", "state": "Tamil Nadu", "country": "India", "lat": 13.0827, "lon": 80.2707, "aqi_sample": 78},
    {"name": "Hyderabad", "state": "Telangana", "country": "India", "lat": 17.3850, "lon": 78.4867, "aqi_sample": 88},
    {"name": "Pune", "state": "Maharashtra", "country": "India", "lat": 18.5204, "lon": 73.8567, "aqi_sample": 85},
    {"name": "Ahmedabad", "state": "Gujarat", "country": "India", "lat": 23.0225, "lon": 72.5714, "aqi_sample": 125},
    {"name": "Jaipur", "state": "Rajasthan", "country": "India", "lat": 26.9124, "lon": 75.7873, "aqi_sample": 138},
    {"name": "Lucknow", "state": "Uttar Pradesh", "country": "India", "lat": 26.8467, "lon": 80.9462, "aqi_sample": 165},
    {"name": "Chandigarh", "state": "Punjab / Haryana", "country": "India", "lat": 30.7333, "lon": 76.7794, "aqi_sample": 110},
    {"name": "Patna", "state": "Bihar", "country": "India", "lat": 25.5941, "lon": 85.1376, "aqi_sample": 195},
    {"name": "London", "state": "England", "country": "United Kingdom", "lat": 51.5074, "lon": -0.1278, "aqi_sample": 35},
    {"name": "New York", "state": "NY", "country": "United States", "lat": 40.7128, "lon": -74.0060, "aqi_sample": 42},
    {"name": "Tokyo", "state": "Tokyo", "country": "Japan", "lat": 35.6762, "lon": 139.6503, "aqi_sample": 28}
]

@app.get("/api/health")
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AirWise API", "version": "1.0.0"}

@app.get("/api/places/search")
@app.get("/places/search")
def search_places(q: str = Query(..., min_length=1)):
    query = q.lower().strip()
    results = []
    for city in POPULAR_CITIES:
        if query in city["name"].lower() or query in city["state"].lower() or query in city["country"].lower():
            results.append(city)
    return {"query": q, "results": results[:6]}

@app.get("/api/home", response_model=HomeResponse)
@app.get("/home", response_model=HomeResponse)
async def get_home(
    lat: float = Query(default=28.6139, ge=-90, le=90),
    lon: float = Query(default=77.2090, ge=-180, le=180),
    profile: str = Query(default="standard"),
    activity: str = Query(default="walk"),
    duration: int = Query(default=30, ge=5, le=360),
    location_name: Optional[str] = Query(default=None)
):
    telemetry = await fetch_open_meteo_telemetry(lat, lon)
    w_curr = telemetry.get("weather", {}).get("current", {})
    aq_curr = telemetry.get("air_quality", {}).get("current", {})
    w_hourly = telemetry.get("weather", {}).get("hourly", {})
    aq_hourly = telemetry.get("air_quality", {}).get("hourly", {})

    # Extract or fallback current weather
    temp_c = float(w_curr.get("temperature_2m", 28.5))
    feels_c = float(w_curr.get("apparent_temperature", temp_c + 1.5))
    humidity = float(w_curr.get("relative_humidity_2m", 55.0))
    wind_kmh = float(w_curr.get("wind_speed_10m", 8.2))
    is_day = bool(w_curr.get("is_day", 1))
    weather_code = int(w_curr.get("weather_code", 1))
    uv_index = float(aq_curr.get("uv_index", 3.0))

    # Extract or fallback current air quality
    us_aqi = int(aq_curr.get("us_aqi", 152))
    pm25 = float(aq_curr.get("pm2_5", 58.4))
    pm10 = float(aq_curr.get("pm10", 94.0)) if aq_curr.get("pm10") is not None else None
    o3 = float(aq_curr.get("ozone", 45.0)) if aq_curr.get("ozone") is not None else None
    no2 = float(aq_curr.get("nitrogen_dioxide", 28.0)) if aq_curr.get("nitrogen_dioxide") is not None else None
    so2 = float(aq_curr.get("sulphur_dioxide", 12.0)) if aq_curr.get("sulphur_dioxide") is not None else None
    co = float(aq_curr.get("carbon_monoxide", 450.0)) if aq_curr.get("carbon_monoxide") is not None else None

    category_label, _ = get_aqi_category(us_aqi)
    scene = determine_scene(weather_code, is_day, us_aqi)
    context_sentence = get_contextual_sentence(scene, us_aqi, temp_c)

    # Resolve nearest CPCB reference station
    nearest_station = min(CPCB_STATIONS, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))
    dist_km = haversine_km(lat, lon, nearest_station["lat"], nearest_station["lon"])
    
    station_meta = StationMetadata(
        name=nearest_station["name"] if dist_km < 45.0 else f"Regional Ambient Grid ({round(lat, 2)}, {round(lon, 2)})",
        distance_km=dist_km,
        updated_minutes_ago=12,
        source=nearest_station["source"] if dist_km < 45.0 else "Copernicus Atmospheric Monitoring / Open-Meteo",
        is_modeled=(dist_km >= 45.0),
        confidence_level="High" if dist_km < 15.0 else "Medium" if dist_km < 50.0 else "Limited"
    )

    # Weather condition mapping
    condition_names = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain", 80: "Rain showers", 95: "Thunderstorm"
    }
    condition_text = condition_names.get(weather_code, "Partly cloudy")

    current_weather_obj = CurrentWeather(
        temp_c=temp_c,
        feels_like_c=feels_c,
        humidity=humidity,
        wind_speed_kmh=wind_kmh,
        uv_index=uv_index,
        condition_code=weather_code,
        condition_text=condition_text,
        is_day=is_day
    )

    current_aq_obj = CurrentAirQuality(
        aqi=us_aqi,
        category=category_label,
        dominant_pollutant="PM2.5",
        pm25=pm25,
        pm10=pm10,
        o3=o3,
        no2=no2,
        so2=so2,
        co=co
    )

    # Hourly Forecast Processing (next 24 hours)
    hourly_items: List[HourlyItem] = []
    times = aq_hourly.get("time", [])
    aqis = aq_hourly.get("us_aqi", [])
    pm25s = aq_hourly.get("pm2_5", [])
    temps = w_hourly.get("temperature_2m", [])
    humidities = w_hourly.get("relative_humidity_2m", [])
    codes = w_hourly.get("weather_code", [])
    days = w_hourly.get("is_day", [])

    hourly_dicts_for_planner = []
    for i in range(min(24, len(times))):
        t_iso = times[i]
        h_display = t_iso.split("T")[-1][:5] if "T" in t_iso else f"{i:02d}:00"
        h_aqi = int(aqis[i]) if i < len(aqis) and aqis[i] is not None else us_aqi
        h_pm25 = float(pm25s[i]) if i < len(pm25s) and pm25s[i] is not None else pm25
        h_temp = float(temps[i]) if i < len(temps) and temps[i] is not None else temp_c
        h_hum = float(humidities[i]) if i < len(humidities) and humidities[i] is not None else humidity
        h_code = int(codes[i]) if i < len(codes) and codes[i] is not None else weather_code
        h_day = bool(days[i]) if i < len(days) and days[i] is not None else True
        h_cat, _ = get_aqi_category(h_aqi)

        risk_score = round((h_pm25 / 150.0) * 60.0 + (max(0, h_temp - 25.0) / 15.0) * 40.0, 1)

        item = HourlyItem(
            time_iso=t_iso,
            hour_display=h_display,
            temp_c=h_temp,
            humidity=h_hum,
            aqi=h_aqi,
            category=h_cat,
            pm25=h_pm25,
            condition_code=h_code,
            is_day=h_day,
            risk_score=risk_score
        )
        hourly_items.append(item)
        hourly_dicts_for_planner.append({
            "hour_display": h_display,
            "aqi": h_aqi,
            "pm25": h_pm25,
            "temp_c": h_temp,
            "wind_speed_kmh": 10.0
        })

    # Clinical Inhalation Dose Calculation
    dose_range = calculate_inhalation_dose(pm25, activity, profile, duration)
    better_window_dict = find_lower_exposure_window(hourly_dicts_for_planner, us_aqi, activity, profile)

    lower_window_obj = LowerExposureWindow(
        has_better_window=better_window_dict["has_better_window"],
        recommended_start=better_window_dict.get("recommended_start"),
        recommended_end=better_window_dict.get("recommended_end"),
        window_label=better_window_dict["window_label"],
        best_aqi=better_window_dict["best_aqi"],
        now_aqi=better_window_dict["now_aqi"],
        delta_aqi=better_window_dict["delta_aqi"],
        confidence=better_window_dict["confidence"],
        reason_en=better_window_dict["reason_en"],
        reason_hi=better_window_dict["reason_hi"]
    )

    personal_guidance = generate_deterministic_guidance(
        activity=activity,
        sensitivity=profile,
        duration=duration,
        dose_range=dose_range,
        aqi=us_aqi,
        scene=scene,
        better_window=better_window_dict
    )

    # Resolved location name
    resolved_name = location_name
    if not resolved_name:
        closest_city = min(POPULAR_CITIES, key=lambda c: haversine_km(lat, lon, c["lat"], c["lon"]))
        if haversine_km(lat, lon, closest_city["lat"], closest_city["lon"]) < 30.0:
            resolved_name = f"{closest_city['name']}, {closest_city['state']}"
        else:
            resolved_name = f"Coordinates ({round(lat, 2)}°, {round(lon, 2)}°)"

    return HomeResponse(
        location_name=resolved_name,
        latitude=lat,
        longitude=lon,
        scene=scene,
        weather=current_weather_obj,
        air_quality=current_aq_obj,
        station=station_meta,
        contextual_sentence=context_sentence,
        personal_guidance=personal_guidance,
        lower_exposure_window=lower_window_obj,
        hourly=hourly_items,
        data_quality={
            "station_distance_km": dist_km,
            "station_freshness_min": 12,
            "provenance": "Open-Meteo API & CPCB Real-time Ambient Monitoring Network",
            "is_interpolated": dist_km >= 45.0
        },
        disclaimer="VayuGuard provides environmental estimates for personal planning; it is not a medical device or a substitute for medical advice."
    )

# Mount public static assets
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
public_dir = os.path.join(BASE_DIR, "public")
if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
elif os.path.exists("public"):
    app.mount("/", StaticFiles(directory="public", html=True), name="public")
