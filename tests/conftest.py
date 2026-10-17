"""테스트는 네트워크·DB·API 키 없이 돈다: 가짜 임베딩 + 메모리 저장소 + 오프라인 LLM.
Postgres로도 돌리고 싶으면: TEST_DATABASE_URL=postgresql://... pytest"""
import os

os.environ["EMBEDDER"] = "fake"
os.environ["EMBED_DIM"] = "256"
os.environ["LLM_PROVIDER"] = "none"
os.environ["QUOTE_RAG"] = "0"
os.environ["EXTRACTOR"] = "regex"        # LLM 해석은 test_understand.py 에서 가짜 응답으로 검사          # RAG 견적 단계는 테스트에서 명시적으로 켠다
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, get_store  # noqa: E402


@pytest.fixture()
def client():
    get_store().clear()
    c = TestClient(app)
    c.post("/ingest", json={"folder": "data/docs"})
    yield c
    get_store().clear()
