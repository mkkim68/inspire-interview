"""견적 에이전트: 플래너가 다음 도구를 고르고, 루프가 실행하며 trace 를 남긴다.
키가 없으면 RulePlanner(결정적 순서). LLM 플래너도 next_action(state) 만 구현하면 교체할 수 있다."""
from pathlib import Path

from .chunking import make_chunks
from .config import settings
from .quote import RATE_SOURCE, QuoteRequest, estimate, validate
from .retrieval import hybrid_search

REF_DIR = Path(__file__).resolve().parent.parent / "data" / "quote"
REF_FILTER = {"kind": "quote_ref"}
SAMPLE_NOTICE = "※ 단가·공수는 샘플 가정값이며 실제 계약 금액이 아닙니다."


def ensure_refs_loaded(store, embedder) -> int:
    """data/quote 근거 문서를 적재한다. content_hash 로 중복을 막으므로 여러 번 불러도 안전."""
    chunks = [c for p in sorted(REF_DIR.glob("*.md"))
              for c in make_chunks(p.read_text(encoding="utf-8"), p.name, settings.chunk_size, REF_FILTER)]
    if not chunks:
        return 0
    return store.add_chunks(chunks, embedder.embed_documents([c["content"] for c in chunks]))


# --- 도구: (state, store, embedder) -> trace 에 남길 요약 문자열 ---

def search_refs(state, store, embedder) -> str:
    ensure_refs_loaded(store, embedder)
    req = state["req"]
    queries = ["연구행정 PI 과업 범위 사례", "컨설팅 단가 혼합 단가 부가세"] + \
              [f"{s} 과업 기본 공수" for s in ["common"] + req.scopes]
    refs: dict[str, dict] = {}
    for q in queries:
        for d in hybrid_search(store, embedder, q, k=2, where=REF_FILTER):
            refs.setdefault(d["chunk_id"], d)
    state["refs"] = list(refs.values())
    return f"근거 {len(refs)}개 청크 검색 ({', '.join(sorted({d['source'] for d in refs.values()})) or '없음'})"


def tool_estimate(state, store, embedder) -> str:
    state["quote"] = estimate(state["req"])
    return f"{len(state['quote']['items'])}개 항목, 합계 {state['quote']['total']:,}원"


def render_quote(state, store, embedder) -> str:
    req, q = state["req"], state["quote"]
    lines = [f"# 견적서 — {req.university}", "",
             f"- 연구자 수: {req.researchers:,}명 (규모 계수 {q['factor']})",
             f"- 혼합 단가: {q['rate']:,}원/MM (출처: {RATE_SOURCE})", "",
             "| 과업 | 공수(MM) | 금액(원) | 출처 |", "|---|---:|---:|---|"]
    lines += [f"| {i['name']} | {i['mm']} | {i['amount']:,} | {i['source']} |" for i in q["items"]]
    lines += ["", f"- 소계: {q['subtotal']:,}원", f"- 부가세(10%): {q['vat']:,}원", f"- **합계: {q['total']:,}원**", ""]
    sources = sorted({d["source"] for d in state["refs"]})
    lines.append(f"근거 문서: {', '.join(sources)}" if sources else "⚠ 검색된 근거 문서가 없습니다.")
    lines.append(SAMPLE_NOTICE)
    state["markdown"] = "\n".join(lines)
    return f"견적서 {len(lines)}줄 작성"


TOOLS = {"search_refs": search_refs, "estimate": tool_estimate, "render_quote": render_quote}


class RulePlanner:
    """상태에서 아직 없는 것을 순서대로 채운다: 근거 → 계산 → 견적서."""

    def next_action(self, state) -> str | None:
        for key, tool in (("refs", "search_refs"), ("quote", "estimate"), ("markdown", "render_quote")):
            if key not in state:
                return tool
        return None


def run_agent(req: QuoteRequest, store, embedder, planner=None, max_steps: int = 6) -> dict:
    result = {"status": "ok", "questions": [], "quote": None, "quote_markdown": "", "sources": [], "trace": []}
    questions = validate(req)
    if questions:
        return {**result, "status": "needs_info", "questions": questions}
    planner = planner or RulePlanner()
    state = {"req": req}
    for step in range(1, max_steps + 1):
        tool = planner.next_action(state)
        if tool is None:
            return {**result, "quote": state["quote"], "quote_markdown": state["markdown"],
                    "sources": [{"source": d["source"], "chunk_id": d["chunk_id"]} for d in state["refs"]]}
        if tool not in TOOLS:
            return {**result, "status": "error", "questions": [f"알 수 없는 도구: {tool}"]}
        summary = TOOLS[tool](state, store, embedder)
        result["trace"].append({"step": step, "tool": tool, "summary": summary})
    return {**result, "status": "error", "questions": [f"최대 반복({max_steps}) 초과"]}
