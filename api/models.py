from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field

class UserProfileQuery(BaseModel):
    sensitivity: str = Field(default="standard", description="standard, sensitive_respiratory, sensitive_cardiac, child_elderly, outdoor_worker")
    activity: str = Field(default="walk", description="rest, walk, run_cycle, outdoor_labor")
    duration_minutes: int = Field(default=30, ge=5, le=360)

class StationMetadata(BaseModel):
    name: str
    distance_km: float
    updated_minutes_ago: int
    source: str
    is_modeled: bool = False
    confidence_level: str = "High"  # High, Medium, Limited
    is_far: bool = False
    warning: Optional[str] = None

class CurrentWeather(BaseModel):
    temp_c: float
    feels_like_c: float
    humidity: float
    wind_speed_kmh: float
    uv_index: float
    condition_code: int
    condition_text: str
    is_day: bool

class CurrentAirQuality(BaseModel):
    aqi: int
    category: str
    dominant_pollutant: str
    pm25: float
    pm10: Optional[float] = None
    o3: Optional[float] = None
    no2: Optional[float] = None
    so2: Optional[float] = None
    co: Optional[float] = None

class ExposureEstimate(BaseModel):
    dose_min_ug: float
    dose_max_ug: float
    qualitative_impact: str
    comparison_context: str
    assumptions: List[str]

class LowerExposureWindow(BaseModel):
    has_better_window: bool
    recommended_start: Optional[str] = None
    recommended_end: Optional[str] = None
    window_label: str
    best_aqi: int
    now_aqi: int
    delta_aqi: int
    confidence: str  # High, Medium, Limited
    reason_en: str
    reason_hi: str

class HourlyItem(BaseModel):
    time_iso: str
    hour_display: str
    temp_c: float
    humidity: float
    aqi: int
    category: str
    pm25: float
    condition_code: int
    is_day: bool
    risk_score: float

class CigaretteEquivalents(BaseModel):
    cigarette_count: float
    with_n95: float
    full_day_cigarettes: float
    headline_en: str
    headline_hi: str
    subtext_en: str
    subtext_hi: str

class HomeResponse(BaseModel):
    location_name: str
    latitude: float
    longitude: float
    scene: str  # clear, cloudy, rain, haze, night
    weather: CurrentWeather
    air_quality: CurrentAirQuality
    station: StationMetadata
    contextual_sentence: Dict[str, str]  # en, hi
    personal_guidance: Dict[str, Any]
    cigarette_equivalents: CigaretteEquivalents
    lower_exposure_window: LowerExposureWindow
    hourly: List[HourlyItem]
    nearby_stations: List[Dict[str, Any]] = []
    data_quality: Dict[str, Any]
    disclaimer: str

