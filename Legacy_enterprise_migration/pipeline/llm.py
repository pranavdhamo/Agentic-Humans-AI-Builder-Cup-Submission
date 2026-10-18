"""LLM providers for the migration pipeline.

GeminiProvider  - the real thing: Google Gemini via the google-genai SDK (API key from GEMINI_API_KEY).
MockProvider    - scripted, offline, deterministic. NOT a model: it replays pre-baked answers (a reference port with
                  a few deliberately injected mistakes that disappear over iterations) so the generate -> verify ->
                  repair loop itself can be tested without an API key or network.
Both return an LlmResult with the parsed JSON answer and token usage.
"""
import json, os, re
from dataclasses import dataclass, field


@dataclass
class LlmResult:
    data: dict                      # parsed JSON: {"files": {path: content}, "notes": str}
    prompt_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    raw: str = ""


def parse_json_answer(text: str) -> dict:
    """Models sometimes wrap JSON in a markdown fence; accept both."""
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    if m: t = m.group(1)
    return json.loads(t)


def _key_from_dotenv() -> str | None:
    """Repo-root .env (git-ignored): either NAME=value lines or a single line holding just the key. Never printed."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / ".env"
    if not p.exists(): return None
    for line in p.read_text().splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#"): continue
        if "=" in line:
            name, _, value = line.partition("=")
            if name.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"): return value.strip().strip("\"'")
        else:
            return line.strip("\"'")
    return None


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None, temperature: float = 0.2):
        from google import genai                       # imported lazily so the mock path needs no SDK
        from google.genai import types
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or _key_from_dotenv()
        if not key:
            raise SystemExit("Set GEMINI_API_KEY (Google AI Studio key) in your environment or in a git-ignored .env at the repo root.")
        self._types = types
        self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=600_000))   # 10 min hard cap per request (ms)
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
        self.temperature = temperature

    def _generate_with_retry(self, system: str, prompt: str, attempts: int = 6):
        """Overload (503) and rate limits (429) are normal on busy models: back off and retry instead of failing the run."""
        import time
        import httpx
        from google.genai import errors
        delay = 20
        for i in range(attempts):
            try:
                if getattr(self, "_plain", False):
                    return self._client.models.generate_content(
                        model=self.model, contents=system + "\n\n" + prompt + "\n\nReply with ONLY the JSON object.",
                        config=self._types.GenerateContentConfig(temperature=self.temperature))
                return self._client.models.generate_content(
                    model=self.model, contents=prompt,
                    config=self._types.GenerateContentConfig(
                        system_instruction=system, temperature=self.temperature, response_mime_type="application/json"))
            except httpx.TransportError as e:               # DNS blip, dropped connection, timeout
                if i == attempts - 1: raise
                print(f"  network error ({type(e).__name__}): retrying in {delay}s ({i + 1}/{attempts - 1})", flush=True)
                time.sleep(delay); delay = min(delay * 2, 240)
            except errors.APIError as e:
                if getattr(e, "code", None) == 400 and not getattr(self, "_plain", False):
                    # some models reject system instructions / JSON mode: fold the system text into the prompt
                    print(f"  model rejected structured config ({str(e)[:90]!r}); retrying as plain text", flush=True)
                    self._plain = True
                    return self._client.models.generate_content(
                        model=self.model, contents=system + "\n\n" + prompt + "\n\nReply with ONLY the JSON object.",
                        config=self._types.GenerateContentConfig(temperature=self.temperature))
                transient = getattr(e, "code", None) in (429, 500, 503, 504)
                if not transient or i == attempts - 1: raise
                print(f"  gemini {e.code}: retrying in {delay}s ({i + 1}/{attempts - 1})", flush=True)
                time.sleep(delay); delay = min(delay * 2, 240)

    def complete(self, system: str, prompt: str) -> LlmResult:
        import time
        t0 = time.time()
        resp = self._generate_with_retry(system, prompt)
        u = getattr(resp, "usage_metadata", None)
        return LlmResult(data=parse_json_answer(resp.text), raw=resp.text,
                         prompt_tokens=getattr(u, "prompt_token_count", 0) or 0,
                         output_tokens=getattr(u, "candidates_token_count", 0) or 0, seconds=time.time() - t0)


class MockProvider:
    """Replays `versions[i]` (a callable returning {path: content}) on the i-th call; the last repeats."""
    name = "mock"
    model = "scripted-offline"

    def __init__(self, versions):
        self.versions, self.calls = versions, 0

    def complete(self, system: str, prompt: str) -> LlmResult:
        i = min(self.calls, len(self.versions) - 1); self.calls += 1
        files = self.versions[i]()
        return LlmResult(data={"files": files, "notes": f"MOCK scripted response #{i} (not a model)"},
                         prompt_tokens=len(prompt) // 4, output_tokens=sum(len(v) for v in files.values()) // 4)
