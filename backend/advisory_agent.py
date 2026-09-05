import os
import re
import json
from typing import Dict, Any, Optional, List
import httpx
from dotenv import load_dotenv

from backend.models import (
    PersonaType,
    AdvisoryContent,
    DosageMetrics,
    WeatherTelemetry,
    PollutantBreakdown,
    PersonalizationRequest,
    ProfileEvaluationResponse,
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class AdvisoryAgent:
    @staticmethod
    async def generate_advisory(
        persona: PersonaType,
        aqi: int,
        pollutants: PollutantBreakdown,
        weather: WeatherTelemetry,
        dosage: DosageMetrics,
        city: str,
    ) -> AdvisoryContent:
        """Generates grounded bilingual medical advice with LLM or deterministic fallback."""
        if GROQ_API_KEY:
            llm_result = await AdvisoryAgent._call_groq(
                persona, aqi, pollutants, weather, dosage, city
            )
            if llm_result:
                return llm_result

        return AdvisoryAgent._deterministic_advisory(
            persona, aqi, pollutants, weather, dosage, city
        )

    @staticmethod
    async def _call_groq(
        persona: PersonaType,
        aqi: int,
        pollutants: PollutantBreakdown,
        weather: WeatherTelemetry,
        dosage: DosageMetrics,
        city: str,
    ) -> Optional[AdvisoryContent]:
        """Calls Groq for structured clinical doctor advice."""
        prompt = f"""
You are the patient's caring personal pulmonologist and respiratory physician in private practice.
Analyze their real-time telemetry:
- Location: {city}
- Persona: {persona.value} ({dosage.clinical_exertion_label})
- Ambient AQI: {aqi}, PM2.5: {pollutants.pm25} µg/m³
- Temperature: {weather.temperature_c}°C, Humidity: {weather.humidity_percent}%, Heat Index: {weather.heat_index_c}°C
- Biological Dose Inhaled Rate: {dosage.inhaled_rate_ug_per_min} µg/min
- Deposition Fraction (DF): {dosage.deposition_fraction}
- Safe Time Remaining: {dosage.safe_time_remaining_minutes} minutes

Output strict JSON with these keys:
1. "english": Warm, caring 2-sentence clinical guidance spoken directly to the patient ("As your doctor...", "I want you to...") explaining the physiological mechanism.
2. "hindi": Caring, respectful Hindi translation in family doctor tone ("आपके डॉक्टर के रूप में मेरी सलाह...").
3. "key_action": Single 3-5 word direct doctor command.
4. "n95_recommended": boolean.
5. "outdoor_allowed": boolean.
"""
        candidate_models = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.6-27b",
        ]
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                for model in candidate_models:
                    res = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a caring personal doctor and pulmonary specialist. Always return valid JSON only.",
                                },
                                {"role": "user", "content": prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.2,
                        },
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
                        parsed = json.loads(raw)
                        return AdvisoryContent(
                            english=parsed.get("english", ""),
                            hindi=parsed.get("hindi", ""),
                            key_action=parsed.get("key_action", "Protect Respiratory Tract"),
                            n95_recommended=bool(parsed.get("n95_recommended", True)),
                            outdoor_allowed=bool(parsed.get("outdoor_allowed", False)),
                        )
                    elif res.status_code == 404:
                        continue
        except Exception as e:
            print(f"[AdvisoryAgent] Groq API error: {e}")
        return None

    @staticmethod
    def _deterministic_advisory(
        persona: PersonaType,
        aqi: int,
        pollutants: PollutantBreakdown,
        weather: WeatherTelemetry,
        dosage: DosageMetrics,
        city: str,
    ) -> AdvisoryContent:
        rate = dosage.inhaled_rate_ug_per_min
        pm25 = pollutants.pm25

        if persona == PersonaType.ASTHMATIC:
            if aqi > 150 or pm25 > 60:
                en = (
                    f"Acute bronchial spasm alert: With a high lung deposition fraction of {dosage.deposition_fraction}, "
                    f"you are inhaling {rate} µg/min of fine particulates. Keep a rescue bronchodilator inhaler on hand and remain indoors."
                )
                hi = (
                    f"अस्थमा और फेफड़ों के लिए गंभीर चेतावनी: हवा में पीएम 2.5 का स्तर अत्यधिक होने से आपके फेफड़ों में प्रति मिनट {rate} माइक्रोग्राम कण जमा हो रहे हैं। "
                    "कृपया अपना इनहेलर पास रखें और बाहरी गतिविधियों से बचें।"
                )
                action = "Keep Inhaler Ready & Stay Indoors"
                n95 = True
                outdoor = False
            else:
                en = (
                    f"Moderate particulate load. Inhaling {rate} µg/min. Light outdoor activity is acceptable with protective masking."
                )
                hi = (
                    f"वायु गुणवत्ता मध्यम है। वर्तमान में आप {rate} माइक्रोग्राम प्रति मिनट साँस ले रहे हैं। सावधानी के साथ बाहर जा सकते हैं।"
                )
                action = "Mask Recommended Outdoors"
                n95 = False
                outdoor = True

        elif persona == PersonaType.RUNNER:
            if aqi > 120 or pm25 > 45:
                en = (
                    f"High aerobic minute ventilation (0.045 m³/min) causes severe toxic accumulation ({rate} µg/min). "
                    "Deep mouth-breathing bypasses nasal cilia; reschedule aerobic run to the early morning safe window."
                )
                hi = (
                    f"दौड़ने वाले एथलीटों के लिए चेतावनी: तेज सांस लेने से फेफड़ों में बहुत तेजी से ({rate} µg/min) जहरीले कण प्रवेश कर रहे हैं। "
                    "खुले में दौड़ने के बजाय सुबह के सुरक्षित समय का चयन करें या इनडोर वर्कआउट करें।"
                )
                action = "Postpone Outdoor Run"
                n95 = True
                outdoor = False
            else:
                en = (
                    f"Aerobic window open. Inhaling manageable particulate load ({rate} µg/min). Safe for morning workout."
                )
                hi = (
                    f"दौड़ने के लिए स्थिति संतोषजनक है। प्रति मिनट साँस दर {rate} माइक्रोग्राम है। सुबह की दौड़ जारी रख सकते हैं।"
                )
                action = "Safe for Outdoor Cardio"
                n95 = False
                outdoor = True

        elif persona == PersonaType.DELIVERY:
            if aqi > 150:
                en = (
                    f"Continuous road exposure: Traffic exhaust and ambient particulates produce an inhaled rate of {rate} µg/min. "
                    f"Daily safe threshold reached in {dosage.safe_time_remaining_minutes} mins. Sealed N95 respirator is strictly required."
                )
                hi = (
                    f"डिलीवरी राइडर्स के लिए सख्त निर्देश: सड़कों पर लगातार रहने से आपके फेफड़ों में {rate} µg/min जहरीले कण जा रहे हैं। "
                    "अपनी शिफ्ट के दौरान एयर-टाइट N95 मास्क अवश्य पहनें और पर्याप्त पानी पिएं।"
                )
                action = "N95 Respirator Mandatory"
                n95 = True
                outdoor = True
            else:
                en = (
                    f"Moderate transit exposure ({rate} µg/min). Standard dust filtration recommended on active vehicular routes."
                )
                hi = (
                    f"सड़क पर यातायात के दौरान मध्यम प्रदूषण है। वाहन चलाते समय मास्क का उपयोग करें।"
                )
                action = "Wear Protective Mask"
                n95 = False
                outdoor = True

        elif persona == PersonaType.SENIOR:
            if aqi > 130 or weather.heat_index_c > 35:
                en = (
                    f"Cardiopulmonary risk alert: Fine particles increase blood viscosity, compounded by {weather.heat_index_c}°C heat index. "
                    "Avoid outdoor walks during peak sun hours to prevent cardiovascular strain."
                )
                hi = (
                    f"वरिष्ठ नागरिकों के लिए विशेष सलाह: उच्च प्रदूषण और {weather.heat_index_c}°C तापमान से हृदय और रक्तचाप पर दबाव बढ़ता है। "
                    "दोपहर के समय बाहर टहलने से बचें और घर के अंदर रहें।"
                )
                action = "Rest Indoors in Clean Air"
                n95 = True
                outdoor = False
            else:
                en = (
                    f"Mild environmental conditions. Safe for leisurely garden walk. Stay hydrated."
                )
                hi = (
                    f"मौसम सामान्य है। पार्क में हल्की सैर के लिए सुरक्षित है। समय पर पानी पिएं।"
                )
                action = "Safe for Light Walk"
                n95 = False
                outdoor = True

        else:
            if aqi > 150:
                en = (
                    f"Unhealthy atmospheric stagnation across {city}. Inhaling {rate} µg/min. Limit unnecessary outdoor exposure."
                )
                hi = (
                    f"{city} में वायु गुणवत्ता अस्वस्थ है। प्रति मिनट {rate} माइक्रोग्राम कण फेफड़ों में जा रहे हैं। अनावश्यक रूप से बाहर निकलने से बचें।"
                )
                action = "Limit Outdoor Exposure"
                n95 = True
                outdoor = False
            else:
                en = (
                    f"Air quality in {city} is acceptable for normal daily routines ({rate} µg/min)."
                )
                hi = (
                    f"{city} में वायु गुणवत्ता सामान्य दैनिक गतिविधियों के लिए सुरक्षित है।"
                )
                action = "Normal Outdoor Routines"
                n95 = False
                outdoor = True

        return AdvisoryContent(
            english=en,
            hindi=hi,
            key_action=action,
            n95_recommended=n95,
            outdoor_allowed=outdoor,
        )

    @staticmethod
    async def evaluate_personalization_profile(
        req: PersonalizationRequest,
    ) -> ProfileEvaluationResponse:
        """Evaluates user personalization profile using free AI model or clinical matrix."""
        # Support free-form profile_text
        text = (req.profile_text or "").lower()
        occ = (req.occupation or "").lower()
        conditions = [c.lower() for c in req.health_conditions]
        commute = (req.commute_mode or "").lower()
        hours = req.outdoor_hours or 2.0
        aqi = req.current_aqi or 186
        pm25 = req.current_pm25 or 118.4

        # 1. Custom minute ventilation (Ve)
        if any(w in text or w in occ for w in ["runner", "athlete", "run", "jog", "cardio", "marathon"]):
            ve = 0.045
        elif any(w in text or w in occ for w in ["delivery", "construction", "courier", "rider", "bike", "scooter", "motorcycle", "driver", "field"]):
            ve = 0.024
        elif any(w in text or w in occ or w in commute for w in ["commuter", "metro", "bus", "walk"]):
            ve = 0.020
        elif any(w in text or w in occ for w in ["senior", "elderly", "retired", "old"]):
            ve = 0.012
        else:
            ve = 0.016

        # 2. Custom deposition fraction (DF)
        df = 0.40
        if any(w in text for w in ["asthma", "bronchitis", "wheez", "lung", "respiratory"]) or any("asthma" in c or "bronchitis" in c for c in conditions):
            df = max(df, 0.65)
        if any(w in text for w in ["heart", "cardio", "bp", "blood pressure", "hypertension"]) or any("cardio" in c or "heart" in c or "hypertension" in c for c in conditions):
            df = max(df, 0.55)
        if any(w in text for w in ["allerg", "sinus", "dust", "rhinitis"]) or any("allerg" in c for c in conditions):
            df = max(df, 0.52)
        if any(w in text for w in ["smok", "cigarette", "vape"]) or any("smok" in c for c in conditions):
            df = max(df, 0.58)
        if any(w in text for w in ["pregnan"]) or any("pregnan" in c for c in conditions):
            df = max(df, 0.55)

        # 3. Custom safe daily limit
        if df >= 0.60 or any(w in text or w in occ for w in ["senior", "elderly", "asthma"]):
            daily_limit = 20.0
        elif df >= 0.50:
            daily_limit = 28.0
        else:
            daily_limit = 45.0

        inhaled_rate = round(pm25 * ve * df, 2)
        safe_minutes = max(0, int((daily_limit / max(0.01, inhaled_rate))))

        # 4. Vulnerability Level
        if (df >= 0.60 or "heart" in text or any("cardio" in c for c in conditions)) and (hours >= 3 or aqi >= 150):
            vuln = "Critical"
        elif df >= 0.50 or hours >= 4 or aqi >= 140:
            vuln = "High"
        elif hours >= 2 or aqi >= 80:
            vuln = "Moderate"
        else:
            vuln = "Low"

        # Deterministic clinical evaluation baseline
        det_eval = AdvisoryAgent._deterministic_profile_eval(
            req, ve, df, daily_limit, inhaled_rate, safe_minutes, vuln
        )

        # Try Free AI API (Groq or Gemini) if key provided by user or in env
        active_key = req.user_api_key or GROQ_API_KEY or GEMINI_API_KEY
        if active_key:
            ai_eval = await AdvisoryAgent._call_ai_profile_eval(
                req, active_key, ve, df, daily_limit, inhaled_rate, safe_minutes, vuln, det_eval
            )
            if ai_eval:
                return ai_eval

        return det_eval

    @staticmethod
    def _clean_user_role(role: str) -> str:
        if not role or not isinstance(role, str):
            return "Active Individual"
        r = role.strip()
        patterns = [
            r"^i\s+am\s+an?\s+",
            r"^i'm\s+an?\s+",
            r"^i\s+am\s+",
            r"^i'm\s+",
            r"^working\s+as\s+an?\s+",
            r"^work\s+as\s+an?\s+",
            r"^job\s+is\s+an?\s+",
            r"^my\s+role\s+is\s+an?\s+",
            r"^my\s+job\s+is\s+an?\s+",
            r"^daily\s+work/routine:\s*",
        ]
        for pat in patterns:
            r = re.sub(pat, "", r, flags=re.IGNORECASE).strip()
        low = r.lower()
        if "gymrat" in low or "gym rat" in low or "gym-rat" in low or "bodybuilder" in low or "weightlifter" in low or "lifter" in low:
            return "Dedicated Gym-Goer / Lifter"
        if "coder" in low or "programmer" in low or "developer" in low:
            return "Software Engineer"
        if "biker" in low or (low == "rider"):
            return "Motorcycle Commuter"
        r = r.strip(".,;:!- ")
        if not r or len(r) < 3:
            return "Active Individual"
        return r.title()

    @staticmethod
    def _clean_clinical_eval(
        eval_text: str,
        fallback_eval: str,
        work_name: str,
        city_name: str,
        aqi_val: int,
    ) -> str:
        if not eval_text or not isinstance(eval_text, str) or len(eval_text.strip()) < 10:
            return fallback_eval

        text = eval_text.strip()
        clean_role = AdvisoryAgent._clean_user_role(work_name)
        expected_prefix = f"As your doctor, looking at your routine as a {clean_role} in {city_name} (AQI {aqi_val})"

        # Clean any clumsy "as a i am a" patterns
        text = re.sub(r"as\s+a\s+i\s+am\s+a\b", f"as a {clean_role}", text, flags=re.IGNORECASE)
        text = re.sub(r"as\s+a\s+i'm\s+a\b", f"as a {clean_role}", text, flags=re.IGNORECASE)

        # Ensure required opening phrase
        if not text.lower().startswith("as your doctor, looking at your routine as a"):
            if text.lower().startswith("as your doctor"):
                text = f"{expected_prefix}, " + text[len("as your doctor"):].lstrip(",.:; ")
            else:
                text = f"{expected_prefix}, {text}"

        # Keep maximum 2 sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if len(sentences) > 2:
            text = " ".join(sentences[:2])

        # Gracefully trim if extremely long, but NEVER discard AI output
        words = text.split()
        if len(words) > 42:
            text = " ".join(words[:42]).rstrip(",;:-") + "."

        return text

    @staticmethod
    def _clean_short_sentence(
        text: str,
        fallback_text: str,
        prefix: str = "",
        max_words: int = 22,
    ) -> str:
        if not text or not isinstance(text, str) or len(text.strip()) < 5:
            return fallback_text
        text = text.strip()
        if prefix and not text.lower().startswith(prefix.lower()):
            text = f"{prefix} {text}"
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if sentences:
            text = sentences[0]
        # Gracefully trim rather than discarding to fallback
        words = text.split()
        if len(words) > max_words + 10:
            text = " ".join(words[:max_words + 10]).rstrip(",;:-") + "."
        return text

    @staticmethod
    def _normalize_steps(
        raw_tips: Any,
        fallback_tips: List[str],
    ) -> List[str]:
        if isinstance(raw_tips, str):
            raw_tips = [line.strip() for line in raw_tips.splitlines() if line.strip()]
        elif not isinstance(raw_tips, list):
            raw_tips = []

        result = []
        for i in range(1, 5):
            tip_text = ""
            if raw_tips and len(raw_tips) >= i and str(raw_tips[i - 1]).strip():
                tip_text = str(raw_tips[i - 1]).strip()
            elif fallback_tips and len(fallback_tips) >= i:
                tip_text = str(fallback_tips[i - 1]).strip()

            # Clean any leading Step / index prefix
            m = re.match(r"^(?:Step\s*\d+[\s:.\-—]+|\d+[\s:.\-—]+)?(.*)$", tip_text, re.IGNORECASE)
            cleaned = m.group(1).strip() if m else tip_text

            title = ""
            action = ""
            if "—" in cleaned:
                parts = cleaned.split("—", 1)
                title, action = parts[0].strip(), parts[1].strip()
            elif ":" in cleaned:
                parts = cleaned.split(":", 1)
                title, action = parts[0].strip(), parts[1].strip()
            elif " - " in cleaned:
                parts = cleaned.split(" - ", 1)
                title, action = parts[0].strip(), parts[1].strip()
            else:
                fb_parts = fallback_tips[i - 1].split("—", 1) if fallback_tips and len(fallback_tips) >= i and "—" in fallback_tips[i - 1] else []
                if fb_parts:
                    fb_title = fb_parts[0].replace(f"Step {i}:", "").strip(" []")
                    title, action = fb_title, cleaned
                else:
                    title, action = "Action", cleaned

            title = title.strip(" []")
            action = action.strip()
            act_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', action) if s.strip()]
            if act_sentences:
                action = act_sentences[0]

            act_words = action.split()
            if len(act_words) > 22:
                action = " ".join(act_words[:22]).rstrip(",;:-") + "."

            result.append(f"Step {i}: {title} — {action}")
        return result

    @staticmethod
    def _build_profile_response(
        req: PersonalizationRequest,
        raw_dict: Dict[str, Any],
        det_eval: ProfileEvaluationResponse,
        work_name: str,
        city_name: str,
        aqi_val: int,
        ve: float,
        df: float,
        daily_limit: float,
        inhaled_rate: float,
        safe_minutes: int,
        vuln: str,
    ) -> ProfileEvaluationResponse:
        summary = raw_dict.get("profile_summary", det_eval.profile_summary)
        vuln_level = raw_dict.get("vulnerability_level", vuln)

        # 1. clinical_evaluation: max 2 sentences, under 35 words, starting with required opening
        clinical_eval = AdvisoryAgent._clean_clinical_eval(
            raw_dict.get("clinical_evaluation", ""),
            det_eval.clinical_evaluation,
            work_name,
            city_name,
            aqi_val,
        )

        # 2. hindi_evaluation: 1-2 caring sentences
        hindi_eval = raw_dict.get("hindi_evaluation", "")
        if not hindi_eval or not isinstance(hindi_eval, str) or len(hindi_eval.strip()) < 5:
            hindi_eval = det_eval.hindi_evaluation
        else:
            h_sentences = [s.strip() for s in re.split(r'(?<=[।!?])\s+', hindi_eval.strip()) if s.strip()]
            if len(h_sentences) > 2:
                hindi_eval = " ".join(h_sentences[:2])

        # 3. personalized_tips: exactly 4 items formatted as "Step X: [Title] — [Action]"
        raw_tips = raw_dict.get("personalized_tips", [])
        tips = AdvisoryAgent._normalize_steps(raw_tips, det_eval.personalized_tips)

        # 4. protective_gear_recommendation: 1 concise sentence (<20 words)
        gear = AdvisoryAgent._clean_short_sentence(
            raw_dict.get("protective_gear_recommendation", ""),
            det_eval.protective_gear_recommendation,
            prefix="My prescription:",
            max_words=20,
        )

        # 5. commute_advisory: 1 concise sentence (<20 words)
        commute_adv = AdvisoryAgent._clean_short_sentence(
            raw_dict.get("commute_advisory", ""),
            det_eval.commute_advisory,
            max_words=20,
        )

        # 6. indoor_air_advice: 1 concise sentence (<20 words)
        indoor = AdvisoryAgent._clean_short_sentence(
            raw_dict.get("indoor_air_advice", ""),
            det_eval.indoor_air_advice,
            max_words=20,
        )

        return ProfileEvaluationResponse(
            profile_summary=summary,
            vulnerability_level=vuln_level,
            custom_minute_ventilation=ve,
            custom_deposition_fraction=df,
            custom_daily_limit_ug=daily_limit,
            inhaled_rate_ug_min=inhaled_rate,
            safe_outdoor_minutes_today=safe_minutes,
            clinical_evaluation=clinical_eval,
            hindi_evaluation=hindi_eval,
            personalized_tips=tips,
            protective_gear_recommendation=gear,
            indoor_air_advice=indoor,
            commute_advisory=commute_adv,
        )

    @staticmethod
    async def _call_ai_profile_eval(
        req: PersonalizationRequest,
        api_key: str,
        ve: float,
        df: float,
        daily_limit: float,
        inhaled_rate: float,
        safe_minutes: int,
        vuln: str,
        det_eval: ProfileEvaluationResponse,
    ) -> Optional[ProfileEvaluationResponse]:
        """Calls Groq or Google Gemini with Doctor Persona for personalized concise clinical evaluation."""
        text = (req.profile_text or "").lower()
        occ = (req.occupation or "").lower()
        conditions = [c.lower() for c in req.health_conditions]
        commute = (req.commute_mode or "").lower()

        is_delivery = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["delivery", "courier", "rider", "swiggy", "zomato"])
        is_runner = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["runner", "athlete", "running", "jog", "cardio", "marathon"])
        is_gym = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["gym", "lift", "lifter", "workout", "fitness", "bodybuilding", "weights", "strength", "crossfit", "gymrat", "gym rat"])
        is_senior = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["senior", "elderly", "retired", "old age", "70 years", "65 years", "grandparent"])
        is_2wheeler = any(re.search(rf"\b{re.escape(w)}\b", commute) or re.search(rf"\b{re.escape(w)}\b", text) for w in ["motorcycle", "bike", "scooter", "motorbike", "2-wheeler", "two-wheeler"])

        raw_occ = req.occupation.strip() if req.occupation and req.occupation not in ("General", "Active Professional") else None
        work_name = AdvisoryAgent._clean_user_role(raw_occ) if raw_occ else None
        if not work_name or work_name == "Active Individual":
            if req.profile_text:
                m_role = re.search(r"(?:work as an?|working as an?|i am an?|occupation:\s*|role:\s*|job:\s*|daily work/routine:\s*)([a-zA-Z\s\-]{3,30}?)(?:\s+(?:in|at|for|commute|outdoors|with)|[,.\n]|$)", req.profile_text, re.IGNORECASE)
                if m_role:
                    work_name = AdvisoryAgent._clean_user_role(m_role.group(1))
        if not work_name or work_name == "Active Individual":
            work_name = (
                "Dedicated Gym-Goer / Lifter" if is_gym else (
                    "Delivery Rider" if is_delivery else (
                        "Runner / Athlete" if is_runner else (
                            "Retired Senior" if is_senior else "Active Individual"
                        )
                    )
                )
            )
        city_name = req.city or "your city"
        aqi_val = req.current_aqi or 186

        routine_parts = []
        if req.profile_text:
            routine_parts.append(req.profile_text.strip())
        if req.occupation and req.occupation != "General" and req.occupation.lower() not in (req.profile_text or "").lower():
            routine_parts.append(f"Work/Role: {work_name}")
        if req.outdoor_hours and str(req.outdoor_hours) not in (req.profile_text or ""):
            routine_parts.append(f"Outdoor exposure: ~{req.outdoor_hours:g} hours/day")
        if req.commute_mode and req.commute_mode != "Commuter" and req.commute_mode.lower() not in (req.profile_text or "").lower():
            routine_parts.append(f"Commute mode: {req.commute_mode}")
        if req.health_conditions and any(c.lower() not in (req.profile_text or "").lower() for c in req.health_conditions):
            routine_parts.append(f"Health conditions/allergies: {', '.join(req.health_conditions)}")

        user_details = " | ".join(routine_parts) if routine_parts else (
            req.profile_text or f"Work: {work_name}, Commute: {req.commute_mode}, Outdoor: {req.outdoor_hours} hrs, Conditions: {', '.join(req.health_conditions)}"
        )

        system_prompt = f"""You are the patient's dedicated personal physician, sports pulmonologist, and environmental clinical specialist.
Provide concise, warm, caring medical advice formatted as 4 CONCISE, HIGHLY SPECIALIZED ACTIONABLE STEPS tailored strictly to the person's specific routine, occupation, and health context.

CRITICAL ANTI-GENERIC DIRECTIVE:
NEVER give generic, repetitive public health clichés like:
- "wear an N95 mask" or "wear a mask during commute" (unless specifying exact sport or industrial valved models with clinical rationale)
- "run a HEPA purifier in bedroom" or "keep windows closed"
- "perform a saline nasal rinse twice daily"
- "drink plenty of water / stay hydrated"
The patient is consulting YOU for DEEP, CLINICAL SPECIALIZATION tailored to their exact activities:
- If the patient is into gym, lifting, bodybuilding, running, or fitness:
  * Address heavy mouth-breathing minute ventilation (jumping from 7 L/min to 60+ L/min) during heavy compound lifts, driving soot into the alveoli.
  * Counter pollution's blunting of endothelial nitric oxide (NO) synthase and muscle pumps (e.g. dietary nitrates/citrulline pre-workout).
  * Advise extending inter-set rest periods (3+ min) so exercise hyperpnea subsides before the next set.
  * Gym micro-environment positioning (away from open street shutters and high-traffic doors; near filtered HVAC).
  * Post-workout cellular antioxidant replenishment: oral N-acetylcysteine (NAC 600mg) and Vitamin C to restore lung glutathione reserves.
- If the patient is a delivery rider, cyclist, or two-wheeler commuter:
  * Address helmet airflow, road-level diesel exhaust plume buffering at red lights, sweat/moisture management under respirators, and corneal particulate wash.
- If the patient is an office worker, student, or programmer:
  * Address indoor CO2 vs PM2.5 infiltration trade-offs, avoiding midday walks during photochemical smog peaks, desktop air delivery, screen eye strain exacerbation.
- If the patient has asthma or respiratory sensitivities:
  * Address pre-exposure preventative bronchodilator timing, cold-air smog bronchospasm triggers, airway warming, and mucus thinning.
- If the patient has eye/throat irritation or allergies:
  * Address lipid-based artificial tears, soothing pharyngeal rinses, and immediate post-transit clothing/decontamination routines.

STRICT CLINICAL RULES FOR JSON OUTPUT:
1. "clinical_evaluation":
   - MUST BE SHORT: maximum 2 sentences, strictly under 40 words total!
   - MUST open with: "As your doctor, looking at your routine as a {work_name} in {city_name} (AQI {aqi_val})..."
   - State the primary physiological goal concisely without generic clichés.
2. "hindi_evaluation":
   - MUST BE SHORT: 1-2 caring, respectful sentences in fluent Hindi (Devanagari script).
3. "personalized_tips":
   - EXACTLY 4 concise, numbered actionable steps:
     "Step 1: [Specialized Title] — [1-sentence highly specific action, 10-22 words]"
     "Step 2: [Specialized Title] — [1-sentence highly specific action, 10-22 words]"
     "Step 3: [Specialized Title] — [1-sentence highly specific action, 10-22 words]"
     "Step 4: [Specialized Title] — [1-sentence highly specific action, 10-22 words]"
   - Every single step MUST be hyper-tailored to their specific activity, commute, and symptoms! No generic boilerplates.
4. "protective_gear_recommendation":
   - 1 concise sentence (<22 words) with specific gear for their exact activity (e.g. valved sport respirator, wrap-around eyewear). Must start with "My prescription: ".
5. "commute_advisory":
   - 1 concise tactical sentence (<22 words) for their specific transit mode.
6. "indoor_air_advice":
   - 1 concise sentence (<22 words) for indoor recovery.
7. "profile_summary":
   - Short clinical title, e.g. "Dr. Care Plan: {work_name} - Health & Performance Shield".
8. "vulnerability_level":
   - "{vuln}" (or "Low", "Moderate", "High", "Critical").

Respond ONLY with valid JSON matching this schema:
{{
  "profile_summary": "string",
  "vulnerability_level": "string",
  "clinical_evaluation": "string",
  "hindi_evaluation": "string",
  "personalized_tips": ["string", "string", "string", "string"],
  "protective_gear_recommendation": "string",
  "indoor_air_advice": "string",
  "commute_advisory": "string"
}}"""

        user_prompt = f"""Patient Consultation File:
- Patient Work / Role: {work_name}
- City & AQI: {city_name} (AQI: {aqi_val}, PM2.5: {req.current_pm25} µg/m³)
- Daily Outdoor Exposure: {req.outdoor_hours} hours/day
- Commute Mode: {req.commute_mode}
- Pre-existing Health Conditions & Symptoms: {', '.join(req.health_conditions) if req.health_conditions else 'None specified'}
- Personal Routine Notes: "{user_details}"
- Inhalation Rate: {inhaled_rate} µg/min, Lung Deposition Fraction: {df}, Assessed Vulnerability: {vuln}

Doctor, provide your concise clinical evaluation and 4 hyper-specialized actionable steps in strict JSON.
CRITICAL CONSTRAINTS:
1. clinical_evaluation: MUST BE SHORT (maximum 2 sentences, under 40 words!), opening: "As your doctor, looking at your routine as a {work_name} in {city_name} (AQI {aqi_val})..."
2. hindi_evaluation: 1-2 caring sentences in Hindi.
3. personalized_tips: EXACTLY 4 concise actionable steps:
   "Step 1: [Title] — [Concise 1-sentence action, 10-22 words]"
   "Step 2: [Title] — [Concise 1-sentence action, 10-22 words]"
   "Step 3: [Title] — [Concise 1-sentence action, 10-22 words]"
   "Step 4: [Title] — [Concise 1-sentence action, 10-22 words]"
   Zero generic advice. Strictly tailor each step to their specific activity, commute, and health!
4. protective_gear_recommendation & commute_advisory: 1 concise sentence (<22 words) each."""

        try:
            # Check if Gemini key
            if api_key.startswith("AIza"):
                gemini_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
                body = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"parts": [{"text": user_prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
                }
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for g_model in gemini_models:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{g_model}:generateContent?key={api_key}"
                        res = await client.post(url, json=body)
                        if res.status_code == 200:
                            data = res.json()
                            text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
                            d = json.loads(text_resp)
                            return AdvisoryAgent._build_profile_response(
                                req=req,
                                raw_dict=d,
                                det_eval=det_eval,
                                work_name=work_name,
                                city_name=city_name,
                                aqi_val=aqi_val,
                                ve=ve,
                                df=df,
                                daily_limit=daily_limit,
                                inhaled_rate=inhaled_rate,
                                safe_minutes=safe_minutes,
                                vuln=vuln,
                            )
                        elif res.status_code == 404:
                            continue
            else:
                # Groq API with fast candidate models
                candidate_models = [
                    "openai/gpt-oss-120b",
                    "openai/gpt-oss-20b",
                    "qwen/qwen3.6-27b",
                ]
                async with httpx.AsyncClient(timeout=8.0) as client:
                    for model in candidate_models:
                        res = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}"},
                            json={
                                "model": model,
                                "messages": [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt},
                                ],
                                "response_format": {"type": "json_object"},
                                "temperature": 0.2,
                            },
                        )
                        if res.status_code == 200:
                            content = res.json()["choices"][0]["message"]["content"].strip()
                            if content.startswith("```"):
                                lines = content.splitlines()
                                if lines[0].startswith("```"):
                                    lines = lines[1:]
                                if lines and lines[-1].startswith("```"):
                                    lines = lines[:-1]
                                content = "\n".join(lines).strip()
                            d = json.loads(content)
                            return AdvisoryAgent._build_profile_response(
                                req=req,
                                raw_dict=d,
                                det_eval=det_eval,
                                work_name=work_name,
                                city_name=city_name,
                                aqi_val=aqi_val,
                                ve=ve,
                                df=df,
                                daily_limit=daily_limit,
                                inhaled_rate=inhaled_rate,
                                safe_minutes=safe_minutes,
                                vuln=vuln,
                            )
                        elif res.status_code == 404:
                            continue
        except Exception as e:
            print(f"[AdvisoryAgent] AI profile evaluation exception: {e}")
        return None

    @staticmethod
    def _deterministic_profile_eval(
        req: PersonalizationRequest,
        ve: float,
        df: float,
        daily_limit: float,
        inhaled_rate: float,
        safe_minutes: int,
        vuln: str,
    ) -> ProfileEvaluationResponse:
        """Physician-grounded evaluation matrix for offline/zero-API execution."""
        text = (req.profile_text or "").lower()
        occ = (req.occupation or "").lower()
        conditions = [c.lower() for c in req.health_conditions]
        commute = (req.commute_mode or "").lower()

        has_asthma = any(w in text for w in ["asthma", "bronchitis", "wheez", "tight in the chest", "tightness in chest"]) or any("asthma" in c or "bronchitis" in c for c in conditions)
        has_heart = any(w in text for w in ["heart", "cardio", "bp", "blood pressure", "hypertension", "arrhythmia"]) or any("cardio" in c or "heart" in c or "hypertension" in c or "arrhythmia" in c for c in conditions)
        has_allergies = any(w in text for w in ["allerg", "dust", "pollen", "sinus", "rhinitis", "sneeze", "itch"]) or any("allerg" in c for c in conditions)
        has_eye_issues = any(w in text for w in ["eye", "sting", "burn", "tear", "watery"])
        has_throat_cough = any(w in text for w in ["throat", "cough", "phlegm", "irritat"])
        is_delivery = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["delivery", "courier", "rider", "swiggy", "zomato"])
        is_runner = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["runner", "athlete", "running", "jog", "cardio", "marathon"])
        is_gym = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["gym", "lift", "lifter", "workout", "fitness", "bodybuilding", "weights", "strength", "crossfit", "gymrat", "gym rat"])
        is_senior = any(re.search(rf"\b{re.escape(w)}\b", text) or re.search(rf"\b{re.escape(w)}\b", occ) for w in ["senior", "elderly", "retired", "old age", "70 years", "65 years", "grandparent"])
        is_2wheeler = any(re.search(rf"\b{re.escape(w)}\b", commute) or re.search(rf"\b{re.escape(w)}\b", text) for w in ["motorcycle", "bike", "scooter", "motorbike", "2-wheeler", "two-wheeler"])

        # Work / Routine description
        raw_occ = req.occupation.strip() if req.occupation and req.occupation not in ("General", "Active Professional") else None
        work_desc = AdvisoryAgent._clean_user_role(raw_occ) if raw_occ else None
        if not work_desc or work_desc == "Active Individual":
            if req.profile_text:
                m_role = re.search(r"(?:work as an?|working as an?|i am an?|occupation:\s*|role:\s*|job:\s*|daily work/routine:\s*)([a-zA-Z\s\-]{3,30}?)(?:\s+(?:in|at|for|commute|outdoors|with)|[,.\n]|$)", req.profile_text, re.IGNORECASE)
                if m_role:
                    work_desc = AdvisoryAgent._clean_user_role(m_role.group(1))
        if not work_desc or work_desc == "Active Individual":
            work_desc = (
                "Dedicated Gym-Goer / Lifter" if is_gym else (
                    "Delivery Rider" if is_delivery else (
                        "Runner / Athlete" if is_runner else (
                            "Retired Senior" if is_senior else "Active Individual"
                        )
                    )
                )
            )
        city = req.city or "your city"
        aqi = req.current_aqi or 186
        hours_str = f"{req.outdoor_hours:g} hours" if req.outdoor_hours else "daily hours"

        # Title
        profile_title = f"Dr. Care Plan: {req.profile_name} (Personal Health Shield)" if req.profile_name and req.profile_name != "My Profile" else f"Dr. Care Plan: {work_desc} Health Shield"

        # 1. Clinical Evaluation (English, max 2 sentences, strictly under 40 words!)
        if has_asthma:
            eval_en = (
                f"As your doctor, looking at your routine as a {work_desc} in {city} (AQI {aqi}), "
                "our clinical priority is preventing airway constriction. "
                "Keep your rescue inhaler handy and limit exertion."
            )
            eval_hi = (
                f"आपके डॉक्टर के रूप में सलाह है कि {city} में AQI {aqi} के दौरान फेफड़ों की सुरक्षा जरूरी है। "
                "अपना इनहेलर पास रखें और बाहर N95 मास्क अवश्य पहनें।"
            )
        elif is_gym:
            eval_en = (
                f"As your doctor, looking at your routine as a {work_desc} in {city} (AQI {aqi}), "
                "our clinical goal is protecting alveoli from high-ventilation particulate intake and preserving nitric oxide for recovery."
            )
            eval_hi = (
                f"आपके डॉक्टर के रूप में सलाह है कि {city} में AQI {aqi} के दौरान भारी वर्कआउट में फेफड़ों और मांसपेशियों की रिकवरी का ध्यान रखें।"
            )
        elif has_heart or is_senior:
            eval_en = (
                f"As your doctor, looking at your routine as a {work_desc} in {city} (AQI {aqi}), "
                "our clinical goal is preventing cardiovascular strain. "
                "Limit outdoor walks and rest immediately if fatigued."
            )
            eval_hi = (
                f"आपके डॉक्टर के रूप में सलाह है कि {city} में AQI {aqi} के दौरान दिल पर दबाव न पड़ने दें। "
                "दोपहर में बाहर निकलने से बचें और घर पर पर्याप्त आराम करें।"
            )
        elif is_runner:
            eval_en = (
                f"As your doctor, looking at your routine as a {work_desc} in {city} (AQI {aqi}), "
                "our clinical goal is avoiding deep particulate deposition. "
                "Shift cardio workouts indoors until air clears."
            )
            eval_hi = (
                f"आपके डॉक्टर के रूप में सलाह है कि {city} में AQI {aqi} के दौरान खुले में तेज दौड़ने से बचें। "
                "फेफड़ों की सुरक्षा के लिए सुबह जल्दी या इनडोर वर्कआउट को प्राथमिकता दें।"
            )
        else:
            eval_en = (
                f"As your doctor, looking at your routine as a {work_desc} in {city} (AQI {aqi}), "
                "our clinical goal is minimizing toxic soot intake. "
                "Wear certified barrier protection during all outdoor travel."
            )
            eval_hi = (
                f"आपके डॉक्टर के रूप में सलाह है कि {city} में AQI {aqi} को देखते हुए बाहर निकलते समय N95 मास्क जरूर पहनें। "
                "जहरीले धुएं से फेफड़ों का बचाव आज सबसे जरूरी है।"
            )

        # 2. Exactly 4 concise actionable steps ("Step X: [Title] — [Action, 10-22 words max]")
        candidate_steps = []

        # Gym-specific steps first if gymrat / lifter
        if is_gym:
            candidate_steps.append(("Ventilation Pacing", "Extend inter-set rest to 3 minutes on heavy compound lifts to allow exercise hyperpnea to settle."))
            candidate_steps.append(("Nitric Oxide Defense", "Consume dietary citrulline or beetroot pre-workout to counter pollutant-mediated endothelial vasoconstriction."))
            candidate_steps.append(("Gym Micro-Zoning", "Train in interior free-weight areas away from open street shutters to avoid vehicular exhaust."))
            candidate_steps.append(("Glutathione Recovery", "Take 600 mg N-acetylcysteine (NAC) and Vitamin C post-workout to quench lung oxidative stress."))

        # Symptom-specific steps
        if has_eye_issues:
            candidate_steps.append(("Ocular Relief", "Rinse stinging eyes with preservative-free artificial tears every 90 minutes to wash out acidic exhaust."))
        if has_asthma:
            candidate_steps.append(("Bronchial Pre-treatment", "Take two preventative puffs of your prescribed rescue inhaler 15 minutes before venturing outdoors."))
        if has_heart:
            candidate_steps.append(("Cardiac Pacing", "Keep physical exertion light and monitor your resting pulse immediately after outdoor transit."))
        if has_throat_cough or has_allergies:
            candidate_steps.append(("Airway Clearance", "Perform a sterile saline nasal wash immediately after returning indoors to flush trapped allergens."))
        if has_throat_cough:
            candidate_steps.append(("Throat Soothing", "Sip warm water with honey indoors to soothe airway irritation and calm dry coughs."))

        # Work / Commute / Routine specific steps
        if is_delivery or is_2wheeler:
            candidate_steps.append(("Traffic Buffering", "Pull back 5 meters from diesel exhaust pipes while stopped at congested traffic intersections."))
            candidate_steps.append(("Barrier Defense", f"Wear a sealed N95 respirator under your helmet during your {hours_str} delivery shift."))
        elif is_runner:
            candidate_steps.append(("Workout Timing", "Shift your cardio training to 6:00 AM before ground vehicular soot and ozone build up."))
            candidate_steps.append(("Indoor Substitution", f"Move cardio workouts to an indoor treadmill whenever ambient AQI in {city} exceeds 150."))
        elif is_senior:
            candidate_steps.append(("Route Relocation", "Walk along interior park pathways set back at least 20 meters from perimeter roads."))
            candidate_steps.append(("Walk Duration", "Limit your evening walk to 25 minutes today to avoid cumulative cardiovascular particulate stress."))

        if "metro" in commute:
            candidate_steps.append(("Platform Shielding", "Keep your N95 respirator firmly sealed while waiting on underground subway transit platforms."))
        elif "car" in commute:
            candidate_steps.append(("Cabin Recirculation", "Set vehicle air conditioning to internal recirculation mode to block external exhaust fumes."))

        # Fallback candidate steps to ensure at least 4 unique steps
        candidate_steps.append(("Barrier Defense", "Wear a certified N95 respirator covering your nose and mouth whenever travelling outdoors."))
        candidate_steps.append(("Bedroom Recovery", "Run a True-HEPA purifier overnight to allow your airways to heal in clean air."))
        candidate_steps.append(("Hydration Defense", "Drink at least 2.5 liters of clean water daily to help your mucous membranes clear pollutants."))
        candidate_steps.append(("Exposure Spacing", f"Limit continuous outdoor sessions to under 30 minutes during peak smog hours in {city}."))

        # Deduplicate preserving order
        seen_titles = set()
        unique_steps = []
        for title, action in candidate_steps:
            if title not in seen_titles:
                seen_titles.add(title)
                unique_steps.append((title, action))

        tips = [f"Step {i}: {title} — {action}" for i, (title, action) in enumerate(unique_steps[:4], 1)]

        # 3. Doctor's Gear Prescription (<20 words)
        if is_delivery or is_2wheeler:
            gear = f"My prescription: Wear a snug N95 respirator with a cool-flow valve under your helmet during your {hours_str} shift."
        elif is_runner:
            gear = "My prescription: Wear a lightweight sports N95 mask or shift workouts to indoor filtered spaces."
        elif has_heart or is_senior:
            gear = "My prescription: Wear an easy-breathing certified N95 respirator during your entire evening walk."
        elif has_asthma or has_allergies:
            gear = "My prescription: Wear a tightly sealed N95 respirator with an adjustable nose clip outdoors."
        else:
            gear = "My prescription: Wear a certified N95 respirator whenever venturing outdoors in high pollution."

        # 4. Doctor's Commute Note (<20 words)
        if is_delivery or is_2wheeler:
            commute_adv = "Stay back at least 5 meters from diesel exhaust pipes at congested traffic signals."
        elif is_runner:
            commute_adv = "Choose interior park tracks away from high-traffic ring roads during morning exercise."
        elif "metro" in commute:
            commute_adv = "Keep your N95 respirator sealed while waiting on underground subway transit platforms."
        elif "car" in commute:
            commute_adv = "Set car ventilation to internal recirculation and keep all windows tightly rolled up."
        elif is_senior or "walk" in commute:
            commute_adv = "Walk along inner park pathways away from congested perimeter roads to reduce soot inhalation."
        else:
            commute_adv = "Choose pedestrian paths set back from main roads to avoid heavy vehicular exhaust plumes."

        # 5. Doctor's Indoor Air Advice (<20 words)
        indoor = "Run a True-HEPA purifier in your bedroom to keep PM2.5 below 10 µg/m³ while sleeping."

        return ProfileEvaluationResponse(
            profile_summary=profile_title,
            vulnerability_level=vuln,
            custom_minute_ventilation=ve,
            custom_deposition_fraction=df,
            custom_daily_limit_ug=daily_limit,
            inhaled_rate_ug_min=inhaled_rate,
            safe_outdoor_minutes_today=safe_minutes,
            clinical_evaluation=eval_en,
            hindi_evaluation=eval_hi,
            personalized_tips=tips,
            protective_gear_recommendation=gear,
            indoor_air_advice=indoor,
            commute_advisory=commute_adv,
        )
