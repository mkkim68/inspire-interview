"""견적 계산. 숫자는 여기서만 만든다 (LLM·렌더러는 숫자를 바꾸지 않는다).
값은 샘플 가정값이며 data/quote/*.md 와 같아야 한다 (테스트로 검사).

  공수(MM)  = Σ 모듈별 (고정 + 교수 수 × 교수당 + 연구자 수 × 연구자당)
  표준 기간 = 총 공수 ÷ 표준 투입 4명,  필요 인원 = 총 공수 ÷ 요청 기간 (8명 초과면 실행 불가)
  할증      = 요청 기간 < 표준 기간이면 0.15 × (표준 기간 ÷ 요청 기간 − 1)
  금액      = 공수 × 혼합 단가 + 할증,  VAT = 소계 10% (원 미만 버림)
"""
import math
from dataclasses import asdict, dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

RATE_SOURCE = "rate_card.md"
MODULE_SOURCE = "modules.md"
CASE_SOURCE = "snu_pi_case.md"

# 직급: (단가 원/MM, 투입 비율)
RATES = {"책임": (15_000_000, Decimal("0.2")), "선임": (11_000_000, Decimal("0.4")), "전임": (8_000_000, Decimal("0.4"))}
BLENDED_RATE = int(sum(Decimal(p) * r for p, r in RATES.values()))

# 모듈 키: (이름, 고정 MM, 교수 1명당 MM, 연구자 1명당 MM). common 은 항상 포함.
MODULES = {
    "common": ("현황 분석·To-Be 설계·사업관리", Decimal("2.0"), Decimal("0.01"), Decimal("0.002")),
    "planning": ("연구기획", Decimal("0.5"), Decimal("0.015"), Decimal("0")),
    "award": ("과제수주", Decimal("0.5"), Decimal("0.015"), Decimal("0")),
    "funding": ("연구비 관리", Decimal("0.5"), Decimal("0"), Decimal("0.004")),
    "outcome": ("성과 활용", Decimal("0.5"), Decimal("0.02"), Decimal("0")),
    "roadmap": ("차세대 시스템 구축 방향·실행 로드맵", Decimal("2.0"), Decimal("0"), Decimal("0.002")),
}
SCOPES = [k for k in MODULES if k != "common"]

RESEARCHERS_PER_PROF = 5        # 연구자 수 미입력 시 가정
STD_TEAM, MAX_TEAM = 4, 8       # 표준 / 최대 투입 인원
COMPRESSION = Decimal("0.15")   # 기간 압축 할증 계수
VAT_RATE = Decimal("0.1")


@dataclass
class QuoteRequest:
    university: str = ""
    professors: int | None = None
    researchers: int | None = None   # 비우면 교수 수 × 5 로 가정
    months: int | None = None
    scopes: list[str] = field(default_factory=list)


# 기준 사례: 서울대 (조건은 비교용 가정값, 실제 계약 금액은 비공개)
REFERENCE_CASE = QuoteRequest(university="서울대학교", professors=50, researchers=250, months=3, scopes=list(SCOPES))


def validate(req: QuoteRequest) -> list[str]:
    """필수 입력이 빠졌거나 잘못되면 되물을 질문 목록을 돌려준다. 비어 있으면 통과."""
    questions = []
    if not req.university.strip():
        questions.append("견적을 받을 대학명을 알려주세요.")
    if req.professors is None or req.professors < 1:
        questions.append("대학의 교수 수(1명 이상)를 알려주세요.")
    elif req.researchers is not None and req.researchers < req.professors:
        questions.append("연구자 수는 교수 수 이상이어야 합니다. 연구자 수를 확인해 주세요(모르면 비워 두세요).")
    if req.months is None or req.months < 1:
        questions.append("희망 수행 기간(개월, 1 이상)을 알려주세요.")
    if not req.scopes:
        questions.append(f"어떤 과업 범위가 필요하신가요? ({', '.join(SCOPES)})")
    unknown = [s for s in req.scopes if s not in SCOPES]
    if unknown:
        questions.append(f"지원하지 않는 범위입니다: {', '.join(unknown)}. 다음 중에서 골라주세요: {', '.join(SCOPES)}")
    return questions


def _r(x: Decimal, q: str) -> Decimal:
    return x.quantize(Decimal(q), rounding=ROUND_HALF_UP)


def effort(req: QuoteRequest) -> tuple[list[dict], Decimal, int, bool]:
    """모듈별 공수. (항목, 총 공수, 연구자 수, 연구자 수 가정 여부)"""
    assumed = req.researchers is None
    researchers = req.professors * RESEARCHERS_PER_PROF if assumed else req.researchers
    items = []
    for key in ["common"] + [s for s in SCOPES if s in req.scopes]:   # 카탈로그 순서, 중복 제거
        name, fixed, per_prof, per_res = MODULES[key]
        mm = _r(fixed + per_prof * req.professors + per_res * researchers, "0.01")
        items.append({"module": key, "name": name, "mm": mm, "source": MODULE_SOURCE})
    return items, sum(i["mm"] for i in items), researchers, assumed


def schedule(total_mm: Decimal, months: int) -> dict:
    std = total_mm / STD_TEAM
    team = total_mm / months
    premium = Decimal(1) if months >= std else _r(1 + COMPRESSION * (std / months - 1), "0.0001")
    return {"std_months": float(_r(std, "0.01")), "team": float(_r(team, "0.01")),
            "premium": float(premium), "feasible": team <= MAX_TEAM}


def estimate(req: QuoteRequest) -> dict:
    items, total_mm, researchers, assumed = effort(req)
    sched = schedule(total_mm, req.months)
    out = [{**i, "mm": float(i["mm"]), "amount": int(i["mm"] * BLENDED_RATE)} for i in items]
    base = sum(i["amount"] for i in out)
    surcharge = int(base * (Decimal(str(sched["premium"])) - 1))
    subtotal = base + surcharge
    vat = int(subtotal * VAT_RATE)
    return {"items": out, "total_mm": float(total_mm), "professors": req.professors, "researchers": researchers,
            "researchers_assumed": assumed, "months": req.months, "schedule": sched, "rate": BLENDED_RATE,
            "base": base, "surcharge": surcharge, "subtotal": subtotal, "vat": vat, "total": subtotal + vat}


def propose_options(req: QuoteRequest) -> list[dict]:
    """실행 불가 요청의 대안. A: 최대 인원으로 가능한 최소 기간, B: 기간 유지 + 들어가는 범위만 (카탈로그 순)."""
    _, total_mm, _, _ = effort(req)
    min_months = math.ceil(total_mm / MAX_TEAM)
    a = replace(req, months=min_months)
    options = [{"label": f"기간을 {min_months}개월로 늘리기", "request": asdict(a), "estimate": estimate(a)}]
    capacity = MAX_TEAM * req.months
    keep: list[str] = []
    for s in [s for s in SCOPES if s in req.scopes]:
        if effort(replace(req, scopes=keep + [s]))[1] <= capacity:
            keep.append(s)
    if keep and keep != [s for s in SCOPES if s in req.scopes]:
        b = replace(req, scopes=keep)
        names = ", ".join(MODULES[s][0] for s in keep)
        options.append({"label": f"{req.months}개월 유지, 범위를 {names}(으)로 축소", "request": asdict(b),
                        "estimate": estimate(b)})
    return options


def compare(est: dict, case_est: dict) -> dict:
    """기준 사례 대비 배율 (소수 2자리)."""
    ratio = lambda k: float(_r(Decimal(str(est[k])) / Decimal(str(case_est[k])), "0.01"))
    return {"ratios": {k: ratio(k) for k in ("professors", "researchers", "total_mm", "months", "total")}}
