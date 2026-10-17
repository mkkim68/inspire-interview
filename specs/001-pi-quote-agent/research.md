# Research: 대학 연구행정 PI 견적 에이전트

## 1. 금액 계산 방식
- **Decision**: 모듈 공수(M/M) = 기본 공수 × 규모 계수(소수 1자리 반올림). 금액 = 공수 × 혼합 단가(원/MM).
  `Decimal`로 계산해 원 단위 정수로 만든다. VAT = 소계 × 10% (원 단위 버림).
- **Rationale**: 컨설팅 견적의 일반적 구조(M/M × 단가). Decimal로 부동소수 오차를 없애 결정성 보장(SC-002).
- **Alternatives**: 직급별 공수를 따로 산정 → 입력·설명이 복잡해져 시간 내 구현 어려움.

## 2. 단가·공수 데이터 위치
- **Decision**: 계산에 쓰는 값은 `app/quote.py` 상수, 같은 값을 `data/quote/*.md` 근거 문서에 표로 기록.
  테스트가 두 곳의 숫자가 일치하는지 검사한다.
- **Rationale**: 계산은 코드(원칙 II), 출처는 검색 가능한 문서(원칙 III). 불일치는 테스트로 잡는다.
- **Alternatives**: md 표를 파싱해 계산 → 파서 오류가 금액 오류로 이어질 위험, 시간 부족.

## 3. 에이전트 플래너
- **Decision**: `Planner.next_action(state) -> (tool, args) | None` 인터페이스. 오프라인에서는 `RulePlanner`
  (상태에 없는 것을 순서대로 채움). `run_agent`는 `max_steps=6`에서 강제 종료.
- **Rationale**: 키 없이 결정적으로 테스트 가능. LLM tool use 플래너는 같은 인터페이스로 나중에 교체.
- **Alternatives**: 처음부터 LLM tool use → 키가 없어 시연·테스트 불가.

## 4. 근거 문서 적재·검색
- **Decision**: `/quote` 첫 호출 시 `data/quote/*.md`를 `meta={"kind":"quote_ref"}`로 적재(content_hash로 멱등).
  모듈별 질의로 `hybrid_search(..., where={"kind":"quote_ref"})`.
- **Rationale**: 기존 RAG·필터를 그대로 재사용, 사내 문서(`data/docs`)와 섞이지 않음.

## 5. 규모 계수 (가정)
- 연구자 1,000명 미만 0.8 / 1,000~2,999명 1.0 / 3,000명 이상 1.3
