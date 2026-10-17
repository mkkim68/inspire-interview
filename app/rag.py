"""검색 결과로 프롬프트를 만들고, 답의 인용이 실제 문서를 가리키는지 검증한다."""
import re

from . import llm

NOT_FOUND = "제공된 문서에서 해당 정보를 찾을 수 없습니다."


def build_prompt(question: str, docs: list[dict]) -> str:
    ctx = "\n\n---\n\n".join(f"[{i}] {d['source']}\n{d['content']}" for i, d in enumerate(docs, 1))
    return (
        "아래 컨텍스트만 사용해 질문에 답하세요.\n"
        "## 규칙\n"
        f"1. 컨텍스트에 없는 내용이면 정확히 \"{NOT_FOUND}\" 라고만 답하세요.\n"
        "2. 문장마다 근거 문서 번호를 [1] 형식으로 붙이세요.\n"
        "3. 추측하지 마세요.\n\n"
        f"## 컨텍스트\n{ctx}\n\n## 질문\n{question}\n\n## 답변\n"
    )


def check_citations(answer: str, num_docs: int) -> dict:
    if answer.strip() == NOT_FOUND:
        return {"ok": True, "reason": "not_found"}
    cites = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    if not cites:
        return {"ok": False, "reason": "no_citation", "citations": []}
    if any(c < 1 or c > num_docs for c in cites):
        return {"ok": False, "reason": "invalid_citation", "citations": cites}
    return {"ok": True, "reason": "ok", "citations": cites}


def answer(question: str, docs: list[dict]) -> dict:
    if not docs:
        return {"answer": NOT_FOUND, "check": {"ok": True, "reason": "no_docs"}, "sources": []}
    text = llm.generate(build_prompt(question, docs))
    return {
        "answer": text,
        "check": check_citations(text, len(docs)),
        "sources": [{"n": i, "source": d["source"], "chunk_id": d["chunk_id"]} for i, d in enumerate(docs, 1)],
    }
