import pytest
from backend.models import PersonaType
from backend.clinical_engine import (
    compute_inhalation_dosage,
    evaluate_compound_stressors,
    calculate_aqi_from_pm25,
    calculate_heat_index,
    compute_route_exposure,
    PERSONA_PARAMETERS,
)


def test_minute_ventilation_and_deposition_fractions():
    # Runner minute ventilation should be 0.045
    assert PERSONA_PARAMETERS[PersonaType.RUNNER]["minute_ventilation"] == 0.045
    # Asthmatic deposition fraction should be 0.65
    assert PERSONA_PARAMETERS[PersonaType.ASTHMATIC]["deposition_fraction"] == 0.65
    # General baseline minute ventilation 0.018, DF 0.40
    assert PERSONA_PARAMETERS[PersonaType.GENERAL]["minute_ventilation"] == 0.018
    assert PERSONA_PARAMETERS[PersonaType.GENERAL]["deposition_fraction"] == 0.40


def test_dosage_calculation():
    pm25 = 100.0
    dosage_asthmatic = compute_inhalation_dosage(pm25, PersonaType.ASTHMATIC, 20)
    expected_rate = round(100.0 * 0.016 * 0.65, 2)
    assert dosage_asthmatic.inhaled_rate_ug_per_min == expected_rate
    assert dosage_asthmatic.current_session_dose_ug == round(expected_rate * 20, 1)


def test_heat_index_calculation():
    hi = calculate_heat_index(32.0, 70.0)
    assert hi > 35.0  # Heat index is amplified by high relative humidity


def test_compound_stressors_cardiovascular():
    alerts = evaluate_compound_stressors(
        pm25=120.0,
        temp_c=36.0,
        humidity=65.0,
        heat_index_c=42.0,
        persona=PersonaType.SENIOR,
    )
    assert any(a.type == "cardiovascular" for a in alerts)


def test_route_exposure_comparison():
    routes = compute_route_exposure(100.0, PersonaType.GENERAL)
    assert len(routes) == 2
    highway = next(r for r in routes if r.route_type == "highway")
    green = next(r for r in routes if r.route_type == "green")
    assert green.total_dose_ug < highway.total_dose_ug
    assert green.saving_percent > 40.0


@pytest.mark.anyio
async def test_personalization_profile_evaluation():
    from backend.models import PersonalizationRequest
    from backend.advisory_agent import AdvisoryAgent

    req = PersonalizationRequest(
        occupation="Delivery Rider",
        health_conditions=["Asthma / Chronic Bronchitis"],
        outdoor_hours=6.0,
        commute_mode="Motorcycle / Scooter",
        current_aqi=190,
        current_pm25=125.0,
    )
    result = await AdvisoryAgent.evaluate_personalization_profile(req)
    assert result.vulnerability_level == "Critical"
    assert result.custom_deposition_fraction >= 0.65
    assert len(result.personalized_tips) == 4
    assert any(term in result.protective_gear_recommendation for term in ["N95", "P100", "respirator", "mask"])

    # Clinical evaluation constraints: max 2 sentences, under 42 words, opening check
    assert result.clinical_evaluation.startswith("As your doctor, looking at your routine as a")
    assert len(result.clinical_evaluation.split()) <= 42

    # Tips formatted as Step 1..4: [Title] — [Action]
    for i, tip in enumerate(result.personalized_tips, 1):
        assert tip.startswith(f"Step {i}:")
        assert " — " in tip

    # Gear and commute advisories: <= 25 words
    assert len(result.protective_gear_recommendation.split()) <= 25
    assert len(result.commute_advisory.split()) < 20


def test_calculate_cigarette_equivalents():
    from api.clinical_engine import calculate_cigarette_equivalents

    # Benchmark: 22 ug/m3 PM2.5 over 24h outdoor = 1.0 cigarette
    res_24h = calculate_cigarette_equivalents(pm25=22.0, activity="walk", duration_minutes=30)
    assert res_24h["full_day_cigarettes"] == 1.0

    # High PM2.5 (110 ug/m3): 24h = 5.0 cigs
    res_110 = calculate_cigarette_equivalents(pm25=110.0, activity="walk", duration_minutes=30)
    assert res_110["full_day_cigarettes"] == 5.0
    # Inhaled mass: 110 * 0.016 * 30 = 52.8 ug
    # Cigarette count: round(52.8 / 352.0, 2) = 0.15
    assert res_110["cigarette_count"] == 0.15
    # With N95 (90% reduction): round(0.15 * 0.10, 2) = 0.01 (or 0.02)
    assert res_110["with_n95"] == round(0.15 * 0.10, 2)
    assert "headline_en" in res_110 and len(res_110["headline_en"]) > 0
    assert "headline_hi" in res_110 and len(res_110["headline_hi"]) > 0
    assert "subtext_en" in res_110 and len(res_110["subtext_en"]) > 0
    assert "subtext_hi" in res_110 and len(res_110["subtext_hi"]) > 0

    # Test minimum 0.05 clamping on low exposure
    res_low = calculate_cigarette_equivalents(pm25=1.0, activity="rest", duration_minutes=5)
    assert res_low["cigarette_count"] == 0.05
    assert res_low["with_n95"] == 0.01

    # Test run_cycle (VE = 0.038)
    # pm25 = 200, dur = 60 -> inhaled = 200 * 0.038 * 60 = 456 ug -> 456 / 352 = 1.29545 -> round = 1.30
    res_run = calculate_cigarette_equivalents(pm25=200.0, activity="run_cycle", duration_minutes=60)
    assert res_run["cigarette_count"] == 1.30
    assert res_run["with_n95"] == 0.13
    assert res_run["full_day_cigarettes"] == round(200.0 / 22.0, 1)

    # Test outdoor_labor / work_shift (VE = 0.030)
    res_labor = calculate_cigarette_equivalents(pm25=100.0, activity="outdoor_labor", duration_minutes=60)
    # inhaled = 100 * 0.030 * 60 = 180 ug -> 180 / 352 = 0.51136 -> 0.51
    assert res_labor["cigarette_count"] == 0.51


