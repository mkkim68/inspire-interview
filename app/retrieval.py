"""하이브리드 검색: 벡터(의미) + 키워드(정확한 단어)를 RRF로 합친다."""


def rrf_fuse(rankings: list[list[dict]], k: int = 60, top_n: int = 4) -> list[dict]:
    """RRF_score(d) = Σ 1 / (k + rank).  점수 스케일이 달라도 순위만으로 합칠 수 있다."""
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            cid = doc["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            by_id.setdefault(cid, doc)
    ordered = sorted(scores, key=lambda c: (-scores[c], c))[:top_n]
    return [{**by_id[c], "score": round(scores[c], 5)} for c in ordered]


def filter_relative(results: list[dict], min_rel_score: float | None) -> list[dict]:
    """1등 점수의 min_rel_score 배 미만인 결과는 버린다. 예: 0.6 → 1등의 60% 미만 제거"""
    if not results or not min_rel_score:
        return results
    top = results[0]["score"]
    return [r for r in results if r["score"] >= top * min_rel_score]


def hybrid_search(store, embedder, query: str, k: int, where: dict | None = None,
                  mode: str = "hybrid", candidates: int = 20,
                  min_rel_score: float | None = None) -> list[dict]:
    """mode: "vector" | "keyword" | "hybrid" — 비교 실험을 쉽게 하려고 분리"""
    if mode == "vector":
        results = store.vector_search(embedder.embed_query(query), k, where)
    elif mode == "keyword":
        results = store.keyword_search(query, k, where)
    else:
        vec = store.vector_search(embedder.embed_query(query), candidates, where)
        kw = store.keyword_search(query, candidates, where)
        results = rrf_fuse([vec, kw], top_n=k)
    return filter_relative(results, min_rel_score)
