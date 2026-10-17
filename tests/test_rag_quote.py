"""RAG 견적 테스트 — data/quote/mock/ 가상 데이터 사용 (실제 데이터 아님)."""
from app.agent import RulePlanner, run_agent
from app.embeddings import get_embedder
from app.intake import ChatSession
from app.main import get_store
from app.quote import QuoteRequest
from app.rag import check_citations
from app.rag_quote import (case_based_range, draft_narrative, load_mock_cases, retrieve_similar_cases,
                           rfp_conditions)

REQ = QuoteRequest(university="고려대학교", professors=300, researchers=1200, months=4, scopes=["funding", "roadmap"])


def _fresh():
    get_store().clear()
    return get_store(), get_embedder()


# --- ① 유사 사례 검색 ---

def test_mock_cases_are_labeled():
    cases = load_mock_cases()
    assert len(cases) == 30 and all(c["mock"] for c in cases)


def test_similar_cases_share_scope():
    store, emb = _fresh()
    hits = retrieve_similar_cases(REQ, store, emb, k=5)
    assert len(hits) == 5
    assert sum(bool(set(h["scopes"]) & set(REQ.scopes)) for h in hits) >= 3


def test_case_based_range_is_ordered():
    store, emb = _fresh()
    r = case_based_range(retrieve_similar_cases(REQ, store, emb, k=5), REQ)
    assert r["n"] == 5 and r["low"] <= r["median"] <= r["high"]


# --- ② RFP 조항 검색 → 조건 ---

def test_rfp_conditions_from_retrieved_clauses():
    store, emb = _fresh()
    out = rfp_conditions("rfp_garam", store, emb)
    e = out["conditions"]
    assert (e["university"], e["professors"], e["researchers"], e["months"]) == ("가람대학교", 420, 2100, 4)
    assert e["budget"] == 180_000_000
    assert {"award", "funding", "roadmap"} <= set(e["scopes"])
    assert any("보고" in u for u in e["unhandled"])
    assert set(out["clauses"]) >= {"사업기간", "사업예산", "과업 범위"}


def test_rfp_endpoint_fills_chat_session(client):
    r = client.post("/rfp", json={"session_id": "rfp1", "name": "rfp_nuri"}).json()
    assert r["slots"]["university"] == "누리대학교" and r["slots"]["months"] == 3
    assert r["status"] in ("ok", "infeasible")


# --- ③ 과업 수행 내용 생성 (인용 포함) ---

def test_narrative_cites_retrieved_proposals():
    store, emb = _fresh()
    n = draft_narrative(REQ, store, emb)
    assert check_citations(n["text"], len(n["sources"]))["ok"]
    assert "연구비" in n["text"] and n["sources"]


# --- 에이전트 연결 ---

def test_agent_with_rag_adds_steps():
    store, emb = _fresh()
    res = run_agent(REQ, store, emb, planner=RulePlanner(use_rag=True))
    tools = [t["tool"] for t in res["trace"]]
    assert tools[-3:] == ["retrieve_cases", "draft_narrative", "render_quote"]
    md = res["quote_markdown"]
    assert "유사 사례" in md and "가상 데이터" in md and "과업 수행 내용" in md
    assert res["similar_cases"] and res["narrative"]["check"]["ok"]


def test_agent_without_rag_is_unchanged():
    store, emb = _fresh()
    res = run_agent(REQ, store, emb)
    assert "retrieve_cases" not in [t["tool"] for t in res["trace"]]


# --- 긴 조항 청킹 (e5 512토큰 한계, 뒷부분 손실 방지) ---

def test_long_clause_is_split_with_heading_and_nothing_lost():
    from app.rag_quote import _sections
    body = " ".join(f"세부 과업 {i}번은 연구비 정산 절차를 점검한다." for i in range(60)) + " 마지막 조건은 보안서약서 제출이다."
    chunks = _sections(f"# 가상 RFP\n\n## 4. 과업 범위\n{body}\n\n## 5. 기타\n보고 월 1회.", "rfp_long", {"kind": "rfp"})
    scope = [c for c in chunks if "과업 범위" in c["content"]]
    assert len(scope) > 1                                       # 500자 넘는 조항은 나뉜다
    assert all(c["content"].startswith("# 4. 과업 범위") for c in scope)   # 조각마다 조항 제목
    assert all(len(c["content"]) <= 520 for c in scope)
    assert any("보안서약서" in c["content"] for c in scope)       # 뒷부분이 버려지지 않는다
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)   # ID 중복 없음 (RRF 덮어쓰기 방지)
