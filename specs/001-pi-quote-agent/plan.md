# Implementation Plan: 대학 연구행정 PI 견적 에이전트

**Branch**: `quote-agent` | **Date**: 2026-10-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-pi-quote-agent/spec.md`

## Summary

대학명·연구자 수·과업 범위를 받아 항목별 견적서를 돌려주는 `/quote` API와 웹 화면을 기존 RAG 템플릿 위에
추가한다. 금액은 순수 함수 `estimate()`가 계산하고, 에이전트 루프(`run_agent`)가 도구
`search_refs`(기존 `hybrid_search` 재사용) → `estimate` → `render_quote`를 순서대로 호출하며 trace를 남긴다.
LLM 키가 없으므로 다음 행동은 결정적 `RulePlanner`가 고른다(키가 생기면 LLM 플래너로 교체 가능한 구조).

## Technical Context

**Language/Version**: Python 3.12 (conda env `interview`)

**Primary Dependencies**: FastAPI, pydantic (기존). 신규 의존성 없음.

**Storage**: 기존 store(MemoryStore / PgVectorStore). 견적 근거 문서는 `meta={"kind": "quote_ref"}`로 적재.

**Testing**: pytest + FastAPI TestClient (FakeEmbedder, MemoryStore, LLM_PROVIDER=none)

**Target Platform**: 로컬 서버 (uvicorn)

**Project Type**: web-service (단일 프로젝트 + 정적 HTML 1장)

**Performance Goals**: 견적 1건 1초 이내 (오프라인 기준)

**Constraints**: 오프라인 동작, 신규 라이브러리 금지, 남은 시간 약 1시간 50분 → 최소 범위

**Scale/Scope**: 과업 모듈 6개(공통 1 + 선택 5), 근거 문서 3개

## Constitution Check

| 원칙 | 적용 | 판정 |
|---|---|---|
| I. 오프라인 우선 | RulePlanner, FakeEmbedder/MemoryStore로 전체 테스트 | PASS |
| II. 숫자는 코드가 계산 | `estimate()` 순수 함수(Decimal), 렌더러는 숫자를 포맷만 함, 일치 테스트 | PASS |
| III. 근거 추적 | 항목별 `source`(실제 `data/quote/*.md`), 응답 `sources`·`trace` | PASS |
| IV. 테스트 동반 | `tests/test_quote.py` 신규, 기존 13개 유지 | PASS |
| V. 비밀정보 분리 | 키 사용 없음 | PASS |
| VI. Store 일관성 | store 인터페이스 변경 없음(기존 `where` 필터 사용) | PASS |

Post-design 재확인: 위 판정 유지. 위반 없음 → Complexity Tracking 불필요.

## Project Structure

### Documentation (this feature)

```text
specs/001-pi-quote-agent/
├── spec.md
├── plan.md              # 이 파일
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/quote-api.md
└── tasks.md             # /speckit-tasks 출력
```

### Source Code (repository root)

```text
app/
├── quote.py        # 신규: 상수(단가·모듈·계수), QuoteRequest 검증, estimate()
├── agent.py        # 신규: 도구 3개, RulePlanner, run_agent(), ensure_refs_loaded()
├── main.py         # 수정: POST /quote, GET /
└── static/index.html  # 신규: 입력 폼 + 견적서 표시
data/quote/
├── rate_card.md    # 직급별 단가·투입 비율 (샘플 가정)
├── modules.md      # 과업 모듈 카탈로그·기본 공수·규모 계수 (샘플 가정)
└── snu_pi_case.md  # 서울대 연구행정시스템 PI 사례 (공개 기사 범위)
tests/
└── test_quote.py   # 신규
```

**Structure Decision**: 기존 단일 프로젝트 구조에 모듈 2개 + 정적 페이지 1개를 추가한다. 기존
`/ingest`·`/search`·`/ask`와 `data/docs` 기반 테스트는 건드리지 않는다.
