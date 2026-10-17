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


# --- 실제 사례 근거 (data/quote/cases.csv 공개 입찰공고) ---

from app.calibration import case_groups, evidence, load_reference_cases  # noqa: E402


def test_reference_cases_convert_vat_and_skip_duplicates():
    rows = load_reference_cases()
    deu = next(r for r in rows if r["university"] == "동의대학교")
    assert deu["price"] == 863_636_363 and deu["price_derived"] is True     # 950,000,000 ÷ 1.1
    knou = next(r for r in rows if r["university"] == "한국방송통신대학교")
    assert knou["price"] == 889_900_000                                    # 978,890,000 ÷ 1.1 (float 오차 없이)
    assert sum(r["university"] == "경북대학교" for r in rows) == 1            # 재공고 중복 제외
    assert all(r["source_url"].startswith("http") for r in rows)


def test_case_groups_split_by_scope():
    g = case_groups(load_reference_cases())
    assert g["small"]["n"] == 3 and g["enterprise"]["n"] == 5
    assert g["small"]["max"] < g["enterprise"]["min"]


def test_evidence_flags_review_when_data_is_thin():
    ev = evidence(195_040_000, scope_keyword="연구행정")
    assert ev["confidence"] == "low"
    assert ev["position"] == "between"            # 약식 그룹 최대 < 1.95억 < 전사 그룹 최소
    assert ev["scope_cases"] == 0
    assert ev["review"]["required"] and len(ev["review"]["reasons"]) >= 2
