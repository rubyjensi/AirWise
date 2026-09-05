"""
Clinical Verification Script for AirWise Doctor Persona
Evaluates multiple patient profiles through AdvisoryAgent.evaluate_personalization_profile
to verify tone, personalization, and clinical grounding.
"""

import asyncio
from backend.models import PersonalizationRequest
from backend.advisory_agent import AdvisoryAgent

async def run_evaluations():
    test_profiles = [
        PersonalizationRequest(
            profile_name="Rohan (Food Delivery)",
            occupation="Delivery Rider",
            health_conditions=["Asthma / Chronic Bronchitis"],
            outdoor_hours=6.0,
            commute_mode="Motorcycle / Scooter",
            profile_text="I do food delivery 6 hours daily on my motorbike. My eyes sting and burn from vehicle exhaust, and I get wheezy and tight in the chest in the evening around heavy traffic.",
            current_aqi=248,
            current_pm25=162.5,
            city="Connaught Place, New Delhi",
        ),
        PersonalizationRequest(
            profile_name="Priya (Marathon Runner)",
            occupation="Runner / Athlete",
            health_conditions=["Seasonal Dust / Pollen Allergies"],
            outdoor_hours=1.5,
            commute_mode="Active Running / Jogging",
            profile_text="I train for half-marathons with morning 10km outdoor runs. My throat gets itchy and I have dry cough and sneezing fits afterwards when running along ring roads.",
            current_aqi=175,
            current_pm25=95.0,
            city="Bengaluru, Karnataka",
        ),
        PersonalizationRequest(
            profile_name="Mr. Kapoor (Senior Citizen)",
            occupation="Retired Senior",
            health_conditions=["Hypertension / High BP", "Mild Arrhythmia"],
            outdoor_hours=1.0,
            commute_mode="Walking",
            profile_text="I am 70 years old with high blood pressure. I take a 45-minute evening walk in the colony park. On smoggy evenings I feel pressure in my chest and get fatigued quickly.",
            current_aqi=280,
            current_pm25=190.0,
            city="Noida, Sector 62",
        ),
    ]

    print("=" * 80)
    print("AIRWISE DOCTOR PERSONA & CLINICAL EVALUATION TEST")
    print("=" * 80)

    for p in test_profiles:
        print(f"\nEvaluating Profile: {p.profile_name} in {p.city} (AQI: {p.current_aqi})")
        res = await AdvisoryAgent.evaluate_personalization_profile(p)
        print("-" * 60)
        print(f"Summary Title: {res.profile_summary}")
        print(f"Risk Tier: {res.vulnerability_level}")
        print(f"Safe Minutes Today: {res.safe_outdoor_minutes_today} mins | Inhaled Rate: {res.inhaled_rate_ug_min} ug/min")
        print(f"\n[Doctor's Clinical Evaluation]:\n{res.clinical_evaluation}")
        print(f"\n[Doctor's Hindi Advisory]:\n{res.hindi_evaluation}")
        print("\n[Doctor's 4 Prescription Tips (Steps)]:")
        for i, tip in enumerate(res.personalized_tips, 1):
            if tip.startswith("Step"):
                print(f"  {tip}")
            else:
                print(f"  {i}. {tip}")
        print(f"\n[Doctor's Gear Prescription]:\n  {res.protective_gear_recommendation}")
        print(f"\n[Doctor's Commute Note]:\n  {res.commute_advisory}")
        print(f"\n[Doctor's Indoor Guidance]:\n  {res.indoor_air_advice}")
        print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run_evaluations())
