def test_health(client):
    r = client.get("/health").json()
    assert r["ok"] and r["chunks"] > 0


def test_ingest_is_idempotent(client):
    again = client.post("/ingest", json={"folder": "data/docs"}).json()
    assert again["added"] == 0 and again["skipped_duplicates"] == again["chunks"]


def test_ingest_bad_folder(client):
    assert client.post("/ingest", json={"folder": "nope/"}).status_code == 400


def test_keyword_finds_exact_error_code(client):
    res = client.post("/search", json={"query": "0x8007", "mode": "keyword", "k": 1}).json()["results"]
    assert res and res[0]["source"] == "it_security.md"


def test_hybrid_search(client):
    res = client.post("/search", json={"query": "연차 이월", "k": 3}).json()["results"]
    assert res[0]["source"] == "hr_leave.md"


def test_metadata_filter(client):
    client.post("/ingest", json={"docs": [{"source": "secret.md", "text": "임원 연봉 테이블 연차", "meta": {"dept": "exec"}}]})
    res = client.post("/search", json={"query": "연차", "k": 5, "where": {"dept": "exec"}}).json()["results"]
    assert [r["source"] for r in res] == ["secret.md"]


def test_ask_returns_cited_answer(client):
    r = client.post("/ask", json={"query": "연차 이월 규정", "k": 3}).json()
    assert r["check"]["ok"] and r["sources"][0]["n"] == 1
    assert "[1]" in r["answer"]

def test_relative_threshold_drops_weak_results(client):
    loose = client.post("/search", json={"query": "연차 이월", "k": 3}).json()["results"]
    strict = client.post("/search", json={"query": "연차 이월", "k": 3, "min_rel_score": 0.6}).json()["results"]
    assert len(strict) < len(loose)
    assert strict[0]["source"] == "hr_leave.md"