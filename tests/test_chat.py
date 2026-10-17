"""대화형 접수 창구 테스트 (규칙 기반 추출, 키 없이)."""
from app.intake import extract

ALL = {"planning", "award", "funding", "outcome", "roadmap"}


# --- 조건 추출 ---

def test_extract_full_sentence():
    e = extract("고려대인데 교수는 100명쯤이고 연구비 관리랑 로드맵만, 두 달 안에 끝내야 해요. 주 1회 보고도 필요해요")
    assert e["university"] == "고려대학교"
    assert e["professors"] == 100 and e["months"] == 2
    assert set(e["scopes"]) == {"funding", "roadmap"}
    assert any("주 1회 보고" in u for u in e["unhandled"])


def test_extract_researchers_and_comma_numbers():
    e = extract("서울대학교, 교수 1,200명, 연구원 6,000명, 6개월")
    assert (e["university"], e["professors"], e["researchers"], e["months"]) == ("서울대학교", 1200, 6000, 6)


def test_extract_weeks_round_up_to_months():
    assert extract("8주 안에")["months"] == 2
    assert extract("10주 정도")["months"] == 3


def test_extract_all_scopes():
    assert set(extract("전체 범위로 해주세요")["scopes"]) == ALL


def test_max_is_not_a_university():
    e = extract("최대 8명까지 투입 가능한가요")
    assert e["university"] is None and e["professors"] is None


def test_extract_nothing():
    e = extract("안녕하세요")
    assert e == {"university": None, "professors": None, "researchers": None, "months": None, "scopes": [],
                 "unhandled": []}


# --- 다턴 대화 (/chat) ---

def _chat(client, sid, msg):
    r = client.post("/chat", json={"session_id": sid, "message": msg})
    assert r.status_code == 200
    return r.json()


def test_multi_turn_asks_then_quotes(client):
    first = _chat(client, "t1", "고려대 견적 받고 싶어요")
    assert first["status"] == "needs_info"
    assert first["slots"]["university"] == "고려대학교"
    assert any("교수" in q for q in first["questions"]) and any("기간" in q for q in first["questions"])

    second = _chat(client, "t1", "교수 100명, 연구자 500명, 전체 범위로 2개월")
    assert second["status"] == "ok"
    assert second["result"]["quote"]["total"] == 214_544_000
    assert "214,544,000" in second["reply"]


def test_unhandled_conditions_go_to_review(client):
    res = _chat(client, "t2", "고려대 교수 100명 연구자 500명 전체 범위 2개월, 현장 상주 필요")
    assert res["status"] == "ok"
    assert any("현장 상주" in u for u in res["unhandled"])
    assert any("반영 안 된" in r for r in res["result"]["review"]["reasons"])
    assert "반영 안 된" in res["reply"]


def test_reset_starts_over(client):
    _chat(client, "t3", "고려대 교수 100명")
    res = _chat(client, "t3", "처음부터 다시")
    assert res["status"] == "reset" and res["slots"]["university"] is None


def test_sessions_are_separate(client):
    _chat(client, "a", "고려대 교수 100명")
    assert _chat(client, "b", "안녕하세요")["slots"]["university"] is None
