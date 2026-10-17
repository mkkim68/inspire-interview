"""검색 품질 측정: 모드별 Recall@K, MRR 비교.
    python -m scripts.eval_retrieval              (data/docs 적재 후 data/eval.jsonl 로 평가)
    python -m scripts.eval_retrieval --k 3
면접 포인트: "바꿀 때마다 같은 평가셋으로 재측정했습니다"를 숫자로 보여줄 수 있다.
"""
import argparse
import json
from pathlib import Path

from app.embeddings import get_embedder
from app.main import IngestReq, get_store, ingest
from app.retrieval import hybrid_search


def recall_at_k(ret: list[str], rel: set[str], k: int) -> float:
    return len(set(ret[:k]) & rel) / len(rel) if rel else 0.0


def rr(ret: list[str], rel: set[str]) -> float:
    return next((1 / i for i, d in enumerate(ret, 1) if d in rel), 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--eval", default="data/eval.jsonl")
    ap.add_argument("--docs", default="data/docs")
    a = ap.parse_args()

    ingest(IngestReq(folder=a.docs))
    rows = [json.loads(l) for l in Path(a.eval).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{'mode':<8} {'Recall@'+str(a.k):>9} {'MRR':>6}   misses")
    for mode in ("vector", "keyword", "hybrid"):
        rec = mrr = 0.0
        misses = []
        for r in rows:
            hits = hybrid_search(get_store(), get_embedder(), r["question"], a.k, mode=mode)
            sources = [h["source"] for h in hits]
            rel = set(r["relevant"])
            rec += recall_at_k(sources, rel, a.k)
            mrr += rr(sources, rel)
            if not rel & set(sources):
                misses.append(r["question"])
        n = len(rows)
        print(f"{mode:<8} {rec / n:>9.2f} {mrr / n:>6.2f}   {misses[:2]}")


if __name__ == "__main__":
    main()
