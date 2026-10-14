"""
Provider-agnostic LLM client for FREE tiers (Groq by default). Every provider below speaks the OpenAI-compatible protocol, so one
`openai` package is the only dependency and no OpenAI account is needed.

Switch provider in .env:  LLM_PROVIDER=groq | gemini | mistral | ollama     (optionally LLM_MODEL=...)
Built for free-tier limits: automatic retry with the wait time the server asks for, a fallback to a smaller model, a small on-disk
cache for repeated deterministic prompts, and a minimum gap between calls.
"""
from __future__ import annotations
import hashlib, json, os, re, time
from pathlib import Path
from typing import Callable, Optional
from src.utils.config import ROOT

PROVIDERS = {
    # NOTE: Groq retired llama-3.3-70b-versatile and llama-3.1-8b-instant on 2026-08-16. Free models change often, so besides these defaults
    # the client auto-discovers a working model from the provider's live /models list (see _next_model) and you can pin one with LLM_MODEL.
    "groq":    dict(base_url="https://api.groq.com/openai/v1", key_env="GROQ_API_KEY", model="openai/gpt-oss-120b", fallback="openai/gpt-oss-20b",
                    prefer=["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
    "gemini":  dict(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", key_env="GEMINI_API_KEY", model="gemini-2.5-flash", fallback="gemini-2.0-flash",
                    prefer=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"]),
    "mistral": dict(base_url="https://api.mistral.ai/v1", key_env="MISTRAL_API_KEY", model="mistral-small-latest", fallback="open-mistral-nemo",
                    prefer=["mistral-small-latest", "open-mistral-nemo", "ministral-8b-latest"]),
    "ollama":  dict(base_url="http://localhost:11434/v1", key_env=None, model="llama3.1", fallback=None, prefer=["llama3.1", "llama3.2", "mistral"]),
}
CACHE_DIR = ROOT / "data" / "external" / "llm_cache"
MIN_GAP_S = 0.6

_override: Optional[Callable] = None          # tests: replace the real model with a function(messages, **kw) -> str


def _is_reasoning(model: str) -> bool:
    return any(k in model.lower() for k in ("gpt-oss", "qwen3", "deepseek-r1", "o1", "o3"))


def _clean(text: str) -> str:
    """Some reasoning models leak <think>...</think>; the app only wants the answer."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


class LLMError(RuntimeError):
    """Raised with a human-readable message the UI can show."""


def set_llm_override(fn: Optional[Callable]):
    global _override
    _override = fn


class LLMClient:
    def __init__(self, provider: str | None = None, model: str | None = None, use_cache: bool = True):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()
        if self.provider not in PROVIDERS:
            raise LLMError(f"Unknown LLM_PROVIDER '{self.provider}'. Use one of: {', '.join(PROVIDERS)}")
        cfg = PROVIDERS[self.provider]; self.cfg = cfg
        self.model = model or os.getenv("LLM_MODEL") or cfg["model"]
        self.api_key = os.getenv(cfg["key_env"], "") if cfg["key_env"] else "ollama"
        self.use_cache = use_cache; self._last_call = 0.0; self._client = None; self._tried: set[str] = set()

    # ---------------------------------------------------------------- status
    def is_configured(self) -> bool:
        return _override is not None or bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.cfg["base_url"], timeout=60, max_retries=0)
        return self._client

    # ---------------------------------------------------------------- cache
    def _cache_path(self, model, messages, temperature, max_tokens, json_mode) -> Path:
        key = json.dumps([self.provider, model, messages, temperature, max_tokens, json_mode], sort_keys=True)
        return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")

    # ---------------------------------------------------------------- model auto-discovery
    def _next_model(self, current: str) -> str | None:
        """The model id was rejected (retired / no access). Ask the provider which models exist and pick the best one we have not tried."""
        self._tried.add(current)
        prefer = self.cfg.get("prefer", [])
        try:
            ids = [m.id.replace("models/", "") for m in self._get_client().models.list().data]
        except Exception:
            ids = []
        for cand in prefer:
            if cand in self._tried:
                continue
            if not ids or cand in ids:
                return cand
        return None

    # ---------------------------------------------------------------- main call
    def chat(self, messages: list[dict] | str, system: str | None = None, temperature: float = 0.1,
             max_tokens: int = 900, json_mode: bool = False) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if system:
            messages = [{"role": "system", "content": system}] + list(messages)
        if _override is not None:
            return _override(messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode)
        if not self.is_configured():
            raise LLMError(f"No API key found. Add {self.cfg['key_env']}=... to your .env file (free key: console.groq.com).")

        cacheable = self.use_cache and temperature <= 0.2
        path = self._cache_path(self.model, messages, temperature, max_tokens, json_mode)
        if cacheable and path.exists():
            return json.loads(path.read_text())["text"]

        import openai
        model, last_err = self.model, None
        for attempt in range(6):
            wait = MIN_GAP_S - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                reasoning = _is_reasoning(model)
                kw = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens + (900 if reasoning else 0))   # reasoning tokens count against the limit
                if "gpt-oss" in model:
                    kw["extra_body"] = {"reasoning_effort": "low"}                       # fast + cheap; plenty for SQL and short summaries
                if json_mode:
                    kw["response_format"] = {"type": "json_object"}
                resp = self._get_client().chat.completions.create(**kw)
                self._last_call = time.time()
                text = _clean(resp.choices[0].message.content)
                if not text and attempt < 3:                                              # empty = the model spent its whole budget thinking
                    max_tokens = int(max_tokens * 1.8) + 200; continue
                if cacheable and text:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps({"text": text}))
                return text
            except openai.AuthenticationError:
                raise LLMError(f"The {self.provider} API key was rejected. Check {self.cfg['key_env']} in your .env file.")
            except openai.RateLimitError as e:
                last_err = e; delay = self._retry_after(e, attempt)
                if attempt >= 1 and self.cfg["fallback"] and model != self.cfg["fallback"]:
                    model = self.cfg["fallback"]                       # smaller model has a much bigger free quota
                time.sleep(min(delay, 30))
            except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
                last_err = e; time.sleep(min(2 ** attempt, 15))
            except openai.NotFoundError as e:                                              # model retired / not available to this key
                nxt = self._next_model(model)
                if nxt is None:
                    raise LLMError(f"The model '{model}' is not available on {self.provider} and no alternative was found. Open "
                                   f"console.groq.com/docs/models (or your provider's model list), pick a current free model and set LLM_MODEL=<id> in .env.")
                model = self.model = nxt; last_err = e
            except openai.BadRequestError as e:
                if json_mode and "json" in str(e).lower():
                    json_mode = False; continue                        # model without JSON mode: retry as plain text
                raise LLMError(f"The model rejected the request: {str(e)[:200]}")
        raise LLMError(f"The {self.provider} free tier is busy or rate-limited right now. Wait a minute and try again. ({type(last_err).__name__})")

    @staticmethod
    def _retry_after(err, attempt: int) -> float:
        try:
            h = err.response.headers.get("retry-after")
            if h:
                return float(h) + 0.5
        except Exception:
            pass
        m = re.search(r"try again in (\d+(?:\.\d+)?)\s*(ms|s|m)", str(err))
        if m:
            v = float(m.group(1)); return v / 1000 if m.group(2) == "ms" else v * 60 if m.group(2) == "m" else v + 0.5
        return 2.0 * (attempt + 1)


_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def llm_available() -> bool:
    return get_client().is_configured()


def safe_chat(prompt: str, system: str | None = None, fallback: str = "", **kw) -> tuple[str, bool]:
    """Returns (text, used_llm). If the LLM is unavailable the caller's deterministic fallback text is returned instead of an error."""
    try:
        return get_client().chat(prompt, system=system, **kw), True
    except LLMError:
        return fallback, False
