"""계수 보정 파이프라인 테스트. 아래 사례는 테스트 전용 합성 데이터 (실제 입찰 데이터 아님)."""
from app.calibration import calibrate, fit, load_cases, loo_mape, predict

RATE = 10_000_000


def _case(prof, mm):
    return {"professors": prof, "price": int(mm * RATE), "months": None}


# 공수 = 2 + 0.01 × 교수 수 를 정확히 따르는 합성 사례
EXACT = [_case(p, 2 + 0.01 * p) for p in (300, 600, 900, 1200, 1500)]


def test_fit_recovers_known_coefficients():
    a, b = fit(EXACT, RATE)
    assert abs(a - 2) < 1e-9 and abs(b - 0.01) < 1e-9


def test_loo_error_zero_on_exact_data():
    assert loo_mape(EXACT, RATE) < 1e-9


def test_noisy_data_has_positive_error():
    noisy = [_case(p, (2 + 0.01 * p) * f) for p, f in zip((300, 600, 900, 1200, 1500), (1.2, 0.85, 1.1, 0.9, 1.15))]
    assert loo_mape(noisy, RATE) > 0.05


def test_too_few_cases_is_low_confidence():
    cal = calibrate(EXACT[:2], RATE)
    assert cal["confidence"] == "low" and cal["a"] is None and predict(cal, 500, RATE) is None


def test_good_fit_is_not_low_confidence():
    cal = calibrate(EXACT, RATE)
    assert cal["confidence"] == "medium" and cal["mape"] == 0


def test_large_error_is_low_confidence():
    wild = [_case(p, (2 + 0.01 * p) * f) for p, f in zip((300, 600, 900, 1200, 1500), (2.5, 0.4, 1.9, 0.5, 2.2))]
    assert calibrate(wild, RATE)["confidence"] == "low"


def test_predict_gives_range():
    pred = predict(calibrate(EXACT, RATE), 1000, RATE)
    assert pred["mm"] == 12.0 and pred["low"] == pred["price"] == pred["high"] == 120_000_000


def test_load_cases_skips_unverified_rows(tmp_path):
    p = tmp_path / "cases.csv"
    p.write_text("university,estimated_price_vat_excl,professors,months\n"
                 "A대,500000000,1000,6\nB대,,800,5\nC대,300000000,,4\n", encoding="utf-8")
    rows = load_cases(p)
    assert [r["university"] for r in rows] == ["A대"] and rows[0]["months"] == 6.0
