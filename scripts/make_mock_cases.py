"""가상(목) 견적 사례 30건 생성 — 실제 데이터 아님. RAG 파이프라인 시연·테스트용.
    python -m scripts.make_mock_cases     → data/quote/mock/cases.jsonl
고정 시드라 다시 만들어도 같은 결과. 금액은 산정식 × 사업 유형 배수 × 잡음(가상)으로 만든다."""
import json
import math
import random
from pathlib import Path

from app.quote import MAX_TEAM, SCOPES, QuoteRequest, estimate

OUT = Path(__file__).resolve().parent.parent / "data" / "quote" / "mock" / "cases.jsonl"
UNIVS = ["가람", "누리", "다솜", "라온", "마루", "바름", "새솔", "아라", "자람", "하늘",
         "한별", "늘봄", "도담", "보람", "솔빛", "윤슬", "이음", "푸름", "한울", "여울"]
TYPE_MULT = {"PI": 1.0, "ISP": 1.5, "ISMP": 2.0}
# 같은 범위를 대학마다 다른 표현으로 쓴다 → 벡터(의미) 검색이 필요해지는 상황
PHRASES = {
    "planning": ["연구기획 프로세스 개선", "연구 과제 발굴·기획 체계 정비", "중장기 연구전략 수립 지원 업무 재설계"],
    "award": ["과제수주 프로세스 개선", "과제 신청·선정·협약 절차 표준화", "연구과제 공모 대응 체계 정비"],
    "funding": ["연구비 관리 프로세스 개선", "연구비 집행·정산 체계 재설계", "연구비 사용 및 감사 대응 업무 혁신"],
    "outcome": ["성과 활용 프로세스 개선", "연구성과 관리·기술이전 체계 정비", "특허·기술사업화 성과관리 고도화"],
    "roadmap": ["차세대 연구행정시스템 구축 방향 및 실행 로드맵", "통합 연구관리시스템 목표모델·이행계획 수립",
                "정보시스템 마스터플랜 및 단계별 구축 로드맵"],
}


def make(seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for i in range(30):
        typ = rng.choice(list(TYPE_MULT))
        scopes = sorted(rng.sample(SCOPES, rng.randint(1, 5)), key=SCOPES.index)
        prof = rng.randrange(100, 700, 10)
        res = prof * rng.randint(3, 5)
        months = rng.randint(2, 8)
        req = QuoteRequest(university="x", professors=prof, researchers=res, months=months, scopes=scopes)
        if not (e := estimate(req))["schedule"]["feasible"]:   # 가상 사례도 실행 가능한 기간으로만 만든다
            months = math.ceil(e["total_mm"] / MAX_TEAM)
            req = QuoteRequest(university="x", professors=prof, researchers=res, months=months, scopes=scopes)
        base = estimate(req)["subtotal"]
        price = int(base * TYPE_MULT[typ] * rng.uniform(0.8, 1.25) / 10_000) * 10_000
        univ = f"{UNIVS[i % len(UNIVS)]}대학교" if i < 20 else f"{UNIVS[i % len(UNIVS)]}과학기술대학교"
        desc = ", ".join(rng.choice(PHRASES[s]) for s in scopes)
        cases.append({"case_id": f"M{i + 1:03d}", "university": univ, "type": typ,
                      "title": f"{univ} 연구행정 {typ} 용역", "scope_text": desc, "scopes": scopes,
                      "professors": prof, "researchers": res, "months": months, "price_vat_excl": price,
                      "mock": True})
    return cases


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in make()) + "\n", encoding="utf-8")
    print(f"{OUT} — {len(make())}건 (가상 데이터)")
