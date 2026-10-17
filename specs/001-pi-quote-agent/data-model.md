# Data Model: 대학 연구행정 PI 견적 에이전트

## 상수 (샘플 가정값, `app/quote.py` ↔ `data/quote/*.md`)

| 직급 | 단가(원/MM) | 투입 비율 |
|---|---|---|
| 책임 | 15,000,000 | 0.2 |
| 선임 | 11,000,000 | 0.4 |
| 전임 | 8,000,000 | 0.4 |

혼합 단가 = 15,000,000×0.2 + 11,000,000×0.4 + 8,000,000×0.4 = **10,600,000원/MM**

| 모듈 키 | 이름 | 기본 공수(MM) | 선택 |
|---|---|---|---|
| common | 현황 분석·To-Be 설계·사업관리 | 4.0 | 항상 포함 |
| planning | 연구기획 | 2.0 | 선택 |
| award | 과제수주 | 2.0 | 선택 |
| funding | 연구비 관리 | 3.0 | 선택 |
| outcome | 성과 활용 | 2.0 | 선택 |
| roadmap | 차세대 시스템 구축 방향·실행 로드맵 | 3.0 | 선택 |

## QuoteRequest
- `university: str` — 비어 있으면 안 됨
- `researchers: int | None` — 1 이상
- `scopes: list[str]` — 1개 이상, 각각 위 선택 모듈 키 중 하나
- 검증 실패 → `status="needs_info"`, `questions: list[str]`

## LineItem
- `module`, `name`, `mm`(소수 1자리), `amount`(원, int), `source`(근거 문서 파일명)

## Quote (estimate 결과)
- `items: list[LineItem]`, `factor`, `rate`, `subtotal`, `vat`, `total`

## AgentResult (/quote 응답)
- `status: "ok" | "needs_info"`, `questions`, `quote`(Quote), `quote_markdown`, `sources: list[str]`,
  `trace: list[{step, tool, summary}]`

## 상태 전이 (run_agent)
`검증` → (실패) `needs_info` 종료 / (성공) `search_refs` → `estimate` → `render_quote` → `ok` 종료.
`max_steps` 초과 시 `status="error"`.

## 기준 예시 (테스트 기대값)
고려대학교 / 2,000명(계수 1.0) / funding+roadmap → 공수 4.0+3.0+3.0 = 10.0MM →
소계 106,000,000 / VAT 10,600,000 / 합계 116,600,000

## Amendment v2 — 규모·기간 기반 (현행 기준, 위 규모 계수 방식을 대체)

| 모듈 | 고정 MM | 교수 1명당 | 연구자 1명당 |
|---|---|---|---|
| common | 2.0 | 0.01 | 0.002 |
| planning | 0.5 | 0.015 | 0 |
| award | 0.5 | 0.015 | 0 |
| funding | 0.5 | 0 | 0.004 |
| outcome | 0.5 | 0.02 | 0 |
| roadmap | 2.0 | 0 | 0.002 |

- 표준 4명 / 최대 8명 / 압축 할증 0.15 × (표준 기간 ÷ 요청 기간 − 1) / 연구자 미입력 = 교수 × 5
- 상태: `ok` | `infeasible`(options 2개) | `needs_info` | `error`

| 시나리오 | 공수 | 기간 판단 | 합계 |
|---|---|---|---|
| 서울대 50/250/3개월 (기준) | 11.0MM | 표준 2.75개월, 할증 없음 | 128,260,000 |
| 고려대 100/500/2개월 | 16.0MM | 8명, 할증 ×1.15 | 214,544,000 (서울대 대비 ×1.67) |
| 고려대 100/500/1개월 | 16.0MM | 16명 → 불가 | 대안 A 2개월 214,544,000 / 대안 B 연구기획+과제수주 107,272,000 |
