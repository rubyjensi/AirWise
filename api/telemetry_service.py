"""
VayuGuard Telemetry Service
Integrates Open-Meteo (zero-key open atmospheric telemetry) and WAQI/CPCB sensor metadata
with transparent data provenance, Haversine proximity, and rounded-grid caching.
"""

import httpx
import math
import time
import os
from typing import Dict, Any, List, Optional, Tuple

# In-memory short-term cache: key -> (timestamp, data)
_CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes

# Curated CPCB Reference Stations for fallback validation across Indian metropolitan areas
# Curated CPCB Reference Stations for fallback validation & live map plotting
CPCB_STATIONS = [
    # Delhi NCR
    {"name": "Mandir Marg, Delhi (DPCC)", "lat": 28.6364, "lon": 77.1990, "source": "DPCC Real-time Monitor", "aqi_offset": 0},
    {"name": "Anand Vihar, Delhi (CPCB)", "lat": 28.6476, "lon": 77.3158, "source": "CPCB Continuous Ambient", "aqi_offset": 28},
    {"name": "RK Puram, Delhi (DPCC)", "lat": 28.5632, "lon": 77.1869, "source": "DPCC Real-time Monitor", "aqi_offset": -8},
    {"name": "Punjabi Bagh, Delhi (DPCC)", "lat": 28.6740, "lon": 77.1310, "source": "DPCC Continuous Station", "aqi_offset": 12},
    {"name": "Lodhi Road, Delhi (IMD)", "lat": 28.5910, "lon": 77.2270, "source": "IMD Safar Monitor", "aqi_offset": -16},
    {"name": "IGI Airport T3, Delhi (IMD)", "lat": 28.5562, "lon": 77.1000, "source": "IMD Airport Sensor", "aqi_offset": -10},
    {"name": "Sector 62, Noida (UPPCB)", "lat": 28.6258, "lon": 77.3649, "source": "UPPCB Continuous Monitor", "aqi_offset": 18},
    {"name": "Vikas Sadan, Gurugram (HSPCB)", "lat": 28.4595, "lon": 77.0266, "source": "HSPCB Ambient Station", "aqi_offset": 14},

    # Mumbai Region
    {"name": "Bandra Kurla Complex, Mumbai (MPCB)", "lat": 19.0662, "lon": 72.8687, "source": "MPCB Continuous Monitor", "aqi_offset": 6},
    {"name": "Colaba, Mumbai (CPCB)", "lat": 18.9067, "lon": 72.8147, "source": "CPCB Ambient Station", "aqi_offset": -14},
    {"name": "Chembur, Mumbai (MPCB)", "lat": 19.0522, "lon": 72.8994, "source": "MPCB Ambient Monitor", "aqi_offset": 15},
    {"name": "Worli, Mumbai (MPCB)", "lat": 19.0178, "lon": 72.8178, "source": "MPCB Real-time Sensor", "aqi_offset": -8},
    {"name": "Vashi, Navi Mumbai (MPCB)", "lat": 19.0771, "lon": 72.9986, "source": "MPCB Industrial Grid", "aqi_offset": 12},

    # Bengaluru Region
    {"name": "BTM Layout, Bengaluru (KSPCB)", "lat": 12.9166, "lon": 77.6101, "source": "KSPCB Continuous Monitor", "aqi_offset": -4},
    {"name": "Silk Board, Bengaluru (CPCB)", "lat": 12.9172, "lon": 77.6228, "source": "CPCB Ambient Monitor", "aqi_offset": 18},
    {"name": "Peenya, Bengaluru (KSPCB)", "lat": 13.0285, "lon": 77.5197, "source": "KSPCB Industrial Station", "aqi_offset": 22},
    {"name": "City Railway Station, Bengaluru (KSPCB)", "lat": 12.9772, "lon": 77.5713, "source": "KSPCB Urban Monitor", "aqi_offset": 8},

    # Central India - Indore & Bhopal (MPPCB)
    {"name": "Chhoti Gwaltoli, Indore (MPPCB)", "lat": 22.7196, "lon": 75.8677, "source": "MPPCB Continuous Station", "aqi_offset": 5},
    {"name": "Sanwer Road Industrial Area, Indore (MPPCB)", "lat": 22.7667, "lon": 75.8611, "source": "MPPCB Industrial Station", "aqi_offset": 14},
    {"name": "Vijay Nagar, Indore (MPPCB)", "lat": 22.7533, "lon": 75.8937, "source": "MPPCB Ambient Sensor", "aqi_offset": -2},
    {"name": "T.T. Nagar, Bhopal (MPPCB)", "lat": 23.2332, "lon": 77.3995, "source": "MPPCB Real-time Monitor", "aqi_offset": 0},
    {"name": "Paryavaran Parisar, Bhopal (MPPCB)", "lat": 23.2156, "lon": 77.4350, "source": "MPPCB Continuous Station", "aqi_offset": -4},

    # Western India - Gujarat & Rajasthan
    {"name": "Maninagar, Ahmedabad (GPCB)", "lat": 22.9966, "lon": 72.6030, "source": "GPCB Continuous Monitor", "aqi_offset": 8},
    {"name": "Mansarovar, Jaipur (RSPCB)", "lat": 26.8529, "lon": 75.7684, "source": "RSPCB Ambient Station", "aqi_offset": 6},

    # Northern & Eastern India - Lucknow, Chandigarh, Patna
    {"name": "Lalbagh, Lucknow (UPPCB)", "lat": 26.8467, "lon": 80.9462, "source": "UPPCB Continuous Station", "aqi_offset": 12},
    {"name": "Sector 22, Chandigarh (CPCC)", "lat": 30.7333, "lon": 76.7794, "source": "CPCC Real-time Monitor", "aqi_offset": -5},
    {"name": "Muradpur, Patna (BSPCB)", "lat": 25.6207, "lon": 85.1666, "source": "BSPCB Continuous Station", "aqi_offset": 15},
]

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance between two GPS coordinates in kilometers."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)

def get_aqi_category(us_aqi: int) -> Tuple[str, str]:
    """Returns (Category Label, CSS Accent Key)"""
    if us_aqi <= 50:
        return "Good", "good"
    elif us_aqi <= 100:
        return "Moderate", "moderate"
    elif us_aqi <= 150:
        return "Sensitive Groups", "sensitive"
    elif us_aqi <= 200:
        return "Unhealthy", "unhealthy"
    elif us_aqi <= 300:
        return "Very Unhealthy", "very-unhealthy"
    else:
        return "Hazardous", "hazardous"

def determine_scene(weather_code: int, is_day: bool, aqi: int) -> str:
    """Determines atmospheric background theme: clear, cloudy, rain, haze, night."""
    # Rain / drizzle / thunderstorms
    if weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]:
        return "rain"
    # Severe haze or high particulate concentration
    if aqi >= 160 or weather_code in [45, 48]:
        return "haze"
    # Night time
    if not is_day:
        return "night"
    # Cloudy
    if weather_code in [2, 3]:
        return "cloudy"
    # Clear daytime
    return "clear"

def get_contextual_sentence(scene: str, aqi: int, temp_c: float) -> Dict[str, str]:
    """Generates the primary glanceable sentence on the hero screen."""
    if scene == "rain":
        return {
            "en": "Rain is clearing the air—enjoy the fresh conditions when showers ease.",
            "hi": "बारिश से हवा साफ़ हो रही है—हल्की बौछारों के बाद ताज़गी का आनंद लें।"
        }
    elif aqi > 250:
        return {
            "en": "Heavy particulate haze—keep outdoor activity minimal and protect your breath.",
            "hi": "हवा में भारी प्रदूषण—बाहरी गतिविधियों को सीमित रखें और सावधानी बरतें।"
        }
    elif aqi > 150:
        return {
            "en": "A hazy atmosphere—lighter activity and shorter outdoor time are the better call.",
            "hi": "हवा में धुंध का असर—धीमी गति और कम समय बाहर बिताना बेहतर रहेगा।"
        }
    elif aqi > 100:
        return {
            "en": "Moderate air quality—sensitive individuals may want to plan a gentler pace.",
            "hi": "मध्यम वायु गुणवत्ता—संवेदनशील लोगों के लिए हल्की गतिविधि उपयुक्त रहेगी।"
        }
    elif temp_c > 35:
        return {
            "en": "Warm and clear—hydrate well and aim for shade during midday hours.",
            "hi": "धूप और गर्मी का असर—पर्याप्त पानी पिएं और दोपहर में छांव में रहें।"
        }
    else:
        return {
            "en": "Clear skies and receptive air—an inviting time to step outside.",
            "hi": "साफ़ और सुखद मौसम—बाहर टहलने या कसरत के लिए अनुकूल समय।"
        }

async def fetch_open_meteo_telemetry(lat: float, lon: float) -> Dict[str, Any]:
    """Fetches combined weather and air quality hourly telemetry from Open-Meteo."""
    grid_lat = round(lat, 2)
    grid_lon = round(lon, 2)
    cache_key = f"{grid_lat}:{grid_lon}"
    
    now = time.time()
    if cache_key in _CACHE:
        ts, cached_data = _CACHE[cache_key]
        if now - ts < CACHE_TTL_SECONDS:
            return cached_data
            
    # Asynchronous requests to Open-Meteo Weather and Air Quality APIs
    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m"
        f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,is_day"
        f"&timezone=auto&forecast_days=2"
    )
    
    aq_url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}"
        f"&current=us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide,uv_index"
        f"&hourly=us_aqi,pm2_5,pm10,ozone,uv_index"
        f"&timezone=auto&forecast_days=2"
    )
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            weather_res, aq_res = await asyncio.gather(
                client.get(weather_url),
                client.get(aq_url),
                return_exceptions=True
            )
            
            w_json = weather_res.json() if not isinstance(weather_res, Exception) and weather_res.status_code == 200 else {}
            aq_json = aq_res.json() if not isinstance(aq_res, Exception) and aq_res.status_code == 200 else {}
            
            payload = {"weather": w_json, "air_quality": aq_json, "fetched_at": now}
            _CACHE[cache_key] = (now, payload)
            return payload
        except Exception as e:
            # If network error occurs, return fallback fixture
            return {"weather": {}, "air_quality": {}, "error": str(e), "fetched_at": now}

import asyncio
