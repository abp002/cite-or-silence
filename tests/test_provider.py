import httpx
import pytest

from cite_or_silence.provider import Ollama


def ollama_up() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/version", timeout=2).is_success
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not ollama_up(), reason="needs a local Ollama with qwen3:14b")
def test_overlong_prompt_raises_instead_of_being_truncated():
    # 2026-10-09: a 17,656-token judge prompt was cut to 8,194 in a 16k window and the
    # check on prompt_eval_count let it through, since it ran after the cut.
    with pytest.raises(Exception, match="context"):
        Ollama(num_ctx=1024).complete("palabra " * 3000, {"type": "object"})
