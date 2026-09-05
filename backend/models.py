from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class PersonaType(str, Enum):
    DELIVERY = "delivery"
    ASTHMATIC = "asthmatic"
    RUNNER = "runner"
    SENIOR = "senior"
    GENERAL = "general"


class PollutantBreakdown(BaseModel):
    pm25: float = Field(..., description="PM2.5 in µg/m³")
    pm10: Optional[float] = Field(None, description="PM10 in µg/m³")
    o3: Optional[float] = Field(None, description="Ozone O3 in µg/m³")
    no2: Optional[float] = Field(None, description="NO2 in µg/m³")
    so2: Optional[float] = Field(None, description="SO2 in µg/m³")
    co: Optional[float] = Field(None, description="CO in µg/m³")


class WeatherTelemetry(BaseModel):
    temperature_c: float
    humidity_percent: float
    wind_speed_kmh: float
    heat_index_c: float
    weather_code: int = 0
    condition_text: str = "Clear"
    is_day: bool = True


class StationInfo(BaseModel):
    name: str
    distance_km: float
    latitude: float
    longitude: float
    source: str = "CPCB / WAQI"
    updated_at: str
    is_far: bool = False
    warning: Optional[str] = None


class StationMetadata(BaseModel):
    name: str
    distance_km: float
    updated_minutes_ago: int
    source: str
    is_modeled: bool = False
    confidence_level: str = "High"  # High, Medium, Limited
    is_far: bool = False
    warning: Optional[str] = None


class DosageMetrics(BaseModel):
    inhaled_rate_ug_per_min: float
    current_session_dose_ug: float
    daily_limit_ug: float
    budget_used_percent: float
    safe_time_remaining_minutes: int
    deposition_fraction: float
    minute_ventilation_m3_min: float
    clinical_exertion_label: str


class CompoundAlert(BaseModel):
    severity: str  # "normal", "warning", "critical"
    type: str  # "cardiovascular", "bronchial", "general"
    title: str
    message: str
    physiological_impact: str


class HourlySlot(BaseModel):
    time_str: str
    hour: int
    aqi: int
    pm25: float
    temperature_c: float
    risk_level: str  # "good", "moderate", "unhealthy", "hazardous"
    is_safe_window: bool = False


class RouteOption(BaseModel):
    name: str
    route_type: str  # "highway", "green"
    duration_minutes: int
    distance_km: float
    pm25_avg: float
    total_dose_ug: float
    saving_percent: float = 0.0
    recommendation: str


class AdvisoryContent(BaseModel):
    english: str
    hindi: str
    key_action: str
    n95_recommended: bool
    outdoor_allowed: bool


class AnalysisResponse(BaseModel):
    city: str
    coordinates: Dict[str, float]
    natural_headline: str
    aqi: int
    aqi_category: str
    station: StationInfo
    weather: WeatherTelemetry
    pollutants: PollutantBreakdown
    persona: PersonaType
    dosage: DosageMetrics
    compound_alerts: List[CompoundAlert]
    advisory: AdvisoryContent
    hourly_forecast: List[HourlySlot]
    safe_activity_window: Dict[str, Any]
    route_comparison: List[RouteOption]
    timestamp: str


class PersonalizationRequest(BaseModel):
    profile_text: Optional[str] = Field(None, description="Free-text description of work, routine, and health issues")
    profile_name: Optional[str] = Field("My Profile", description="Label for this profile")
    occupation: Optional[str] = Field("General", description="Work/Occupation")
    health_conditions: Optional[List[str]] = Field(default_factory=list, description="Pre-existing conditions")
    outdoor_hours: Optional[float] = Field(2.0, description="Hours spent outdoors per day")
    commute_mode: Optional[str] = Field("Commuter", description="Commute mode")
    current_aqi: Optional[int] = 186
    current_pm25: Optional[float] = 118.4
    temperature_c: Optional[float] = 30.0
    humidity_percent: Optional[float] = 55.0
    heat_index_c: Optional[float] = 33.0
    city: Optional[str] = "Connaught Place, Delhi"
    user_api_key: Optional[str] = None  # Optional user Groq or Gemini API key


class ProfileEvaluationResponse(BaseModel):
    profile_summary: str
    vulnerability_level: str  # "Low", "Moderate", "High", "Critical"
    custom_minute_ventilation: float
    custom_deposition_fraction: float
    custom_daily_limit_ug: float
    inhaled_rate_ug_min: float
    safe_outdoor_minutes_today: int
    clinical_evaluation: str
    hindi_evaluation: str
    personalized_tips: List[str]
    protective_gear_recommendation: str
    indoor_air_advice: str
    commute_advisory: str
    personalized_faqs: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    routine_questions: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
