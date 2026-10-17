"""견적 에이전트 테스트. 기대값은 specs/001-pi-quote-agent/data-model.md 의 기준 예시 (샘플 가정값)."""
from dataclasses import replace

from app.agent import REF_DIR, run_agent
from app.embeddings import get_embedder
from app.main import get_store
from app.quote import (BLENDED_RATE, MODULES, RATES, REFERENCE_CASE, SCOPES, QuoteRequest, compare,
                       estimate, propose_options)

ALL = list(SCOPES)
SNU = QuoteRequest(university="서울대학교", professors=50, researchers=250, months=3, scopes=ALL)
KOREA_2M = QuoteRequest(university="고려대학교", professors=100, researchers=500, months=2, scopes=ALL)
KOREA_1M = replace(KOREA_2M, months=1)


def _run(req):
    get_store().clear()
    return run_agent(req, get_store(), get_embedder())


# --- US4: 규모·기간으로 금액 산정 ---

def test_snu_reference_reproduces_three_months():
    q = estimate(SNU)
    assert q["total_mm"] == 11.0
    assert q["schedule"]["std_months"] == 2.75 and q["schedule"]["premium"] == 1.0
    assert (q["base"], q["surcharge"], q["vat"], q["total"]) == (116_600_000, 0, 11_660_000, 128_260_000)


def test_korea_two_months_has_compression_premium():
    q = estimate(KOREA_2M)
    assert q["total_mm"] == 16.0
    assert q["schedule"] == {"std_months": 4.0, "team": 8.0, "premium": 1.15, "feasible": True}
    assert (q["base"], q["surcharge"], q["subtotal"]) == (169_600_000, 25_440_000, 195_040_000)
    assert (q["vat"], q["total"]) == (19_504_000, 214_544_000)


def test_estimate_is_deterministic():
    assert all(estimate(KOREA_2M) == estimate(KOREA_2M) for _ in range(100))


def test_more_professors_more_effort():
    assert estimate(replace(SNU, professors=80))["total_mm"] > estimate(SNU)["total_mm"]


def test_more_researchers_more_effort():
    assert estimate(replace(SNU, researchers=1000))["total_mm"] > estimate(SNU)["total_mm"]


def test_researchers_drive_funding_not_planning():
    """연구자 수는 연구비 관리 공수를 키우고, 연구기획 공수는 바꾸지 않는다."""
    mm = lambda req, key: next(i["mm"] for i in estimate(req)["items"] if i["module"] == key)
    more = replace(SNU, researchers=1000)
    assert mm(more, "funding") > mm(SNU, "funding")
    assert mm(more, "planning") == mm(SNU, "planning")


def test_shorter_period_costs_more():
    totals = [estimate(replace(KOREA_2M, months=m))["total"] for m in (4, 3, 2)]
    assert totals[0] < totals[1] < totals[2]
    assert estimate(replace(KOREA_2M, months=6))["total"] == totals[0]   # 표준 기간 이상은 할증 없음


def test_more_scope_costs_more():
    assert estimate(replace(SNU, scopes=["funding"]))["total"] < estimate(SNU)["total"]


def test_researchers_default_is_assumed_and_flagged():
    q = estimate(replace(SNU, researchers=None))
    assert q["researchers"] == 250 and q["researchers_assumed"] is True
    assert estimate(SNU)["researchers_assumed"] is False


# --- US5: 실행 불가 → 대안 ---

def test_korea_one_month_is_infeasible():
    assert estimate(KOREA_1M)["schedule"]["feasible"] is False


def test_options_for_infeasible_request():
    a, b = propose_options(KOREA_1M)
    assert a["request"]["months"] == 2 and a["estimate"]["total"] == 214_544_000
    assert b["request"]["months"] == 1 and b["request"]["scopes"] == ["planning", "award"]
    assert b["estimate"]["total_mm"] == 8.0 and b["estimate"]["schedule"]["feasible"]


def test_agent_infeasible_path():
    res = _run(KOREA_1M)
    assert res["status"] == "infeasible" and res["quote"] is None and len(res["options"]) == 2
    tools = [t["tool"] for t in res["trace"]]
    assert "propose_options" in tools and "price" not in tools
    assert "8명" in res["quote_markdown"]
    assert "할증 ×1.45" not in res["quote_markdown"]   # 불가능한 일정의 할증은 보여주지 않는다


# --- US6: 기준 사례 비교 ---

def test_compare_with_snu():
    c = compare(estimate(KOREA_2M), estimate(SNU))
    assert c["ratios"] == {"professors": 2.0, "researchers": 2.0, "total_mm": 1.45, "months": 0.67, "total": 1.67}


def test_agent_ok_path_trace_and_numbers():
    res = _run(KOREA_2M)
    assert res["status"] == "ok"
    assert [t["tool"] for t in res["trace"]] == \
        ["search_refs", "estimate_effort", "check_schedule", "price", "compare_case", "check_evidence",
         "render_quote"]
    assert res["quote"] == estimate(KOREA_2M)
    md = res["quote_markdown"]
    for n in (res["quote"]["base"], res["quote"]["surcharge"], res["quote"]["vat"], res["quote"]["total"]):
        assert f"{n:,}" in md
    assert "서울대학교" in md and res["comparison"]["ratios"]["total"] == 1.67


# --- 근거 추적 ---

def test_sources_are_real_reference_docs():
    files = {p.name for p in REF_DIR.glob("*.md")}
    res = _run(KOREA_2M)
    assert res["sources"] and {s["source"] for s in res["sources"]} <= files
    assert all(i["source"] in files for i in res["quote"]["items"])


def test_sample_notice_in_quote():
    assert "샘플 가정값" in _run(KOREA_2M)["quote_markdown"]


def test_constants_match_reference_docs():
    """계산 상수와 근거 문서의 숫자가 어긋나면 실패 — 문서만 고치고 코드를 안 고치는 실수를 잡는다."""
    rate_doc = (REF_DIR / "rate_card.md").read_text(encoding="utf-8")
    module_doc = (REF_DIR / "modules.md").read_text(encoding="utf-8")
    case_doc = (REF_DIR / "snu_pi_case.md").read_text(encoding="utf-8")
    for grade, (price, ratio) in RATES.items():
        assert f"| {grade} | {price:,} | {ratio} |" in rate_doc
    assert f"{BLENDED_RATE:,}원/MM" in rate_doc
    for key, (name, fixed, per_p, per_r) in MODULES.items():
        assert f"{key} {name}: 고정 {fixed} MM + 교수 1명당 {per_p} MM + 연구자 1명당 {per_r} MM" in module_doc
    c = REFERENCE_CASE
    assert f"교수 {c.professors}명, 연구자 {c.researchers}명, 기간 {c.months}개월" in case_doc


# --- 되묻기 ---

def test_missing_fields_ask():
    res = _run(QuoteRequest(scopes=["funding"]))
    assert res["status"] == "needs_info" and len(res["questions"]) == 3   # 대학명, 교수 수, 기간


def test_researchers_below_professors_asks():
    assert _run(replace(SNU, researchers=10))["status"] == "needs_info"


def test_unknown_scope_is_reported():
    res = _run(replace(SNU, scopes=["funding", "hr"]))
    assert res["status"] == "needs_info" and any("hr" in q for q in res["questions"])


def test_max_steps_stops_loop():
    class Stuck:
        def next_action(self, state):
            return "estimate_effort"
    get_store().clear()
    res = run_agent(SNU, get_store(), get_embedder(), planner=Stuck(), max_steps=3)
    assert res["status"] == "error" and len(res["trace"]) == 3


# --- API·화면 ---

def test_quote_api(client):
    body = client.post("/quote", json={"university": "고려대학교", "professors": 100, "researchers": 500,
                                       "months": 2, "scopes": ALL}).json()
    assert body["status"] == "ok" and body["quote"]["total"] == 214_544_000


def test_quote_api_infeasible(client):
    body = client.post("/quote", json={"university": "고려대학교", "professors": 100, "months": 1,
                                       "scopes": ALL}).json()
    assert body["status"] == "infeasible" and body["options"]


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "/quote" in r.text and "months" in r.text


# --- 근거 상태 표시 (실제 사례) ---

def test_quote_shows_evidence_and_requires_review():
    res = _run(KOREA_2M)
    assert res["review"]["required"] is True and res["review"]["reasons"]
    assert res["evidence"]["groups"]["enterprise"]["n"] == 5
    md = res["quote_markdown"]
    assert "담당자 검토 필요" in md and "검증 아님" in md and "동의대학교" in md
