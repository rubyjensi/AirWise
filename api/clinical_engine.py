"""
VayuGuard Clinical & Exposure Engine
Translates environmental telemetry into range-based biological inhalation dose estimates
and identifies lower-exposure activity windows based on peer-reviewed pulmonary models.
"""

from typing import Dict, Any, List, Optional, Tuple
import math

# Minute ventilation rates (m3/min): (min, typical, max)
VENTILATION_RATES: Dict[str, Tuple[float, float, float]] = {
    "rest": (0.0055, 0.0070, 0.0085),
    "walk": (0.0130, 0.0160, 0.0200),
    "run_cycle": (0.0300, 0.0380, 0.0460),
    "outdoor_labor": (0.0240, 0.0300, 0.0360),
}

# Pulmonary deposition fraction (fraction of inhaled PM2.5 deposited in tracheobronchial/alveolar region)
DEPOSITION_FRACTIONS: Dict[str, Tuple[float, float, float]] = {
    "standard": (0.35, 0.40, 0.45),
    "sensitive_respiratory": (0.55, 0.62, 0.70),  # Higher deposition due to airway narrowing & turbulence
    "sensitive_cardiac": (0.40, 0.45, 0.50),
    "child_elderly": (0.46, 0.52, 0.58),          # Smaller airway caliber / altered clearance
    "outdoor_worker": (0.37, 0.42, 0.48),
}

def calculate_heat_index(temp_c: float, humidity: float) -> float:
    """Calculates apparent temperature / heat index in Celsius."""
    if temp_c < 20.0:
        return temp_c
    # Rothfusz regression equation simplified for Celsius
    t = (temp_c * 9 / 5) + 32
    r = humidity
    hi_f = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r
            - 0.00683783 * t * t - 0.05481717 * r * r + 0.00122874 * t * t * r
            + 0.00085282 * t * r * r - 0.00000199 * t * t * r * r)
    hi_c = (hi_f - 32) * 5 / 9
    return round(max(temp_c, hi_c), 1)

def calculate_inhalation_dose(
    pm25_ug_m3: float,
    activity: str,
    sensitivity: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Calculates estimated inhaled PM2.5 deposition range in micrograms (ug).
    Formula: Inhaled Dose = Concentration * Ventilation Rate * Time * Deposition Fraction
    """
    act = activity if activity in VENTILATION_RATES else "walk"
    sens = sensitivity if sensitivity in DEPOSITION_FRACTIONS else "standard"
    
    ve_min, ve_typ, ve_max = VENTILATION_RATES[act]
    df_min, df_typ, df_max = DEPOSITION_FRACTIONS[sens]
    
    t = float(max(5, min(duration_minutes, 360)))
    
    # Calculate dose range in micrograms
    dose_min = pm25_ug_m3 * ve_min * t * df_min
    dose_max = pm25_ug_m3 * ve_max * t * df_max
    dose_typ = pm25_ug_m3 * ve_typ * t * df_typ
    
    # WHO 24-hr guideline comparison baseline (15 ug/m3 * 0.007 m3/min * 1440 min * 0.40 ≈ 60 ug daily deposition)
    # A reference 30-min walk in clean WHO-level air deposits ~1.2 ug
    clean_air_reference = 15.0 * 0.016 * 30.0 * 0.40  # ~2.88 ug
    multiple_of_clean = round(dose_typ / max(0.1, clean_air_reference), 1)
    
    qualitative_impact = "Low"
    if dose_typ > 60:
        qualitative_impact = "Elevated"
    elif dose_typ > 30:
        qualitative_impact = "Moderate"
    elif dose_typ > 15:
        qualitative_impact = "Notable"
        
    assumptions = [
        f"Minute ventilation for '{act}': ~{round(ve_typ * 1000, 1)} L/min ({round(ve_min * 1000)}–{round(ve_max * 1000)} L/min).",
        f"Alveolar deposition fraction calibrated for '{sens}': ~{int(df_typ * 100)}% ({int(df_min * 100)}%–{int(df_max * 100)}%).",
        "Assumes ambient outdoor exposure without certified particulate filtration (well-fitted N95/FFP2 reduces particulate dose by ~90%).",
        "Estimates reflect fine particulate mass (PM2.5); ozone and nitrogen dioxide elicit distinct epithelial reactions."
    ]
    
    return {
        "dose_min_ug": round(max(0.1, dose_min), 1),
        "dose_max_ug": round(max(0.2, dose_max), 1),
        "dose_typical_ug": round(max(0.1, dose_typ), 1),
        "multiple_of_clean": multiple_of_clean,
        "qualitative_impact": qualitative_impact,
        "assumptions": assumptions
    }

def evaluate_multi_stressor(
    pm25: float,
    temp_c: float,
    humidity: float,
    o3: Optional[float] = None
) -> Dict[str, Any]:
    """Identifies compound weather-air quality physiological stressors."""
    heat_index = calculate_heat_index(temp_c, humidity)
    flags = []
    
    if heat_index >= 38.0 and pm25 >= 75.0:
        flags.append({
            "code": "CARDIOVASCULAR_STRAIN",
            "title_en": "Heat & Particulate Strain",
            "title_hi": "गर्मी और वायु प्रदूषण का दोहरा असर",
            "desc_en": "Elevated heat index accelerates heart rate while fine particulates promote systemic vascular inflammation."
        })
    elif humidity <= 25.0 and pm25 >= 60.0:
        flags.append({
            "code": "MUCOSAL_DEHYDRATION",
            "title_en": "Dry Airway Irritation",
            "title_hi": "शुष्क हवा और गले में जलन",
            "desc_en": "Low humidity dehydrates mucous membranes, impairing the respiratory tract's natural cilia clearance."
        })
        
    if o3 and o3 >= 100.0:
        flags.append({
            "code": "PHOTOCHEMICAL_OZONE",
            "title_en": "Ground-Level Ozone Peak",
            "title_hi": "ओजोन का बढ़ता स्तर",
            "desc_en": "Solar UV has catalyzed secondary ozone formation, which acts as a direct bronchial irritant."
        })
        
    return {
        "heat_index_c": heat_index,
        "compound_flags": flags
    }

def find_lower_exposure_window(
    hourly_data: List[Dict[str, Any]],
    current_aqi: int,
    activity: str,
    sensitivity: str
) -> Dict[str, Any]:
    """
    Scans the next 18-24 hours to discover the optimal 90-120 minute lower-exposure window.
    Only recommends a window if there is a meaningful reduction (>20% or >=25 AQI points).
    """
    if not hourly_data or len(hourly_data) < 3:
        return {
            "has_better_window": False,
            "window_label": "Consistent conditions",
            "best_aqi": current_aqi,
            "now_aqi": current_aqi,
            "delta_aqi": 0,
            "confidence": "Limited",
            "reason_en": "Air quality is expected to remain relatively stable over the next 12 hours.",
            "reason_hi": "अगले 12 घंटों में वायु गुणवत्ता में कोई बड़ा बदलाव अपेक्षित नहीं है।"
        }
    
    # Consider candidate 2-hour windows
    best_avg_aqi = float('inf')
    best_idx = -1
    
    # Search within the next 18 hours (ignoring past hours)
    search_limit = min(18, len(hourly_data) - 1)
    
    for i in range(1, search_limit):
        # 2-hour rolling average
        window_aqi = (hourly_data[i]["aqi"] + hourly_data[i+1]["aqi"]) / 2.0
        if window_aqi < best_avg_aqi:
            best_avg_aqi = window_aqi
            best_idx = i
            
    best_aqi_int = int(round(best_avg_aqi))
    delta = current_aqi - best_aqi_int
    
    # A meaningful improvement is either >= 25 AQI drop or >= 20% lower
    if delta >= 25 or (current_aqi > 50 and delta / current_aqi >= 0.20):
        start_hour = hourly_data[best_idx].get("hour_display", "")
        end_hour = hourly_data[min(len(hourly_data)-1, best_idx + 2)].get("hour_display", "")
        window_label = f"{start_hour} – {end_hour}"
        
        # Determine meteorological rationale
        best_hour_data = hourly_data[best_idx]
        best_wind = best_hour_data.get("wind_speed_kmh", 8.0)
        is_evening = "17:" in start_hour or "18:" in start_hour or "19:" in start_hour or "20:" in start_hour
        is_early_morning = "05:" in start_hour or "06:" in start_hour or "07:" in start_hour
        
        if best_wind > 12.0:
            reason_en = "PM2.5 is forecast to disperse as surface ventilation and wind speeds pick up."
            reason_hi = "तेज़ हवाओं के कारण प्रदूषक कणों का बिखराव होगा और हवा साफ़ होगी।"
        elif is_evening:
            reason_en = "Photochemical ozone levels subside and boundary layer ventilation improves."
            reason_hi = "शाम के समय ओजोन और सतह के तापमान में गिरावट से राहत मिलेगी।"
        elif is_early_morning:
            reason_en = "Traffic emissions and photochemical activity are lower in this early window."
            reason_hi = "सुबह के समय वाहनों का धुआं और प्रदूषण तुलनात्मक रूप से कम रहता है।"
        else:
            reason_en = "Atmospheric conditions are forecast to offer lower particulate concentrations."
            reason_hi = "इस समय वायुमंडल में प्रदूषण कणों की सांद्रता कम रहने का अनुमान है।"
            
        return {
            "has_better_window": True,
            "recommended_start": start_hour,
            "recommended_end": end_hour,
            "window_label": window_label,
            "best_aqi": best_aqi_int,
            "now_aqi": current_aqi,
            "delta_aqi": delta,
            "confidence": "High" if len(hourly_data) >= 12 else "Medium",
            "reason_en": reason_en,
            "reason_hi": reason_hi
        }
    else:
        return {
            "has_better_window": False,
            "window_label": "No significantly cleaner window today",
            "best_aqi": best_aqi_int,
            "now_aqi": current_aqi,
            "delta_aqi": max(0, delta),
            "confidence": "High",
            "reason_en": "Conditions are relatively consistent. If stepping outside, keep duration moderate.",
            "reason_hi": "वायु गुणवत्ता लगभग एक समान रहेगी। बाहर निकलते समय समय-सीमा सीमित रखें।"
        }


def calculate_cigarette_equivalents(
    pm25: float,
    activity: str,
    duration_minutes: int
) -> Dict[str, Any]:
    """
    Calculates cigarette equivalence using the Berkeley Earth / Muller formulation:
    - 22 µg/m³ PM2.5 over 24h = 1 cigarette = 352 µg inhaled mass benchmark.
    - Minute ventilation rates (VE in m³/min):
        rest: 0.007 m³/min (7 L/min)
        walk: 0.016 m³/min (16 L/min)
        run_cycle: 0.038 m³/min (38 L/min)
        outdoor_labor / work shift: 0.030 m³/min (30 L/min)
    - Inhaled mass (µg) = pm25 * VE * duration_minutes.
    - Cigarette count = round(inhaled_mass / 352.0, 2), min 0.05.
    - With N95 mask (90% filtration) = round(cigarette_count * 0.10, 2).
    - Full day 24h outdoor cigarette equivalent = round(pm25 / 22.0, 1).
    """
    pm25_val = max(0.0, float(pm25))
    dur = max(1, int(duration_minutes))

    # Minute ventilation rates (m3/min)
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

    # Activity labels for readable subtext
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

