# Tasks: 대학 연구행정 PI 견적 에이전트

**Input**: Design documents from `/specs/001-pi-quote-agent/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/quote-api.md

**Tests**: TDD 요청됨 — 각 스토리에서 테스트를 먼저 쓰고 실패를 확인한 뒤 구현한다.

## Phase 1: Setup

- [ ] T001 [P] 샘플 단가표 작성 (책임 15,000,000/0.2, 선임 11,000,000/0.4, 전임 8,000,000/0.4, 혼합 10,600,000원/MM, "샘플 가정값" 명시) in data/quote/rate_card.md
- [ ] T002 [P] 과업 모듈 카탈로그 작성 (common 4.0, planning 2.0, award 2.0, funding 3.0, outcome 2.0, roadmap 3.0 MM; 규모 계수 <1000=0.8, 1000~2999=1.0, ≥3000=1.3) in data/quote/modules.md
- [ ] T003 [P] 서울대 연구행정시스템 PI 사례 요약 (공개 기사 범위만, 금액·기간 비공개 명시) in data/quote/snu_pi_case.md

## Phase 2: Foundational

- [ ] T004 상수(RATES, MODULES, 규모 계수)와 `validate(req) -> list[str]` 질문 목록 반환 함수 in app/quote.py
  - university 비어 있으면 안 됨 / researchers ≥ 1 / scopes 1개 이상, 각각 planning|award|funding|outcome|roadmap

## Phase 3: User Story 1 — 항목별 견적서 받기 (P1) 🎯 MVP

**Goal**: 입력 → 항목·소계·VAT·합계가 담긴 견적
**Independent Test**: 고려대학교/2000/funding+roadmap → 합계 116,600,000

- [ ] T005 [US1] 테스트 먼저: estimate 기대값(10.0MM, 소계 106,000,000, VAT 10,600,000, 합계 116,600,000), 결정성, 범위 추가 시 증가, 규모 계수 반영 in tests/test_quote.py
- [ ] T006 [US1] `estimate(req) -> dict` 순수 함수 (Decimal, 공수 소수 1자리 반올림, VAT 원 단위 버림) in app/quote.py
- [ ] T007 [US1] 테스트 먼저: run_agent 성공 경로·렌더된 견적서 숫자 = estimate 결과, POST /quote 200 in tests/test_quote.py
- [ ] T008 [US1] 도구 search_refs/estimate/render_quote, RulePlanner, `run_agent(req, max_steps=6)`, `ensure_refs_loaded()` (data/quote 를 meta {"kind":"quote_ref"} 로 적재) in app/agent.py
- [ ] T009 [US1] `POST /quote` 엔드포인트 in app/main.py
- [ ] T010 [US1] 입력 폼 → /quote → 견적서 표시 페이지, `GET /` 서빙 in app/static/index.html, app/main.py

## Phase 4: User Story 2 — 근거 확인 (P2)

**Independent Test**: sources ⊆ data/quote 파일, trace 순서 = search_refs → estimate → render_quote

- [ ] T011 [US2] 테스트: sources 실재, 항목별 source, trace 순서, "샘플 가정값" 문구, 상수 ↔ md 숫자 일치 in tests/test_quote.py
- [ ] T012 [US2] 부족한 부분 보완 (항목 source, 견적서 하단 안내·출처 표시) in app/agent.py

## Phase 5: User Story 3 — 정보 부족 시 되묻기 (P3)

**Independent Test**: scopes=[] → status needs_info + 범위 질문

- [ ] T013 [US3] 테스트: 범위 누락, 대학명+연구자 수 누락(질문 2개), 연구자 수 0, 지원하지 않는 범위, max_steps 초과 시 error in tests/test_quote.py
- [ ] T014 [US3] run_agent 에서 validate 실패 시 needs_info 반환, 화면에 질문 표시 in app/agent.py, app/static/index.html

## Phase 6: Polish

- [ ] T015 README 에 견적 에이전트 사용법·설계 원칙·한계 추가 in README.md
- [ ] T016 quickstart.md 시나리오 수동 검증 (uvicorn + 브라우저/curl) in specs/001-pi-quote-agent/quickstart.md

## Dependencies

- Setup(T001–T003) → Foundational(T004) → US1(T005–T010) → US2(T011–T012), US3(T013–T014) → Polish
- US2·US3 는 US1 이후 서로 독립 (같은 테스트 파일이므로 순차 작성 권장)

## Parallel Example

- T001, T002, T003 동시 작성 가능 (서로 다른 파일)

## Implementation Strategy

- MVP = US1 까지 (T001–T010). 끝나면 커밋·시연 가능.
- 이후 US2 → US3 → Polish 순서로 스토리마다 pytest 통과 후 커밋.
