# interview-starter

사내 문서 Q&A를 위한 RAG API 뼈대예요. 면접 과제가 나오면 여기서부터 확장해요.

```
문서(.md/.txt) → 재귀 청킹 → 임베딩(multilingual-e5) → Postgres + pgvector
질문 → 벡터 검색 + 키워드 검색 → RRF 합치기 → 출처 번호 붙인 프롬프트 → LLM → 인용 검증
```

## 처음 한 번 (맥, 터미널에 한 줄씩)

```bash
conda activate interview
```
```bash
cd ~/interview/interview-starter
```
```bash
pip install -r requirements.txt
```
```bash
cp .env.example .env
```
그다음 `.env` 파일을 열어 `ANTHROPIC_API_KEY=` 뒤에 키를 붙여 넣어요.

## 매번 실행

```bash
docker compose up -d db
```
```bash
python -m pytest -q
```
→ `11 passed` 가 나오면 정상이에요. 이 테스트는 DB나 키가 없어도 돌아가요.

```bash
python -m scripts.ingest data/docs
```
```bash
uvicorn app.main:app --reload
```
브라우저에서 http://localhost:8000/docs 를 열면 `/ask` 를 바로 눌러볼 수 있어요.

```bash
python -m scripts.eval_retrieval --k 3
```
→ vector / keyword / hybrid 의 Recall@3, MRR 을 한 번에 비교해요.

## Docker가 안 될 때 (비상구)

`.env` 에서 `DATABASE_URL=` 을 비워 두면 메모리 저장소로 똑같이 돌아가요. 키가 없으면 `LLM_PROVIDER=none` 으로 검색 결과에서 발췌한 답을 보여줘요.

## 면접에서 설명할 포인트

| 선택 | 이유 |
|---|---|
| 재귀 청킹 + content_hash | 문단 단위로 의미를 유지하고, 다시 적재해도 중복이 안 생겨요 (멱등) |
| multilingual-e5 | 한국어 문서라 다국어 임베딩. 가볍고(384차원) 노트북에서도 빨라요 |
| pgvector + HNSW | Postgres 하나로 벡터·메타데이터·키워드 검색을 같이 해요 |
| 하이브리드 + RRF | 의미 검색이 놓치는 에러코드·고유명사를 키워드가 잡아요. 순위만 합쳐서 정규화가 필요 없어요 |
| 메타데이터 필터 (`where`) | 부서별 권한 필터를 LLM에 넣기 **전에** 적용해요 |
| 인용 검증 | 답의 [n] 이 실제 검색된 문서인지 코드로 확인해요 (환각 방지) |
| 저장소 2종 + 가짜 임베딩 | 테스트가 네트워크·DB 없이 돌아요. 실패 원인을 분리하기 쉬워요 |

## 확장 아이디어 (과제에 따라)
- 리랭커 추가 (상위 20개를 cross-encoder로 재정렬)
- PDF 로더 (`pypdf`), 표가 많으면 Docling
- `/ask` 응답에 토큰 사용량·지연시간 로깅
- LLM-as-judge 로 답변 품질 1~5점 채점
- 에이전트화: 검색을 도구로 두고 계산·DB 조회 도구 추가
