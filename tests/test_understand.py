"""LLM 해석 + 원문 근거 검증 테스트. 실제 API 대신 가짜 LLM 응답(Understood)을 주입한다."""
from app.intake import ChatSession, reply
from app.understand import Understood, understand

MSG = "고려대인데요, 교수님이 한 300분 정도 계시고 석 달 안에 끝났으면 해요. 예산은 1.5억 안쪽이요"


def fake(**kw):
    return lambda _msg: Understood(intent="conditions", **kw)


def test_fuzzy_values_pass_and_are_echoed():
    u = understand(MSG, call=fake(university="고려대학교", professors=300, professors_text="300분 정도",
                                  months=3, months_text="석 달", budget_won=150_000_000, budget_text="1.5억 안쪽"))
    assert (u["professors"], u["months"], u["budget"]) == (300, 3, 150_000_000)
    assert u["source"] == "llm" and not u["dropped"]
    assert any("석 달" in n for n in u["notes"])      # 숫자 없는 해석은 사용자에게 되보여 준다


def test_number_not_matching_span_is_dropped():
    u = understand(MSG, call=fake(professors=3000, professors_text="300분 정도"))
    assert u["professors"] is None and any("교수 수" in d for d in u["dropped"])


def test_span_not_in_message_is_dropped():
    u = understand(MSG, call=fake(researchers=2000, researchers_text="연구자 2000명"))
    assert u["researchers"] is None and any("원문 근거" in d for d in u["dropped"])


def test_budget_span_checked_with_parser():
    bad = understand(MSG, call=fake(budget_won=15_000_000, budget_text="1.5억 안쪽"))
    assert bad["budget"] is None and bad["dropped"]


def test_weeks_span_rounds_up():
    u = understand("8주 정도면 좋겠어요", call=fake(months=2, months_text="8주 정도"))
    assert u["months"] == 2


def test_llm_failure_falls_back_to_regex():
    def boom(_):
        raise RuntimeError("network")
    u = understand("고려대 교수 100명 2개월", call=boom)
    assert u["source"].startswith("regex") and u["professors"] == 100 and u["months"] == 2


def test_default_is_regex_without_llm():
    assert understand("고려대 교수 100명")["source"] == "regex"


def _reply(monkeypatch, session, msg, call):
    import app.understand as und
    from app.embeddings import get_embedder
    from app.main import get_store
    monkeypatch.setattr(und, "_call_claude", call)
    monkeypatch.setattr(und, "llm_enabled", lambda: True)
    return reply(session, msg, get_store(), get_embedder())


def test_correction_removes_scope(client, monkeypatch):
    s = ChatSession()
    s.slots.update(university="고려대학교", professors=100, researchers=500, months=4,
                   scopes=["funding", "outcome", "roadmap"])
    out = _reply(monkeypatch, s, "로드맵은 빼주세요",
                 lambda _m: Understood(intent="correction", remove_scopes=["roadmap"]))
    assert s.slots["scopes"] == ["funding", "outcome"] and out["understood"]["intent"] == "correction"


def test_dropped_value_is_asked_back(client, monkeypatch):
    out = _reply(monkeypatch, ChatSession(), MSG,
                 fake(university="고려대학교", professors=3000, professors_text="300분 정도"))
    assert out["status"] == "needs_info" and "확인이 필요해요" in out["reply"]
