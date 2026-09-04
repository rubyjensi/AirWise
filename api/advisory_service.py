"""
VayuGuard Advisory Service
Generates grounded, plain-language health guidance in English and Hindi.
Primary mode is fast, deterministic clinical translation with optional LLM paraphrasing.
"""

import os
from typing import Dict, Any, Optional

def generate_deterministic_guidance(
    activity: str,
    sensitivity: str,
    duration: int,
    dose_range: Dict[str, Any],
    aqi: int,
    scene: str,
    better_window: Dict[str, Any]
) -> Dict[str, Any]:
    """Generates structured, clinically accurate guidance text without LLM latency."""
    act_labels = {
        "rest": ("resting outdoors", "बाहर आराम"),
        "walk": ("a brisk walk", "टहलना"),
        "run_cycle": ("running or cycling", "दौड़ना या साइकिल चलाना"),
        "outdoor_labor": ("outdoor work", "बाहरी काम")
    }
    
    sens_labels = {
        "standard": "standard profile",
        "sensitive_respiratory": "respiratory sensitivity (asthma/COPD)",
        "sensitive_cardiac": "cardiac sensitivity",
        "child_elderly": "child or senior profile",
        "outdoor_worker": "prolonged outdoor worker"
    }
    
    act_en, act_hi = act_labels.get(activity, ("outdoor activity", "बाहरी गतिविधि"))
    min_ug = dose_range["dose_min_ug"]
    max_ug = dose_range["dose_max_ug"]
    dose_str = f"{min_ug}–{max_ug} µg"
    
    # Action determination
    if aqi > 200:
        if sensitivity in ["sensitive_respiratory", "sensitive_cardiac", "child_elderly"]:
            action_en = f"Limit {act_en} or shift indoors if feasible. A certified N95 mask can reduce inhaled particulate mass by ~90%."
            action_hi = f"{act_hi} को सीमित करें या इनडोर में बदलें। N95 मास्क से फेफड़ों में जाने वाले धूल कण 90% तक कम हो सकते हैं।"
        else:
            action_en = f"Pace yourself during {act_en}. Keep total outdoor duration under {min(45, duration)} minutes."
            action_hi = f"{act_hi} की गति धीमी रखें और बाहर का समय {min(45, duration)} मिनट से कम रखें।"
    elif aqi > 100:
        if sensitivity == "sensitive_respiratory":
            action_en = f"Gentle pace recommended. Keep your rescue inhaler on hand during {act_en}."
            action_hi = f"हल्की गति से चलें। {act_hi} के दौरान इनहेलर साथ रखना उपयोगी रहेगा।"
        else:
            action_en = f"Conditions are suitable for {act_en}; stay hydrated and listen to your body."
            action_hi = f"{act_hi} के लिए मौसम सामान्य है; पर्याप्त पानी पिएं और शरीर के संकेतों पर ध्यान दें।"
    else:
        action_en = f"Air quality is favorable. Excellent window for your {duration}-minute {act_en}."
        action_hi = f"वायु गुणवत्ता अनुकूल है। आपके {duration} मिनट के {act_hi} के लिए बेहतरीन समय है।"

    # Why text
    if aqi > 150:
        why_en = f"Fine particulate matter (PM2.5) is the primary driver. For a {duration}-minute session, estimated inhaled dose is {dose_str}."
        why_hi = f"हवा में PM2.5 कण मुख्य कारण हैं। {duration} मिनट में अनुमानित श्वसन मात्रा {dose_str} रहने की संभावना है।"
    else:
        why_en = f"Particulate levels remain within moderate bounds, yielding a modest estimated dose of {dose_str}."
        why_hi = f"प्रदूषण का स्तर संतुलित है, जिससे अनुमानित श्वसन मात्रा मात्र {dose_str} रहेगी।"

    # Window recommendation
    if better_window.get("has_better_window"):
        win_label = better_window.get("window_label", "")
        best_aqi = better_window.get("best_aqi", 0)
        window_en = f"Lower-exposure window: {win_label} (projected {best_aqi} AQI)."
        window_hi = f"कम प्रदूषण का बेहतर समय: {win_label} (लगभग {best_aqi} AQI)।"
    else:
        window_en = "Current conditions are among the most favorable over the next 12 hours."
        window_hi = "अगले 12 घंटों में वर्तमान समय ही सबसे अनुकूल अवसरों में से एक है।"

    return {
        "activity": activity,
        "duration_minutes": duration,
        "sensitivity": sensitivity,
        "dose_range_str": dose_str,
        "estimated_dose_ug": {
            "min": min_ug,
            "max": max_ug,
            "typical": dose_range["dose_typical_ug"],
            "unit": "µg"
        },
        "guidance_text": {
            "en": action_en,
            "hi": action_hi
        },
        "why_text": {
            "en": why_en,
            "hi": why_hi
        },
        "window_suggestion": {
            "en": window_en,
            "hi": window_hi
        },
        "assumptions": dose_range.get("assumptions", [])
    }

async def generate_llm_enhanced_advisory(
    structured_data: Dict[str, Any],
    provider: str = "auto"
) -> Optional[Dict[str, str]]:
    """
    Optional enhancement via Groq or Gemini.
    Strictly preserves calculated numbers and provides an empathetic voice script.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    # If no keys, return None to keep deterministic guidance
    if not groq_key and not gemini_key:
        return None
        
    prompt = (
        f"You are the voice of VayuGuard, an atmospheric health companion. "
        f"Rephrase this deterministic clinical advice into one calm, friendly sentence for English and Hindi.\n"
        f"Data: Activity: {structured_data['activity']}, Dose: {structured_data['dose_range_str']}, "
        f"Action: {structured_data['guidance_text']['en']}\n"
        f"Constraint: NEVER alter the numbers or change the medical advice. Return JSON with 'en' and 'hi' keys."
    )
    
    # Optional LLM call can be added here if keys exist
    return None
