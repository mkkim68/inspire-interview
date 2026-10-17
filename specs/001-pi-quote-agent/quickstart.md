# Quickstart: 대학 연구행정 PI 견적 에이전트

## 사전 준비
```bash
conda activate interview
```

## 테스트 (DB·키 없이)
```bash
python -m pytest -q          # 기존 13개 + 견적 테스트 모두 통과해야 함
```

## 서버 실행·시연
```bash
uvicorn app.main:app --reload    # http://localhost:8000/
```
1. `/` 에서 "고려대학교 / 2000 / 연구비 관리 + 실행 로드맵" 제출
   → 합계 **116,600,000원** (소계 106,000,000 + VAT 10,600,000), 출처 3개, trace 3단계
2. 범위를 모두 해제하고 제출 → "정보 필요" + 범위를 묻는 질문

## API로 확인
```bash
curl -s -X POST localhost:8000/quote -H 'content-type: application/json' \
  -d '{"university":"고려대학교","researchers":2000,"scopes":["funding","roadmap"]}'
```
계약: [contracts/quote-api.md](./contracts/quote-api.md), 기대값: [data-model.md](./data-model.md)
