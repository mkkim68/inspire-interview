"""실제 입찰 사례로 공수 계수를 맞추고, 한 건씩 빼고 예측(LOO)해 오차를 잰다.

  사례 공수(MM) = 추정가격(VAT 제외) ÷ 혼합 단가
  공수 ≈ a + b × 교수 수           (최소제곱)
  확신도: 사례 수와 LOO 평균 절대 오차율(MAPE)로 판단. 낮으면 사람 검토 필요.
"""
import csv
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
