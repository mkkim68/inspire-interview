"""임베딩. 실제 모델(e5)과 테스트용 가짜 모델을 같은 인터페이스로."""
import hashlib
import re
from functools import lru_cache

import numpy as np

from .config import settings


class FakeEmbedder:
    """네트워크·모델 없이 돌아가는 결정적 임베딩 (단어 해시 bag-of-words). 테스트·비상용."""

    def __init__(self, dim: int):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = np.zeros(self.dim)
        for tok in re.findall(r"[0-9a-z가-힣]+", text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class E5Embedder:
    """intfloat/multilingual-e5-*: 문서엔 'passage: ', 질문엔 'query: ' 접두어가 규칙."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # 무거우니 필요할 때만 import
        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode([f"passage: {t}" for t in texts], normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(f"query: {text}", normalize_embeddings=True).tolist()


@lru_cache
def get_embedder():
    if settings.embedder == "fake":
        return FakeEmbedder(settings.embed_dim)
    return E5Embedder(settings.embed_model)
