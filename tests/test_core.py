from app.chunking import make_chunks, recursive_split
from app.rag import NOT_FOUND, check_citations
from app.retrieval import rrf_fuse


def test_recursive_split_respects_max_len():
    text = "\n\n".join(["문단 " + "가" * 30] * 5)
    chunks = recursive_split(text, 50)
    assert chunks and all(len(c) <= 50 for c in chunks)


def test_make_chunks_has_ids_and_hash():
    cs = make_chunks("a\n\nb", "x.md", 1)
    assert [c["chunk_id"] for c in cs] == ["x.md#0", "x.md#1"]
    assert cs[0]["content_hash"] != cs[1]["content_hash"]


def test_rrf_prefers_agreement():
    a = [{"chunk_id": "x"}, {"chunk_id": "y"}]
    b = [{"chunk_id": "z"}, {"chunk_id": "y"}]
    assert rrf_fuse([a, b], top_n=1)[0]["chunk_id"] == "y"


def test_check_citations():
    assert check_citations(NOT_FOUND, 2)["ok"]
    assert check_citations("답입니다.", 2)["reason"] == "no_citation"
    assert check_citations("답[3]", 2)["reason"] == "invalid_citation"
    assert check_citations("답[1][2]", 2)["ok"]

def test_chunks_keep_document_title():
    text = "# 휴가 규정\n\n## 연차\n" + "가" * 50 + "\n\n## 병가\n병가는 연 10일"
    cs = make_chunks(text, "hr.md", 60)
    assert len(cs) >= 2
    assert all(c["content"].startswith("# 휴가 규정") for c in cs)