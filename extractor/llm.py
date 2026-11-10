"""LLM adapter. The only file that knows about a provider.

Pick the provider with LLM_PROVIDER (gemini | fixture). Model name comes from
GEMINI_MODEL. The key comes from GEMINI_API_KEY (put it in .env.local).
"""
import json
import mimetypes
import os
import random
import re
import time
from pathlib import Path

PROMPT = """You read one invoice (PDF or image) and return ONLY a JSON object:
{"vendor": str, "invoice_number": str, "invoice_date": "YYYY-MM-DD",
 "subtotal": number, "tax": number, "total": number, "currency": "USD",
 "line_items": [{"description": str, "quantity": number, "unit_price": number, "amount": number}],
 "confidence": number between 0 and 1}
Copy numbers exactly as printed. Do not fix or guess missing values: if a field
is unreadable use your best reading and lower "confidence". No prose, no markdown."""

RETRY_CODES = {429, 500, 502, 503, 504}


class ExtractionError(Exception):
    pass


class FatalExtractionError(ExtractionError):
    """Same failure would hit every file (bad key, retired model). Stop the run."""


FATAL_CODES = {400, 401, 403, 404}


def parse_json(text: str) -> dict:
    """Model output -> dict. Tolerates ```json fences."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"model did not return valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ExtractionError("model JSON is not an object")
    return data


def _retry_delay(err) -> float | None:
    """Gemini 429s say 'retryDelay': '23s' in the error text. Use it if present."""
    m = re.search(r"retry(?:Delay|\s+in)\D{0,5}(\d+(?:\.\d+)?)", str(err), re.I)
    return float(m.group(1)) if m else None


class GeminiExtractor:
    def __init__(self, client=None, model=None, max_retries=5, base_delay=2.0,
                 min_interval=None, sleep=time.sleep, clock=time.monotonic):
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.max_retries, self.base_delay = max_retries, base_delay
        # free tier allows roughly 10 requests/min on flash models; 6s spacing stays under
        self.min_interval = float(os.environ.get("GEMINI_MIN_INTERVAL", 6)) if min_interval is None else min_interval
        self.sleep, self.clock, self._last = sleep, clock, None
        self._client = client

    @property
    def client(self):
        if self._client is None:
            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise ExtractionError("GEMINI_API_KEY not set. Put it in .env.local or use --dry-run.")
            from google import genai  # lazy: tests and dry-run need no SDK call
            from google.genai import types
            # a hung request has no default timeout in the SDK; 60s then retry
            self._client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60_000))
        return self._client

    def _throttle(self):
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    def _call(self, path: Path):
        from google.genai import types
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        part = types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)
        cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0)
        return self.client.models.generate_content(model=self.model, contents=[part, PROMPT], config=cfg)

    def extract(self, path: Path) -> dict:
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self._call(path)
                return parse_json(resp.text)
            except ExtractionError:
                raise
            except Exception as e:  # SDK errors carry .code; anything else is not retried
                code = getattr(e, "code", None)
                if code is None and "timeout" in type(e).__name__.lower():
                    code = 504  # treat client-side timeouts like a gateway timeout
                if code in FATAL_CODES:
                    raise FatalExtractionError(f"Gemini call failed ({code}): {e}") from e
                if code not in RETRY_CODES or attempt == self.max_retries:
                    raise ExtractionError(f"Gemini call failed ({code}): {e}") from e
                delay = _retry_delay(e) or self.base_delay * 2 ** attempt
                self.sleep(delay + random.uniform(0, 1))
        raise ExtractionError("unreachable")


class FixtureExtractor:
    """--dry-run: reads fixtures/<file stem>.json instead of calling a model."""

    def __init__(self, folder="fixtures"):
        self.folder = Path(folder)

    def extract(self, path: Path) -> dict:
        f = self.folder / f"{path.stem}.json"
        if not f.exists():
            raise ExtractionError(f"no cached fixture for {path.name}")
        return parse_json(f.read_text(encoding="utf-8"))


def get_extractor(dry_run=False, fixtures="fixtures"):
    provider = "fixture" if dry_run else os.environ.get("LLM_PROVIDER", "gemini").lower()
    if provider == "fixture":
        return FixtureExtractor(fixtures)
    if provider == "gemini":
        if not os.environ.get("GEMINI_API_KEY"):
            raise ExtractionError("GEMINI_API_KEY not set. Put it in .env.local or use --dry-run.")
        return GeminiExtractor()
    raise ExtractionError(f"unknown LLM_PROVIDER '{provider}'")
