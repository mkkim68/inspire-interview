# 자주 쓰는 명령 모음.  make db / make run / make test / make eval
.PHONY: db down run test eval ingest

db:        ## Postgres + pgvector 띄우기
	docker compose up -d db

down:      ## DB 끄기
	docker compose down

run:       ## API 서버 (http://localhost:8000/docs)
	uvicorn app.main:app --reload

ingest:    ## data/docs 적재
	python -m scripts.ingest data/docs

test:      ## 테스트 (DB·키 없이 동작)
	python -m pytest -q

eval:      ## 검색 모드별 Recall@3, MRR 비교
	python -m scripts.eval_retrieval --k 3
