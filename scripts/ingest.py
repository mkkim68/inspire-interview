"""폴더의 .md/.txt를 적재.  python -m scripts.ingest data/docs
여러 번 실행해도 같은 내용은 다시 들어가지 않는다(content_hash)."""
import sys

from app.main import IngestReq, ingest

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "data/docs"
    print(ingest(IngestReq(folder=folder)))
