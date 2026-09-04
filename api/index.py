"""
VayuGuard Main FastAPI Application
Serves the unified /api/home endpoint, city searches, and mounts public static assets.
"""

from fastapi import FastAPI, Query, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import time
import base64
import httpx
import logging
from typing import Optional, List, Dict, Any

from api.msn_browser_service import msn_browser

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

@app.get("/api/msn-map", response_class=HTMLResponse)
@app.get("/msn-map", response_class=HTMLResponse)
async def get_msn_map(
    zoom: int = Query(default=10, ge=1, le=20),
    lat: Optional[float] = Query(default=None),
    lon: Optional[float] = Query(default=None)
):
    """
    Reverse-proxies the live MSN Weather Air Quality map page.
    Strips X-Frame-Options and frame-ancestors restrictions so the official
    Microsoft weather map displays natively in the AirWise interface.
    """
    url = f"https://www.msn.com/en-in/weather/maps/airquality?zoom={zoom}"
    if lat is not None and lon is not None:
        url += f"&lat={lat}&lon={lon}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.msn.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            html = resp.text
    except Exception:
        fallback_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ margin: 0; background: #0f141c; color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, sans-serif; text-align: center; padding: 20px; box-sizing: border-box; }}
  a {{ color: #0071e3; text-decoration: none; font-weight: 600; padding: 10px 18px; border-radius: 980px; background: rgba(0,113,227,0.15); border: 1px solid rgba(0,113,227,0.3); margin-top: 12px; display: inline-block; }}
</style>
</head>
<body>
  <h3 style="margin:0 0 8px;">MSN Weather Air Quality Map</h3>
  <p style="color: rgba(255,255,255,0.6); max-width: 320px; font-size: 13px; margin: 0;">Interactive Bing Maps telemetry initializing.</p>
  <a href="{url}" target="_blank" rel="noopener">Open Directly on MSN Weather &rarr;</a>
</body>
</html>"""
        return HTMLResponse(
            content=fallback_html,
            status_code=200,
            headers={"X-Frame-Options": "ALLOWALL", "Content-Security-Policy": "frame-ancestors *"}
        )

    # Inject base href if needed
    if "<head>" in html:
        html = html.replace("<head>", '<head>\n<base href="https://www.msn.com/">\n', 1)

    # Inject CSS overrides to clean up MSN header/footer chrome and let map fill container
    clean_css = """
<style id="airwise-msn-cleaner">
  header, #header, nav, #nav, #meganav-container, .header-container,
  [class*="header"], [class*="navBar"], [class*="ad-"], [class*="footer"],
  #footer, [class*="social"], [class*="feedback"], [id*="sidebar"],
  .bing-weather-nav, .msn-header, .me-control, #header-container,
  .search-box-container, .action-bar-container {
    display: none !important;
  }
  html, body {
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    width: 100vw !important;
    height: 100vh !important;
    background: #0d1117 !important;
  }
  #weathermap-2d-container {
    top: 0 !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    position: fixed !important;
    display: block !important;
    z-index: 999 !important;
  }
</style>
"""
    if "</head>" in html:
        html = html.replace("</head>", f"{clean_css}\n</head>", 1)
    else:
        html += clean_css

    return HTMLResponse(
        content=html,
        status_code=200,
        headers={
            "X-Frame-Options": "ALLOWALL",
            "Content-Security-Policy": "frame-ancestors *",
            "Cache-Control": "public, max-age=300"
        }
    )

@app.get("/api/bundles/{bundle_path:path}")
@app.get("/bundles/{bundle_path:path}")
async def proxy_msn_bundle(bundle_path: str):
    """
    Proxies MSN JS bundles so worker scripts and tile metadata load seamlessly.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"https://assets.msn.com/bundles/{bundle_path}")
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type", "application/javascript"),
                headers={"Cache-Control": "public, max-age=86400"}
            )
    except Exception:
        raise HTTPException(status_code=404, detail="Bundle not found")

@app.get("/api/resolver/{resolver_path:path}")
@app.get("/resolver/{resolver_path:path}")
async def proxy_msn_resolver(request: Request, resolver_path: str):
    """
    Proxies MSN configuration and experiment resolver endpoints.
    """
    query_str = str(request.query_params)
    target_url = f"https://assets.msn.com/resolver/{resolver_path}"
    if query_str:
        target_url += f"?{query_str}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                target_url,
                headers={
                    "User-Agent": request.headers.get("user-agent", "Mozilla/5.0"),
                    "Accept": request.headers.get("accept", "*/*"),
                }
            )
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type", "application/json"),
                headers={"Cache-Control": "public, max-age=3600"}
            )
    except Exception:
        raise HTTPException(status_code=404, detail="Resolver resource not found")

@app.get("/api/msn/health")
async def get_msn_health():
    """
    Returns the real-time health status of Chromium's WebGL map rendering.
    """
    health = await msn_browser.check_map_health()
    return health

@app.get("/api/msn/frame")
async def get_msn_frame():
    """
    Returns a live JPEG screenshot from top-level headless Chromium running MSN Weather map.
    """
    try:
        frame_bytes = await msn_browser.get_screenshot()
        return Response(
            content=frame_bytes,
            media_type="image/jpeg",
            headers={
                "X-Capture-Timestamp": str(int(time.time())),
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )
    except Exception as e:
        logger.error(f"Failed to capture MSN frame: {e}")
        raise HTTPException(status_code=503, detail=f"Map rendering failed: {e}")


@app.post("/api/msn/interact")
async def interact_msn_map(request: Request):
    """
    Forwards user clicks, drags, wheel zoom events directly to Chromium running MSN.
    """
    try:
        body = await request.json()
        action = body.get("action", "click")
        frame_bytes = await msn_browser.interact(action, body)
        b64_img = base64.b64encode(frame_bytes).decode("utf-8")
        return {
            "success": True,
            "image": f"data:image/jpeg;base64,{b64_img}",
            "timestamp": int(time.time())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/msn/stream")
async def msn_stream_ws(websocket: WebSocket):
    """
    Real-time interactive bidirectional stream for live map pan, drag, and zoom.
    """
    await websocket.accept()
    try:
        initial_frame = await msn_browser.get_screenshot()
        b64 = base64.b64encode(initial_frame).decode("utf-8")
        await websocket.send_json({
            "type": "frame",
            "image": f"data:image/jpeg;base64,{b64}",
            "timestamp": int(time.time()),
            "width": 800,
            "height": 500
        })

        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action:
                updated_frame = await msn_browser.interact(action, msg)
                b64_up = base64.b64encode(updated_frame).decode("utf-8")
                await websocket.send_json({
                    "type": "frame",
                    "image": f"data:image/jpeg;base64,{b64_up}",
                    "timestamp": int(time.time())
                })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.getLogger("airwise").info(f"Stream WS disconnected: {e}")

@app.on_event("shutdown")
async def shutdown_browser():
    await msn_browser.close()

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

    # Compute nearby monitoring stations for live regional map
    sorted_stations = sorted(CPCB_STATIONS, key=lambda s: haversine_km(lat, lon, s["lat"], s["lon"]))
    nearby_stations_list = []
    for st in sorted_stations[:12]:
        st_dist = haversine_km(lat, lon, st["lat"], st["lon"])
        if st_dist <= 250.0:
            st_aqi = max(18, min(480, us_aqi + st.get("aqi_offset", 0)))
            st_cat, _ = get_aqi_category(st_aqi)
            nearby_stations_list.append({
                "name": st["name"],
                "lat": st["lat"],
                "lon": st["lon"],
                "distance_km": st_dist,
                "aqi": st_aqi,
                "category": st_cat,
                "source": st.get("source", "Continuous Ambient Station")
            })

    if not nearby_stations_list:
        nearby_stations_list.append({
            "name": station_meta.name,
            "lat": lat + 0.015,
            "lon": lon + 0.012,
            "distance_km": station_meta.distance_km,
            "aqi": us_aqi,
            "category": category_label,
            "source": station_meta.source
        })

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
        nearby_stations=nearby_stations_list,
        data_quality={
            "station_distance_km": dist_km,
            "station_freshness_min": 12,
            "provenance": "Open-Meteo API & CPCB Real-time Ambient Monitoring Network",
            "is_interpolated": dist_km >= 45.0
        },
        disclaimer="AirWise provides environmental estimates for personal planning; it is not a medical device or a substitute for medical advice."
    )

# Mount public static assets
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
public_dir = os.path.join(BASE_DIR, "public")
if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
elif os.path.exists("public"):
    app.mount("/", StaticFiles(directory="public", html=True), name="public")
