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
