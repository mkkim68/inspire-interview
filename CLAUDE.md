# CLAUDE.md — 이 저장소에서 일할 때의 규칙

## 프로젝트
사내 문서 RAG API 템플릿. FastAPI + Postgres(pgvector) + 하이브리드 검색(벡터 + 키워드, RRF).
면접 과제에 맞게 이 뼈대를 확장한다.

## 구조
- `app/config.py`     환경변수 (.env)
- `app/chunking.py`   재귀 청킹 + content_hash (중복 적재 방지)
- `app/embeddings.py` E5Embedder(실제) / FakeEmbedder(테스트)
- `app/store.py`      PgVectorStore / MemoryStore — 같은 메서드: add_chunks, vector_search, keyword_search, count, clear
- `app/retrieval.py`  rrf_fuse, hybrid_search(mode=vector|keyword|hybrid)
- `app/rag.py`        프롬프트 조립, 인용 검증
- `app/llm.py`        LLM 호출 래퍼 (anthropic | openai | none)
- `app/main.py`       엔드포인트: /health /ingest /search /ask /reset
- `scripts/eval_retrieval.py`  모드별 Recall@K, MRR
- `tests/`            DB·네트워크·키 없이 도는 테스트

## 작업 방식 (반드시 지킬 것)
1. 코드를 쓰기 전에 **계획을 먼저 짧게 제시**하고, 무엇을 바꿀지·완료 기준(테스트)을 적는다.
2. 작은 단위로 바꾸고, 바꿀 때마다 `python -m pytest -q` 를 실행한다.
3. **기존 테스트를 삭제하거나 약하게 바꾸지 않는다.** 실패하면 코드를 고친다.
4. 새 기능에는 테스트를 같이 추가한다. 외부 API·DB가 필요 없는 형태로 (FakeEmbedder, MemoryStore, LLM_PROVIDER=none).
5. 존재하는지 확실하지 않은 라이브러리 함수는 쓰기 전에 확인한다.
6. API 키·비밀번호를 코드에 쓰지 않는다. `.env` 만 사용.
7. 저장소 인터페이스(store)를 바꾸면 MemoryStore와 PgVectorStore를 **둘 다** 고친다.
8. 끝나면 무엇을 바꿨는지, 어떤 테스트로 확인했는지, 남은 한계가 무엇인지 3줄로 요약한다.

## 자주 쓰는 명령
- 테스트: `python -m pytest -q`
- 서버: `uvicorn app.main:app --reload`  → http://localhost:8000/docs
- DB: `docker compose up -d db`
- 평가: `python -m scripts.eval_retrieval --k 3`
