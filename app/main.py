"""FastAPI 서버.  실행: uvicorn app.main:app --reload   →  http://localhost:8000/docs"""
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import rag
from .agent import run_agent
from .chunking import make_chunks
from .config import settings
from .embeddings import get_embedder
from .intake import ChatSession, reply
from .quote import QuoteRequest
from .rag_quote import rfp_conditions
from .retrieval import hybrid_search
from .store import MemoryStore, PgVectorStore

app = FastAPI(title="Interview Starter — RAG API")


@lru_cache
def get_store():
    if settings.database_url:
        return PgVectorStore(settings.database_url, get_embedder().dim)
    return MemoryStore()


class Doc(BaseModel):
    source: str
    text: str
    meta: dict = Field(default_factory=dict)


class IngestReq(BaseModel):
    docs: list[Doc] = Field(default_factory=list)
    folder: str | None = None      # 서버가 읽을 수 있는 폴더 경로 (.md/.txt)


class SearchReq(BaseModel):
    query: str
    k: int = settings.top_k
    mode: str = Field("hybrid", pattern="^(vector|keyword|hybrid)$")
    where: dict | None = None      # 메타데이터 필터 예: {"dept": "hr"}
    min_rel_score: float | None = None


@app.get("/health")
def health():
    return {"ok": True, "store": type(get_store()).__name__, "chunks": get_store().count(),
            "embedder": settings.embedder, "llm": settings.llm_provider}


@app.post("/ingest")
def ingest(req: IngestReq):
    docs = list(req.docs)
    failed: list[str] = []
    if req.folder:
        root = Path(req.folder)
        if not root.is_dir():
            raise HTTPException(400, f"folder not found: {req.folder}")
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() in {".md", ".txt"}:
                try:
                    docs.append(Doc(source=p.name, text=p.read_text(encoding="utf-8")))
                except Exception as e:  # 한 파일 실패로 전체를 멈추지 않는다
                    failed.append(f"{p.name}: {e}")
    chunks = [c for d in docs for c in make_chunks(d.text, d.source, settings.chunk_size, d.meta)]
    if not chunks:
        return {"docs": len(docs), "chunks": 0, "added": 0, "failed": failed}
    vectors = get_embedder().embed_documents([c["content"] for c in chunks])
    added = get_store().add_chunks(chunks, vectors)
    return {"docs": len(docs), "chunks": len(chunks), "added": added, "skipped_duplicates": len(chunks) - added,
            "failed": failed}


@app.post("/search")
def search(req: SearchReq):
    return {"results": hybrid_search(get_store(), get_embedder(), req.query, req.k, req.where, req.mode, min_rel_score=req.min_rel_score)}


@app.post("/ask")
def ask(req: SearchReq):
    docs = hybrid_search(get_store(), get_embedder(), req.query, req.k, req.where, req.mode, min_rel_score=req.min_rel_score)
    return {**rag.answer(req.query, docs), "retrieved": docs}


class QuoteReq(BaseModel):
    university: str = ""
    professors: int | None = None
    researchers: int | None = None     # 비우면 교수 수 × 5 로 가정
    months: int | None = None
    scopes: list[str] = Field(default_factory=list)


@app.post("/quote")
def quote(req: QuoteReq):
    return run_agent(QuoteRequest(**req.model_dump()), get_store(), get_embedder())


class ChatReq(BaseModel):
    session_id: str = "default"
    message: str


SESSIONS: dict[str, ChatSession] = {}   # 데모용 메모리 세션 (서버 재시작 시 사라짐)


@app.post("/chat")
def chat(req: ChatReq):
    session = SESSIONS.setdefault(req.session_id, ChatSession())
    return reply(session, req.message, get_store(), get_embedder())


class RfpReq(BaseModel):
    session_id: str = "default"
    name: str | None = None        # data/quote/mock/rfps/<name>.md (가상 RFP)
    text: str | None = None        # 또는 RFP 본문 (## 조항 제목 형식)


@app.post("/rfp")
def rfp(req: RfpReq):
    """② RFP 조항 검색 → 조건 추출 → 대화 세션에 채우고 견적까지."""
    if not req.name and not req.text:
        raise HTTPException(400, "name 또는 text 가 필요합니다")
    rid = req.name or f"upload-{req.session_id}"
    found = rfp_conditions(rid, get_store(), get_embedder(), text=req.text)
    session = SESSIONS.setdefault(req.session_id, ChatSession())
    out = reply(session, "", get_store(), get_embedder(), prefilled=found["conditions"])
    return {**out, "rfp_clauses": found["clauses"]}


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.delete("/reset")
def reset():
    get_store().clear()
    return {"ok": True}
