"""견적 에이전트 테스트. 기대값은 specs/001-pi-quote-agent/data-model.md 의 기준 예시."""
from app.agent import run_agent
from app.embeddings import get_embedder
from app.main import get_store
from app.quote import QuoteRequest, estimate

KOREA = QuoteRequest(university="고려대학교", researchers=2000, scopes=["funding", "roadmap"])


# --- US1: 항목별 견적서 ---

def test_estimate_reference_example():
    q = estimate(KOREA)
    assert [i["module"] for i in q["items"]] == ["common", "funding", "roadmap"]
    assert sum(i["mm"] for i in q["items"]) == 10.0
    assert q["rate"] == 10_600_000
    assert (q["subtotal"], q["vat"], q["total"]) == (106_000_000, 10_600_000, 116_600_000)


def test_estimate_is_deterministic():
    assert all(estimate(KOREA) == estimate(KOREA) for _ in range(100))


def test_more_scope_costs_more():
    more = QuoteRequest(university="고려대학교", researchers=2000, scopes=["funding", "roadmap", "planning"])
    assert estimate(more)["total"] > estimate(KOREA)["total"]


def test_scale_factor_applies():
    big = QuoteRequest(university="고려대학교", researchers=5000, scopes=["funding", "roadmap"])
    small = QuoteRequest(university="고려대학교", researchers=500, scopes=["funding", "roadmap"])
    assert estimate(big)["factor"] == 1.3 and estimate(small)["factor"] == 0.8
    assert estimate(small)["total"] < estimate(KOREA)["total"] < estimate(big)["total"]


def test_vat_truncates_won():
    # 소규모(0.8) × common 4.0 → 3.2MM, planning 2.0 → 1.6MM: 소계 50,880,000 → VAT 5,088,000
    q = estimate(QuoteRequest(university="A대", researchers=100, scopes=["planning"]))
    assert q["vat"] == q["subtotal"] // 10


def test_run_agent_renders_estimate_numbers():
    get_store().clear()
    res = run_agent(KOREA, get_store(), get_embedder())
    assert res["status"] == "ok"
    md = res["quote_markdown"]
    assert "고려대학교" in md
    for n in (res["quote"]["subtotal"], res["quote"]["vat"], res["quote"]["total"]):
        assert f"{n:,}" in md
    assert res["quote"] == estimate(KOREA)


def test_quote_api(client):
    r = client.post("/quote", json={"university": "고려대학교", "researchers": 2000, "scopes": ["funding", "roadmap"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["quote"]["total"] == 116_600_000


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "/quote" in r.text


# --- US2: 근거 확인 ---

def _ok_result():
    get_store().clear()
    return run_agent(KOREA, get_store(), get_embedder())


def test_sources_are_real_reference_docs():
    from app.agent import REF_DIR
    files = {p.name for p in REF_DIR.glob("*.md")}
    res = _ok_result()
    assert res["sources"] and {s["source"] for s in res["sources"]} <= files
    assert all(i["source"] in files for i in res["quote"]["items"])


def test_trace_order():
    assert [t["tool"] for t in _ok_result()["trace"]] == ["search_refs", "estimate", "render_quote"]


def test_sample_notice_in_quote():
    assert "샘플 가정값" in _ok_result()["quote_markdown"]


def test_constants_match_reference_docs():
    """계산 상수와 근거 문서의 숫자가 어긋나면 실패 — 문서만 고치고 코드를 안 고치는 실수를 잡는다."""
    from app.agent import REF_DIR
    from app.quote import BLENDED_RATE, MODULES, RATES
    rate_doc = (REF_DIR / "rate_card.md").read_text(encoding="utf-8")
    module_doc = (REF_DIR / "modules.md").read_text(encoding="utf-8")
    for grade, (price, ratio) in RATES.items():
        assert f"| {grade} | {price:,} | {ratio} |" in rate_doc
    assert f"{BLENDED_RATE:,}원/MM" in rate_doc
    for key, (name, base) in MODULES.items():
        assert f"{key} {name}: 기본 공수 {base} MM" in module_doc


# --- US3: 정보 부족 시 되묻기 ---

def _ask(**kw):
    return run_agent(QuoteRequest(**kw), get_store(), get_embedder())


def test_missing_scope_asks():
    res = _ask(university="고려대학교", researchers=2000, scopes=[])
    assert res["status"] == "needs_info" and res["quote"] is None
    assert any("과업 범위" in q for q in res["questions"])


def test_missing_university_and_researchers_asks_both():
    res = _ask(scopes=["funding"])
    assert res["status"] == "needs_info" and len(res["questions"]) == 2


def test_zero_researchers_asks():
    assert _ask(university="A대", researchers=0, scopes=["funding"])["status"] == "needs_info"


def test_unknown_scope_is_reported():
    res = _ask(university="A대", researchers=100, scopes=["funding", "hr"])
    assert res["status"] == "needs_info" and any("hr" in q for q in res["questions"])


def test_max_steps_stops_loop():
    class Stuck:
        def next_action(self, state):
            return "estimate"
    get_store().clear()
    res = run_agent(KOREA, get_store(), get_embedder(), planner=Stuck(), max_steps=3)
    assert res["status"] == "error" and len(res["trace"]) == 3


def test_quote_api_needs_info(client):
    body = client.post("/quote", json={"university": "고려대학교", "researchers": 2000}).json()
    assert body["status"] == "needs_info" and body["questions"]
