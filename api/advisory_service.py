"""
VayuGuard Advisory Service
Generates grounded, plain-language health guidance in English and Hindi.
Primary mode is fast, deterministic clinical translation with optional LLM paraphrasing.
"""

import os
import json
from typing import Dict, Any, Optional
import httpx

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
    Optional doctor enhancement via Groq or Gemini.
    Strictly preserves calculated numbers and provides an empathetic personal physician consultation script.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if not groq_key and not gemini_key:
        return None

    prompt = (
        f"You are the user's dedicated personal physician and pulmonologist speaking directly to your patient.\n"
        f"Rephrase this deterministic clinical guidance into a deeply caring, warm, medically precise consultation sentence in English and Hindi.\n"
        f"Tone: Conversational, caring family doctor speaking directly to 'you' ('As your doctor...', 'I want you to...').\n"
        f"Hindi MUST start with: 'आपके डॉक्टर के रूप में मेरी सलाह है कि...'\n"
        f"Clinical Telemetry: Activity: {structured_data.get('activity')}, Sensitivity: {structured_data.get('sensitivity')}, "
        f"Inhaled Dose: {structured_data.get('dose_range_str')}, Action: {structured_data.get('guidance_text', {}).get('en')}\n"
        f"Constraint: Return JSON only with 'en' and 'hi' keys. Never alter numbers."
    )

    candidate_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
    try:
        if groq_key:
            async with httpx.AsyncClient(timeout=6.0) as client:
                for model in candidate_models:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "You are a personal caring physician and pulmonary specialist. Always return valid JSON only."},
                                {"role": "user", "content": prompt}
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.25,
                        }
                    )
                    if res.status_code == 200:
                        raw = res.json()["choices"][0]["message"]["content"].strip()
                        if raw.startswith("```"):
                            lines = raw.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            raw = "\n".join(lines).strip()
                        return json.loads(raw)
                    elif res.status_code == 404:
                        continue
    except Exception as e:
        print(f"[AdvisoryService] LLM enhanced advisory error: {e}")

    return None
