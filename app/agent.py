"""견적 에이전트: 플래너가 상태를 보고 다음 도구를 고르고, 루프가 실행하며 trace 를 남긴다.
키가 없으면 RulePlanner(규칙 기반 분기). LLM 플래너도 next_action(state) 만 구현하면 교체할 수 있다."""
from pathlib import Path

from .calibration import evidence
from . import rag_quote
from .chunking import make_chunks
from .config import settings
from .quote import (CASE_SOURCE, MAX_TEAM, RATE_SOURCE, REFERENCE_CASE, QuoteRequest, compare, effort, estimate,
                    propose_options, schedule, validate)
from .retrieval import hybrid_search

REF_DIR = Path(__file__).resolve().parent.parent / "data" / "quote"
REF_FILTER = {"kind": "quote_ref"}
SAMPLE_NOTICE = "※ 단가·공수·사례 조건은 샘플 가정값이며 실제 계약 금액이 아닙니다."


def ensure_refs_loaded(store, embedder) -> int:
    """data/quote 근거 문서를 적재한다. content_hash 로 중복을 막으므로 여러 번 불러도 안전."""
    chunks = [c for p in sorted(REF_DIR.glob("*.md"))
              for c in make_chunks(p.read_text(encoding="utf-8"), p.name, settings.chunk_size, REF_FILTER)]
    if not chunks:
        return 0
    return store.add_chunks(chunks, embedder.embed_documents([c["content"] for c in chunks]))


def won(n: int) -> str:
    return f"{n:,}원"


# --- 도구: (state, store, embedder) -> trace 에 남길 요약 문자열 ---

def search_refs(state, store, embedder) -> str:
    ensure_refs_loaded(store, embedder)
    req = state["req"]
    queries = ["서울대 연구행정 PI 사례 조건", "컨설팅 단가 혼합 단가 부가세", "기간 압축 할증 투입 인원"] + \
              [f"{s} 과업 공수 교수 연구자" for s in ["common"] + req.scopes]
    refs: dict[str, dict] = {}
    for q in queries:
        for d in hybrid_search(store, embedder, q, k=2, where=REF_FILTER):
            refs.setdefault(d["chunk_id"], d)
    state["refs"] = list(refs.values())
    return f"근거 {len(refs)}개 청크 검색 ({', '.join(sorted({d['source'] for d in refs.values()})) or '없음'})"


def estimate_effort(state, store, embedder) -> str:
    items, total_mm, researchers, assumed = effort(state["req"])
    state["effort"] = {"total_mm": total_mm, "researchers": researchers, "assumed": assumed}
    note = " (교수 수 × 5 가정)" if assumed else ""
    return f"공수 {float(total_mm)}MM — 교수 {state['req'].professors}명, 연구자 {researchers}명{note}"


def check_schedule(state, store, embedder) -> str:
    s = schedule(state["effort"]["total_mm"], state["req"].months)
    state["schedule"] = s
    verdict = "가능" if s["feasible"] else f"불가 (최대 {MAX_TEAM}명 초과)"
    return f"표준 {s['std_months']}개월, 요청 {state['req'].months}개월 → 필요 인원 {s['team']}명, 할증 ×{s['premium']}, {verdict}"


def tool_propose_options(state, store, embedder) -> str:
    state["options"] = propose_options(state["req"])
    return " / ".join(f"{o['label']}: {won(o['estimate']['total'])}" for o in state["options"])


def price(state, store, embedder) -> str:
    state["quote"] = estimate(state["req"])
    q = state["quote"]
    return f"기본 {won(q['base'])} + 할증 {won(q['surcharge'])} + VAT {won(q['vat'])} = {won(q['total'])}"


def compare_case(state, store, embedder) -> str:
    target = state.get("quote") or state["options"][0]["estimate"]   # 불가면 대안 A 와 비교
    state["case"] = estimate(REFERENCE_CASE)
    state["comparison"] = compare(target, state["case"])
    r = state["comparison"]["ratios"]
    return f"{REFERENCE_CASE.university} 대비 공수 ×{r['total_mm']}, 기간 ×{r['months']}, 금액 ×{r['total']}"


def check_evidence(state, store, embedder) -> str:
    target = state.get("quote") or state["options"][0]["estimate"]
    state["evidence"] = evidence(target["subtotal"])
    ev = state["evidence"]
    g = ev["groups"]
    need = "검토 필요" if ev["review"]["required"] else "검토 불필요"
    return (f"실제 사례 {g['small']['n'] + g['enterprise']['n']}건과 비교: 위치 {ev['position']}, "
            f"확신도 {ev['confidence']} → {need}")


def retrieve_cases(state, store, embedder) -> str:
    """① 유사 사례 검색 → 사례 기반 범위 → 공식 금액과 교차검증 (가상 데이터)."""
    req = state["req"]
    target = state.get("quote") or state["options"][0]["estimate"]
    cases = rag_quote.retrieve_similar_cases(req, store, embedder, k=5)
    rng = rag_quote.case_based_range(cases, req)
    check = rag_quote.cross_check(target["subtotal"], rng)
    state["similar"] = {"cases": cases, "range": rng, "check": check}
    if not check["agree"]:
        state["evidence"]["review"]["required"] = True
        state["evidence"]["review"]["reasons"].append(
            f"유사 사례(가상) 기반 중앙값 {won(rng['median'])} 과 공식 금액 차이 {check['diff']:+.0%} (허용 ±25%)")
    return f"유사 사례 {len(cases)}건, 사례 기반 중앙값 {won(rng['median'])}, 공식과 차이 {check['diff']:+.0%}"


def draft_narrative(state, store, embedder) -> str:
    """③ 과거 제안서 문단 검색 → [n] 인용 붙은 과업 수행 내용."""
    state["narrative"] = rag_quote.draft_narrative(state["req"], store, embedder)
    n = state["narrative"]
    return f"과업 수행 내용 {n['mode']} 작성, 인용 {len(n['sources'])}개, 인용 검증 {n['check']['reason']}"


def _items_table(q: dict) -> list[str]:
    rows = ["| 과업 | 공수(MM) | 금액(원) | 출처 |", "|---|---:|---:|---|"]
    rows += [f"| {i['name']} | {i['mm']} | {i['amount']:,} | {i['source']} |" for i in q["items"]]
    return rows


def render_quote(state, store, embedder) -> str:
    req, s, case = state["req"], state["schedule"], REFERENCE_CASE
    eff = state["effort"]
    lines = [f"# 견적서 — {req.university}", "",
             f"- 교수 {req.professors:,}명, 연구자 {eff['researchers']:,}명"
             + (" (미입력 → 교수 수 × 5로 가정)" if eff["assumed"] else ""),
             f"- 총 공수 {float(eff['total_mm'])}MM, 표준 기간 {s['std_months']}개월 (표준 4명 기준)",
             f"- 요청 기간 {req.months}개월 → 필요 인원 {s['team']}명, "
             + (f"기간 할증 ×{s['premium']}" if s["feasible"] else f"최대 {MAX_TEAM}명 초과로 실행 불가"),
             f"- 혼합 단가 {won(state['case']['rate'])}/MM (출처: {RATE_SOURCE})", ""]
    if s["feasible"]:
        q = state["quote"]
        lines += _items_table(q)
        lines += ["", f"- 기본 금액: {won(q['base'])}", f"- 기간 압축 할증: {won(q['surcharge'])}",
                  f"- 소계: {won(q['subtotal'])}", f"- 부가세(10%): {won(q['vat'])}", f"- **합계: {won(q['total'])}**"]
    else:
        lines += [f"**요청 기간 {req.months}개월로는 실행 불가**: {float(eff['total_mm'])}MM 를 {req.months}개월에 끝내려면 "
                  f"{s['team']}명이 필요해 최대 투입 {MAX_TEAM}명을 넘습니다.", "", "## 대안"]
        for o in state["options"]:
            e = o["estimate"]
            lines.append(f"- {o['label']}: 공수 {e['total_mm']}MM, 할증 ×{e['schedule']['premium']}, 합계 {won(e['total'])}")
    r = state["comparison"]["ratios"]
    basis = "" if s["feasible"] else ", 대안 A 기준"
    lines += ["", f"## {case.university} 기준 조건 대비 — 설명용 비교, 검증 아님 (출처: {CASE_SOURCE}{basis})",
              f"- 기준: 교수 {case.professors}명, 연구자 {case.researchers}명, {case.months}개월, 전체 범위 → "
              f"{state['case']['total_mm']}MM, {won(state['case']['total'])}",
              f"- 교수 ×{r['professors']}, 연구자 ×{r['researchers']} → 공수 ×{r['total_mm']}; "
              f"기간 ×{r['months']} → 금액 ×{r['total']}", ""]
    if "narrative" in state:
        n = state["narrative"]
        lines += ["## 과업 수행 내용 (과거 제안서 검색, 가상 데이터)", n["text"],
                  "출처: " + ", ".join(f"[{s['n']}] {s['chunk_id']}" for s in n["sources"]), ""]
    if "similar" in state:
        sim = state["similar"]
        r, c = sim["range"], sim["check"]
        lines += ["## 유사 사례 (하이브리드 검색, 가상 데이터)",
                  f"- 사례 기반 범위: {won(r['low'])} ~ {won(r['high'])}, 중앙값 {won(r['median'])} ({r['note']})",
                  f"- 공식 금액과 차이 {c['diff']:+.0%} → " + ("일치 (±25% 이내)" if c["agree"] else "불일치, 검토 필요")]
        lines += [f"  - {x['case_id']} {x['university']} {x['type']} · 교수 {x['professors']}명 · {x['months']}개월 · "
                  f"{won(x['price_vat_excl'])} · {x['scope_text']}" for x in sim["cases"]]
        lines.append("")
    ev = state["evidence"]
    lines += ["## 실제 사례 근거 (공개 입찰공고, 금액은 VAT 제외)"]
    for g in ev["groups"].values():
        if g["n"]:
            lines.append(f"- {g['name']} {g['n']}건: {won(g['min'])} ~ {won(g['max'])}")
            lines += [f"  - {c['university']}: {won(c['price'])}" + (" (VAT 포함액 ÷1.1)" if c["price_derived"] else "")
                      + (f", {c['months']:g}개월" if c["months"] else "") + f" [{c['verification']}] {c['source_url']}"
                      for c in g["cases"]]
    if ev["review"]["required"]:
        lines += ["", "**⚠ 담당자 검토 필요** (확신도: " + ev["confidence"] + ")"]
        lines += [f"- {r}" for r in ev["review"]["reasons"]]
    lines.append("")
    sources = sorted({d["source"] for d in state["refs"]})
    lines.append(f"근거 문서: {', '.join(sources)}" if sources else "⚠ 검색된 근거 문서가 없습니다.")
    lines.append(SAMPLE_NOTICE)
    state["markdown"] = "\n".join(lines)
    return f"견적서 {len(lines)}줄 작성"


TOOLS = {"search_refs": search_refs, "estimate_effort": estimate_effort, "check_schedule": check_schedule,
         "propose_options": tool_propose_options, "price": price, "compare_case": compare_case,
         "check_evidence": check_evidence, "retrieve_cases": retrieve_cases, "draft_narrative": draft_narrative,
         "render_quote": render_quote}


class RulePlanner:
    def __init__(self, use_rag: bool = False):
        self.use_rag = use_rag   # 켜면 유사 사례 검색 → 과업 수행 내용 단계 추가

    """근거 → 공수 → 일정 판단 → (가능: 가격 / 불가: 대안) → 기준 조건 비교 → 실제 사례 근거 → 견적서."""

    def next_action(self, state) -> str | None:
        if "refs" not in state:
            return "search_refs"
        if "effort" not in state:
            return "estimate_effort"
        if "schedule" not in state:
            return "check_schedule"
        if state["schedule"]["feasible"] and "quote" not in state:
            return "price"
        if not state["schedule"]["feasible"] and "options" not in state:
            return "propose_options"
        if "comparison" not in state:
            return "compare_case"
        if "evidence" not in state:
            return "check_evidence"
        if self.use_rag and "similar" not in state:
            return "retrieve_cases"
        if self.use_rag and "narrative" not in state:
            return "draft_narrative"
        if "markdown" not in state:
            return "render_quote"
        return None


def run_agent(req: QuoteRequest, store, embedder, planner=None, max_steps: int = 10) -> dict:
    result = {"status": "ok", "questions": [], "quote": None, "options": [], "comparison": None,
              "schedule": None, "evidence": None, "review": None, "quote_markdown": "", "sources": [], "trace": []}
    questions = validate(req)
    if questions:
        return {**result, "status": "needs_info", "questions": questions}
    planner = planner or RulePlanner(use_rag=settings.quote_rag)
    state = {"req": req}
    for step in range(1, max_steps + 1):
        tool = planner.next_action(state)
        if tool is None:
            return {**result, "status": "ok" if state["schedule"]["feasible"] else "infeasible",
                    "quote": state.get("quote"), "options": state.get("options", []),
                    "comparison": state["comparison"], "schedule": state["schedule"],
                    "evidence": state["evidence"], "review": state["evidence"]["review"],
                    "similar_cases": state.get("similar"), "narrative": state.get("narrative"),
                    "quote_markdown": state["markdown"],
                    "sources": [{"source": d["source"], "chunk_id": d["chunk_id"]} for d in state["refs"]]}
        if tool not in TOOLS:
            return {**result, "status": "error", "questions": [f"알 수 없는 도구: {tool}"]}
        summary = TOOLS[tool](state, store, embedder)
        result["trace"].append({"step": step, "tool": tool, "summary": summary})
    return {**result, "status": "error", "questions": [f"최대 반복({max_steps}) 초과"]}
