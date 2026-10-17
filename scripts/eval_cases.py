"""유사 사례 검색 품질: 모드별 Recall@K, MRR (data/quote/mock 가상 데이터).
    python -m scripts.eval_cases --k 5
정답: 요청 범위와 사례 범위의 자카드 유사도 ≥ 0.5 인 사례. 질의는 사례와 다른 표현(동의어)으로 쓴다."""
import argparse

from app.embeddings import get_embedder
from app.main import get_store
from app.quote import QuoteRequest
from app.rag_quote import load_mock_cases, retrieve_similar_cases

QUERIES = [  # (요청 범위, 사람이 쓸 법한 문의 표현)
    (["funding"], "연구비 정산이랑 감사 대응 업무가 복잡해서 개선하고 싶어요"),
    (["roadmap"], "새 연구관리 시스템을 어떻게 만들지 마스터플랜이 필요해요"),
    (["outcome"], "특허 기술이전 성과 관리 체계를 정비하려고 합니다"),
    (["planning", "award"], "연구 과제 기획부터 공모 신청 협약까지 절차를 표준화"),
    (["funding", "roadmap"], "연구비 집행 프로세스 혁신과 차세대 시스템 이행계획"),
    (["award"], "과제 신청 선정 협약 업무를 정리하고 싶습니다"),
    (["planning"], "중장기 연구전략 기획 업무 재설계"),
    (["outcome", "roadmap"], "연구성과 관리와 통합 연구관리시스템 목표모델"),
]


def jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    k = ap.parse_args().k
    cases = load_mock_cases()
    print(f"{'mode':<8} {'Recall@' + str(k):>9} {'MRR':>6}")
    for mode in ("vector", "keyword", "hybrid"):
        rec = mrr = 0.0
        for scopes, text in QUERIES:
            rel = {c["case_id"] for c in cases if jaccard(c["scopes"], scopes) >= 0.5}
            req = QuoteRequest(university="x", professors=300, months=4, scopes=scopes)
            hits = retrieve_similar_cases(req, get_store(), get_embedder(), k=k, mode=mode, query=text)  # 사람이 쓴 표현
            ids = [h["case_id"] for h in hits]
            rec += len(set(ids) & rel) / min(len(rel), k) if rel else 0
            mrr += next((1 / i for i, d in enumerate(ids, 1) if d in rel), 0.0)
        print(f"{mode:<8} {rec / len(QUERIES):>9.2f} {mrr / len(QUERIES):>6.2f}")


if __name__ == "__main__":
    main()
