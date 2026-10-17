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
