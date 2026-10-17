"""견적 계산. 숫자는 여기서만 만든다 (LLM·렌더러는 숫자를 바꾸지 않는다).
값은 샘플 가정값이며 data/quote/rate_card.md, modules.md 와 같아야 한다 (테스트로 검사)."""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

RATE_SOURCE = "rate_card.md"
MODULE_SOURCE = "modules.md"

# 직급: (단가 원/MM, 투입 비율)
RATES = {"책임": (15_000_000, Decimal("0.2")), "선임": (11_000_000, Decimal("0.4")), "전임": (8_000_000, Decimal("0.4"))}
BLENDED_RATE = int(sum(Decimal(p) * r for p, r in RATES.values()))

# 모듈 키: (이름, 기본 공수 MM). common 은 항상 포함, 나머지는 선택 범위.
MODULES = {
    "common": ("현황 분석·To-Be 설계·사업관리", Decimal("4.0")),
    "planning": ("연구기획", Decimal("2.0")),
    "award": ("과제수주", Decimal("2.0")),
    "funding": ("연구비 관리", Decimal("3.0")),
    "outcome": ("성과 활용", Decimal("2.0")),
    "roadmap": ("차세대 시스템 구축 방향·실행 로드맵", Decimal("3.0")),
}
SCOPES = [k for k in MODULES if k != "common"]

# (연구자 수 하한, 계수) — 큰 하한부터 검사
SCALE = [(3000, Decimal("1.3")), (1000, Decimal("1.0")), (0, Decimal("0.8"))]
VAT_RATE = Decimal("0.1")


@dataclass
class QuoteRequest:
    university: str = ""
    researchers: int | None = None
    scopes: list[str] = field(default_factory=list)


def scale_factor(researchers: int) -> Decimal:
    return next(f for lo, f in SCALE if researchers >= lo)


def validate(req: QuoteRequest) -> list[str]:
    """필수 입력이 빠졌거나 잘못되면 되물을 질문 목록을 돌려준다. 비어 있으면 통과."""
    questions = []
    if not req.university.strip():
        questions.append("견적을 받을 대학명을 알려주세요.")
    if req.researchers is None or req.researchers < 1:
        questions.append("대학의 연구자 수(1명 이상)를 알려주세요.")
    if not req.scopes:
        questions.append(f"어떤 과업 범위가 필요하신가요? ({', '.join(SCOPES)})")
    unknown = [s for s in req.scopes if s not in SCOPES]
    if unknown:
        questions.append(f"지원하지 않는 범위입니다: {', '.join(unknown)}. 다음 중에서 골라주세요: {', '.join(SCOPES)}")
    return questions


def estimate(req: QuoteRequest) -> dict:
    """공수 = 기본 공수 × 규모 계수(소수 1자리 반올림), 금액 = 공수 × 혼합 단가, VAT = 소계 10%(원 미만 버림)."""
    factor = scale_factor(req.researchers)
    keys = ["common"] + [s for s in SCOPES if s in req.scopes]   # 카탈로그 순서, 중복 제거
    items = []
    for key in keys:
        name, base = MODULES[key]
        mm = (base * factor).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        items.append({"module": key, "name": name, "mm": float(mm), "amount": int(mm * BLENDED_RATE),
                      "source": MODULE_SOURCE})
    subtotal = sum(i["amount"] for i in items)
    vat = int(subtotal * VAT_RATE)
    return {"items": items, "factor": float(factor), "rate": BLENDED_RATE,
            "subtotal": subtotal, "vat": vat, "total": subtotal + vat}
