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

---

## 대학 연구행정 PI 견적 에이전트 (`/quote`)

서울대 「연구행정시스템 PI」 같은 용역을 다른 대학이 문의하면 견적서를 만들어 주는 기능.
설계 문서: `specs/001-pi-quote-agent/` (spec-kit: constitution → spec → plan → tasks → implement)

### 사용법
```bash
uvicorn app.main:app --reload      # http://localhost:8000/  (입력 폼)
curl -X POST localhost:8000/quote -H 'content-type: application/json' \
  -d '{"university":"고려대학교","professors":100,"researchers":500,"months":2,
       "scopes":["planning","award","funding","outcome","roadmap"]}'
# → 16.0MM, 8명 투입, 기간 할증 ×1.15, 합계 214,544,000원 (서울대 기준 대비 ×1.67)
# months=1 이면 → status "infeasible" + 대안 A(2개월) / 대안 B(범위 축소)
```
범위: `planning`(연구기획) `award`(과제수주) `funding`(연구비 관리) `outcome`(성과 활용) `roadmap`(차세대 시스템·로드맵).
공통 과업(현황 분석·To-Be 설계·사업관리)은 항상 포함. 연구자 수를 비우면 교수 수 × 5로 가정하고 견적서에 표시.

### 동작
```
입력(대학명·교수 수·연구자 수(선택)·기간·범위) ─(누락)→ needs_info + 질문 목록
   │
RulePlanner 가 상태를 보고 다음 도구 선택 (최대 10회, trace 기록)
   ├ search_refs      data/quote 근거 문서 적재(meta kind=quote_ref) + hybrid_search
   ├ estimate_effort  모듈별 공수 = 고정 + 교수 수×a + 연구자 수×b
   ├ check_schedule   필요 인원 = 공수 ÷ 기간 → 할증 / 실행 불가 판단
   ├ price            (가능) 공수 × 단가 + 할증 + VAT
   ├ propose_options  (불가) 대안 A 최소 가능 기간 / 대안 B 기간 유지·범위 축소
   ├ compare_case     서울대 기준 조건 대비 배율
   └ render_quote     계산 결과를 그대로 견적서로 포맷
→ status(ok|infeasible), quote, options, comparison, schedule, sources, trace
```

### 설계 원칙
- **숫자는 코드가 계산**: LLM·렌더러는 숫자를 만들지 않는다. 견적서 숫자 = `estimate()` 결과를 테스트로 확인.
- **근거 추적**: 항목별 출처, 검색된 근거 청크(`sources`), 도구 호출 기록(`trace`).
- **문서 ↔ 코드 일치**: 단가표·카탈로그 문서와 계산 상수가 다르면 테스트가 실패.
- **오프라인 동작**: LLM 키 없이 동작. 플래너는 `next_action(state)` 인터페이스라 LLM tool-use 플래너로 교체 가능.

### 대화형 접수 (`POST /chat`, 화면 상단 채팅창)
자연어로 조건을 말하면 대학명·교수 수·연구자 수·기간·범위를 뽑아 누적하고, 부족하면 되묻고, 다 모이면 견적을 냅니다.
예산 상한("예산 1.5억 이하")을 말하면 초과 시 예산 안 대안(할증 없애기 / 범위 축소)을 제안합니다.
견적식에 없는 요청(보고·상주 등)은 '반영 안 된 조건'으로 표시하고 담당자 검토 사유에 넣습니다. 추출은 규칙 기반(키 없이 동작).

### 한계
- 키워드 검색이 한국어 조사를 처리하지 못함(Postgres 'simple'). RFP 문서 검색 기능을 넣을 때 재현율을 측정하고 떨어지면 n-gram(pg_trgm)·형태소 분석 도입.
- 대화 추출은 규칙 기반이라 표현이 다양하면 놓침(되묻기로 보완), 범위 정정 미지원.
- 단가·공수 계수·할증률·서울대 기준 조건은 **샘플 가정값** (서울대 실제 금액·기간 비공개). 실제 수주 데이터로 계수를 보정해야 함.
- 키가 없어 LLM 플래너·자연어 설명은 구현하지 않음 (RulePlanner 로 결정적 실행).
- RFP 문서(PDF/HWP) 업로드, 견적 저장·이력, PDF 내보내기는 범위 밖.
