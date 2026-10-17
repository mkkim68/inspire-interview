"""벡터 저장소 2종: PgVectorStore(운영) / MemoryStore(Docker가 없을 때·테스트).
둘 다 같은 메서드를 제공: add_chunks, vector_search, keyword_search, count, clear
"""
import json
import math
import re
from collections import Counter

import numpy as np


def _tok(text: str) -> list[str]:
    return re.findall(r"[0-9a-z가-힣]+", text.lower())


class MemoryStore:
    def __init__(self):
        self.rows: list[dict] = []
        self.hashes: set[str] = set()

    def add_chunks(self, chunks: list[dict], vectors: list[list[float]]) -> int:
        added = 0
        for c, v in zip(chunks, vectors):
            if c["content_hash"] in self.hashes:   # 같은 내용 재적재 방지 (멱등)
                continue
            self.hashes.add(c["content_hash"])
            self.rows.append({**c, "vec": np.asarray(v, dtype=float)})
            added += 1
        return added

    def _filter(self, where: dict | None):
        return [r for r in self.rows
                if not where or all(r["meta"].get(k) == v for k, v in where.items())]

    def vector_search(self, qvec, k: int, where: dict | None = None) -> list[dict]:
        rows = self._filter(where)
        if not rows:
            return []
        q = np.asarray(qvec, dtype=float)
        scored = [(float(r["vec"] @ q), r) for r in rows]
        scored.sort(key=lambda x: -x[0])
        return [_public(r, s) for s, r in scored[:k]]

    def keyword_search(self, query: str, k: int, where: dict | None = None) -> list[dict]:
        """간단 BM25"""
        rows = self._filter(where)
        if not rows:
            return []
        docs = [_tok(r["content"]) for r in rows]
        N, avgdl = len(docs), sum(map(len, docs)) / len(docs) or 1
        df = Counter(t for d in docs for t in set(d))
        k1, b = 1.5, 0.75
        out = []
        for r, d in zip(rows, docs):
            tf, s = Counter(d), 0.0
            for t in _tok(query):
                if tf[t]:
                    idf = math.log((N - df[t] + 0.5) / (df[t] + 0.5) + 1)
                    s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
            if s > 0:
                out.append((s, r))
        out.sort(key=lambda x: -x[0])
        return [_public(r, s) for s, r in out[:k]]

    def count(self) -> int:
        return len(self.rows)

    def clear(self) -> None:
        self.rows.clear()
        self.hashes.clear()


class PgVectorStore:
    def __init__(self, url: str, dim: int):
        import psycopg
        from pgvector.psycopg import register_vector

        self.conn = psycopg.connect(url, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                id           bigserial PRIMARY KEY,
                chunk_id     text NOT NULL,
                source       text NOT NULL,
                content      text NOT NULL,
                content_hash text UNIQUE NOT NULL,
                meta         jsonb NOT NULL DEFAULT '{{}}',
                embedding    vector({dim}) NOT NULL,
                tsv          tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
            )""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS chunks_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin (tsv)")

    def add_chunks(self, chunks: list[dict], vectors: list[list[float]]) -> int:
        added = 0
        with self.conn.cursor() as cur:
            for c, v in zip(chunks, vectors):
                cur.execute(
                    """INSERT INTO chunks (chunk_id, source, content, content_hash, meta, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (content_hash) DO NOTHING""",
                    (c["chunk_id"], c["source"], c["content"], c["content_hash"],
                     json.dumps(c["meta"], ensure_ascii=False), np.asarray(v, dtype=np.float32)))
                added += cur.rowcount
        return added

    def vector_search(self, qvec, k: int, where: dict | None = None) -> list[dict]:
        q = np.asarray(qvec, dtype=np.float32)
        rows = self.conn.execute(
            """SELECT chunk_id, source, content, meta, 1 - (embedding <=> %s) AS score
               FROM chunks WHERE meta @> %s::jsonb
               ORDER BY embedding <=> %s LIMIT %s""",
            (q, json.dumps(where or {}, ensure_ascii=False), q, k)).fetchall()
        return [_row(r) for r in rows]

    def keyword_search(self, query: str, k: int, where: dict | None = None) -> list[dict]:
        terms = " | ".join(_tok(query))   # 단어 중 하나라도 있으면 매치 (OR)
        if not terms:
            return []
        rows = self.conn.execute(
            """SELECT chunk_id, source, content, meta, ts_rank(tsv, to_tsquery('simple', %s)) AS score
               FROM chunks WHERE tsv @@ to_tsquery('simple', %s) AND meta @> %s::jsonb
               ORDER BY score DESC LIMIT %s""",
            (terms, terms, json.dumps(where or {}, ensure_ascii=False), k)).fetchall()
        return [_row(r) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def clear(self) -> None:
        self.conn.execute("TRUNCATE chunks")


def _public(r: dict, score: float) -> dict:
    return {"chunk_id": r["chunk_id"], "source": r["source"], "content": r["content"],
            "meta": r["meta"], "score": round(float(score), 4)}


def _row(r) -> dict:
    return {"chunk_id": r[0], "source": r[1], "content": r[2], "meta": r[3], "score": round(float(r[4]), 4)}
