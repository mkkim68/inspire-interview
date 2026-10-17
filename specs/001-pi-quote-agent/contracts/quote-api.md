# Contract: Quote API

## POST /quote

Request
```json
{"university": "고려대학교", "researchers": 2000, "scopes": ["funding", "roadmap"]}
```

Response 200 — 완료
```json
{
  "status": "ok",
  "questions": [],
  "quote": {
    "items": [{"module": "common", "name": "...", "mm": 4.0, "amount": 42400000, "source": "modules.md"}],
    "factor": 1.0, "rate": 10600000, "subtotal": 106000000, "vat": 10600000, "total": 116600000
  },
  "quote_markdown": "# 견적서 — 고려대학교 ...",
  "sources": ["modules.md", "rate_card.md", "snu_pi_case.md"],
  "trace": [{"step": 1, "tool": "search_refs", "summary": "..."}, {"step": 2, "tool": "estimate", "summary": "..."},
            {"step": 3, "tool": "render_quote", "summary": "..."}]
}
```

Response 200 — 정보 필요 (필수 입력 누락·잘못된 값)
```json
{"status": "needs_info", "questions": ["어떤 과업 범위가 필요하신가요? (planning, award, ...)"],
 "quote": null, "quote_markdown": "", "sources": [], "trace": []}
```

## GET /

입력 폼(대학명, 연구자 수, 범위 체크박스) → `POST /quote` → 견적서·출처·trace 표시하는 HTML.
