"""견적 RAG: 검색 결과가 견적에 실제로 쓰이는 세 곳. 데이터는 data/quote/mock/ 가상 데이터.
  ① 유사 사례 검색  → 사례 기반 추정 범위, 공식 금액과 교차검증
  ② RFP 조항 검색   → 사업기간·예산·범위 조항에서 견적 조건 추출
  ③ 과업 수행 내용   → 과거 제안서 문단 검색 → [n] 인용 붙인 설명 (LLM 있으면 생성, 없으면 발췌)
숫자는 여기서도 코드가 계산한다 (검색은 '어떤 사례·조항을 볼지'만 정한다)."""
import json
import os
import re
import statistics
from pathlib import Path

from . import llm
from .chunking import make_chunks
from .config import settings
from .quote import MODULES, QuoteRequest
from .rag import build_prompt, check_citations
from .retrieval import hybrid_search

MOCK_DIR = Path(__file__).resolve().parent.parent / "data" / "quote" / "mock"
CASE_FILTER = {"kind": "mock_case"}
PROPOSAL_FILTER = {"kind": "mock_proposal"}
RFP_SECTIONS = {"사업 개요": "사업 개요 발주기관 전임교원 연구자", "사업기간": "사업기간 계약일로부터 개월",
                "사업예산": "사업예산 금 원 부가가치세", "과업 범위": "과업 범위 프로세스 개선 로드맵",
                "기타 요구사항": "기타 요구사항 보고 상주"}


def load_mock_cases() -> list[dict]:
    return [json.loads(line) for line in (MOCK_DIR / "cases.jsonl").read_text(encoding="utf-8").splitlines() if line]


SECTION_MAX = 500   # e5 입력 한계 512토큰 안에 들어오도록 (한국어 약 700~800자에서 잘림)


def _sections(text: str, source: str, meta: dict) -> list[dict]:
    """'## ' 조항 단위로 자르고, 긴 조항은 조항 안에서 다시 나눈다.
    조항 제목을 '# 제목' 으로 바꿔 넘기면 make_chunks 가 조각마다 제목을 붙인다.
    source 에 조항 번호를 넣어 chunk_id 가 '문서#조항#조각' 으로 고유해진다 (RRF 덮어쓰기 방지)."""
    parts = [p.strip() for p in re.split(r"\n(?=## )", text) if p.strip().startswith("## ")]
    return [c for j, p in enumerate(parts) for c in make_chunks(p[1:], f"{source}#{j}", SECTION_MAX, meta)]


def _add(store, embedder, chunks: list[dict]) -> int:
    return store.add_chunks(chunks, embedder.embed_documents([c["content"] for c in chunks])) if chunks else 0


def ensure_mock_loaded(store, embedder) -> int:
    """가상 사례(1건 = 1청크)와 제안서 문단을 적재. content_hash 로 멱등."""
    cases = [make_chunks(f"{c['title']}\n유형: {c['type']}\n과업 범위: {c['scope_text']}", c["case_id"], 1000,
                         {**CASE_FILTER, "case_id": c["case_id"]})[0] for c in load_mock_cases()]
    proposals = _sections((MOCK_DIR / "proposals.md").read_text(encoding="utf-8"), "proposals.md", PROPOSAL_FILTER)
    return _add(store, embedder, cases + proposals)


def case_query(req: QuoteRequest) -> str:
    return "연구행정 과업 범위: " + ", ".join(MODULES[s][0] for s in req.scopes)


def retrieve_similar_cases(req: QuoteRequest, store, embedder, k: int = 5, mode: str = "hybrid",
                           query: str | None = None) -> list[dict]:
    """검색은 '어떤 사례가 비슷한가'만 정하고, 금액·기간은 정형 데이터(cases.jsonl)에서 가져온다."""
    ensure_mock_loaded(store, embedder)
    by_id = {c["case_id"]: c for c in load_mock_cases()}
    hits = hybrid_search(store, embedder, query or case_query(req), k, where=CASE_FILTER, mode=mode)
    return [{**by_id[h["meta"]["case_id"]], "score": h["score"]} for h in hits]


def case_based_range(cases: list[dict], req: QuoteRequest) -> dict:
    """사례 금액을 교수 수 비율의 제곱근으로 규모 보정(가정)한 뒤 최소·중앙·최대."""
    adj = sorted(int(c["price_vat_excl"] * (req.professors / c["professors"]) ** 0.5) for c in cases)
    return {"n": len(adj), "low": adj[0], "median": int(statistics.median(adj)), "high": adj[-1],
            "note": "가상 사례 금액 × √(교수 수 비율) 규모 보정 (가정)"} if adj else {"n": 0}


def cross_check(formula_price: int, rng: dict, tolerance: float = 0.25) -> dict:
    if not rng.get("n"):
        return {"agree": False, "diff": None}
    diff = (formula_price - rng["median"]) / rng["median"]
    return {"agree": abs(diff) <= tolerance, "diff": round(diff, 3)}


# --- ② RFP ---

def rfp_conditions(name: str, store, embedder, text: str | None = None) -> dict:
    """RFP 를 조항 단위로 적재하고, 견적에 필요한 조항을 검색해 그 조항에서만 조건을 뽑는다."""
    from .intake import extract
    text = text if text is not None else (MOCK_DIR / "rfps" / f"{name}.md").read_text(encoding="utf-8")
    where = {"kind": "rfp", "rfp_id": name}
    _add(store, embedder, _sections(text, name, where))
    clauses = {}
    for section, query in RFP_SECTIONS.items():
        hits = hybrid_search(store, embedder, query, 1, where=where)
        if hits:
            clauses[section] = hits[0]["content"]
    return {"clauses": clauses, "conditions": extract("\n".join(clauses.values()))}


# --- ③ 과업 수행 내용 ---

def _llm_available() -> bool:
    p = settings.llm_provider
    return p == "ollama" or (p == "anthropic" and os.getenv("ANTHROPIC_API_KEY")) or \
        (p == "openai" and os.getenv("OPENAI_API_KEY"))


def draft_narrative(req: QuoteRequest, store, embedder) -> dict:
    """범위별로 과거 제안서 문단을 검색해 [n] 으로 인용한다. 숫자는 쓰지 않는다."""
    ensure_mock_loaded(store, embedder)
    docs, seen = [], set()
    for key in ["common"] + list(req.scopes):
        for h in hybrid_search(store, embedder, f"{MODULES[key][0]} 수행 방법 산출물", 1, where=PROPOSAL_FILTER):
            if h["chunk_id"] not in seen:
                seen.add(h["chunk_id"])
                docs.append(h)
    if _llm_available():
        question = (f"{req.university} 견적서의 '과업 수행 내용' 문단을 범위별로 작성하세요. "
                    "금액·공수 같은 숫자는 쓰지 마세요.")
        text = llm.generate(build_prompt(question, docs))
    else:   # 키 없음: 검색된 문단의 첫 문장을 그대로 인용 (발췌형)
        lines = []
        for i, d in enumerate(docs, 1):
            title, _, body = d["content"].partition("\n")
            first = re.split(r"(?<=다\.)\s", body.strip())[0]
            lines.append(f"- {title.lstrip('# ')}: {first} [{i}]")
        text = "\n".join(lines)
    return {"text": text, "check": check_citations(text, len(docs)),
            "sources": [{"n": i, "source": d["source"], "chunk_id": d["chunk_id"]} for i, d in enumerate(docs, 1)],
            "mode": "llm" if _llm_available() else "extractive"}
