import math
from typing import Dict, Any, List, Tuple
from backend.models import (
    PersonaType,
    DosageMetrics,
    CompoundAlert,
    HourlySlot,
    RouteOption,
    PollutantBreakdown,
    WeatherTelemetry,
)

# Physiological constants validated by inhalation toxicology literature
PERSONA_PARAMETERS: Dict[PersonaType, Dict[str, Any]] = {
    PersonaType.DELIVERY: {
        "minute_ventilation": 0.024,  # m³/min (moderate traffic exertion)
        "deposition_fraction": 0.48,  # higher oral breathing bypasses nasal cilia
        "daily_limit_ug": 40.0,
        "label": "Delivery Shift / Outdoor Transit",
    },
    PersonaType.ASTHMATIC: {
        "minute_ventilation": 0.016,  # m³/min
        "deposition_fraction": 0.65,  # compromised mucociliary clearance
        "daily_limit_ug": 22.0,       # lower protective threshold
        "label": "Reactive Airway / Sensitive",
    },
    PersonaType.RUNNER: {
        "minute_ventilation": 0.045,  # m³/min (high aerobic demand)
        "deposition_fraction": 0.45,  # deep lung ventilation
        "daily_limit_ug": 45.0,
        "label": "Aerobic Exercise / Running",
    },
    PersonaType.SENIOR: {
        "minute_ventilation": 0.012,  # m³/min (reduced tidal volume)
        "deposition_fraction": 0.55,  # reduced airway clearance elasticity
        "daily_limit_ug": 25.0,
        "label": "Senior / Cardiopulmonary Vigilance",
    },
    PersonaType.GENERAL: {
        "minute_ventilation": 0.018,  # m³/min (normal walking)
        "deposition_fraction": 0.40,  # baseline nasal filtration
        "daily_limit_ug": 45.0,
        "label": "General Adult Baseline",
    },
}


def calculate_heat_index(temp_c: float, humidity_percent: float) -> float:
    """Calculates Steadman/Rothfusz Heat Index in Celsius."""
    # Convert to Fahrenheit for standard equation
    T = temp_c * 9 / 5 + 32
    RH = humidity_percent

    if T < 80:
        # Simple formula for mild temperatures
        hi_f = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (RH * 0.094))
    else:
        # Full Rothfusz regression equation
        hi_f = (
            -42.379
            + 2.04901523 * T
            + 10.14333127 * RH
            - 0.22475541 * T * RH
            - 0.00683783 * T * T
            - 0.05481717 * RH * RH
            + 0.00122874 * T * T * RH
            + 0.00085282 * T * RH * RH
            - 0.00000199 * T * T * RH * RH
        )
    return round((hi_f - 32) * 5 / 9, 1)


def compute_inhalation_dosage(
    pm25_ug_m3: float,
    persona: PersonaType,
    session_minutes: int = 30,
) -> DosageMetrics:
    """Computes real-time biological particulate dosage (µg) using physiological model.
    Dose (µg) = C_PM2.5 (µg/m³) * Ve (m³/min) * t (min) * DF
    """
    params = PERSONA_PARAMETERS.get(persona, PERSONA_PARAMETERS[PersonaType.GENERAL])
    ve = params["minute_ventilation"]
    df = params["deposition_fraction"]
    daily_limit = params["daily_limit_ug"]

    rate_ug_min = pm25_ug_m3 * ve * df
    current_session_dose = rate_ug_min * session_minutes

    budget_used_percent = min(100.0, (current_session_dose / daily_limit) * 100)

    if rate_ug_min > 0:
        remaining_budget = max(0.0, daily_limit - current_session_dose)
        safe_time_remaining = int(remaining_budget / rate_ug_min)
    else:
        safe_time_remaining = 480

    return DosageMetrics(
        inhaled_rate_ug_per_min=round(rate_ug_min, 2),
        current_session_dose_ug=round(current_session_dose, 1),
        daily_limit_ug=daily_limit,
        budget_used_percent=round(budget_used_percent, 1),
        safe_time_remaining_minutes=safe_time_remaining,
        deposition_fraction=df,
        minute_ventilation_m3_min=ve,
        clinical_exertion_label=params["label"],
    )


def evaluate_compound_stressors(
    pm25: float,
    temp_c: float,
    humidity: float,
    heat_index_c: float,
    persona: PersonaType,
) -> List[CompoundAlert]:
    """Detects multi-stressor synergisms (Heat + PM2.5, Humidity extremes)."""
    alerts: List[CompoundAlert] = []

    # 1. Heat + PM2.5 Synergism: Cardiovascular Strain
    if heat_index_c >= 35.0 and pm25 >= 75.0:
        alerts.append(
            CompoundAlert(
                severity="critical" if heat_index_c >= 39.0 or pm25 >= 150 else "warning",
                type="cardiovascular",
                title="Cardiovascular Heat-Particulate Strain",
                message=(
                    f"Heat index of {heat_index_c}°C coupled with PM2.5 ({pm25} µg/m³) causes "
                    "concurrent systemic vasodilation and particulate inflammation."
                ),
                physiological_impact=(
                    "Elevated heart rate, endothelial irritation, and accelerated cardiac fatigue. "
                    "Hydrate vigorously and avoid all intense outdoor physical labor."
                ),
            )
        )

    # 2. Dry Air + Particulates: Bronchial Dehydration
    if humidity <= 25.0 and pm25 >= 50.0:
        alerts.append(
            CompoundAlert(
                severity="warning",
                type="bronchial",
                title="Airway Dehydration & Ciliary Arrest",
                message=(
                    f"Extremely dry air ({humidity}%) strips moisture from the respiratory mucous layer, "
                    f"allowing fine {pm25} µg/m³ particulates to penetrate unimpeded into alveoli."
                ),
                physiological_impact=(
                    "Triggers cough reflexes, dry throat burning, and acute bronchospasms in sensitive individuals."
                ),
            )
        )

    # 3. Fog/Stagnation Trapping: Inversion Syndrome
    if humidity >= 82.0 and pm25 >= 100.0 and temp_c <= 18.0:
        alerts.append(
            CompoundAlert(
                severity="critical" if pm25 >= 200 else "warning",
                type="general",
                title="Hygroscopic Aerosol Inversion",
                message=(
                    "High humidity (>80%) and cool ground temperatures cause hygroscopic particle growth, "
                    "trapping pollutants in the surface breathing boundary layer."
                ),
                physiological_impact=(
                    "Particles swell in size and lodge deeply in secondary bronchial bifurcations. N95 respirator mandatory."
                ),
            )
        )

    # Asthmatic specific safeguard
    if persona == PersonaType.ASTHMATIC and pm25 >= 60.0 and not alerts:
        alerts.append(
            CompoundAlert(
                severity="warning",
                type="bronchial",
                title="Asthma Bronchoconstriction Advisory",
                message="Elevated particulate threshold exceeds reactive airway safety margin.",
                physiological_impact="Keep rescue bronchodilator (albuterol/salbutamol) immediately accessible.",
            )
        )

    return alerts


def generate_natural_headline(aqi: int, condition_text: str, is_day: bool) -> str:
    """Generates a Good Air-style poetic, natural language editorial summary."""
    time_prefix = "Daylight" if is_day else "Evening"
    
    if aqi <= 45:
        return f"Crisp and clear, an exceptional {time_prefix.lower()} to breathe deeply."
    elif aqi <= 90:
        return "Slightly less than pristine, still perfectly usable air."
    elif aqi <= 140:
        return "A noticeable haze settling over the horizon; sensitive lungs should take notice."
    elif aqi <= 200:
        return "Heavy particulate stagnation; continuous outdoor exertion is ill-advised."
    elif aqi <= 300:
        return "Severe atmospheric hazard; high inhalation toxicity across the city."
    else:
        return "Hazardous emergency conditions; air contains acute particulate burden."


def calculate_aqi_from_pm25(pm25: float) -> Tuple[int, str]:
    """Calculates US EPA Air Quality Index and category from PM2.5 (µg/m³)."""
    # EPA PM2.5 breakpoints
    breakpoints = [
        (0.0, 12.0, 0, 50, "Good"),
        (12.1, 35.4, 51, 100, "Moderate"),
        (35.5, 55.4, 101, 150, "Unhealthy for Sensitive Groups"),
        (55.5, 150.4, 151, 200, "Unhealthy"),
        (150.5, 250.4, 201, 300, "Very Unhealthy"),
        (250.5, 500.4, 301, 500, "Hazardous"),
    ]

    for c_low, c_high, i_low, i_high, cat in breakpoints:
        if c_low <= pm25 <= c_high:
            aqi = round(((i_high - i_low) / (c_high - c_low)) * (pm25 - c_low) + i_low)
            return aqi, cat

    if pm25 > 500.4:
        return 500, "Hazardous"
    return 0, "Good"


def optimize_safe_activity_window(
    hourly_slots: List[HourlySlot],
    window_hours: float = 1.5,
) -> Dict[str, Any]:
    """Finds the lowest hazard activity window in the 24-hour cycle."""
    if len(hourly_slots) < 2:
        return {
            "start_time": "06:00 AM",
            "end_time": "07:30 AM",
            "best_aqi": 85,
            "summary": "Early morning hours offer the least stagnant air.",
            "reason": "Lower vehicle congestion and atmospheric mixing.",
        }

    best_start_idx = 0
    lowest_avg_aqi = float("inf")

    # Evaluate 2 consecutive slots
    for i in range(len(hourly_slots) - 1):
        avg_aqi = (hourly_slots[i].aqi + hourly_slots[i + 1].aqi) / 2
        # Penalize midday heat
        if 12 <= hourly_slots[i].hour <= 16:
            avg_aqi += 15
        if avg_aqi < lowest_avg_aqi:
            lowest_avg_aqi = avg_aqi
            best_start_idx = i

    best_slot = hourly_slots[best_start_idx]
    next_slot = hourly_slots[min(len(hourly_slots) - 1, best_start_idx + 1)]

    # Mark the slot in the list
    hourly_slots[best_start_idx].is_safe_window = True
    if best_start_idx + 1 < len(hourly_slots):
        hourly_slots[best_start_idx + 1].is_safe_window = True

    return {
        "start_time": best_slot.time_str,
        "end_time": next_slot.time_str,
        "best_aqi": int(lowest_avg_aqi),
        "summary": f"Cleanest window: {best_slot.time_str} – {next_slot.time_str}",
        "reason": "Optimal balance of minimal ground stagnation, lower ozone, and cooler ambient air.",
    }


def compute_route_exposure(
    pm25_ambient: float,
    persona: PersonaType,
) -> List[RouteOption]:
    """Compares exposure between Highway transit vs. Green Corridor."""
    params = PERSONA_PARAMETERS.get(persona, PERSONA_PARAMETERS[PersonaType.GENERAL])
    ve = params["minute_ventilation"]
    df = params["deposition_fraction"]

    # Highway: +30% PM2.5 due to diesel tailpipe emissions & tire friction
    highway_pm25 = round(pm25_ambient * 1.30, 1)
    highway_time = 22  # minutes
    highway_dose = round(highway_pm25 * ve * highway_time * df, 1)

    # Green Corridor: -45% PM2.5 due to tree canopy settling & low traffic
    green_pm25 = round(pm25_ambient * 0.55, 1)
    green_time = 26  # minutes (slightly longer detour)
    green_dose = round(green_pm25 * ve * green_time * df, 1)

    saving = round(((highway_dose - green_dose) / max(0.1, highway_dose)) * 100, 1)

    return [
        RouteOption(
            name="Highway Arterial Route",
            route_type="highway",
            duration_minutes=highway_time,
            distance_km=9.4,
            pm25_avg=highway_pm25,
            total_dose_ug=highway_dose,
            saving_percent=0.0,
            recommendation="High diesel soot concentration; heavy vehicular turbulence.",
        ),
        RouteOption(
            name="Green Park / Canopy Corridor",
            route_type="green",
            duration_minutes=green_time,
            distance_km=10.2,
            pm25_avg=green_pm25,
            total_dose_ug=green_dose,
            saving_percent=saving,
            recommendation=f"Saves {saving}% toxic particulate deposition in lungs despite +4 min travel.",
        ),
    ]


def calculate_cigarette_equivalents(
    pm25: float,
    activity: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Calculates cigarette equivalence using the Berkeley Earth / Muller formulation:
    - 22 µg/m³ PM2.5 over 24h = 1 cigarette = 352 µg inhaled mass benchmark.
    - Minute ventilation rates: rest = 0.007 m3/min, walk = 0.016 m3/min,
      run_cycle = 0.038 m3/min, outdoor_labor / work shift = 0.030 m3/min.
    - Inhaled mass ug = pm25 * VE * duration_minutes.
    - Cigarette count = round(inhaled_mass / 352.0, 2), min 0.05.
    - With N95 mask (90% filtration) = round(cigarette_count * 0.10, 2).
    - Full day 24h outdoor cigarette equivalent = round(pm25 / 22.0, 1).
    """
    pm25_val = max(0.0, float(pm25))
    dur = max(1, int(duration_minutes))

    ve_map = {
        "rest": 0.007,
        "walk": 0.016,
        "run_cycle": 0.038,
        "run": 0.038,
        "cycle": 0.038,
        "outdoor_labor": 0.030,
        "work_shift": 0.030,
        "labor": 0.030,
    }
    act_clean = (activity or "walk").lower().strip()
    ve = ve_map.get(act_clean, 0.016)

    inhaled_mass = pm25_val * ve * dur
    raw_cigarettes = inhaled_mass / 352.0
    cigarette_count = round(raw_cigarettes, 2)
    if cigarette_count < 0.05:
        cigarette_count = 0.05

    with_n95 = round(cigarette_count * 0.10, 2)
    full_day_cigarettes = round(pm25_val / 22.0, 1)

    act_labels = {
        "rest": ("resting outdoors", "बाहर विश्राम"),
        "walk": ("walking", "पैदल चलने"),
        "run_cycle": ("running/cycling", "दौड़ने/साइकिल चलाने"),
        "run": ("running", "दौड़ने"),
        "cycle": ("cycling", "साइकिल चलाने"),
        "outdoor_labor": ("outdoor labor", "शारीरिक श्रम"),
        "work_shift": ("work shift", "काम की शिफ्ट"),
    }
    act_label_en, act_label_hi = act_labels.get(act_clean, (act_clean.replace("_", " "), act_clean))

    if cigarette_count >= 1.0:
        headline_en = f"Equivalent to smoking {cigarette_count:.2f} cigarettes"
        headline_hi = f"{cigarette_count:.2f} सिगरेट पीने के बराबर धुआं"
    else:
        headline_en = f"Equivalent to smoking ~{cigarette_count:.2f} cigarettes"
        headline_hi = f"लगभग {cigarette_count:.2f} सिगरेट के धुएं के बराबर असर"

    subtext_en = (
        f"{dur} min of {act_label_en} deposits ~{round(inhaled_mass, 1)} µg PM2.5. "
        f"An N95 respirator reduces intake to ~{with_n95:.2f} cigs (full 24h outdoors = {full_day_cigarettes} cigs)."
    )
    subtext_hi = (
        f"{dur} मिनट {act_label_hi} से फेफड़ों में ~{round(inhaled_mass, 1)} µg PM2.5 जमा होता है। "
        f"N95 मास्क से यह घटकर ~{with_n95:.2f} सिगरेट रह जाता है (24 घंटे में ~{full_day_cigarettes} सिगरेट)।"
    )

    return {
        "cigarette_count": cigarette_count,
        "with_n95": with_n95,
        "full_day_cigarettes": full_day_cigarettes,
        "headline_en": headline_en,
        "headline_hi": headline_hi,
        "subtext_en": subtext_en,
        "subtext_hi": subtext_hi,
    }

