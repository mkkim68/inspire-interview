# 사내 문서 RAG / 대학 PI 견적 에이전트 Constitution

## Core Principles

### I. 오프라인 우선 (Offline-First)
- 모든 테스트와 기본 데모는 DB·네트워크·LLM 키 없이 MUST 동작한다
  (`EMBEDDER=fake`, `MemoryStore`, `LLM_PROVIDER=none`).
- 외부 의존(Postgres, 임베딩 모델, LLM API)은 설정으로 켜는 선택 기능이며, 꺼져 있을 때의
  대체 동작이 MUST 정의되어 있어야 한다.
- 근거: 면접·시연 환경에서 키나 네트워크가 없어도 결과를 보여줄 수 있어야 한다.

### II. 숫자는 코드가 계산한다 (Deterministic Numbers)
- 금액·공수·VAT·합계 등 모든 숫자는 순수 함수가 MUST 계산한다.
- LLM은 계산 결과를 설명·요약만 할 수 있으며, 숫자를 생성하거나 바꾸면 안 된다(MUST NOT).
- 렌더링된 견적서의 숫자는 계산 함수의 반환값과 MUST 일치하며, 이를 테스트로 검증한다.
- 근거: 견적서의 숫자 환각은 곧바로 금전적 손실·신뢰 하락으로 이어진다.

### III. 근거 추적 (Traceable Sources)
- 견적의 각 항목과 답변은 근거 문서(단가표·과업 카탈로그·사례)의 출처를 MUST 단다.
- 출처는 실제로 적재된 문서를 가리켜야 하며, 존재하지 않는 출처를 만들면 안 된다(MUST NOT).
- 에이전트가 호출한 도구와 순서는 응답의 `trace`로 MUST 남긴다.

### IV. 테스트 동반 (Tests Accompany Change)
- 새 기능에는 테스트를 MUST 함께 추가한다.
- 기존 테스트를 삭제하거나 약하게 바꾸면 안 된다(MUST NOT). 실패하면 코드를 고친다.
- 변경 단위마다 `python -m pytest -q` 를 MUST 실행한다.

### V. 비밀정보 분리 (Secrets in .env Only)
- API 키·비밀번호는 `.env` 에만 둔다. 코드·문서·커밋에 쓰면 안 된다(MUST NOT).

### VI. 저장소 인터페이스 일관성 (Store Parity)
- store 인터페이스(add_chunks, vector_search, keyword_search, count, clear)를 바꾸면
  `MemoryStore` 와 `PgVectorStore` 를 MUST 둘 다 고친다.

## 기술 제약

- 스택: Python 3.12, FastAPI, Postgres(pgvector), multilingual-e5-small, 하이브리드 검색(RRF).
- 기존 모듈(`app/retrieval.py`, `app/store.py`, `app/chunking.py`, `app/embeddings.py`,
  `app/llm.py`)을 재사용하고, 같은 일을 하는 코드를 새로 만들지 않는다(SHOULD NOT).
- 존재가 확실하지 않은 라이브러리 함수는 쓰기 전에 MUST 확인한다.
- 샘플·가정 데이터(단가, 공수 등)는 문서에 "샘플 가정값"임을 MUST 명시한다.

## 개발 워크플로

- 코드 작성 전 계획과 완료 기준(테스트)을 먼저 제시한다.
- 작은 단위로 변경 → pytest → 커밋.
- 작업 종료 시 변경 내용, 확인한 테스트, 남은 한계를 3줄로 요약한다.

## Governance

- 이 헌법은 다른 관행보다 우선하며, `CLAUDE.md` 는 런타임 작업 지침으로 함께 따른다.
- 개정은 이 파일을 수정하고 Sync Impact Report와 버전을 갱신하는 방식으로 한다.
- 버전: 원칙 제거·재정의는 MAJOR, 원칙·섹션 추가는 MINOR, 문구 정리는 PATCH.
- spec/plan/tasks 작성과 리뷰 시 위 원칙 준수 여부를 MUST 확인한다.

**Version**: 1.0.0 | **Ratified**: 2026-10-17 | **Last Amended**: 2026-10-17
