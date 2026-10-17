"""문서 → 청크. 문단 → 줄 → 문장 → 단어 순서로 나누는 재귀 분할."""
import hashlib

SEPARATORS = ("\n\n", "\n", ". ", " ")


def recursive_split(text: str, max_len: int, seps: tuple[str, ...] = SEPARATORS) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]
    for i, sep in enumerate(seps):
        if sep not in text:
            continue
        out, buf = [], ""
        for part in (p.strip() for p in text.split(sep)):
            if not part:
                continue
            if len(part) > max_len:
                if buf:
                    out.append(buf)
                    buf = ""
                out.extend(recursive_split(part, max_len, seps[i + 1:]))
                continue
            cand = part if not buf else buf + sep + part
            if len(cand) <= max_len:
                buf = cand
            else:
                out.append(buf)
                buf = part
        if buf:
            out.append(buf)
        return out
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]

def get_title(text: str) -> str:
    """문서의 첫 번째 '# 제목' 줄을 찾아 제목만 돌려준다. 없으면 빈 문자열."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""

def make_chunks(text: str, source: str, max_len: int, meta: dict | None = None) -> list[dict]:
    """청크마다 source, chunk_id, content_hash(중복 적재 방지용)를 붙인다."""
    title = get_title(text)
    chunks = []
    for i, c in enumerate(recursive_split(text, max_len)):
        if title and not c.startswith("# "):
            c = f"# {title}\n{c}"
        chunks.append({
            "chunk_id": f"{source}#{i}",
            "source": source,
            "content": c,
            "content_hash": hashlib.sha256(f"{source}\n{c}".encode()).hexdigest(),
            "meta": meta or {},
        })
    return chunks
