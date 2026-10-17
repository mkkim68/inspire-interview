"""대화형 접수 창구: 자연어 메시지에서 견적 조건을 뽑아 누적하고, 부족하면 되묻고, 다 모이면 견적 에이전트를 돌린다.
추출은 규칙 기반(키 없이 동작). LLM 키가 생기면 extract() 만 바꾸면 된다 — 금액은 계속 quote.py 가 계산."""
import math
import re
from dataclasses import dataclass, field

from .agent import run_agent
from .quote import MODULES, SCOPES, QuoteRequest, validate

# '최대 8명'의 '최대'처럼 '대'로 끝나지만 대학이 아닌 말
NOT_UNIV = {"최대", "확대", "기대", "상대", "시대", "절대", "반대", "현대", "극대", "증대", "연대", "세대"}
UNIV_RE = re.compile(r"^([가-힣A-Za-z]+?)(대학교|대학|대)(인데|이고|이에요|입니다|에서|의|는|은|이|요|에|로)?$")
PROF_RE = re.compile(r"교수(?:진|님)?(?:는|가|이|은)?\s*(?:약\s*)?([\d,]+)\s*명")
RES_RE = re.compile(r"연구(?:자|원|인력)(?:는|가|이|은)?\s*(?:약\s*)?([\d,]+)\s*명")
KOREAN_MONTHS = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
SCOPE_WORDS = [("planning", ("연구기획", "기획")), ("award", ("과제수주", "수주")), ("funding", ("연구비",)),
               ("outcome", ("성과",)), ("roadmap", ("로드맵", "차세대", "시스템 구축"))]
ALL_SCOPE_RE = re.compile(r"전체|전부|모두|전 범위|다 해")
# 견적식에 없는 요청 — 버리지 않고 '반영 안 된 조건'으로 모은다
UNHANDLED_HINTS = ("보고", "상주", "예산", "산출물", "교육", "유지보수", "보안", "감리", "발표", "워크숍")
RESET_RE = re.compile(r"처음부터|새 견적|다시 시작|리셋")


def _university(text: str) -> str | None:
    for tok in re.findall(r"[가-힣A-Za-z]+", text):
        m = UNIV_RE.match(tok)
        if not m or m.group(1) + m.group(2) in NOT_UNIV:
            continue
        name = m.group(1) + m.group(2)
        return name + {"대": "학교", "대학": "교"}.get(m.group(2), "")
    return None


def _months(text: str) -> int | None:
    if m := re.search(r"(\d+)\s*개월", text):
        return int(m.group(1))
    if m := re.search(r"(\d+)\s*주(?!\s*\d)", text):
        return math.ceil(int(m.group(1)) / 4)
    if m := re.search(r"(" + "|".join(KOREAN_MONTHS) + r")\s*달", text):
        return KOREAN_MONTHS[m.group(1)]
    return None


def _int(m) -> int | None:
    return int(m.group(1).replace(",", "")) if m else None


def extract(text: str) -> dict:
    scopes = list(SCOPES) if ALL_SCOPE_RE.search(text) else \
        [key for key, words in SCOPE_WORDS if any(w in text for w in words)]
    clauses = [c.strip() for c in re.split(r"[,.\n!?]|그리고", text) if c.strip()]
    return {"university": _university(text), "professors": _int(PROF_RE.search(text)),
            "researchers": _int(RES_RE.search(text)), "months": _months(text), "scopes": scopes,
            "unhandled": [c for c in clauses if any(h in c for h in UNHANDLED_HINTS)]}


@dataclass
class ChatSession:
    slots: dict = field(default_factory=lambda: {"university": None, "professors": None, "researchers": None,
                                                 "months": None, "scopes": []})
    unhandled: list[str] = field(default_factory=list)

    def merge(self, e: dict) -> None:
        for k in ("university", "professors", "researchers", "months"):
            if e[k] is not None:
                self.slots[k] = e[k]
        self.slots["scopes"] = [s for s in SCOPES if s in self.slots["scopes"] or s in e["scopes"]]
        self.unhandled += [u for u in e["unhandled"] if u not in self.unhandled]

    def request(self) -> QuoteRequest:
        s = self.slots
        return QuoteRequest(university=s["university"] or "", professors=s["professors"],
                            researchers=s["researchers"], months=s["months"], scopes=list(s["scopes"]))


def summary(slots: dict) -> str:
    """지금까지 받은 조건을 사람이 읽는 문장으로."""
    parts = []
    if slots["university"]:
        parts.append(slots["university"])
    if slots["professors"] is not None:
        parts.append(f"교수 {slots['professors']:,}명")
    if slots["researchers"] is not None:
        parts.append(f"연구자 {slots['researchers']:,}명")
    if slots["months"] is not None:
        parts.append(f"{slots['months']}개월")
    if slots["scopes"]:
        parts.append("범위 " + "·".join(MODULES[s][0] for s in slots["scopes"]))
    return ", ".join(parts)


def _won(n: int) -> str:
    return f"{n:,}원"


def reply(session: ChatSession, message: str, store, embedder) -> dict:
    out = {"status": "", "reply": "", "questions": [], "result": None}
    if RESET_RE.search(message):
        session.__init__()
        return {**out, "status": "reset", "reply": "처음부터 다시 시작할게요. 대학명, 교수 수, 기간, 필요한 범위를 알려주세요.",
                "slots": session.slots, "unhandled": []}
    session.merge(extract(message))
    req = session.request()
    questions = validate(req)
    if questions:
        got = summary(session.slots)
        text = "견적을 내려면 아래 정보가 더 필요해요.\n" + "\n".join(f"- {q}" for q in questions)
        if got:
            text += f"\n(지금까지 받은 조건: {got})"
        return {**out, "status": "needs_info", "reply": text, "questions": questions,
                "slots": session.slots, "unhandled": session.unhandled}

    res = run_agent(req, store, embedder)
    if session.unhandled:
        res["review"]["required"] = True
        res["review"]["reasons"].append(f"반영 안 된 요청 조건: {' / '.join(session.unhandled)} — 견적 금액에 포함되지 않음")
    s = res["schedule"]
    if res["status"] == "ok":
        q = res["quote"]
        text = (f"{req.university} 견적이 나왔어요. 공수 {q['total_mm']}MM, 필요 인원 {s['team']}명, "
                f"기간 할증 ×{s['premium']} → 합계 {_won(q['total'])} (VAT 포함).")
    else:
        opts = " / ".join(f"{o['label']}: {_won(o['estimate']['total'])}" for o in res["options"])
        text = f"요청 기간 {req.months}개월로는 어려워요 (필요 인원 {s['team']}명 > 최대 8명). 대안: {opts}"
    if res["review"]["required"]:
        text += "\n⚠ 담당자 검토 필요:\n" + "\n".join(f"- {r}" for r in res["review"]["reasons"])
    return {**out, "status": res["status"], "reply": text, "result": res,
            "slots": session.slots, "unhandled": session.unhandled}
