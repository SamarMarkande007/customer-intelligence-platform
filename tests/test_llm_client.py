"""LLM client behaviour with a fake provider: retired-model auto-recovery, rate-limit retry/fallback, reasoning-model handling."""
import httpx, openai, pytest
from types import SimpleNamespace
from src.llm import llm_client
from src.llm.llm_client import LLMClient, LLMError


def _resp(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _err(cls, status):
    r = httpx.Response(status, request=httpx.Request("POST", "http://x"), headers={"retry-after": "0"})
    return cls("boom", response=r, body=None)


class FakeAPI:
    def __init__(self, behaviours, models):
        self.behaviours, self.model_ids, self.calls = list(behaviours), models, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(data=[SimpleNamespace(id=m) for m in self.model_ids]))

    def _create(self, **kw):
        self.calls.append(kw); b = self.behaviours.pop(0)
        if isinstance(b, Exception):
            raise b
        return _resp(b)


def make(fake, monkeypatch, provider="groq", model=None):
    monkeypatch.setenv("GROQ_API_KEY", "x"); monkeypatch.setattr(llm_client, "MIN_GAP_S", 0); monkeypatch.setattr("time.sleep", lambda s: None)
    c = LLMClient(provider, model=model, use_cache=False); c._client = fake; return c


def test_default_groq_model_is_not_the_retired_one():
    assert llm_client.PROVIDERS["groq"]["model"] == "openai/gpt-oss-120b"


def test_retired_model_auto_switches(monkeypatch):
    fake = FakeAPI([_err(openai.NotFoundError, 404), "OK"], ["openai/gpt-oss-120b", "openai/gpt-oss-20b"])
    c = make(fake, monkeypatch, model="llama-3.3-70b-versatile")
    assert c.chat("hi") == "OK" and c.model == "openai/gpt-oss-120b"
    assert [k["model"] for k in fake.calls] == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]


def test_no_alternative_gives_clear_message(monkeypatch):
    fake = FakeAPI([_err(openai.NotFoundError, 404)] * 6, ["something-else"])
    c = make(fake, monkeypatch, model="llama-3.3-70b-versatile")
    with pytest.raises(LLMError, match="LLM_MODEL"):
        c.chat("hi")


def test_rate_limit_retries_then_succeeds(monkeypatch):
    fake = FakeAPI([_err(openai.RateLimitError, 429), "done"], [])
    assert make(fake, monkeypatch).chat("hi") == "done"


def test_reasoning_model_gets_effort_and_extra_budget_and_think_tags_stripped(monkeypatch):
    fake = FakeAPI(["<think>secret reasoning</think>The answer"], [])
    out = make(fake, monkeypatch).chat("hi", max_tokens=300)
    assert out == "The answer"
    kw = fake.calls[0]; assert kw["extra_body"] == {"reasoning_effort": "low"} and kw["max_tokens"] > 300


def test_empty_reply_is_retried_with_more_tokens(monkeypatch):
    fake = FakeAPI(["", "finally"], [])
    assert make(fake, monkeypatch).chat("hi", max_tokens=100) == "finally" and fake.calls[1]["max_tokens"] > fake.calls[0]["max_tokens"]


def test_bad_key_message(monkeypatch):
    fake = FakeAPI([_err(openai.AuthenticationError, 401)], [])
    with pytest.raises(LLMError, match="rejected"):
        make(fake, monkeypatch).chat("hi")
