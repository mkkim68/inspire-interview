"""실제 입찰 사례로 공수 계수를 맞추고, 한 건씩 빼고 예측(LOO)해 오차를 잰다.

  사례 공수(MM) = 추정가격(VAT 제외) ÷ 혼합 단가
  공수 ≈ a + b × 교수 수           (최소제곱)
  확신도: 사례 수와 LOO 평균 절대 오차율(MAPE)로 판단. 낮으면 사람 검토 필요.
"""
import csv
from decimal import Decimal
from pathlib import Path

import numpy as np

CASES_PATH = Path(__file__).resolve().parent.parent / "data" / "quote" / "cases.csv"
MIN_CASES = 3          # 이보다 적으면 맞출 수 없음 → 확신도 low
GOOD_MAPE = 0.25       # LOO 오차가 이 이하이고 사례가 충분하면 medium 이상


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    """금액·교수 수가 모두 확인된 행만 쓴다 (빈 값은 추정하지 않는다)."""
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("estimated_price_vat_excl") and r.get("professors"):
                rows.append({**r, "price": int(r["estimated_price_vat_excl"]), "professors": int(r["professors"]),
                             "months": float(r["months"]) if r.get("months") else None})
    return rows


def fit(cases: list[dict], rate: int) -> tuple[float, float]:
    """공수 = a + b × 교수 수 를 최소제곱으로 맞춘다. (a, b)"""
    x = np.array([c["professors"] for c in cases], dtype=float)
    y = np.array([c["price"] / rate for c in cases], dtype=float)
    A = np.column_stack([np.ones_like(x), x])
    (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(a), float(b)


def loo_mape(cases: list[dict], rate: int) -> float | None:
    """한 건씩 빼고 나머지로 맞춘 뒤 빠진 건의 금액을 예측. 평균 절대 오차율."""
    if len(cases) < MIN_CASES:
        return None
    errors = []
    for i, held in enumerate(cases):
        a, b = fit(cases[:i] + cases[i + 1:], rate)
        pred = (a + b * held["professors"]) * rate
        errors.append(abs(pred - held["price"]) / held["price"])
    return float(np.mean(errors))


def calibrate(cases: list[dict], rate: int) -> dict:
    n = len(cases)
    if n < MIN_CASES:
        return {"n": n, "a": None, "b": None, "mape": None, "confidence": "low",
                "reason": f"금액·교수 수가 확인된 사례 {n}건 (최소 {MIN_CASES}건 필요)"}
    a, b = fit(cases, rate)
    mape = loo_mape(cases, rate)
    if b <= 0:
        confidence, reason = "low", "교수 수가 늘수록 공수가 줄어드는 결과 — 사례 범위가 섞였을 가능성"
    elif mape > GOOD_MAPE:
        confidence, reason = "low", f"LOO 오차 {mape:.0%} > {GOOD_MAPE:.0%}"
    else:
        confidence = "medium" if n < 8 else "high"
        reason = f"사례 {n}건, LOO 오차 {mape:.0%}"
    return {"n": n, "a": round(a, 3), "b": round(b, 5), "mape": round(mape, 3), "confidence": confidence,
            "reason": reason}


def predict(cal: dict, professors: int, rate: int) -> dict | None:
    """사례 기반 추정 금액(VAT 제외)과 LOO 오차로 만든 범위."""
    if cal["a"] is None:
        return None
    mm = cal["a"] + cal["b"] * professors
    price = int(mm * rate)
    m = cal["mape"]
    return {"mm": round(mm, 2), "price": price, "low": int(price * (1 - m)), "high": int(price * (1 + m))}


# --- 실제 사례 근거: 계수를 맞출 만큼 데이터가 없을 때 "어디쯤인지"와 "검토 필요"를 보여준다 ---

GROUP_NAMES = {"small": "약식·부분 범위 ISP", "enterprise": "전사·차세대 ISP/ISMP"}


def load_reference_cases(path: Path = CASES_PATH) -> list[dict]:
    """금액이 확인된 사례 전부 (중복 공고 include=0 제외). VAT 포함 금액만 있으면 ÷1.1 로 환산하고 표시."""
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("include") == "0":
                continue
            if r.get("estimated_price_vat_excl"):
                price, derived = int(r["estimated_price_vat_excl"]), False
            elif r.get("budget_vat_incl"):
                price, derived = int(Decimal(r["budget_vat_incl"]) / Decimal("1.1")), True   # float 오차 방지
            else:
                continue
            rows.append({**r, "price": price, "price_derived": derived,
                         "months": float(r["months"]) if r.get("months") else None})
    return rows


def case_groups(cases: list[dict]) -> dict:
    groups = {}
    for key, name in GROUP_NAMES.items():
        g = [c for c in cases if c.get("scope_group") == key]
        prices = [c["price"] for c in g]
        groups[key] = {"name": name, "n": len(g), "min": min(prices, default=None), "max": max(prices, default=None),
                       "cases": [{k: c[k] for k in ("university", "project_name", "price", "price_derived", "months",
                                                     "verification", "source_url")} for c in g]}
    return groups


def evidence(formula_price: int, scope_keyword: str = "연구행정", rate: int | None = None) -> dict:
    """공식 금액(VAT 제외)을 실제 사례 그룹과 비교하고, 사람 검토가 필요한지 판단한다."""
    from .quote import BLENDED_RATE
    refs = load_reference_cases()
    groups = case_groups(refs)
    cal = calibrate(load_cases(), rate or BLENDED_RATE)
    small, ent = groups["small"], groups["enterprise"]
    if small["max"] is not None and formula_price <= small["max"]:
        position = "small"
    elif ent["min"] is not None and formula_price >= ent["min"]:
        position = "enterprise"
    else:
        position = "between"
    scope_cases = sum(scope_keyword in c.get("scope_keywords", "") for c in refs)
    reasons = []
    if cal["confidence"] == "low":
        reasons.append(f"계수 보정 확신도 낮음 — {cal['reason']}")
    if scope_cases == 0:
        reasons.append(f"'{scope_keyword}' 범위를 명시한 실제 사례 0건 (서울대 사례는 금액 비공개)")
    if position == "between":
        reasons.append("공식 금액이 실제 사례 그룹(약식·부분 / 전사·차세대) 사이에 있어 어느 쪽에도 근거가 없음")
    return {"calibration": cal, "groups": groups, "position": position, "scope_cases": scope_cases,
            "confidence": cal["confidence"], "review": {"required": bool(reasons), "reasons": reasons}}
