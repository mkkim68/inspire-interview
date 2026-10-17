"""사용자 메시지 해석: LLM 이 애매한 표현을 구조화하고, 코드가 원문 근거로 검증한다. 계산은 하지 않는다.
  LLM  → 의도, 값, 각 숫자의 '원문 구절', 범위 추가·삭제, 반영 안 된 요청
  코드 → 구절이 메시지에 실제로 있는지 + 구절의 숫자와 값이 맞는지 검사, 어긋나면 버리고 되묻기
  실패·키 없음·EXTRACTOR=regex → 정규식 extract() 로 폴백"""
import math
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

from .config import settings
from .intake import extract, parse_budget

Scope = Literal["planning", "award", "funding", "outcome", "roadmap"]


class Understood(BaseModel):
    intent: Literal["conditions", "correction", "reset", "question", "other"]
    university: str | None = Field(None, description="대학 정식 명칭. '고려대' → '고려대학교'")
    professors: int | None = None
    professors_text: str | None = Field(None, description="교수 수를 말한 원문 구절 그대로")
    researchers: int | None = None
    researchers_text: str | None = None
    months: int | None = Field(None, description="수행 기간(개월, 올림)")
    months_text: str | None = None
    budget_won: int | None = Field(None, description="예산 상한(원, VAT 포함)")
    budget_text: str | None = None
    add_scopes: list[Scope] = []
    remove_scopes: list[Scope] = []
    unhandled: list[str] = Field([], description="견적 조건이 아닌 요구사항(보고·상주 등) 원문 구절")


SYSTEM = """너는 대학 연구행정 PI 컨설팅 견적 접수 담당이다. 사용자 메시지에서 견적 조건만 뽑는다. 금액을 계산하거나 추측하지 마라.
범위 키: planning=연구기획, award=과제수주(신청·선정·협약), funding=연구비 관리(집행·정산·감사),
outcome=성과 활용(특허·기술이전), roadmap=차세대 시스템 구축 방향·실행 로드맵(마스터플랜·ISP·ISMP).
규칙:
- 메시지에 없는 값은 null. 대략적 표현("300분 정도", "석 달", "1.5억 안쪽")은 해석하되, *_text 에 원문 구절을 그대로 복사.
- "~은 빼줘" 같은 정정은 remove_scopes, 추가는 add_scopes. "처음부터 다시"는 intent=reset.
- 견적 조건이 아닌 요구(보고 주기, 상주, 산출물 형식 등)는 unhandled 에 원문 구절로.
- 질문만 하면 intent=question."""


def _digits(text: str) -> int | None:
    m = re.search(r"\d[\d,]*", text)
    return int(m.group().replace(",", "")) if m else None


def _consistent(field: str, value: int, span: str) -> bool:
    """구절에 숫자가 있으면 값과 맞아야 한다. 숫자가 없으면(석 달 등) 해석으로 받아들이고 사용자에게 되보여 준다."""
    n = _digits(span)
    if field == "budget_won":
        parsed = parse_budget("예산 " + span)
        return parsed is None or parsed == value
    if n is None:
        return True
    if field == "months":
        if "주" in span:
            return value == math.ceil(n / 4)
        if "년" in span:
            return value == n * 12
    return value == n


def verify(u: Understood, message: str) -> tuple[dict, list[str], list[str]]:
    """(통과한 값, 해석 메모, 버린 이유)"""
    values, notes, dropped = {}, [], []
    if u.university:
        values["university"] = u.university
    for field, span, label in (("professors", u.professors_text, "교수 수"), ("researchers", u.researchers_text, "연구자 수"),
                               ("months", u.months_text, "기간"), ("budget_won", u.budget_text, "예산")):
        value = getattr(u, field)
        if value is None:
            continue
        if not span or span not in message:
            dropped.append(f"{label} {value}: 원문 근거 구절이 메시지에 없음")
        elif value <= 0 or not _consistent(field, value, span):
            dropped.append(f"{label} {value}: '{span}' 과 숫자가 맞지 않음")
        else:
            values["budget" if field == "budget_won" else field] = value
            if _digits(span) is None or "주" in span or "정도" in span or "쯤" in span or "안쪽" in span:
                unit = {"professors": "명", "researchers": "명", "months": "개월", "budget_won": "원"}[field]
                notes.append(f"{label}: '{span}' → {value:,}{unit}")
    return values, notes, dropped


def _call_claude(message: str) -> Understood:
    import anthropic
    resp = anthropic.Anthropic().messages.parse(
        model=settings.llm_model, max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": message}], output_format=Understood)
    return resp.parsed_output


def llm_enabled() -> bool:
    return settings.extractor == "llm" and bool(os.getenv("ANTHROPIC_API_KEY"))


def understand(message: str, call=None) -> dict:
    """extract() 와 같은 모양 + intent·remove_scopes·notes·dropped·source. call 은 테스트용 주입."""
    base = extract(message)
    if call is None and not llm_enabled():
        return {**base, "intent": "conditions", "remove_scopes": [], "notes": [], "dropped": [], "source": "regex"}
    try:
        u = (call or _call_claude)(message)
    except Exception as e:   # 네트워크·키·스키마 오류 → 정규식
        return {**base, "intent": "conditions", "remove_scopes": [], "notes": [], "dropped": [],
                "source": f"regex (LLM 실패: {type(e).__name__})"}
    values, notes, dropped = verify(u, message)
    return {"university": values.get("university"), "professors": values.get("professors"),
            "researchers": values.get("researchers"), "months": values.get("months"), "budget": values.get("budget"),
            "scopes": list(u.add_scopes), "remove_scopes": list(u.remove_scopes),
            "unhandled": u.unhandled or base["unhandled"], "intent": u.intent,
            "notes": notes, "dropped": dropped, "source": "llm"}
