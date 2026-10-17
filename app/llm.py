"""LLM 호출을 한 함수로 감싼다. 공급자를 바꿔도 나머지 코드는 그대로."""
import os
import re

from .config import settings


def generate(prompt: str, max_tokens: int = 700) -> str:
    provider = settings.llm_provider
    if provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(model=settings.llm_model, max_tokens=max_tokens, temperature=0,
                                     messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if b.type == "text")
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(model=settings.llm_model, temperature=0, max_tokens=max_tokens,
                                              messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content or ""
    return _offline_answer(prompt)


def _offline_answer(prompt: str) -> str:
    """키가 없을 때 데모용: 첫 번째 근거 문서의 첫 문장을 [1] 인용과 함께 돌려준다."""
    if "## 컨텍스트\n" not in prompt:
        return "(LLM 미설정)"
    ctx = prompt.split("## 컨텍스트\n", 1)[1].split("\n\n## 질문", 1)[0].strip()
    if not ctx:
        return "제공된 문서에서 해당 정보를 찾을 수 없습니다."
    question = prompt.split("## 질문\n", 1)[1].split("\n\n## 답변", 1)[0] if "## 질문\n" in prompt else ""
    q_words = set(re.findall(r"[0-9a-z가-힣]+", question.lower()))
    first_block = ctx.split("\n\n---\n\n")[0]
    lines = [l.strip() for l in first_block.split("\n")[1:] if l.strip() and not l.startswith("#")]
    if not lines:
        return "제공된 문서에서 해당 정보를 찾을 수 없습니다."
    # 질문과 겹치는 단어가 가장 많은 줄을 고른다 (아주 단순한 추출형 답변)
    best = max(lines, key=lambda l: len(q_words & set(re.findall(r"[0-9a-z가-힣]+", l.lower()))))
    return f"{best[:200]} [1] (오프라인 모드: LLM 키가 없어 검색 결과에서 그대로 발췌했습니다)"
