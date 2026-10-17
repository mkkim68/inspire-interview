"""환경변수 설정. .env 파일이 있으면 자동으로 읽는다."""
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 비어 있으면 Postgres 없이 메모리 저장소로 동작 (Docker가 안 될 때의 비상구)
    database_url: str = os.getenv("DATABASE_URL", "")

    # 임베딩: "e5" = intfloat/multilingual-e5-small (384차원, 한국어 OK) / "fake" = 테스트용 해시 임베딩
    embedder: str = os.getenv("EMBEDDER", "e5")
    embed_model: str = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
    embed_dim: int = int(os.getenv("EMBED_DIM", "384"))

    # LLM: "anthropic" | "openai" | "ollama"(로컬, 키 불필요) | "none"(키 없이 데모: 검색 결과만으로 답)
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

    # 견적 RAG 단계(유사 사례·과업 수행 내용) 사용 여부. 1 이면 켠다 (data/quote/mock 가상 데이터)
    quote_rag: bool = os.getenv("QUOTE_RAG", "0") == "1"
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")

    chunk_size: int = int(os.getenv("CHUNK_SIZE", "300"))
    top_k: int = int(os.getenv("TOP_K", "4"))


settings = Settings()
